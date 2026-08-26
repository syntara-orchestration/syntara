# ESLint Plugin Syntara

Custom ESLint rules for the Syntara UI project to enforce project-specific patterns and best practices.

## Rules

### `no-raw-http-calls`

Disallows raw HTTP usage in UI source code: references to the global `fetch` and `XMLHttpRequest` instantiation. All API communication must go through typed API clients to maintain UI-API parity.

`axios` is blocked at the import boundary via `no-restricted-imports` (error level) in `eslint.config.js`.

Non-`RhUi` icon imports from `@patternfly/react-icons` are also flagged via `no-restricted-imports` (warn level) as part of the icon migration — existing legacy imports are being phased out incrementally.

For `fetch`, the rule flags any reference to the global identifier (direct calls, aliasing, passing as a callback). Property access such as `window.fetch` is allowed.

#### Rationale

The UI codebase uses typed `openapi-fetch` clients that are automatically generated from OpenAPI specifications. These clients provide:

- Full TypeScript type safety for requests and responses
- Automatic validation of request/response shapes
- Guarantee that UI code only calls documented API endpoints
- UI-API parity enforcement by design

Raw HTTP calls bypass all these guarantees and can:

- Hit undocumented or internal endpoints
- Break the UI-API parity contract
- Introduce type safety violations
- Make API changes harder to track

Aliasing patterns such as `const f = fetch; f(url)` are flagged so they cannot bypass a call-site-only check.

#### Usage

**Invalid:**

```typescript
// Raw fetch call
const response = await fetch('/api/workflows')

// Aliasing fetch
const f = fetch
await f('/api/workflows')

// axios import (blocked by no-restricted-imports)
import axios from 'axios'

// Raw XMLHttpRequest
const xhr = new XMLHttpRequest()
xhr.open('GET', '/api/data')
```

**Valid:**

```typescript
// Use typed API clients
import { workflowClient, credentialsClient } from '../client'

const { data } = workflowClient.useQuery('get', '/workflows')
const creds = await credentialsClient.GET('/credentials/{id}', { params: { path: { id } } })

// Named import from a package (not the global fetch)
import { fetch as customFetch } from 'cross-fetch'

// Property access to fetch (e.g. mocks, polyfills)
const fn = window.fetch
```

#### Exceptions

**Config-level allowlist** — preferred for standing legitimate exceptions (coding standards §28):

```javascript
// eslint.config.js
'syntara/no-raw-http-calls': [
  'error',
  {
    allowedFiles: ['**/useFileUploadWithProgress.ts'],
  },
],
```

Used for `useFileUploadWithProgress.ts`, where `XMLHttpRequest` is required for upload progress events (the fetch API does not support upload progress).

**Inline disable with justification** — for one-off pre-auth calls and similar cases:

```typescript
// eslint-disable-next-line syntara/no-raw-http-calls -- pre-auth: fetching providers before token middleware is available
const response = await fetch('/api/auth/providers')
```

Disables without a `-- reason` suffix fail lint.

### `prefer-confirmation-dialog`

Flags raw Modal compositions that appear to be destructive confirmation dialogs. Use `<NxConfirmationDialog>` for consistent UX.

### `prefer-pf-list-components`

Enforces use of PatternFly list components (`<List>`, `<DataList>`) over plain HTML lists.

### `prefer-pf-text-components`

Enforces use of PatternFly text components (`<Text>`, `<Title>`, etc.) over plain HTML text elements.

### `use-design-tokens-not-hardcoded`

Disallows hardcoded color/spacing values. Use PatternFly design tokens instead.

### `no-locale-date-format`

Disallows browser-locale date formatting methods (`toLocaleDateString`, `toLocaleString`, `toLocaleTimeString`) called directly in components, and restricts importing PatternFly's `Timestamp` component to the canonical wrapper components. This keeps every rendered date/time on the same `dateFormat`/`timeFormat` config instead of each call site hand-rolling its own.

Use `DateCell` (table cells / detail fields), `UserTimestamp` (username + date), or `ExecutionTimestamp` (execution start/end ranges) — all in `src/components/table/` — instead of importing `Timestamp` from `@patternfly/react-core` directly. For the handful of plain-string contexts where JSX can't be used (dropdown option labels, `TextInput value=`), use `formatDateTime`/`formatExpirationDate` from `src/utils/dateUtils.ts`.

**Config-level allowlist** — the canonical wrapper components and `dateUtils.ts` itself are exempted via `allowedFiles`:

```javascript
// eslint.config.js
'syntara/no-locale-date-format': [
  'error',
  {
    allowedFiles: [
      '**/utils/dateUtils.ts',
      '**/components/table/DateCell.tsx',
      '**/components/table/ExecutionTimestamp.tsx',
      '**/components/table/UserTimestamp.tsx',
    ],
  },
],
```

### `no-nested-component-definitions`

Disallows React component definitions inside other functions or components (Sonar S6478). Nested components are re-created on every render, causing React to unmount and remount the entire subtree. Move the component to module scope and pass data as props.

Test files and test utility directories are exempt — wrapper components defined in tests are idiomatic.

### `no-hardcoded-doc-urls`

Disallows hardcoded documentation URLs in project code. Use `useDocLink('key')` from `src/utils/docs/useDocLink.ts` and add new keys to `docsUrls.json` when needed.

Exempt: `docsUrls.json`, `useDocLink.ts`, and `*.test.*` / `*.spec.*` files.

## Testing

Run the test suite:

```bash
npx vitest run packages/syntara-ui/eslint-plugin-syntara/__tests__/
```

Run tests for a specific rule:

```bash
npx vitest run eslint-plugin-syntara/__tests__/no-raw-http-calls.test.js
```

### `require-page-title`

Requires every top-level page component (files with a default export) to render a `<title>` JSX element for browser tab titles.

#### Rationale

React 19 natively hoists `<title>` elements to `<head>`, so no third-party library (e.g. `react-helmet`) is needed. By rendering `<title>` in each page component, the browser tab always reflects the current page, improving navigation clarity and accessibility.

#### Usage

```tsx
import { toPageTitle } from '../../utils/toPageTitle'

export default function Workflows() {
  return (
    <SynPage>
      <title>{toPageTitle(['Workflows'])}</title>
      <SynPageHeader title="Workflows" ... />
    </SynPage>
  )
}
```

#### Invalid

```tsx
// ✗ Missing <title> — tab will show the previous page's title on navigation
export default function Workflows() {
  return (
    <SynPage>
      <SynPageHeader title="Workflows" />
    </SynPage>
  )
}
```

The rule only fires on files with a `default export` (i.e. page components) and is scoped via `eslint.config.js` to the explicit list of route-level page files. Sub-components and test files are not checked.

## Contributing

When adding a new rule:

1. Create the rule file in `rules/` (e.g., `rules/my-new-rule.js`)
2. Export it from `index.js`
3. Add it to the ESLint config in `eslint.config.js`
4. Create a test file in `__tests__/` (e.g., `__tests__/my-new-rule.test.js`)
5. Document it in this README
