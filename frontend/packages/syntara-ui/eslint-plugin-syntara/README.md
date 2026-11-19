# ESLint Plugin Syntara

Custom ESLint rules for Syntara UI patterns that are not covered by shared packages.

Shared checks for API paths, documentation URLs, nested component definitions, HTTP clients, and barrel files are configured from `@ansible/eslint-plugin` in `eslint.config.js`.

## Rules

### `no-fetch-aliases`

Disallows storing or passing the global `fetch` function, which would bypass the shared HTTP-client check. Direct `fetch()` calls are reported by `@ansible/no-unapproved-http-client`.

### `require-http-client-disable-reason`

Requires an explanation after `--` when suppressing `@ansible/no-unapproved-http-client`.

### `prefer-confirmation-dialog`

Flags raw Modal compositions that appear to be destructive confirmation dialogs. Use `<SynConfirmationDialog>` for consistent UX.

### `prefer-syn-select`

Flags importing `Select` from `@patternfly/react-core`. Use `<SynSelect>` so scrollable-menu defaults (`isScrollable`, `maxMenuHeight`, popper `preventOverflow`, dismiss-on-outer-scroll) stay consistent. `SelectList`, `SelectOption`, `SelectGroup`, and `MenuToggle` still come from PatternFly. The wrapper file `src/components/SynSelect.tsx` is exempt.

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

## Testing

Run the test suite:

```bash
npx vitest run packages/syntara-ui/eslint-plugin-syntara/__tests__/
```

Run a test for a Syntara-specific rule:

```bash
npx vitest run eslint-plugin-syntara/__tests__/prefer-pf-text-components.test.js
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

The rule only fires on files with a default export, including a local alias such as `export { Page as default }`, and is scoped via `eslint.config.js` to the explicit list of route-level page files. Sub-components and test files are not checked.

## Contributing

When adding a new rule:

1. Create the rule file in `rules/` (e.g., `rules/my-new-rule.js`)
2. Export it from `index.js`
3. Add it to the ESLint config in `eslint.config.js`
4. Create a test file in `__tests__/` (e.g., `__tests__/my-new-rule.test.js`)
5. Document it in this README
