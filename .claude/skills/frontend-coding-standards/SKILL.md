---
description: "Frontend coding standards — PatternFly patterns, API integration, forms, testing, permissions."
user-invocable: false
---

# Coding Standards

Detailed code examples and patterns for this project. Referenced from CLAUDE.md's condensed checklist.

---

## Library References

See [`.claude/skills/frontend-library-references/SKILL.md`](../frontend-library-references/SKILL.md) for `llms.txt` URLs and official docs links for all libraries used in this project. Fetch the relevant entry before writing code against a library to ensure you use current APIs.

---

## Prefer Library and Native Browser APIs Over Custom Code

Before writing custom utilities, hooks, or helpers, check whether the library or the browser platform already provides the functionality. Re-implementing what already exists creates maintenance burden, misses edge cases, and confuses contributors who expect the standard API.

**Libraries first:**

- **TanStack Query** provides `select`, `placeholderData`, `enabled`, `retry`, `staleTime` -- do not re-implement data transformation, caching, or conditional fetching with custom hooks wrapping `useEffect` + `useState`
- **react-hook-form** provides `useFieldArray`, `useWatch`, `setValue`, `reset` -- do not manage dynamic form arrays or field dependencies with manual state
- **Zod** provides `.transform()`, `.refine()`, `.superRefine()`, `.pipe()` -- do not post-process validated data with separate transformation functions
- **PatternFly** provides layout components (Stack, Flex, Grid), form components, and design tokens -- do not build custom equivalents

**Native browser APIs** when no library covers the need:

- `structuredClone()` instead of manual deep copy or JSON round-trips
- `URLSearchParams` instead of manual query string parsing
- `AbortController` instead of custom cancellation logic
- `URL` constructor instead of string concatenation for URLs
- `crypto.getRandomValues()` + a wrapper instead of Math.random() for IDs

**Caveat -- verify browser API availability in all deployment contexts.** Some Web APIs are restricted to secure contexts (HTTPS or localhost). For example, `crypto.randomUUID()` is unavailable over plain HTTP and causes a runtime crash. The project uses `generateUUID()` from `frontend/packages/syntara-ui/src/utils/generateUUID.ts` which wraps `crypto.getRandomValues()` (available in all contexts). When using a native API, check [MDN's "Secure context: required" badge](https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts) and verify the app works over both HTTP and HTTPS.

When reviewing code, flag any pattern that duplicates what a dependency or browser API already exposes. If unsure whether a library covers a use case, check [`.claude/skills/frontend-library-references/SKILL.md`](../frontend-library-references/SKILL.md) and fetch the `llms.txt` URL for that library.

---

## 1. Always Use Typed API Clients — Never Raw `fetch()`

Every API endpoint has a type-safe client generated from OpenAPI contracts. Raw `fetch()` bypasses auth middleware (token refresh, 401 retry), error interceptors, base URL configuration, and TypeScript type safety.

```typescript
// ❌ BAD
const response = await fetch(`/api/v1/credentials/${id}/workflows`, {
  headers: { Authorization: `Bearer ${token}` },
})
const data = (await response.json()) as { id: string; name: string }[]

// ✅ GOOD
const { data } = credentialsClient.useQuery('get', '/credentials/{credential_id}/workflows', {
  params: { path: { credential_id: id } },
})
```

**Exception**: Pre-auth calls (e.g., fetching OIDC providers before login) where no token exists may use `fetch()` with a comment explaining why.

---

## 2. `useQueryState` — Always Use Object Form with `onRetry`

Prefer the object form with explicit `onRetry` for consistency and clear retry intent. The string form still works (it falls back to `refetch`), but should be avoided in new code.

```typescript
// ❌ BAD
const queryState = useQueryState(query, 'Error loading credentials')

// ✅ GOOD
const queryState = useQueryState(query, {
  title: 'Error loading credentials',
  onRetry: () => detachPromise(query.refetch()),
})
```

---

## 3. Never Use Unsafe `as` Casts on API Responses

The typed API client already returns properly typed data. If the response type doesn't match, fix the root cause (contract or types), or use a type guard.

```typescript
// ❌ BAD
const credentials = data?.resources as Credential[]

// ✅ GOOD — use the typed response directly
const { data } = credentialsClient.useQuery('get', '/credentials')
const credentials = data?.resources // Already typed as Credential[]

// ✅ GOOD — if narrowing is needed, use a type guard
function isCredentialArray(value: unknown): value is Credential[] {
  return Array.isArray(value) && value.every((v) => typeof v === 'object' && v !== null && 'id' in v)
}
```

---

## 4. Always Use `NxErrorState` Component — Never Raw Error Markup

The project has a standard `NxErrorState` component that handles retryable errors, displays consistent UI, and shows a retry button automatically for 5xx errors.

```typescript
// ❌ BAD
{error && <span>Unable to load profile information.</span>}

// ✅ GOOD
<NxErrorState
  title="Unable to load profile"
  message={error}
  onRetry={() => detachPromise(refetch())}
/>
```

---

## 5. Always Use Zod + react-hook-form for Forms

Never use manual `useState` per field with hand-written validation. The project standard is Zod schemas with `zodResolver` and `useFormMutationErrorHandler` for automatic 422 field error mapping.

```typescript
// ❌ BAD
const [name, setName] = useState('')
const [errors, setErrors] = useState({})
function validate() {
  if (!name) setErrors({ name: 'Required' })
}

// ✅ GOOD
const schema = z.object({ name: z.string().min(1, 'Required') })
const { register, handleSubmit } = useForm<FormData>({
  resolver: zodResolver(schema, undefined, { mode: 'sync' }),
})
```

### Loading state: Use `isPending` from mutations, not `formState.isSubmitting`

**Enforced by ESLint:** `no-restricted-syntax` (error). See `eslint.config.js`.

`formState.isSubmitting` only covers the synchronous `handleSubmit` wrapper. It does not reflect the actual async mutation state. Use `isPending` from the mutation hook for real loading indicators.

```typescript
// ❌ BAD — isSubmitting resolves before the mutation completes
const { formState: { isSubmitting } } = useForm()
<Button isLoading={isSubmitting}>Save</Button>

// ✅ GOOD — isPending tracks the actual mutation lifecycle
const { mutate, isPending } = credentialsClient.useMutation('post', '/credentials')
<Button isLoading={isPending}>Save</Button>
```

### Step form (with Zod)

1. Create a schema file next to your form: `myNodeFormSchema.ts` — define shape and validation with `z.object()` (use `.superRefine()` for conditional rules, or `z.discriminatedUnion()` for executor-type-style forms). Export the schema and `type MyFormData = z.infer<typeof myNodeFormSchema>`. Import `z` from `'zod'`.
2. For optional number fields use `optionalNumber` from `src/routes/builder/node-forms/shared/formSchemaUtils` so empty `valueAsNumber` inputs (NaN) validate
3. In form component: `useForm<MyFormData>({ resolver: zodResolver(myNodeFormSchema, undefined, { mode: 'sync' }), defaultValues })` — import `zodResolver` from `./shared/formSchemaUtils`
4. Use `useFormMutationErrorHandler(setError)` for API 422 field errors; Zod handles client-side only. See: [`frontend/docs/error-handling.md`](frontend/docs/error-handling.md) - "Client-side validation (Zod + @hookform/resolvers)"

---

## 6. Handle `defaultValues` Reset for Edit Modals

When a form modal is always rendered (not unmounted), `defaultValues` only applies on first mount.

```typescript
// ❌ BAD — stale data on re-open
const { register } = useForm({ defaultValues: { name: item?.name ?? '' } })

// ✅ GOOD — reset when modal opens
const { register, reset } = useForm({ defaultValues: { name: '' } })

useEffect(() => {
  if (isOpen) {
    reset({ name: item?.name ?? '', description: item?.description ?? '' })
  }
}, [isOpen, item, reset])
```

---

## 7. Extract Shared UI Patterns — Avoid Duplication

```typescript
// ❌ BAD — same dialog copy-pasted in 3 files
// Credentials.tsx: 50 lines of disable dialog JSX
// CredentialDetail.tsx: 50 lines of nearly identical JSX

// ✅ GOOD — shared component + hook
<DisableCredentialDialog credential={selected} isOpen={isOpen} onClose={onClose} />
const { handleToggle, handleDelete } = useCredentialActions(credential)
```

### Pattern Recognition Checklist

| Pattern Detected                            | Action Required                                  |
| ------------------------------------------- | ------------------------------------------------ |
| **Repeated JSX structure** (2+ times)       | -> Create a **Component**                        |
| **Repeated logic/state** (2+ times)         | -> Create a **Hook**                             |
| **Repeated utility functions**              | -> Create a **shared utility**                   |
| **Similar components with variants**        | -> Extend existing component with props/variants |
| **Repeated boolean expressions** (2+ files) | -> Extract to a shared predicate function        |

```typescript
// ❌ BAD — same expression duplicated in BuilderWorkflowPageHeader.tsx and ExecutionDetail.tsx
const isCancellable = status === 'pending' || status === 'running'

// ✅ GOOD — shared utility, single source of truth
import { isExecutionCancellable } from '../utils/executionHelpers'
const isCancellable = isExecutionCancellable(status)
```

### Code Review: Spotting Abstraction Opportunities

**CRITICAL: Before implementing new features or during code review, actively look for patterns that indicate abstraction opportunities.**

#### JSX Repetition → Component

**Signs you need a component:**

- Same JSX structure appears in multiple files
- Copy-pasted markup with minor variations
- Similar styling patterns repeated

```tsx
// ❌ BAD: Repeated JSX pattern
<div className="glass rounded-lg p-4">
  <h3 className="text-lg font-bold">{title1}</h3>
  <p className="text-white/60">{description1}</p>
</div>
<div className="glass rounded-lg p-4">
  <h3 className="text-lg font-bold">{title2}</h3>
  <p className="text-white/60">{description2}</p>
</div>

// ✅ GOOD: Extract to component
<InfoCard title={title1} description={description1} />
<InfoCard title={title2} description={description2} />
```

#### Logic Repetition → Hook

**Signs you need a hook:**

- Same useState + useEffect pattern repeated
- Identical data fetching logic
- Common event handling patterns
- Shared form validation logic

```tsx
// ❌ BAD: Repeated logic in multiple components
const [search, setSearch] = useState('')
const fuse = new Fuse(items, { keys: ['name'] })
const filtered = search ? fuse.search(search).map((r) => r.item) : items

// ✅ GOOD: Extract to hook
const { search, setSearch, items: filtered } = useFuse(items, ['name'])
```

#### Review Questions to Ask

When reviewing code, always ask:

1. **"Have I seen this JSX pattern before?"**
   - Search codebase for similar structures
   - Check if a PatternFly component or existing app component already exists
   - Consider if it should be an app-specific component or use PatternFly directly

2. **"Is this logic reusable?"**
   - Would other components benefit from this?
   - Is there already a hook for this in the codebase?
   - Should this be extracted to a shared hook?

3. **"Can I extend an existing component?"**
   - Does a similar component exist with different variants?
   - Can I add a prop instead of creating new component?
   - Would PatternFly variants or modifiers solve this?

#### Migration Triggers

Proactively identify migration opportunities:

```text
Codebase Search Patterns:
- Search for duplicate className patterns
- Look for repeated useState/useEffect combinations
- Find similar component structures across routes
- Check for copy-pasted utility functions
```

**When to extract to shared components:**

- Component used in 2+ unrelated features
- Hook provides generic, reusable functionality
- Pattern is not domain-specific to syntara-ui

### Shared Hooks Available

- `useCursorPagination(options?)` — cursor state + filters + queryParams + footer props
- `useCursorReset(itemCount, hasActiveFilters, cursor, isFetching, setCursor)` — reset to page 1
- `useDialogState<T>()` — dialog open/close state with associated item
- `useDeleteAction(options)` — delete mutation with success/error alerts
- `NxConfirmationDialog` — reusable confirm/cancel modal (`frontend/packages/syntara-ui/src/components/dialogs/NxConfirmationDialog.tsx`)

### List Page Standard Pattern

```typescript
import { useCursorPagination, useCursorReset } from '../../hooks/useCursorPagination'
import { useDialogState } from '../../hooks/useDialogState'
import { useDeleteAction } from '../../hooks/useDeleteAction'
import { NxConfirmationDialog } from '../../components/dialogs/NxConfirmationDialog'

export function MyListPage() {
  const {
    cursor, setCursor, filters, hasActiveFilters, queryParams,
    handleFilterChange, handleClearAllFilters, getFooterProps, getSortParams,
  } = useCursorPagination({
    defaultSort: { field: 'name', direction: 'asc' },
    columns: [{ field: 'name', label: 'Name', isSortable: true }],
  })

  const deleteDialog = useDialogState<MyItem>()

  const query = myClient.useQuery('get', '/items', { params: { query: queryParams } })
  const { mutate: deleteItem } = myClient.useMutation('delete', '/items/{item_id}')

  const handleDelete = useDeleteAction({
    deleteFn: deleteItem,
    buildParams: (item) => ({ params: { path: { item_id: item.id } } }),
    entityLabel: 'item',
    getItemName: (item) => item.name,
    onSuccess: () => detachPromise(query.refetch()),
    onSettled: deleteDialog.close,
  })

  const items = query.data?.resources ?? []
  useCursorReset(items.length, hasActiveFilters, cursor, query.isFetching, setCursor)

  return (
    <NxPage>
      <FilterBar ... />
      <NxScrollableTableContainer
        footer={getFooterProps(query.data)}
      >
        {/* <Th sort={getSortParams('name')}>Name</Th> */}
      </NxScrollableTableContainer>
      <NxConfirmationDialog
        isOpen={deleteDialog.isOpen}
        onClose={deleteDialog.close}
        onConfirm={() => handleDelete(deleteDialog.item)}
        title="Delete item"
        confirmLabel="Delete"
        confirmVariant="danger"
      >
        Are you sure?
      </NxConfirmationDialog>
    </NxPage>
  )
}
```

---

## 8. PatternFly Component Guidelines

### PatternFly First Checklist

Before writing any new UI code, follow this checklist:

1. **Check for Existing Components**
   - Search `frontend/packages/syntara-ui/src/components/` for existing application-specific components
   - Check PatternFly documentation for available components: Button, Alert, Switch, Table, Dialog, EmptyState, Menu, Tooltip, Checkbox, etc.
   - Verify if a PatternFly component or existing app component can be reused or extended

2. **Component Location Strategy**
   - **Application-specific components** → `frontend/packages/syntara-ui/src/components/`
   - Use PatternFly components directly from `@patternfly/react-core` and related packages
   - When in doubt, prefer PatternFly components over custom implementations

3. **Building New Components**
   - ALWAYS use PatternFly components as the foundation
   - Build accessible components following PatternFly patterns and design system
   - Include comprehensive tests (see existing `.test.tsx` files)
   - Place in `frontend/packages/syntara-ui/src/components/` for app-specific components
   - **Use PF6 design tokens instead of hardcoded pixel values** for spacing, sizing, colors, and icons. Use `var(--pf-t--global--spacer--*)` for margins/padding, `var(--pf-t--global--icon--size--*)` for icon dimensions, `var(--pf-t--global--color--*)` for colors, and content-aware units (`ch`, `rem`) for input widths. Hardcoded `px` values are acceptable only for layout constraints (table column widths, fixed panel heights) where no semantic token applies. **CSS modules must also use PF tokens** -- ESLint only catches hardcoded values in JSX, so CSS modules need manual review. Use semantic tokens like `var(--pf-t--global--text--color--subtle)` rather than lower-level tokens like `var(--pf-t--global--color--200)`.
   - **Use `RhUi*` icons** (e.g., `RhUiAddIcon`, `RhUiTrashIcon`, `RhUiEditIcon`) for all action buttons, not legacy PatternFly icons like `PlusCircleIcon`, `CopyIcon`, or `TrashIcon`. The `RhUi*` icon set is the project standard. **Enforced by ESLint:** `no-restricted-imports` (warn) flags any non-`RhUi` import from `@patternfly/react-icons`. Existing legacy icons are being phased out.
   - **Add `shouldFocusToggleOnSelect` to PF Select components** for accessibility. The select should receive focus when a selection is made. This is not a PF default but is needed for proper keyboard navigation.
   - **JSDoc on shared/global component props** -- every exported component in `frontend/packages/syntara-ui/src/components/` (especially `Nx*` components) must have JSDoc descriptions on its props interface. TypeScript types convey shape; JSDoc conveys intent. Describe what each prop controls, when to use optional props, and any non-obvious default behavior. This helps both human contributors and AI agents use components correctly without reading the implementation.

4. **Custom Hooks**
   - Extract reusable logic into custom hooks
   - Place hooks in `frontend/packages/syntara-ui/src/hooks/`
   - Follow naming convention: `useXxx`
   - Include TypeScript types

5. **Code Abstraction**
   - Identify and eliminate redundant code patterns
   - Create shared utilities for common operations
   - Use composition over duplication
   - Follow DRY (Don't Repeat Yourself) principles

6. **React Best Practices**
   - Leverage React 19 features (see §38 for ref-as-prop and ref cleanup functions; §39 for `use(Context)` over `useContext`; §40 for `useOptimistic`)
   - Use functional components and hooks
   - Use proper TypeScript typing (avoid `any`)
   - Implement proper error boundaries
   - Follow component composition patterns
   - Use proper key props for lists
   - Prefer controlled components for forms (react-hook-form)
   - Use proper semantic HTML
   - For PatternFly form controls (TextInput, TextArea, FormSelect, FormGroup), use `validated={hasError ? 'error' : 'default'}` so the non-error state is explicit; do not use `undefined` for the default case

**Example Workflow:**

```text
User Request: "Add a confirmation dialog"
Step 1: Check PatternFly for Dialog/Modal component (exists)
Step 2: Check app components for ConfirmDialog variant (may exist)
Step 3: Use PatternFly Modal or existing app component
Result: Use PatternFly Modal component or extend existing app component
```

### Code Readability Enforcement (ESLint)

ESLint enforces readability, type safety, and code quality rules at `error` level. CI will block violations. See `frontend/packages/syntara-ui/eslint.config.js` for the full list of rules and thresholds.

### Zero New Warnings Policy

**CRITICAL: New code must not introduce new ESLint warnings.** Many rules are currently set to `warn` (not `error`) only because pre-existing violations need gradual cleanup. The team is actively working to convert these warnings to errors. Treat every `warn`-level rule as if it were already `error` when writing new code.

- **New files**: Zero warnings. Follow the rule as documented.
- **Modified files**: Do not increase the warning count. When practical, fix nearby warnings as part of the change.
- **Never suppress without a reason**: If you must add `eslint-disable`, document why.

Rules currently at `warn` that must still be followed in new code include: `testing-library/no-container`, `react-you-might-not-need-an-effect/*`, and `no-restricted-imports` (icon migration). These will be promoted to `error` once existing violations are resolved.

### Refactoring Strategies When Limits Are Hit

- **Long function** → Extract sub-components, custom hooks, or helper functions
- **Deep nesting** → Early returns / guard clauses
- **High complexity** → Split into predicate functions or lookup tables
- **Many params** → Group into `{ options }` object with a TypeScript type
- **Large file** → Split into co-located modules (e.g., `utils.ts`, `hooks.ts`, sub-components)

---

## 9. Internationalization (i18n) — Never Compare Display Strings

User-facing strings that will be translated must only be used for display, never in conditional logic.

```typescript
// ❌ BAD — breaks when translated
const cadence = durationToHumanReadableCadence(parsed.cadence)
if (cadence !== 'Does not repeat') { ... }
if (label === 'Active') { return 'success' }

// ✅ GOOD — compare raw/internal values
if (parsed.cadence) { ... }           // ISO duration like 'P1D'
if (status === 'active') { ... }      // API contract value
```

### Correct Patterns

**1. Compare raw/internal values:**

```typescript
if (parsed.cadence) {
  // parsed.cadence is the ISO duration like 'P1D', not 'Daily'
  parts.push(`Repeats ${cadence.toLowerCase()}`)
}
```

**2. Use TypeScript union types:**

```typescript
type CadenceValue = 'none' | 'daily' | 'weekly' | 'monthly' | 'annually'

// Compare internal values
if (cadence === 'daily') {
  return 'P1D'
}

// Map to display strings separately
const cadenceLabels: Record<CadenceValue, string> = {
  none: 'Does not repeat',
  daily: 'Daily',
  weekly: 'Weekly',
  monthly: 'Monthly',
  annually: 'Annually',
}
```

**3. Use value-to-label mapping:**

```typescript
const statusMap: Record<StatusValue, { label: string; variant: 'success' | 'danger' }> = {
  approved: { label: 'Approved', variant: 'success' },
  rejected: { label: 'Rejected', variant: 'danger' },
  pending: { label: 'Pending', variant: 'warning' },
}
const config = statusMap[apiStatus] // Use value for logic, label for display
```

### Allowed String Comparisons

These types of strings are **safe** to use in logic (they won't be translated):

- **API contract values**: `type === 'converge'`, `status === 'success'`, `type === 'script'`
- **TypeScript enum values**: `activity.type === ActivityTypeEnum.SCRIPT`
- **Internal constants**: `mode === 'development'`, `edge.type === 'buttonEdge'`
- **Technical identifiers**: `file.endsWith('.tsx')`, `id.startsWith('parallel_')`

### Enum Checklist

Before writing conditional logic with strings:

1. Is this string from an API response or TypeScript type? → **Safe to use**
2. Is this an internal constant/identifier? → **Safe to use**
3. Is this string shown to users in the UI? → **Do NOT use in logic**
4. Would this string be translated to other languages? → **Do NOT use in logic**

---

## 10. Use Enum Constants — Never String Literals for Discriminators

**CRITICAL: Use centralized enum constants instead of string literals for discriminators and identifiers to prevent typos.**

String literals in comparisons and assignments are error-prone. A single typo in a string comparison (`activity.type === 'converge'` vs `activity.type === 'convege'`) will silently fail without any TypeScript error, leading to bugs that are hard to track down.

### Why Use Enum Constants

**Problem with string literals:**

```typescript
// ❌ BAD: Typo-prone, no compile-time safety
if (activity.type === 'condition') {
  // works
}
if (activity.type === 'condtion') {
  // typo! No TypeScript error — this condition will never match (silent bug)
}

// ❌ BAD: Inconsistent casing
if (edge.sourceHandle === 'Loop') {
  // Should be 'loop' — never matches (silent bug)
}
```

**Solution with enum constants:**

```typescript
// ✅ GOOD: TypeScript catches typos at compile time
if (activity.type === ActivityTypeEnum.CONDITION) {
  // autocomplete + type checking
}
if (activity.type === ActivityTypeEnum.CONDTION) {
  // TypeScript error! Property 'CONDTION' does not exist
}
```

### Available Enum Values

The codebase provides centralized enum constants in `@syntara/contracts`:

```typescript
import { ActivityTypeEnum, TriggerTypeEnum, ExecutorTypeEnum, EdgeHandleEnum } from '@syntara/contracts'

// Activity types (v2 — executor types are first-class node types, no 'task' wrapper)
ActivityTypeEnum.SCRIPT // 'script'
ActivityTypeEnum.HTTP_REQUEST // 'http_request'
ActivityTypeEnum.AGENTIC // 'agentic'
ActivityTypeEnum.AAP_JOB_TEMPLATE // 'aap_job_template'
ActivityTypeEnum.APPROVAL // 'approval'
ActivityTypeEnum.CONDITION // 'condition'
ActivityTypeEnum.LOOP // 'loop'
ActivityTypeEnum.CONVERGE // 'converge'

// Trigger types
TriggerTypeEnum.MANUAL_TRIGGER // 'manual_trigger'
TriggerTypeEnum.SCHEDULED // 'scheduled'
TriggerTypeEnum.EVENT // 'event'
TriggerTypeEnum.WEBHOOK_TRIGGER // 'webhook_trigger'
TriggerTypeEnum.EDA_TRIGGER // 'eda_trigger'

// Executor types (v2 — executor types are the node type directly, no task.executor wrapper)
ExecutorTypeEnum.SCRIPT // 'script'
ExecutorTypeEnum.HTTP_REQUEST // 'http_request'
ExecutorTypeEnum.AGENTIC // 'agentic'
ExecutorTypeEnum.AAP_JOB_TEMPLATE // 'aap_job_template'
ExecutorTypeEnum.APPROVAL // 'approval'

// Edge handles
EdgeHandleEnum.SOURCE // 'source'
EdgeHandleEnum.TARGET // 'target'
EdgeHandleEnum.LOOP // 'loop'
EdgeHandleEnum.DONE // 'done'
EdgeHandleEnum.END // 'end'
EdgeHandleEnum.TRUE // 'true'
EdgeHandleEnum.FALSE // 'false'
EdgeHandleEnum.APPROVED // 'approved'
EdgeHandleEnum.REJECTED // 'rejected'
```

### When to Use Enum Constants

**Always use enum constants for:**

1. **Type discriminators** - `activity.type`, `trigger.type`
2. **Handle identifiers** - `edge.sourceHandle`, `edge.targetHandle`
3. **Type assignments** - Creating new activities, edges, triggers
4. **Switch statements** - Pattern matching on discriminated unions

**Examples:**

```typescript
// ✅ GOOD: Comparisons
if (activity.type === ActivityTypeEnum.LOOP) { ... }
if (edge.sourceHandle === EdgeHandleEnum.LOOP) { ... }

switch (activity.type) {
  case ActivityTypeEnum.CONDITION:
    return handleCondition(activity)
  case ActivityTypeEnum.LOOP:
    return handleLoop(activity)
}

// ✅ GOOD: Assignments
const activity = {
  type: ActivityTypeEnum.SCRIPT,
  id: generateId(),
  name: 'My Script',
}

const edge = {
  source: nodeId,
  target: targetId,
  sourceHandle: EdgeHandleEnum.LOOP,
  targetHandle: EdgeHandleEnum.END,
}

// ✅ GOOD: Function parameters
function createEdge(sourceHandle: string = EdgeHandleEnum.SOURCE) { ... }
```

### Benefits

1. **Autocomplete** - IDE suggests available values
2. **Type safety** - TypeScript catches typos at compile time
3. **Refactoring** - Rename all usages in one place
4. **Documentation** - Single source of truth for valid values
5. **Consistency** - Prevents case mismatches (`'Loop'` vs `'loop'`)

### Quick Checklist

Before writing a string comparison or assignment:

1. Is this a type discriminator, handle identifier, or status value?
2. If yes → Check if an enum constant exists (ActivityTypeEnum, TriggerTypeEnum, etc.)
3. If enum exists → Use it instead of string literal
4. If no enum exists → Consider creating one if the value is reused

---

## 11. Error Handling with RFC 9457 Problem Details

The application uses RFC 9457 Problem Details for API error responses. See [`frontend/docs/error-handling.md`](frontend/docs/error-handling.md) for complete patterns.

### Error Format

All API errors follow the RFC 9457 Problem Details format:

```typescript
{
  type: "https://api.example.com/errors/validation-error",
  title: "Validation Error",
  detail: "Field 'name' must be between 1 and 255 characters",
  code: "VALIDATION_ERROR",
  retryable: false,
  instance: "/api/v1/workflows"
}
```

### Error Handling Utilities

**Always use error utilities** - never access error fields directly:

```typescript
import {
  getErrorMessage,
  getErrorTitle,
  getErrorCode,
  isRetryableError,
  isServiceUnavailableError,
  isValidationError,
  isConflictError,
} from '../utils/apiErrors'

// ✅ GOOD
const message = getErrorMessage(error)
const title = getErrorTitle(error)

// ❌ BAD
const message = error.detail || error.message // Don't access directly
```

### Error Codes

| Code                    | HTTP Status | Description                      | Retryable |
| ----------------------- | ----------- | -------------------------------- | --------- |
| VALIDATION_ERROR        | 422         | Input validation failed          | No        |
| WORKFLOW_NAME_CONFLICT  | 409         | Workflow name already exists     | No        |
| WORKFLOW_DISABLED       | 400         | Cannot execute disabled workflow | No        |
| PROVIDER_NAME_CONFLICT  | 409         | Provider name already exists     | No        |
| FILE_TOO_LARGE          | 413         | File exceeds size limit          | No        |
| LLM_CONFIGURATION_ERROR | 503         | LLM service not configured       | Yes       |
| TEMPORAL_UNAVAILABLE    | 503         | Workflow engine unavailable      | Yes       |
| INTERNAL_ERROR          | 500         | Internal server error            | Yes       |

### Mutation Error Hooks

Use the correct mutation error hook by context:

- `useFormMutationErrorHandler` for react-hook-form mutations (maps 422 field errors to form fields)
- `useMutationErrorHandler` for non-form mutations

Never use ad-hoc manual error parsing. Use `getErrorMessage()` and `isConflictError()` from `apiErrors.ts` for error inspection.

### Query Invalidation After Mutations

After a state transition (cancel, delete, update), invalidate **all** related queries, not just the primary one. Stale child queries cause UI inconsistencies.

```typescript
// ❌ BAD — activity list still shows "running" after cancellation
queryClient.invalidateQueries({ queryKey: ['get', '/executions/{execution_id}'] })

// ✅ GOOD — invalidate the execution AND its activities
Promise.all([
  queryClient.invalidateQueries({ queryKey: ['get', '/executions/{execution_id}'] }),
  queryClient.invalidateQueries({ queryKey: ['get', '/executions/{execution_id}/activities'] }),
  queryClient.invalidateQueries({ queryKey: ['get', '/executions'] }),
])
```

### Retry Support

For retryable errors, pass an `onRetry` callback:

```typescript
// Query retry support
const query = workflowClient.useQuery('get', '/workflows')
const queryState = useQueryState(query, {
  title: 'Error loading workflows',
  onRetry: () => detachPromise(query.refetch()),
})

// Mutation retry support
const handleError = useMutationErrorHandler()
const { mutate } = workflowClient.useMutation('post', '/workflows')

mutate(data, {
  onError: handleError({
    title: 'Failed to create workflow',
    onRetryable: () => setShowRetry(true),
  }),
})
```

### Retry Button in Error States

The `NxErrorState` component automatically shows a retry button for retryable errors when `onRetry` is provided:

```typescript
// Retry button appears automatically for 5xx errors or errors with retryable=true
<NxErrorState
  title="Failed to load data"
  message={error}
  onRetry={() => detachPromise(refetch())}
/>
```

---

## 12. `NxConfirmationDialog` — Never Inline Modal Boilerplate

Use `NxConfirmationDialog` for all confirmation prompts. Never use raw `Modal` + `ModalHeader` + `ModalBody` + `ModalFooter`. ESLint rule `syntara/prefer-confirmation-dialog` (error) catches raw destructive Modal patterns automatically; the guidance below teaches the correct tier selection and content patterns.

> **Check Storybook first:** Before implementing any confirmation dialog, call the Storybook MCP `get-documentation` tool with id `"components-dialogs-nxconfirmationdialog"`. The stories are the primary source of truth for tier selection, correct prop usage, title format, body copy, checkbox labels, and button labels — and take precedence over the static examples below.

There are **two tiers** of destructive modals depending on reversibility:

### Tier 1: Permanent/irreversible actions (delete, reset)

Requires `titleIconVariant="warning"` + `destructiveAcknowledgement` checkbox. The confirm button stays disabled until the user checks the box.

```typescript
// ❌ BAD — raw Modal, no warning icon, no acknowledgement
<Modal isOpen={isOpen} onClose={onClose} variant="small">
  <ModalHeader title="Delete item" />
  <ModalBody>Are you sure?</ModalBody>
  <ModalFooter>
    <Button variant="danger" onClick={onConfirm}>Delete</Button>
    <Button variant="link" onClick={onClose}>Cancel</Button>
  </ModalFooter>
</Modal>

// ✅ GOOD — warning icon, acknowledgement checkbox, descriptive body
<NxConfirmationDialog
  isOpen={isOpen}
  onClose={onClose}
  onConfirm={handleDelete}
  title="Delete workflow?"
  confirmLabel="Delete"
  confirmVariant="danger"
  titleIconVariant="warning"
  destructiveAcknowledgement={{
    checkboxId: 'delete-workflow-ack',
    label: 'I understand this workflow will be permanently deleted.',
  }}
>
  The workflow <strong>{item?.name}</strong> will be deleted. This cannot be undone.
</NxConfirmationDialog>
```

### Tier 2: Reversible actions (remove, unassign)

Uses `titleIconVariant="warning"` but **no** `destructiveAcknowledgement` checkbox since the action can be undone.

```typescript
// ✅ GOOD — warning icon, descriptive body, no checkbox
<NxConfirmationDialog
  isOpen={!!memberToRemove}
  onClose={() => setMemberToRemove(null)}
  onConfirm={handleRemove}
  title="Remove member?"
  confirmLabel="Remove"
  confirmVariant="danger"
  titleIconVariant="warning"
>
  This removes <strong>{memberToRemove?.username}</strong> from the group.
  They will lose any permissions granted through this group membership.
</NxConfirmationDialog>
```

### Body text rules

- **Never** start with "Are you sure you want to..." — state what will happen instead
- Use `<strong>` for entity names (workflow name, credential name, etc.)
- State the consequence clearly: "This cannot be undone." or "Related permissions will be revoked."
- Title always ends with `?` (e.g., "Delete workflow?" not "Delete workflow")

---

## 13. `useDialogState` — Never Manual useState Pairs

```typescript
// ❌ BAD
const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
const [itemToDelete, setItemToDelete] = useState<User | null>(null)

// ✅ GOOD
const deleteDialog = useDialogState<User>()
// Open: deleteDialog.open(user)
// Close: deleteDialog.close()
// Use: deleteDialog.isOpen, deleteDialog.item
```

---

## 14. `useCursorPagination` — Never Duplicate Cursor Boilerplate

```typescript
// ❌ BAD — 50+ lines repeated per list view (also: do not wire useSortState / useColumnSortState separately)
const [cursor, setCursor] = useState<string | null>(null)
const { filters, clearAllFilters, setAllFilters } = useFilterState()
const filterParams = buildFilterParams(filters)
const queryParams = { limit: 20, ...filterParams, ...(cursor ? { cursor } : {}) }

// ✅ GOOD — filters + sort + cursor in one hook
const {
  cursor,
  setCursor,
  filters,
  hasActiveFilters,
  queryParams,
  handleFilterChange,
  handleClearAllFilters,
  getFooterProps,
  getSortParams,
} = useCursorPagination({
  limit: 20,
  extraParams,
  defaultFilters,
  transformFilters,
  defaultSort, // optional — URL-synced sort merged into queryParams
  columns, // optional — PatternFly getSortParams / handleSort
})
```

---

## 15. Stable React context provider values

Enforced by ESLint rule `react/jsx-no-constructed-context-values` at error level. Wrap context `value` props in `useMemo`.

---

## 16. Module-scoped pure helpers (Sonar)

Prefer **module scope** (or another stable outer scope) for helpers that are **pure**: they only use their parameters and do not close over React props, state, context, or hooks from the component body. Defining those helpers inside the component recreates the function every render and tends to re-trigger Sonar "move to outer scope" maintainability findings without adding behavior.

There is **no ESLint rule** in this repo that matches that Sonar check narrowly; `unicorn/consistent-function-scoping` is broader and was not adopted globally. Use **SonarCloud / code review** to catch new cases until a dedicated lint strategy exists (for example a custom rule or a repo-wide Unicorn cleanup).

```typescript
// ❌ BAD — recreated each render; avoid when the helper is pure
function MyForm() {
  function formatLabel(id: string) {
    return id.toUpperCase()
  }
  // ...
}

// ✅ GOOD — module scope (or a colocated `*.utils.ts` if large)
function formatLabel(id: string) {
  return id.toUpperCase()
}

function MyForm() {
  // ...
}
```

### Row Action Builders

Table row actions that depend on permissions and callbacks are a common case. Extract them into a standalone module-scoped function instead of building the array inline (which triggers eslint-disable temptation and Sonar S6478 findings).

```typescript
// ❌ BAD — complex action array inline, triggers eslint-disable
function CredentialsTable() {
  // eslint-disable-next-line sonarjs/cognitive-complexity
  const getRowActions = (credential: Credential) => [
    { title: 'Edit', onClick: () => setEdit(credential), isAriaDisabled: !canUpdate },
    // ... 20 more lines
  ]
}

// ✅ GOOD — module-scoped builder, no suppression needed
function buildCredentialRowActions(
  credential: Credential,
  permissions: CredentialPermissions,
  callbacks: { onEdit: (c: Credential) => void; onDelete: (c: Credential) => void }
): RowAction[] {
  return [
    {
      key: 'edit',
      title: <IconLabel icon={<RhUiEditIcon />}>Edit credential</IconLabel>,
      isAriaDisabled: !permissions.canUpdate,
      tooltipProps: permissions.canUpdate ? undefined : { content: permissions.tooltips.update },
      onClick: () => callbacks.onEdit(credential),
    },
    { key: 'sep', isSeparator: true },
    {
      key: 'delete',
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete credential</IconLabel>,
      isDanger: true,
      isAriaDisabled: !permissions.canDelete,
      tooltipProps: permissions.canDelete ? undefined : { content: permissions.tooltips.delete },
      onClick: () => callbacks.onDelete(credential),
    },
  ]
}

function CredentialsTable() {
  const getRowActions = (credential: Credential) =>
    buildCredentialRowActions(credential, permissions, { onEdit: setEdit, onDelete: openDeleteDialog })
}
```

---

## 17. Prefer `Set` for membership-only checks (Sonar **typescript:S7776**)

Sonar rule **typescript:S7776** (_Arrays used only for existence checks should be Sets_) applies when a collection is used **mainly or only** to answer "is this value present?"—for example repeated **`Array#includes()`** lookups.

**Why it matters (per Sonar):** `includes()` is **O(n)** per call because it may scan the whole array. **`Set#has()`** is **O(1)** on average. For very small collections the difference is usually negligible; it matters more for **larger lists** and when checks run **often** (loops, drag/drop handlers, render-hot paths).

**What to do:** If membership is the primary use case, keep or build a **`Set`**, use **`.has()`** (and **`.add()`** / **`.delete()`** when the allowed set changes). Do **not** replace arrays when you need **order**, **duplicates**, **indexing**, or **array-specific APIs**—those are valid reasons to stay on an array.

**Official references:** Sonar rule **typescript:S7776** in the Sonar rules catalog; related discussion in ESLint **`unicorn/prefer-set-has`** ([rule doc](https://github.com/sindresorhus/eslint-plugin-unicorn/blob/main/docs/rules/prefer-set-has.md)); [MDN `Set.prototype.has()`](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Set/has), [MDN `Array.prototype.includes()`](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/includes).

```typescript
// ❌ Non-compliant (Sonar S7776) — array used only as a membership bag
const allowedValues = [1, 2, 3, 4, 5]
const isAllowed = (value: number) => allowedValues.includes(value)

// ✅ Compliant — Set for existence
const allowedValues = new Set([1, 2, 3, 4, 5])
const isAllowed = (value: number) => allowedValues.has(value)
```

---

## 18. No nested React components; stable PatternFly `toggle` / render props (Sonar **typescript:S6478**)

Sonar **typescript:S6478** (_React components should not be nested_): do not declare **function or class components inside** another component's body. A nested definition is a **new component type on every parent render**, which can **reset subtree state** and waste reconciliation work.

**PatternFly `Select`, `Dropdown`, `Popover`, etc.** often require a **`toggle={(toggleRef) => …}`** or **`bodyContent={(hide) => …}`**. You cannot remove that callback, but you **must not** declare `function Inner()` / `const Inner = () => …` **inside** the parent component just to return JSX from it.

**Do instead:** define a **named component at module scope** (same file above the export is fine), pass all dynamic bits as **props**, and return that type from the PF prop:

```tsx
// ❌ Non-compliant — component type recreated every parent render
function Parent() {
  function Toggle(props: { toggleRef: Ref<MenuToggleElement> }) {
    return <MenuToggle ref={props.toggleRef}>…</MenuToggle>
  }
  return <Select toggle={(ref) => <Toggle toggleRef={ref} />} />
}

// ✅ Compliant — stable element type; PF still receives a toggle render prop
function ParentMenuToggle(props: Readonly<{ toggleRef: Ref<MenuToggleElement>; label: string }>) {
  return <MenuToggle ref={props.toggleRef}>{props.label}</MenuToggle>
}

function Parent() {
  return <Select toggle={(ref) => <ParentMenuToggle toggleRef={ref} label={label} />} />
```

Sonar's docs also allow factories in props whose names match **`render*`** (and some **`children`** patterns). PatternFly uses names like **`toggle`**, so **module-scoped** presentational components are the usual fix.

**ESLint:** `react/no-unstable-nested-components` overlaps this theme but often still flags **valid** `(ref) => <ModuleScopedToggle … />` shapes unless **`allowAsProps: true`**, which then **permits** many other "component in prop" patterns Sonar would still reject. This repo therefore relies on **SonarCloud S6478** (and review) rather than enabling that rule globally.

---

## 19. `showSuccess` / `showError` — Sentence Case

The object parameter form (`{ title, description? }`) is enforced by ESLint `no-restricted-syntax` at error level. Use **sentence case** for alert titles ("Workflow created successfully", not "Workflow Created Successfully"). The same applies to `showWarning` and `showInfo`.

---

## 20. No Raw HTML Elements for Text Content

Enforced by ESLint rules `syntara/prefer-pf-text-components` and `syntara/prefer-pf-list-components` at error level. Use PF `Content`, `HelperText`, `Label`, `Title` instead of raw `<span>`/`<p>`/`<div>`, and PF `List`/`ListItem` instead of raw `<ul>`/`<ol>`/`<li>`.

**PF Content automatic margin:** PF6 `<Content>` adds automatic margin when rendered as `<p>`, `<small>`, or other block elements. When Content is inside a Flex row, popover header, or other tight layout context, reset it with `margin: 0` via a CSS module class. Prefer a CSS module class over inline `style={{ margin: 0 }}`.

---

## 21. `useMemo` for Derived Data in Custom Hooks

When a custom hook computes derived data (maps, sorted arrays, filtered lists) from query results, wrap the computation in `useMemo`. Without it, the derived data gets a new reference on every render, causing unnecessary re-renders in consumers.

```typescript
// ❌ BAD — new Map and sorted array on every render
export function useResourceActions() {
  const { data } = accessClient.useQuery('get', '/authz/resource-actions')
  const ra = data?.resource_actions ?? {}
  const resourceTypes = Object.keys(ra).sort()
  const actionsByResource = new Map(Object.entries(ra))
  return { resourceTypes, actionsByResource }
}

// ✅ GOOD — stable references when data hasn't changed
export function useResourceActions() {
  const { data } = accessClient.useQuery('get', '/authz/resource-actions')
  const { resourceTypes, actionsByResource } = useMemo(() => {
    const ra: Record<string, string[]> = data?.resource_actions ?? {}
    return {
      resourceTypes: Object.keys(ra).sort(),
      actionsByResource: new Map(
        Object.entries(ra)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([k, v]) => [k, [...v].sort((a, b) => a.localeCompare(b))])
      ),
    }
  }, [data])
  return { resourceTypes, actionsByResource }
}
```

**When to use `useMemo`:**

- The hook transforms query data into a different shape (map, sorted array, filtered list)
- The hook creates new object/array references that consumers would compare by identity
- Multiple consumers share the hook and would all re-render on reference changes

**When NOT to use `useMemo`:**

- Simple pass-through of query data (already referentially stable from React Query)
- Primitive return values (strings, numbers, booleans — identity-stable by nature)

---

## 22. Full list via cursor pagination — `fetchAllPages` + `useAll*` hooks

**Do not** use a single `useQuery` with `limit: 100` (or any fixed cap) for data that must include every row (dropdown option lists, the Settings page, group pickers, etc.). When the API returns more than one page, the rest is silently missing.

**Do** load the full list by following `next` cursors in a small utility, then cache with React Query in a dedicated hook:

- Use `fetchAllPages` from `frontend/packages/syntara-ui/src/utils/fetchAllPages.ts` (safety caps: `MAX_PAGES`, `MAX_ITEMS`, loop detection).
- Expose one hook per resource, e.g. `useAllProjects`, `useAllSettings`, in the route/feature folder, with `queryKey` like `['all-projects']` and a matching test file.
- **Tables** that paginate in the UI should keep using **`useCursorPagination`** — `fetchAllPages` is only for "need every row once" scenarios (dropdowns, full settings catalog, modals).

```typescript
// ❌ BAD — at most 100 projects, no second page
accessClient.useQuery('get', '/projects', { params: { query: { limit: 100 } } })

// ✅ GOOD — shared hook, all pages merged, React Query dedupes across consumers
const { projects } = useAllProjects()
```

---

## 23. Prefer Event Handlers and Derived State Over `useEffect`

`useEffect` is for **synchronizing with external systems** (DOM subscriptions, timers, WebSockets, fetching on mount). It is **not** for transforming data, handling user events, or cascading form state changes. Misuse causes extra render cycles, stale state bugs, and harder-to-follow data flow.

**Reference**: [You Might Not Need an Effect — React docs](https://react.dev/learn/you-might-not-need-an-effect)

**ESLint enforcement**: `eslint-plugin-react-you-might-not-need-an-effect` is configured as `warn` for all 8 rules in `eslint.config.js`.

### When `useEffect` IS correct

- **Subscriptions with cleanup**: event listeners, ResizeObserver, WebSocket connections
- **Timers**: intervals, debounce timeouts (with cleanup)
- **Fetching data on mount** (prefer React Query's `useQuery` when available)
- **Syncing with external libraries**: Monaco editor, ReactFlow, third-party widgets
- **Modal form reset** (§6): `reset()` in `useEffect` keyed on `[isOpen, item]` for always-mounted modals

### Anti-patterns to avoid

#### A. Derived state — compute during render

```typescript
// ❌ BAD — extra render cycle
const [fullName, setFullName] = useState('')
useEffect(() => {
  setFullName(`${firstName} ${lastName}`)
}, [firstName, lastName])

// ✅ GOOD — calculate during render
const fullName = `${firstName} ${lastName}`

// ✅ GOOD — expensive computation
const filtered = useMemo(() => items.filter(expensivePredicate), [items])
```

#### B. Cascading form field resets — use `onChange` handlers

```typescript
// ❌ BAD — useEffect watches field, triggers another setState
const scope = useWatch({ control, name: 'scope' })
useEffect(() => {
  setValue('roleName', '')
}, [scope, setValue])

// ✅ GOOD — reset in the same event that caused the change
<FormSelect
  onChange={(_event, value) => {
    field.onChange(value)
    setValue('roleName', '')
  }}
>
```

#### C. Notifying parent about state changes — update in handler

```typescript
// ❌ BAD — parent updates after child renders
useEffect(() => {
  onChange(isOn)
}, [isOn, onChange])

// ✅ GOOD — update both in the same handler
function handleToggle() {
  const next = !isOn
  setIsOn(next)
  onChange(next)
}
```

#### D. Resetting state on prop change — use `key` or conditional reset

```typescript
// ❌ BAD — extra render with stale state
useEffect(() => {
  setComment('')
}, [userId])

// ✅ GOOD — key forces remount, state resets automatically
<Profile userId={userId} key={userId} />

// ✅ GOOD — conditional reset during render (no effect needed)
if (!isOpen && destructiveAcknowledged) {
  setDestructiveAcknowledged(false)
}
```

#### E. Mirroring props in state — use the prop directly

```typescript
// ❌ BAD — local state mirrors prop
const [isChecked, setIsChecked] = useState(checked)
useEffect(() => { setIsChecked(checked) }, [checked])

// ✅ GOOD — use prop directly, let parent control state
<Switch isChecked={checked} onChange={(_e, v) => handleChange?.(v)} />
```

---

## 25. Prefer CSS Modules Over Inline Style Objects

Inline style objects (`style={{ margin: 0, color: '...' }}`) create a new object reference on every render and cannot be cached by the browser. Use CSS module classes instead.

```typescript
// ❌ BAD — new object every render, not cacheable
const userStyle = { margin: 0, color: 'var(--pf-t--global--color--brand--default)' } as const
<Content style={userStyle}>{user}</Content>

// ✅ GOOD — CSS module class, cacheable, no render overhead
import styles from './UserTimestamp.module.css'
<Content className={styles.user}>{user}</Content>
```

```css
/* UserTimestamp.module.css */
.user {
  margin: 0;
  color: var(--pf-t--global--color--brand--default);
}
```

**When inline styles are acceptable:**

- One-off dynamic values computed at runtime (e.g., `style={{ width: `${percent}%` }}`)
- Styles that genuinely depend on props and have no fixed set of variants

---

## 26. No Mutable Counters Inside `.map()`

Do not use `let` counters incremented inside `.map()` or `.forEach()`. Mutable variables inside render paths break React's expectations about pure rendering and make the code harder to reason about.

```typescript
// ❌ BAD — mutable counter inside .map()
let rowIndex = 0
return groups.map(([id, { credentials }]) => {
  return credentials.map((cred) => {
    const currentIndex = rowIndex++
    return <Row key={cred.id} rowIndex={currentIndex} />
  })
})

// ⚠️ ACCEPTABLE but O(n²) — indexOf scans from the start for every row
const allCredentials = [...groupedCredentials.values()].flatMap(({ credentials }) => credentials)
return groups.map(([id, { credentials }]) => {
  return credentials.map((cred) => {
    const rowIndex = allCredentials.indexOf(cred)
    return <Row key={cred.id} rowIndex={rowIndex} />
  })
})

// ✅ BEST — pre-build an index Map for O(1) lookups per row
const indexMap = new Map<string, number>()
let globalIndex = 0
for (const { credentials } of groupedCredentials.values()) {
  for (const cred of credentials) {
    indexMap.set(cred.id, globalIndex++)
  }
}

return groups.map(([id, { credentials }]) => {
  return credentials.map((cred) => (
    <Row key={cred.id} rowIndex={indexMap.get(cred.id) ?? 0} />
  ))
})
```

**When `indexOf` is fine:** Small lists (under ~50 items) where the O(n) scan is negligible. For table rows with grouped/nested data or any list that may grow, prefer the Map approach.

---

## 27. `aria-label` Only on Interactive Elements

**Enforced by ESLint:** `no-restricted-syntax` (error for `<span>`). See `eslint.config.js`.

Do not add `aria-label` to non-interactive elements like `<span>` or `<div>`. Assistive technologies only announce `aria-label` on interactive elements, widgets, landmarks, images, and iframes. On a `<span>`, it is ignored by most screen readers.

```typescript
// ❌ BAD — aria-label on a non-interactive span
<span aria-label="Status indicator">{statusText}</span>

// ✅ GOOD — inner text content is sufficient for screen readers
<span>{statusText}</span>

// ✅ GOOD — aria-label on an interactive element
<Button aria-label="Close dialog" variant="plain" icon={<TimesIcon />} />
```

**Reference:** [MDN aria-label](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Attributes/aria-label) -- "in practice, it is supported only on interactive elements, widgets, landmarks, images, and iframes."

---

## 28. Never Use `eslint-disable` -- Fix the Code Instead

**Do not add `eslint-disable`, `eslint-disable-next-line`, or `eslint-disable-line` comments to new or modified code.** Every lint rule exists to catch a real problem. The correct response to a lint violation is to fix the code so the rule passes, not to silence the rule.

This applies to **all** rules without exception: `jsx-a11y/*`, `react-hooks/*`, `testing-library/*`, `@typescript-eslint/*`, `sonarjs/*`, and every other configured rule.

```typescript
// ❌ BAD — suppressing instead of fixing
// eslint-disable-next-line testing-library/no-node-access
const wrapper = container.querySelector('.pf-v6-c-file-upload')

// ❌ BAD — suppressing an a11y rule introduces real accessibility bugs
// eslint-disable-next-line jsx-a11y/no-static-element-interactions -- prevent toggle
<div onClick={handleClick}>

// ❌ BAD — suppressing type safety rules hides real type errors
// eslint-disable-next-line @typescript-eslint/no-unsafe-return
return mockStore()

// ✅ GOOD — fix the code so the rule passes
const wrapper = screen.getByRole('group', { name: 'File upload' })
<button type="button" onClick={handleClick}>
return mockStore() as ReturnType<typeof createStore>
```

**When a lint rule fires:**

1. **Understand what the rule protects** (accessibility, type safety, testing quality, code complexity)
2. **Fix the code**: restructure markup, use semantic HTML, add proper types, extract functions, use PatternFly components
3. **If the violation is in a third-party component** (e.g., PatternFly renders no accessible role), file an upstream issue and find a workaround that does not suppress the rule (e.g., use a different query, wrap in a labeled container)

**Pre-existing suppressions** in the codebase are technical debt being cleaned up. Do not add new ones. When modifying a file that already has suppressions, remove them if the fix is straightforward.

---

## 29. Conditional Hook Execution via Wrapper Component

When a hook is called unconditionally but its data is only needed for one mode (e.g., create vs. edit), extract a small wrapper component that calls the hook and is only rendered when needed. This avoids unnecessary API calls and follows React's rules of hooks.

```typescript
// ❌ BAD — fetches all groups even in edit mode where groups are not shown
function UserFormFields({ isEdit, control }: Props) {
  const { groups, isLoading } = useAllGroups()
  return (
    <>
      {/* ...other fields... */}
      {!isEdit && <GroupMultiSelect groups={groups} isLoading={isLoading} />}
    </>
  )
}

// ✅ GOOD — hook only called when the component renders
function GroupField({ control }: Readonly<{ control: Control<UserFormData> }>) {
  const { groups, isLoading } = useAllGroups()
  const groupOptions = useMemo(() => groups.map((g) => ({ name: g.name })), [groups])
  return (
    <Controller
      name="group_names"
      control={control}
      render={({ field }) => (
        <FormGroup label="Groups" fieldId="user-groups-select">
          <GroupMultiSelect
            selected={field.value ?? []}
            onChange={field.onChange}
            isLoading={isLoading}
            groupOptions={groupOptions}
          />
        </FormGroup>
      )}
    />
  )
}

function UserFormFields({ isEdit, control }: Props) {
  return (
    <>
      {/* ...other fields... */}
      {!isEdit && <GroupField control={control} />}
    </>
  )
}
```

---

## 30. Leverage Existing Libraries Before Writing Custom Code

**Always use the project's established libraries for their intended purpose.** Do not reimplement functionality that an installed library already provides. Manual reimplementations lose caching, deduplication, retry, DevTools integration, and consistency with the rest of the codebase.

**Always prefer browser-native APIs over custom utilities.** The browser already provides well-tested, zero-dependency solutions for many common tasks. Use them before reaching for a library or writing custom code.

### The Tech Stack Contract

| Concern                      | Use this                                                       | Not this                                     |
| ---------------------------- | -------------------------------------------------------------- | -------------------------------------------- |
| **Server state (queries)**   | TanStack Query `useQuery` / `useQueries` via typed API clients | Manual `useEffect` + `useState` + `fetch`    |
| **Server state (mutations)** | TanStack Query `useMutation` via typed API clients             | Manual `useEffect` + `Promise` chains        |
| **Form state**               | `react-hook-form` + Zod `zodResolver`                          | Manual `useState` per field                  |
| **Client state (global)**    | Zustand stores (workflow builder)                              | React Context with manual reducers           |
| **Styling**                  | PatternFly components + PF6 design tokens + CSS modules        | Inline style objects, raw HTML, hardcoded px |
| **API calls**                | Typed clients from `client.tsx`                                | Raw `fetch()`                                |
| **Error handling**           | `useQueryState`, `useMutationErrorHandler`, `NxErrorState`     | Ad-hoc try/catch with custom JSX             |
| **Pagination**               | `useCursorPagination`                                          | Manual cursor/filter/queryParams state       |
| **Dialogs**                  | `NxConfirmationDialog` + `useDialogState`                      | Raw `Modal` + manual open/close state        |

### Browser-Native APIs First

Before writing a utility function, check if a browser API already does it:

| Task                          | Use this browser API                               | Not this                                                |
| ----------------------------- | -------------------------------------------------- | ------------------------------------------------------- |
| **Parse/build query strings** | `URLSearchParams`                                  | Manual string splitting/joining                         |
| **Deep clone objects**        | `structuredClone()`                                | JSON.parse(JSON.stringify()) or hand-rolled clone       |
| **Cancel async work**         | `AbortController` + `AbortSignal`                  | Manual `cancelled` flags                                |
| **Debounce/throttle**         | `requestAnimationFrame`, `setTimeout` with cleanup | Custom debounce utility (unless shared across 3+ files) |
| **Unique IDs**                | `crypto.randomUUID()`                              | Custom ID generators                                    |
| **Check array membership**    | `Set.has()`                                        | `Array.includes()` in hot paths (see §17)               |
| **Format dates for display**  | Project `dateUtils.ts` (wraps `date-fns`)          | Raw `Date.toLocaleString()` or manual formatting        |

### Why This Matters

When a library is in the dependency tree and the codebase uses it everywhere else, a hand-rolled alternative:

1. **Loses features for free** -- TanStack Query gives caching, deduplication, retry, stale-while-revalidate, and DevTools. A `useEffect` + `useState` hook gets none of these.
2. **Creates two patterns** -- Future contributors must learn and maintain both the standard approach and the custom one.
3. **Blocks composition** -- TanStack Query consumers can invalidate permission caches after role changes (`queryClient.invalidateQueries`). A manual hook cannot participate in this flow.

### Decision Process

Before writing a new hook or utility:

1. **Check the tech stack table above** -- is there a library that covers this concern?
2. **Search the codebase** -- has someone already solved this? (`grep -r "useQuery\|useMutation\|useForm" src/hooks/`)
3. **Check `src/hooks/`** -- reusable hooks live here; extend before duplicating
4. **Only then** write custom code, and document _why_ the standard tool doesn't fit

### Example: Permission Checking

```typescript
// ❌ BAD - manual useEffect + useState for an API call (loses caching, dedup, retry)
function useCanI(action: string, resourceType: string) {
  const [allowed, setAllowed] = useState(false)
  const [isChecking, setIsChecking] = useState(true)
  useEffect(() => {
    let cancelled = false
    accessFetchClient
      .POST('/authz/can_i', { body: { action, resource_type: resourceType } })
      .then(({ data }) => {
        if (!cancelled) setAllowed(data?.allowed === true)
      })
      .finally(() => {
        if (!cancelled) setIsChecking(false)
      })
    return () => {
      cancelled = true
    }
  }, [action, resourceType])
  return { allowed, isChecking }
}

// ✅ GOOD - TanStack Query handles caching, dedup, retry, and DevTools
// (this is the actual implementation in hooks/useCanI.ts)
function useCanI(action: string, resourceType: string, options?: UseCanIOptions) {
  const { data, isLoading, isError } = useQuery({
    queryKey: [
      'authz',
      'can_i',
      {
        action,
        resource_type: resourceType,
        ...(options?.resourceId ? { resource_id: options.resourceId } : {}),
      },
    ],
    queryFn: () =>
      accessFetchClient.POST('/authz/can_i', {
        body: { action, resource_type: resourceType },
      }),
    select: (res) => res.data?.allowed === true,
    staleTime: Infinity,
    retry: false,
  })
  return { allowed: data ?? false, isChecking: isLoading, isError }
}
```

> **Trade-off: `staleTime: Infinity`** means permissions are fetched once per session and
> never automatically re-fetched. If an admin revokes a user's role, the change won't take
> effect in that user's browser until (a) a role/assignment mutation triggers
> `queryClient.invalidateQueries({ queryKey: ['authz', 'can_i'] })`, or (b) the user logs
> out (`queryClient.clear()`). This is intentional — permission checks are high-frequency
> and low-change, so we trade freshness for reduced API load. Server-side enforcement
> remains the ultimate authority; the UI cache is a UX optimization, not a security boundary.

---

## 31. Permission Gating Patterns

All CRUD and destructive actions must be gated by permissions. See [`frontend/docs/permissions-rbac.md`](frontend/docs/permissions-rbac.md) for the full architecture.

### When to create a domain hook vs inline `useCanI`

- **Domain hook** (`use*Permissions`): when a page has 3+ gated actions, or when the same permissions are checked in multiple components (e.g. list + detail). Returns `can*` booleans, `isLoading`, and `tooltips`.
- **Inline `useCanI`**: when a single isolated action needs gating (e.g. `CancelExecutionButton`).

### Action button gating pattern

```tsx
// Use DisabledWithTooltip + isAriaDisabled for action buttons
<DisabledWithTooltip isDisabled={!permissions.canCreate} content={permissions.tooltips.create}>
  <Button isAriaDisabled={!permissions.canCreate} onClick={permissions.canCreate ? handleCreate : undefined}>
    Create
  </Button>
</DisabledWithTooltip>
```

For kebab menu items, use `isAriaDisabled` and `tooltipProps`:

```tsx
{
  title: <IconLabel icon={<RhUiEditIcon />}>Edit</IconLabel>,
  isAriaDisabled: !permissions.canUpdate,
  tooltipProps: permissions.canUpdate ? undefined : { content: permissions.tooltips.update },
  onClick: permissions.canUpdate ? handleEdit : undefined,
}
```

### Tooltip copy

Always use `permissionTooltip()` from `hooks/permissionUtils.ts` for consistent copy:

```tsx
permissionTooltip('create a workflow', 'workflow:create')
// → "To create a workflow, you need a role with the workflow:create policy. Contact your Admin to request access."
```

### Navigation gating

In `navigationItems.tsx`, use `requiredPermissions` (array, OR logic) for visibility and `routePermission` (single) for route guards:

```tsx
{
  label: 'Settings',
  requiredPermissions: [{ action: 'read', resourceType: 'setting' }],
}
{
  label: 'Create User',
  routePermission: { action: 'create', resourceType: 'user' },
}
```

### Tab gating

Detail pages conditionally show/hide tabs based on permissions. Use a `use*DetailPermissions` hook:

```tsx
const { canReadGroups, canReadAssignments } = useUserDetailPermissions(userId)
const visibleTabs = computeVisibleTabs(canReadGroups, canReadAssignments, isLoading)
```

When a user views their own profile, apply a self-permission exception (`isSelf`) so tabs like Groups and Identities remain visible even without system-wide read permission.

### Builder / editor read-only mode

For editor-style pages where many controls depend on a single permission, use a `canEdit` flag from the domain hook instead of wrapping every control individually:

```tsx
const { canEdit, tooltips } = useBuilderPermissions(isNew)
// canEdit = isNew ? canCreate : canUpdate
// Builder enters full read-only mode when canEdit is false
```

### Cache invalidation

After role or assignment mutations, invalidate all permission caches:

```tsx
queryClient.invalidateQueries({ queryKey: ['authz', 'can_i'] })
```

### Mock API

When adding new permission-gated features, add role-aware responses in `frontend/packages/syntara-mock-api/src/handlers.ts` for all 4 roles (admin, viewer, auditor, user) and E2E tests in `permission-gating.spec.ts`.

---

## 32. No Section-Divider Comments — Use JSDoc on Declarations Instead

Do not use `// ---`, `// ===`, or `// -----...-----` banners to separate regions of a file. These comments explain _where_ code lives, not _why_ it exists. They add visual noise without adding meaning, and they drift out of sync with the code as the file evolves.

```typescript
// ❌ BAD — section dividers that explain nothing
// ---------------------------------------------------------------------------
// Help text components
// ---------------------------------------------------------------------------
function WebhookPathHelp() { ... }

// --- Story components ---
function DefaultStory() { ... }

// ✅ GOOD — if a declaration needs context, attach it as JSDoc
/**
 * Shared between `NxListPanelTabs` and `NxListPanelContent`. Placed at `NxListPanel`
 * (not `NxListPanelTabs`) so `NxListPanelContent` rendered via a TanStack Router `<Outlet>`
 * can still consume it as a descendant of `NxListPanel` but not of `NxListPanelTabs`.
 */
type NxListPanelTabContextValue = { ... }
```

**Why:** Section banners explain _what_ code is, which well-named identifiers already communicate. JSDoc on a declaration travels with the symbol into tooling (IDE hover, generated docs), so the documentation stays attached even after the file is reorganised or the symbol is moved.

**What to do instead:**

- If a group of declarations has a non-obvious purpose, add a `/** */` JSDoc comment to the first (or most important) declaration in the group.
- If the code is self-explanatory, write no comment at all.
- Never write a freestanding comment whose sole purpose is to label a file region.

---

## 33. No `// TODO` Comments in Shipped Code

Do not ship `// TODO`, `// FIXME`, `// HACK`, or `// XXX` comments in PRs. These represent deferred work that should be tracked in an issue, not buried in source code where it is invisible to project management and will rot.

```typescript
// ❌ BAD — deferred work hidden in code
// TODO: Replace with generated type once switch schema is added to the OpenAPI spec bundle
export type SwitchConfig = { cases: Array<{ label: string }> }

// ✅ GOOD — use the best type available now, track the follow-up in an issue
/** Switch step configuration. Uses inline type until the OpenAPI spec includes the switch schema (#XXXXX). */
export type SwitchConfig = { cases: Array<{ label: string }> }
```

**Why:**

- TODOs in code are invisible to sprint planning and backlog grooming
- They accumulate silently and never get addressed
- They signal incomplete work shipping to production
- They make it unclear whether the PR is actually done

**What to do instead:**

1. If the work is needed before the PR can ship, do it now
2. If the work is a genuine follow-up, create an issue and reference it in a brief inline comment (e.g., `// Inline type until #12345 adds generated schema`)
3. If the work is aspirational ("it would be nice to..."), do not add a comment at all

---

## 33. Documentation Links -- `useDocLink` Hook

**Never hardcode documentation URLs.** Use the `useDocLink` hook to resolve documentation links. Community builds open the shared repo README for every key; extended builds resolve per-key product URLs when configured.

### Architecture

The doc link system has five parts:

1. **`frontend/packages/syntara-ui/src/utils/docs/docsUrls.json`** -- flat map of logical doc keys to **path fragments** (one string per key). Adding a new page means adding a new entry here.
2. **`frontend/packages/syntara-ui/src/utils/docs/docsConfig.json`** -- community homepage URL + docs `version` used when substituting `{version}` in product bases.
3. **`frontend/packages/syntara-ui/src/utils/docs/loadDocsConfig.ts`** -- build-time merge via `import.meta.glob` of optional `docsConfig.overlay.json` / `docsUrls.overlay.json` (gitignored; injected only on extended builds).
4. **`frontend/packages/syntara-ui/src/utils/docs/types.ts`** -- `DocKey` type is derived from `keyof typeof docsUrls`, so TypeScript rejects any key not in the JSON at compile time.
5. **`frontend/packages/syntara-ui/src/utils/docs/DocLinkProvider.tsx` + `useDocLink.ts`** -- React context (wired in `App.tsx`) reads `VITE_EXTENDED` for community vs extended mode, then `resolveDocUrl` builds the final URL.

### Usage

```typescript
import { useDocLink } from '../../utils/docs/useDocLink'

function WorkflowsPage() {
  const docLink = useDocLink('workflows')  // type-safe DocKey
  return <NxPageHeader title="Workflows" docLink={docLink} />
}
```

`NxPageHeader` renders the `docLink` as an external link icon next to the page title.

For the workflow builder's node editor panel, pass `docLink` as a prop to `NodeEditorLayout`, which enables its "Documentation" button (previously disabled with "Coming soon").

The sidebar help icon (`AppDockedNav`) uses the `home` key. In community mode that is the same README URL as every other key; in extended mode it resolves to the configured product landing page.

### Adding a New Doc Link

1. Add a flat path entry to `frontend/packages/syntara-ui/src/utils/docs/docsUrls.json`:

```json
{
  "myNewPage": "__PLACEHOLDER__/my-new-page"
}
```

2. Use it in your component -- the `DocKey` type updates automatically from the JSON:

```typescript
const docLink = useDocLink('myNewPage')
```

3. Pass it to `NxPageHeader`:

```typescript
<NxPageHeader title="My New Page" docLink={docLink} />
```

### Community vs extended

Controlled by **`VITE_EXTENDED`** (`true` / `1` = extended; unset = community). Do not use `VITE_DOC_MODE` or `VITE_APP_MODE` — they are ignored.

| Build | Help link |
|-------|-----------|
| Community | Always community README for every key |
| Extended | Per-key product URL when configured, otherwise community README |

### Rules

1. **Never hardcode doc URLs** -- always use `useDocLink(key)` so links follow community vs extended resolution
2. **Every page with `NxPageHeader` should have a `docLink`** -- pass the hook result to the `docLink` prop
3. **`DocKey` is enforced by TypeScript** -- passing a string not in `docsUrls.json` is a compile error
4. **Keep paths as obvious placeholders until real URLs exist** -- use `__PLACEHOLDER__/...` (not subtle strings that could look real)

---

## 34. Use `<Link>` for Navigation, `<Button>` for Actions

**For in-app route changes, always use `<Link>` from the router.** Never use `<Button onClick={() => navigate(...)}>` or `<a href="...">`. A raw `<a>` with `href` bypasses the router and causes a full page reload.

```typescript
// ❌ BAD — button with programmatic navigation
<Button variant="link" onClick={() => navigate(`/users/${user.id}`)}>
  {user.name}
</Button>

// ❌ BAD — raw anchor bypasses the router, causes full page reload
<a href={`/users/${user.id}`}>{user.name}</a>

// ✅ GOOD — router Link, supports middle-click and client-side navigation
<Link to={`/users/${user.id}`}>{user.name}</Link>

// ✅ GOOD — button is correct when the action is NOT navigation
<Button onClick={() => openDeleteDialog(user)}>Delete user</Button>
```

### Decision Rule

| What happens when clicked?                        | Use                             |
| ------------------------------------------------- | ------------------------------- |
| In-app route change                               | `<Link>` (router component)     |
| In-page state change (modal, toggle, form submit) | `<Button>`                      |
| Downloads a file                                  | `<a>` with `download` attribute |

### Common Violations

- **Table name columns** that navigate to detail pages -- use `LinkCell` or `<Link>`
- **Empty-state CTAs** like "Go to settings" -- use `<Link>` if it navigates
- **Breadcrumb-like buttons** that go "back" to a list -- use `<Link>`
- **Card titles** that open a detail view -- use `<Link>`

---

## 35. Unique `aria-label` on Repeated Interactive Elements

When interactive elements (checkboxes, buttons, toggles) repeat inside a list or table, each instance **must** have a unique accessible name. Without this, screen reader users cannot distinguish between rows -- "Select row" repeated 20 times is unusable.

**Reference:** [WCAG 2.1 SC 4.1.2 Name, Role, Value](https://www.w3.org/WAI/WCAG21/Understanding/name-role-value.html), [PatternFly selectable table](https://www.patternfly.org/components/table/#selectable-radio-input)

```typescript
// ❌ BAD — every row has the same label
<Checkbox aria-label="Select row" />

// ❌ BAD — hardcoded index breaks a11y tree
<Td select={{ rowIndex: 0, onSelect, isSelected }} />

// ✅ GOOD — unique label per row
<Checkbox aria-label={`Select row ${rowIndex}`} />

// ✅ GOOD — descriptive label with resource name
<Checkbox aria-label={`Select ${credential.name}`} />

// ✅ GOOD — PF table with correct rowIndex
<Td select={{ rowIndex, onSelect, isSelected }} />
```

### Where This Applies

| Element                    | Pattern                                                                         |
| -------------------------- | ------------------------------------------------------------------------------- |
| Table row checkboxes       | `aria-label={`Select row ${rowIndex}`}` or `aria-label={`Select ${item.name}`}` |
| Table row radio buttons    | `aria-label={`Choose ${item.name}`}`                                            |
| Kebab/action menus per row | `aria-label={`Actions for ${item.name}`}`                                       |
| Toggle switches per row    | `aria-label={`Enable ${item.name}`}`                                            |
| Expand/collapse per row    | Handled by PF `<Td expand>` automatically                                       |

**Note:** This complements §27 (which says don't put `aria-label` on non-interactive elements like `<span>`). This section says: when you DO use `aria-label` on interactive elements in a list, make each one unique.

---

## 36. Invalid and Not-Found States Must Use `NxEmptyState*` Components

When a detail page receives an invalid ID or the resource is not found (404), render a structured `NxEmptyState*` component (`NxEmptyStateNoData`, `NxEmptyStateFilter`, `NxEmptyStateServiceUnavailable`, or `NxEmptyState` for generic cases) -- never raw text or a bare paragraph. This ensures visual consistency, accessible heading hierarchy, and a clear recovery path.

**Reference:** [PatternFly Empty State](https://www.patternfly.org/components/empty-state), [Nielsen Norman: Error Messages](https://www.nngroup.com/articles/error-message-guidelines/)

```typescript
// ❌ BAD — raw text, no structure, no recovery path
if (!isValidId) {
  return <PageShell title="Error">Invalid identity provider ID.</PageShell>
}

// ❌ BAD — custom paragraph, inconsistent with sibling pages
if (isNotFound) {
  return (
    <PageShell title="Not found">
      <p>The provider was not found. Go back to the list.</p>
    </PageShell>
  )
}

// ✅ GOOD — structured empty state with icon, heading, and recovery
if (!isValidId) {
  return (
    <PageShell title={pageTitle} breadcrumbs={breadcrumbs}>
      <NxEmptyState headingLevel="h2" titleText="Invalid identity provider" icon={RhUiSearchIcon} isFullHeight>
        The identity provider ID in the URL is not valid.
      </NxEmptyState>
    </PageShell>
  )
}

// ✅ GOOD — not found with navigation back to list
if (isNotFound) {
  return (
    <PageShell title={pageTitle} breadcrumbs={breadcrumbs}>
      <NxEmptyStateNoData
        headingLevel="h2"
        titleText="Identity provider not found"
        isFullHeight
      >
        The identity provider may have been deleted.{' '}
        <Link to="/system-administration/authentication">Return to Authentication</Link>.
      </NxEmptyStateNoData>
    </PageShell>
  )
}
```

### When to Use Which Component

| Scenario                          | Component                              | Icon             |
| --------------------------------- | -------------------------------------- | ---------------- |
| Invalid ID format (bad URL param) | `NxEmptyState`                         | `RhUiSearchIcon` |
| Resource not found (404 from API) | `NxEmptyStateNoData` or `NxEmptyState` | `SearchIcon`     |
| No permission to view             | `NxEmptyState` with `status="danger"`  | `LockIcon`       |

### Consistency Rule

Look at sibling pages in the same route directory. If `IdentityProviderDetail.tsx` uses `<NxEmptyState>` for its not-found state, the new `EditGroupMapping.tsx` in the same directory must match that pattern -- not introduce raw text.

## 37. Browser Tab Titles -- `toPageTitle`

Every top-level page component (default export with an `<NxPage>` render) must include `<title>` as the first child of `<NxPage>`. React 19 hoists it to `<head>` automatically — no third-party library needed.

```tsx
import { toPageTitle } from '../../utils/toPageTitle'

export default function Workflows() {
  return (
    <NxPage>
      <title>{toPageTitle(['Workflows'])}</title>
      <NxPageHeader title="Workflows" ... />
    </NxPage>
  )
}
```

- **Static pages**: pass a string literal — `toPageTitle(['Credentials'])`
- **Dynamic pages**: pass the entity name — `toPageTitle([integration.name])` (falls back gracefully if undefined/null)
- **Loading/error states**: use a static fallback — `toPageTitle(['Integration'])`
- **Multi-segment pages**: `toPageTitle(['admin', 'Users'])` → `admin | Users | Nexus`

## 38. React 19 Ref Patterns — No `forwardRef`; Prefer Ref Cleanup Functions

React 19 passes `ref` as a regular prop. Prefer the patterns below for all new and migrated code. See the [React 19 release notes](https://react.dev/blog/2024/12/05/react-19#ref-as-a-prop) and [cleanup functions for refs](https://react.dev/blog/2024/12/05/react-19#cleanup-functions-for-refs).

### Ref as a prop (do not use `forwardRef`)

```tsx
// ❌ BAD — React 19 makes forwardRef unnecessary
export const NxPanel = forwardRef<HTMLDivElement, NxPanelProps>(function NxPanel(props, ref) {
  return <Panel ref={ref} {...props} />
})

// ✅ GOOD — accept ref as a regular prop
export function NxPanel({ ref, ...props }: NxPanelProps & { ref?: Ref<HTMLDivElement> }) {
  return <Panel ref={ref} {...props} />
}
```

For imperative handles, keep `useImperativeHandle` and still take `ref` as a prop (see `ExpandableCodeEditor`).

### Ref callback cleanup functions

When attaching DOM listeners or observers to a mounted element, return a cleanup from the ref callback instead of pairing `useRef` + `useEffect`:

```tsx
// ❌ BAD — paired useRef + useEffect for element lifecycle
const scrollRef = useRef<HTMLDivElement>(null)
useEffect(() => {
  const el = scrollRef.current
  if (!el) return
  el.addEventListener('scroll', onScroll, { passive: true })
  return () => el.removeEventListener('scroll', onScroll)
}, [])

// ✅ GOOD — React 19 calls the returned cleanup when the node unmounts
const scrollRef = useCallback((node: HTMLElement | null) => {
  if (!node) return
  node.addEventListener('scroll', onScroll, { passive: true })
  return () => {
    node.removeEventListener('scroll', onScroll)
  }
}, [])
```

Wrap callback refs that return cleanups in `useCallback`. A new function identity each render makes React run the previous cleanup and re-attach listeners even when the DOM node is unchanged.

`useScrollOverflow` is the reference implementation for multi-node setup with stable ref cleanups.

## 39. React 19 Context — Prefer `use(Context)` Over `useContext`

React 19's [`use`](https://react.dev/reference/react/use) reads context (and other reactive values). Prefer `use(Context)` over `useContext(Context)` for all new and migrated code.

```tsx
// ❌ BAD — legacy useContext
import { useContext } from 'react'
const value = useContext(AlertContext)

// ✅ GOOD — React 19 use()
import { use } from 'react'
const value = use(AlertContext)
```

`use(Context)` is the standard for reading React context in this codebase. Keep using domain hooks that wrap it (`useAlerts`, `useBrand`, `useDocLink`, etc.) — migrate the implementation inside those hooks, not every call site that already goes through a hook.

## 40. React 19 Optimistic UI — `useOptimistic` for Async Mutations

When a mutation has a clear before/after UI (toggles, counters, list membership), prefer React 19 [`useOptimistic`](https://react.dev/reference/react/useOptimistic) so the UI updates immediately and rolls back if the Action fails.

```tsx
import { startTransition, useOptimistic } from 'react'

const [optimisticItems, setOptimisticItems] = useOptimistic(items, (current, update: EnabledUpdate) =>
  current.map((item) => (item.id === update.id ? { ...item, enabled: update.enabled } : item))
)

function setEnabled(item: Item, enabled: boolean) {
  startTransition(async () => {
    setOptimisticItems({ id: item.id, enabled })
    try {
      await mutateAsync({ body: { enabled } })
      await refetch()
    } catch (error) {
      showError(error) // base `items` unchanged → UI rolls back when the Action ends
    }
  })
}
```

Rules of thumb:

- Call the optimistic setter **inside** a `startTransition` / Action (or an Action prop). Outside an Action, React warns and the optimistic flash is unreliable.
- Prefer `mutateAsync` + `await` so the Action stays pending until the server round-trip finishes.
- Await refetch (or otherwise converge server state) **before** the Action ends on success, so the UI does not snap back to stale query data.
- Keep confirmation dialogs for destructive toggles (e.g. credential disable) — apply the optimistic update on confirm, not when opening the dialog.
- Skip `useOptimistic` when the success path is entangled with conflict handling, dirty client stores, or multi-step workflows (e.g. workflow publish).

Reference implementation: `useOptimisticCredentialEnabled` (credentials list enable/disable).
