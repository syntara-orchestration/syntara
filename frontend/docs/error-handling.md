# API Error Handling

This document describes the error handling implementation in the Syntara UI, including parsing 4xx/5xx API responses and surfacing meaningful messages to users.

---

## Table of Contents

1. [Overview](#overview)
2. [Error Parsing Utilities](#error-parsing-utilities)
3. [Query State Hook](#query-state-hook)
4. [Mutation Error Handlers](#mutation-error-handlers)
5. [503 Service Unavailable Handling](#503-service-unavailable-handling)
6. [Error Components](#error-components)
7. [Usage Examples](#usage-examples)

---

## Overview

The UI provides consistent error handling across all API interactions:

- **Query errors**: Automatically displayed via `useQueryState` hook
- **Mutation errors**: Handled via `useMutationErrorHandler` hook or `getErrorMessage` utility
- **503 Service Unavailable**: Special handling for configuration errors (e.g., missing API keys)

### Backend Error Formats Supported

```typescript
// Structured API error (e.g., 503)
{ error: "service_unavailable", message: "OPENROUTER_API_KEY is required..." }

// FastAPI standard error
{ detail: "error message" }

// FastAPI validation errors
{ detail: [{ loc: ["body", "name"], msg: "field required" }] }

// Nested detail object
{ detail: { error: "...", message: "..." } }

// RFC 9457 / problem-details style
{ title: "Not Found", detail: "Resource does not exist" }

// openapi-fetch error with cause
{ cause: { message: "...", status: 503 } }
```

---

## Error Parsing Utilities

**Location:** `packages/syntara-ui/src/utils/apiErrors.ts`

A utility module for parsing API error responses consistently across the application.

### Functions

| Function                           | Description                                                   |
| ---------------------------------- | ------------------------------------------------------------- |
| `getErrorMessage(error)`           | Extracts user-friendly message from various error formats     |
| `getErrorStatus(error)`            | Extracts HTTP status code from error                          |
| `getErrorCode(error)`              | Extracts error code (e.g., `"service_unavailable"`)           |
| `getErrorTitle(error)`             | Returns human-readable title for error codes                  |
| `isServiceUnavailableError(error)` | Detects 503 errors by status code or error code               |
| `isAdminConfigurationError(error)` | Detects configuration-related errors                          |
| `isValidationError(error)`         | Detects 422 validation errors with FastAPI detail arrays      |
| `getValidationFieldErrors(error)`  | Extracts field-level validation errors for form mapping       |
| `isRetryableError(error)`          | Detects errors marked as retryable (5xx or `retryable: true`) |
| `isConflictError(error)`           | Detects 409 conflict errors (e.g., duplicate names)           |

### Usage Example

```typescript
import { getErrorMessage, isServiceUnavailableError } from '../utils/apiErrors'

// In a mutation error handler
onError: (error) => {
  const message = getErrorMessage(error) // Extracts meaningful message
  showError({ title: 'Request failed', description: message })
}

// Check for 503 errors
if (isServiceUnavailableError(error)) {
  return <SynEmptyStateServiceUnavailable description={getErrorMessage(error)} />
}
```

---

## Query Error Handling

### useQueryState Hook

**Location:** `packages/syntara-ui/src/components/states/useQueryState.tsx`

Automatically handles query loading, error, and 503 states.

| Error Type              | Component Rendered                |
| ----------------------- | --------------------------------- |
| 503 Service Unavailable | `SynEmptyStateServiceUnavailable` |
| Other errors            | `SynErrorState` + alert           |
| Loading                 | `SynLoadingState`                 |
| Success                 | `null` (render data)              |

#### Usage

The second argument accepts either a string (shorthand for title) or an options object:

```tsx
import { detachPromise } from '../../utils/detachPromise'

// Simple usage with title string
const query = workflowClient.useQuery('get', '/workflows')
const queryState = useQueryState(query, 'Error loading workflows')

if (queryState) return queryState // Renders appropriate state component
return <WorkflowList data={query.data} />

// With options object (supports retry)
const queryState = useQueryState(query, {
  title: 'Error loading workflows',
  onRetry: () => detachPromise(query.refetch()),
})
```

**Fire-and-forget promises:** Do not use JavaScript’s unary `void` to discard a promise (for example `void query.refetch()`). It is hard to read, is flagged by Sonar (S3735), and is disallowed by ESLint `no-void` in this repo. In synchronous callbacks such as `onRetry`, use `detachPromise(query.refetch())` from `utils/detachPromise` (it wraps with `Promise.resolve` so tests that mock `refetch` as `vi.fn()` returning `undefined` do not throw). Alternatively `await query.refetch()` when the enclosing function is `async` and should surface failures.

For **auth or other security-sensitive** work, prefer **`await`** in an `async` handler (or an explicit `.catch`) so failures can be shown to the user. For **`useEffect` bootstraps** (e.g. cookie refresh, public provider list), use a **named `async` function** and handle errors inside it; use a **targeted `eslint-disable-next-line @typescript-eslint/no-floating-promises`** on the call from the sync effect if you cannot `await` at the top level — do **not** use **`detachPromise`** there. If you must detach from a sync callback elsewhere while still reporting failures, pass **`detachPromise(promise, { onReject: (err) => { ... } })`**. When `onReject` is omitted, production builds call **`globalThis.reportError`** on rejection (in addition to dev `console.warn`) so failures are not fully silent in monitoring.

### useApiErrorAlert Hook

**Location:** `packages/syntara-ui/src/hooks/useApiErrorAlert.ts`

Shows a deduped alert for query errors. Automatically parses 4xx/5xx response bodies.

```tsx
const { error } = workflowClient.useQuery('get', '/workflows/{workflow_id}')

// Show alert for errors (deduped, won't spam on re-renders)
useApiErrorAlert(error, { title: 'Error loading workflow' })
```

---

## Mutation Error Handling

### useMutationErrorHandler Hook

**Location:** `packages/syntara-ui/src/hooks/useMutationErrorHandler.ts`

Provides consistent error handling for mutations with special 503 support.

#### Features

- Automatic 503 detection with warning alert (amber, not red)
- Consistent error message extraction from various formats
- Custom 503 handler support for component-specific behavior
- Integration with `useAlerts` from app components

#### Usage Examples

```tsx
const handleError = useMutationErrorHandler()

// Basic usage
const { mutate } = workflowClient.useMutation('post', '/workflows')
mutate(data, {
  onError: handleError({ title: 'Failed to create workflow' }),
})

// With custom 503 handling (e.g., show inline UI instead of alert)
const [showServiceUnavailable, setShowServiceUnavailable] = useState(false)

mutate(data, {
  onError: handleError({
    title: 'Request failed',
    on503: () => setShowServiceUnavailable(true),
  }),
})

// With context for better error messages
mutate(data, {
  onError: handleError({
    title: 'Workflow failed',
    context: `Workflow "${workflow.name}"`,
  }),
})
```

### useFormMutationErrorHandler Hook

**Location:** `packages/syntara-ui/src/hooks/useFormMutationErrorHandler.ts`

Specialized hook for form-backed mutations that combines `useMutationErrorHandler` with automatic field-level error mapping.

#### Features

- All features from `useMutationErrorHandler` (alerts, 503 handling, etc.)
- Automatically maps FastAPI validation errors to react-hook-form fields
- Configurable field mapping via `mapValidationToFields` option

#### Usage Examples

```tsx
import { useFormMutationErrorHandler } from '../../hooks/useFormMutationErrorHandler'

// Basic usage with react-hook-form
const { control, handleSubmit, setError } = useForm<ToolProvider>()
const handleError = useFormMutationErrorHandler<ToolProvider>(setError)

createIntegration(data, {
  onError: handleError({
    title: 'Failed to add integration',
    context: toolProvider.name ? `Integration "${toolProvider.name}"` : undefined,
  }),
})

// Disable field mapping (only show alert)
onError: handleError({
  title: 'Failed to update',
  mapValidationToFields: false,
})
```

#### How it Works

When a 422 validation error occurs with FastAPI detail arrays:

```json
{
  "detail": [{ "loc": ["body", "configuration", "api_key"], "msg": "Field required" }]
}
```

The hook automatically calls `setError('configuration.api_key', { type: 'server', message: 'Field required' })`, displaying the error inline on the form field while also showing an alert.

### Client-side validation (Zod + @hookform/resolvers)

For consistent shape and client-side validation, forms can use **Zod** with **@hookform/resolvers/zod**:

- **Single source of truth**: One schema defines both the form type and validation rules (required, format, etc.).
- **Type inference**: Use `z.infer<typeof schema>` for the form type instead of hand-written interfaces.
- **Backend errors unchanged**: `useFormMutationErrorHandler` and `getValidationFieldErrors` still map 422 field errors to the form; Zod handles client-side rules only.

**Reusable helpers (builder step forms live under `node-forms/`):**

- **`node-forms/shared/formSchemaUtils.ts`** — Re-exports **`zodResolver`** from `@hookform/resolvers/zod` and **`optionalNumber`** for fields with `valueAsNumber` that can be NaN. Step forms in `node-forms/` import `zodResolver` and `optionalNumber` from `./shared/formSchemaUtils`. Use `zodResolver(schema, undefined, { mode: 'sync' })` with your Zod schema (import `z` from `'zod'`).

**Where it's used:**

- **Integration form:** `packages/syntara-ui/src/routes/configuration/integrations/form/integrationFormSchema.ts` and `IntegrationForm.tsx` (imports `zodResolver` from `@hookform/resolvers/zod`).
- **Step forms (builder):** Each has a schema file in `packages/syntara-ui/src/routes/builder/node-forms/` and uses `zodResolver(schema, undefined, { mode: 'sync' })` from `shared/formSchemaUtils.ts`:
  - Task Agent (`aiAgentFormSchema.ts`), Approval (`approvalFormSchema.ts`), Action (`actionFormSchema.ts`), Loop (`loopFormSchema.ts`), AAP (`aapFormSchema.ts`), Condition (`conditionFormSchema.ts`), Converge (`convergeFormSchema.ts`), Trigger (`triggerFormSchema.ts`).

### Direct Usage with getErrorMessage

For simpler cases or custom alert handling:

```tsx
import { getErrorMessage } from '../utils/apiErrors'

mutate(data, {
  onError: (error) => {
    showError({ title: 'Failed to save', description: getErrorMessage(error) })
  },
})
```

---

## 503 Service Unavailable Handling

### SynEmptyStateServiceUnavailable Component

**Location:** `packages/syntara-ui/src/components/states/SynEmptyStateServiceUnavailable.tsx`

A reusable component for displaying 503 Service Unavailable errors. Uses PatternFly's `EmptyState` component with an error icon.

#### Props

| Prop            | Type      | Default                 | Description                       |
| --------------- | --------- | ----------------------- | --------------------------------- |
| `title`         | `string`  | `"Service Unavailable"` | The error title                   |
| `description`   | `string`  | Default message         | The error description             |
| `showAdminHint` | `boolean` | `true`                  | Show "contact administrator" hint |

#### Usage

```tsx
import { SynEmptyStateServiceUnavailable } from './components/states/SynEmptyStateServiceUnavailable'

// Basic usage with defaults
<SynEmptyStateServiceUnavailable />

// With custom message from API
<SynEmptyStateServiceUnavailable
  title="AI Service Unavailable"
  description="OPENROUTER_API_KEY environment variable is required."
/>

// Without admin contact hint
<EmptyStateServiceUnavailable
  title="Service Temporarily Unavailable"
  description="Please try again later."
  showAdminHint={false}
/>
```

### Backend Integration

The backend returns HTTP 503 when the OpenRouter API key is not configured:

```json
{
  "error": "service_unavailable",
  "message": "OPENROUTER_API_KEY environment variable is required. Get your API key from https://openrouter.ai/keys"
}
```

#### User Experience Flow

```
┌─────────────────────────────────────────────────────────────┐
│ User Action: Submit prompt to /api/v1/invocations           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Backend: Check OPENROUTER_API_KEY                           │
│ ├─ Key exists → 202 Accepted (create invocation)            │
│ └─ Key missing → 503 Service Unavailable                    │
└─────────────────────────────────────────────────────────────┘
                              │
                    (if 503)  ▼
┌─────────────────────────────────────────────────────────────┐
│ UI: Display EmptyStateServiceUnavailable                    │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │                                                         │ │
│ │        Service Unavailable                              │ │
│ │                                                         │ │
│ │   OPENROUTER_API_KEY environment variable is required.  │ │
│ │   Get your API key from https://openrouter.ai/keys      │ │
│ │                                                         │ │
│ │   If this persists, contact your system administrator.  │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
packages/
└── syntara-ui/
    └── src/
        ├── components/
        │   └── states/
        │       ├── SynEmptyStateServiceUnavailable.tsx       # 503 empty state
        │       ├── SynEmptyStateServiceUnavailable.test.tsx
        │       ├── useQueryState.tsx          # Query state hook (handles 503)
        │       └── SynErrorState.tsx             # Generic error display with retry
        ├── hooks/
        │   ├── useApiErrorAlert.ts            # Deduped error alerts
        │   ├── useMutationErrorHandler.ts     # Mutation error handler
        │   └── useFormMutationErrorHandler.ts # Form-aware mutation error handler
        └── utils/
            ├── apiErrors.ts                   # Error parsing utilities
            └── apiErrors.test.ts
```

---

## Testing

### Unit Tests

| File                                       | Tests | Coverage                                         |
| ------------------------------------------ | ----- | ------------------------------------------------ |
| `apiErrors.test.ts`                        | 25    | Error parsing, 503 detection, message extraction |
| `SynEmptyStateServiceUnavailable.test.tsx` | 5     | Component rendering, props                       |

### Running Tests

```bash
# Run all tests
npm test

# Run specific test file
npx vitest run packages/syntara-ui/src/utils/apiErrors.test.ts
```

---

## Future Enhancements

The following enhancements are planned for future iterations:

1. **Migrate existing mutation error handlers** — When implementing the chat feature, migrate inline `onError` handlers to use `useMutationErrorHandler` for consistency.

2. **Global 503 banner** — For system-wide configuration errors, consider adding a persistent banner at the top of the app instead of per-component handling.

3. **Retry logic for temporary 503s** — Add automatic retry with exponential backoff for truly temporary 503 errors (distinguishing them from configuration issues via error codes).

---

## Related Links

- OpenAPI Schema: `schemas/base/shared-resources.openapi.yaml` (Error schema)
- Agent Orchestrator API: `schemas/agent_orchestrator/agent-orchestrator-api.yaml` (503 response definition)
