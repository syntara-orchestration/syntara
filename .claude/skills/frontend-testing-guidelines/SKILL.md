---
description: "Frontend testing standards — Vitest, Testing Library, vitest-axe, coverage requirements, accessibility testing."
user-invocable: false
---

# Testing Guidelines

Comprehensive testing standards for this project. Referenced from frontend/AGENTS.md.

---

## Core Principle: Test Behavior, Not Implementation

Write tests that verify **what** your code does, not **how** it does it. Tests should survive refactoring.

---

## Coverage Requirements

**CI (blocks merge):** merged Vitest coverage must meet **85% statements**. That is
`nyc check-coverage --statements 85` in `packages/syntara-ui/scripts/merge-coverage.js`,
run by the `(Frontend) Coverage Report` required check. It is a **global** gate on
merged shards, not a per-file gate.

There is **no** `scripts/check-pr-coverage.js`. Vitest has **no** coverage
thresholds in config. SonarCloud coverage is informational (not a required check).

**Authoring target:** aim for ~80% statements/branches/functions/lines on **new**
files so the global 85% does not regress. Utilities 90%+. Existing files can
improve gradually.

Run locally from `frontend/packages/syntara-ui`:

```bash
npm run test:coverage        # Generate coverage report
```

**Critical: files never imported are silently excluded from coverage reports**

Without an explicit `include` glob, modules that are never imported in any test won't appear in coverage output at all — making overall numbers look better than they are:

```typescript
// vitest.config.ts — include all source so unused files appear in reports.
// This repo does not set Vitest coverage.thresholds; CI uses nyc 85% statements.
coverage: {
  provider: 'v8',
  include: ['src/**/*.{ts,tsx}'],           // required — include all source files
  exclude: ['src/**/*.stories.tsx', 'src/**/*.d.ts'],
}
```

**TypeScript strips bare `istanbul ignore` comments — use `@preserve`:**

```typescript
// ❌ Stripped by esbuild before coverage instrumentation sees it
/* istanbul ignore next */
/* v8 ignore next */

// ✅ Survives the TypeScript → JS transform
/* istanbul ignore next -- @preserve */
/* v8 ignore next -- @preserve */
/* v8 ignore start -- @preserve */
/* v8 ignore stop -- @preserve */
```

---

## AAA Pattern (Arrange-Act-Assert)

Structure every test with three phases:

```typescript
it('increments counter when button clicked', async () => {
  // Arrange - Set up test data and render
  const user = userEvent.setup()
  render(<Counter initialValue={0} />)

  // Act - Perform the action
  await user.click(screen.getByRole('button', { name: 'Increment' }))

  // Assert - Verify the outcome
  expect(screen.getByText('Count: 1')).toBeInTheDocument()
})
```

---

## Test Modes: jsdom vs Playwright E2E

### Default (jsdom) — Fast, Lightweight for Most Tests

- File naming: `*.test.ts` or `*.test.tsx`
- Use for: Component rendering, user interactions, form validation, hooks, utilities
- Environment: Simulated DOM via jsdom

**Example — jsdom test (use for most cases):**

```typescript
// File: Counter.test.tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test } from 'vitest'
import { Counter } from './Counter'

test('increments count on button click', async () => {
  const user = userEvent.setup()
  render(<Counter />)

  await user.click(screen.getByRole('button', { name: /increment/i }))

  expect(screen.getByText('Count: 1')).toBeInTheDocument()
})
```

### Playwright E2E — Full Workflow Tests in Real Browser

- File naming: `*.spec.ts` under `frontend/packages/syntara-ui/e2e`
- Use for: End-to-end user flows, routing, and integration testing
- Environment: Playwright + Chromium (mock API by default, real backend supported)
- Commands:
  - `npm run e2e` - Run headless
  - `npm run e2e:ui` - Run with Playwright UI
- **Default:** Playwright starts mock API (port 3300) + UI (port 4173)
- **Real backend:** Set `SYNTARA_E2E_SKIP_WEB_SERVER=1` and run UI separately against backend

**When to use Playwright E2E:**

- Multi-step workflows that cross routes or screens
- Integration with mock API or real backend flows
- Validating full user journeys (create, edit, save, delete)
- Smoke tests for critical paths before releases

**Example — Playwright E2E (use for multi-step workflows):**

```ts
// File: packages/syntara-ui/e2e/workflows.spec.ts
import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName } from './helpers/workflows'

test('user creates a workflow', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-test')

  try {
    await app.goto(toAppUrl('/workflows'))
    await app.getByRole('button', { name: 'Create workflow' }).click()
    await app.getByPlaceholder('Workflow name').fill(workflowName)
    await app.getByRole('button', { name: 'Save' }).click()
    await expect(app.getByText('Workflow created successfully')).toBeVisible()
  } finally {
    // Cleanup — delete created resources (especially when testing against real backend)
    // ... cleanup logic
  }
})
```

**Important:** When running against the real backend, always clean up created resources (they persist in a real database). See the [Playwright E2E skill](../frontend-playwright-e2e/SKILL.md) for both mock API and real backend setup.

**For comprehensive E2E guidance:** See [`.claude/skills/frontend-playwright-e2e/SKILL.md`](../frontend-playwright-e2e/SKILL.md)

### Why the Distinction Matters

- jsdom/happy-dom **simulate** browser behavior in Node.js and can miss cross-page issues
- E2E runs in a **real browser** with routing, network, and storage in place
- Trade-off: E2E is slower but validates full user journeys

### Decision Tree

```text
Does the component use browser-specific APIs?
├─ Yes → Use Playwright E2E (packages/syntara-ui/e2e/*.spec.ts)
│  └─ Examples: IntersectionObserver, ResizeObserver, Canvas, real layout
└─ No → Use jsdom (*.test.tsx)
   └─ Examples: Rendering, clicks, state, forms, most user interactions
```

**Default to jsdom** unless you specifically need browser APIs — it's much faster.

### Shift-Left E2E Testing (Test Tagging for PR Checks)

Use Playwright's `@pr-check` tag to mark critical E2E tests that should run on every PR, while the full suite runs on devel and in downstream pipelines.

**Tag syntax:**

```typescript
// Single test tagging
test('user can log in @pr-check', async ({ page }) => {
  await page.goto('/login')
  await page.fill('[name="username"]', 'admin')
  await page.fill('[name="password"]', 'password')
  await page.click('button[type="submit"]')
  await expect(page).toHaveURL('/dashboard')
})

// Describe block tagging (all tests inherit the tag)
test.describe('Workflow CRUD @pr-check', () => {
  test('create minimal workflow', async ({ page }) => {
    await page.goto('/workflows/new')
    await page.fill('[name="name"]', 'Test Workflow')
    await page.click('button[type="submit"]')
    await expect(page.locator('.success-message')).toBeVisible()
  })
})

// No tag - runs in full suite only
test('complex workflow validation', async ({ page }) => {
  // Runs in full suite, not in PR checks
})
```

**Running tagged tests:**

```bash
cd packages/syntara-ui

# Run only PR check tests (critical subset)
npm run e2e:pr-check

# Run tests excluding PR checks (for validation)
npm run e2e:exclude-pr-check

# Direct Playwright commands
npx playwright test --grep @pr-check          # Filter by tag
npx playwright test --grep-invert @pr-check   # Exclude tag
npx playwright test --grep @pr-check --list   # List tagged tests
```

**Selection guidelines** — mark tests with `@pr-check` if they:

✅ **Execute meaningful code paths that serve as "canary" tests**

- Detect early when something is broken (deployment config, API changes, routing)
- Cover core user journeys end-to-end
- Validate critical infrastructure (auth, API connectivity, error handling)

✅ **Critical user workflows**

- Login/logout
- Core CRUD operations (workflows, credentials, executions)
- Main navigation paths

✅ **Security-critical paths**

- Authentication flows
- Authorization checks
- Session management
- Token revocation

❌ **Exclude from PR checks:**

- Variations of the same test
- Edge case scenarios
- Tests requiring extensive setup
- Slow or flaky tests

**Note on execution time:** While faster tests are preferred for better CI feedback, the primary criterion is coverage of critical paths that catch deployment issues early. Choose tests based on what they validate, not solely on speed.

**Troubleshooting:**

```bash
# List what tests would run
npx playwright test --grep @pr-check --list

# Search for tagged tests
grep -r "@pr-check" packages/syntara-ui/e2e/

# Verify npm scripts
cat packages/syntara-ui/package.json | grep e2e:pr-check
```

**References:**

- [Playwright Documentation - Tags](https://playwright.dev/docs/test-annotations#tag-tests)

---

## What to Test

| Type          | Focus On                                                | Coverage Target |
| ------------- | ------------------------------------------------------- | --------------- |
| **Component** | User interactions, conditional rendering, accessibility | 80%+            |
| **Hook**      | Return values, state transitions, callback invocations  | 80%+            |
| **Store**     | Actions modify state correctly, edge cases              | 80%+            |
| **Utility**   | Input → output transformations, boundary conditions     | 90%+            |

## What NOT to Test

- Implementation details (internal state, private methods)
- Third-party library behavior
- Static content that doesn't change
- Generated files (`**/*.d.ts`, `**/mockData`, API contracts)

---

## Testing Rules (Mandatory)

### 1. Use Accessible Queries

Follow Testing Library query priority:

1. `getByRole` — queries accessible roles (best for buttons, headings, links)
2. `getByLabelText` — queries form elements by their label
3. `getByPlaceholderText` — queries by placeholder text
4. `getByText` — queries by visible text content
5. `getByTestId` — last resort when no accessible query works

```typescript
// ✅ GOOD: Accessible queries verify real user experience
screen.getByRole('switch', { name: 'Enabled' })
screen.getByRole('button', { name: 'Submit' })
screen.getByLabelText('Email address')
screen.getByRole('heading', { name: /welcome/i })
screen.getByRole('status') // or screen.getByText(/loading/i)
screen.getByRole('alert') // for error states
```

Rules with many pre-existing violations are set to `warn` (not `error`) to allow gradual migration. **New test code must produce zero warnings** -- these rules will be promoted to `error` once existing violations are cleaned up. See [.claude/skills/frontend-coding-standards/SKILL.md section 8 -- Zero New Warnings Policy](../frontend-coding-standards/SKILL.md).

**Async queries: use `findBy*` instead of `waitFor + getBy*`**

`findBy*` is the async equivalent of `getBy*` — it retries until the element appears and gives better error messages:

```typescript
// ❌ Redundant — waitFor wrapping getBy* is what findBy* already does
const button = await waitFor(() => screen.getByRole('button', { name: 'Save' }))

// ✅ Correct — findBy* handles the wait internally with better error output
const button = await screen.findByRole('button', { name: 'Save' })
await userEvent.click(button)
```

Also: use `query*` **only** for asserting absence. Using `query*` when the element should exist produces poor error messages:

```typescript
// ❌ Poor error message when element is missing
expect(screen.queryByRole('alert')).toBeInTheDocument()

// ✅ Clear failure message
expect(screen.getByRole('alert')).toBeInTheDocument()

// ✅ query* is correct only for asserting absence
expect(screen.queryByRole('alert')).not.toBeInTheDocument()
```

**Scope assertions with `within()`:** When asserting on elements inside a specific container (dialog footer, form group, select dropdown), use `within()` to scope queries. This prevents false positives from matching elements elsewhere on the page.

```typescript
// ❌ BAD: Could match buttons from any part of the page
const buttons = screen.getAllByRole('button')

// ✅ GOOD: Scoped to the dialog footer
const footer = within(dialog).getByRole('contentinfo')
const buttons = within(footer).getAllByRole('button')
expect(buttons[0]).toHaveTextContent('Save')
expect(buttons[1]).toHaveTextContent('Cancel')

// ✅ GOOD: Scoped to a specific select
const projectSelect = screen.getByLabelText('Credential project')
expect(within(projectSelect).getByRole('option', { name: 'Project Alpha' })).toBeInTheDocument()
```

### 2. Every New Component Must Have a `vitest-axe` Test

Include at least one `toHaveNoViolations()` test. Test multiple states for thorough coverage.

```typescript
import { axe } from 'vitest-axe'

it('has no accessibility violations', async () => {
  const { container } = render(<MyComponent />, { wrapper })
  const results = await axe(container)
  expect(results).toHaveNoViolations()
})
```

**When to add axe assertions:**

- Every new component should include at least one `toHaveNoViolations()` test
- Test multiple states (default, with actions, error states) for thorough coverage
- For expandable components (tables, panels), test the **expanded state** separately
- axe tests are async -- always `await axe(container)`

```typescript
// ✅ Test both default and expanded states
it('has no accessibility violations when rows are expanded', async () => {
  const user = userEvent.setup()
  const { container } = render(<MyTable />, { wrapper })
  await user.click(screen.getByRole('button', { name: /expand all/i }))
  expect(await axe(container)).toHaveNoViolations()
})
```

**Important**: vitest-axe requires `jsdom` as the test environment — `happy-dom` has a known bug that causes axe to silently pass even when violations exist. See the full explanation in the Accessibility Testing section below.

### 3. Every New Custom Hook Must Have a Dedicated Test File

New reusable hooks (`use*.ts`) must have a corresponding `use*.test.ts(x)` file — not just indirect coverage from a component test. Hook tests should cover:

- Return values and state transitions
- Callback invocations and side effects
- Edge cases (empty data, error states, loading states)

```typescript
// ❌ BAD — hook only tested indirectly through a component
// No useDebouncedValue.test.ts exists

// ✅ GOOD — dedicated hook test
import { renderHook, act } from '@testing-library/react'
import { useDebouncedValue } from './useDebouncedValue'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

it('returns debounced value after delay', async () => {
  const { result, rerender } = renderHook(({ value }) => useDebouncedValue(value, 300), {
    initialProps: { value: 'hello' },
  })

  rerender({ value: 'world' })
  expect(result.current).toBe('hello') // not yet debounced

  await act(() => vi.advanceTimersByTime(300))
  expect(result.current).toBe('world') // debounced
})
```

This ensures the hook file itself is measured (not only indirect coverage from a component test) and prevents regressions when the consuming component changes.

### 4. Unnecessary `useEffect` in Hooks

The ESLint plugin `eslint-plugin-react-you-might-not-need-an-effect` (configured at `warn` level) catches most unnecessary `useEffect` patterns automatically. See [.claude/skills/frontend-coding-standards/SKILL.md §23](../frontend-coding-standards/SKILL.md) for details.

### 5. Isolate the Field Under Test in Validation Tests

When testing that a specific field shows a required validation error, fill in all _other_ required fields first. Otherwise the assertion may pass today but break if field validation order changes.

```typescript
// ❌ BAD — only fills name, leaves other fields empty; assertion depends on validation order
await user.type(screen.getByLabelText('Name'), 'Test')
await user.click(screen.getByRole('button', { name: 'Create' }))
await screen.findByText('Project is required')

// ✅ GOOD — fills all required fields except the one under test
await user.type(screen.getByLabelText('Name'), 'Test')
await user.selectOptions(screen.getByLabelText('Type'), 'type-1')
// intentionally skip project
await user.click(screen.getByRole('button', { name: 'Create' }))
await screen.findByText('Project is required')
```

### 6. Assert Element Absence Explicitly

When verifying that a UI element is hidden in a certain state, assert its absence explicitly with `queryByRole` / `queryByText`. Do not assume its absence is implied by other assertions.

```typescript
// ❌ BAD — only asserts the empty state is visible, doesn't verify the header button is gone
expect(screen.getByText('No credentials')).toBeInTheDocument()

// ✅ GOOD — explicitly asserts the create button is absent in empty state
expect(screen.getByText('No credentials')).toBeInTheDocument()
expect(screen.queryByRole('button', { name: 'Create credential' })).not.toBeInTheDocument()
```

### 7. Typed Mock Functions

Use generic type parameters on `vi.fn()` instead of double-casting (`vi.fn() as unknown as Type`). This keeps type safety without losing readability.

```typescript
// ❌ BAD — double cast, loses type safety
const setError = vi.fn() as unknown as UseFormSetError<FormData>

// ✅ GOOD — typed mock function
const setError = vi.fn<UseFormSetError<FormData>>()
```

### 8. Test Names Must Be Accurate, Unique, and Current

- **No duplicate test names** within the same describe block -- `vitest` may silently skip or overwrite one. **Enforced by ESLint:** `vitest/no-identical-title` (error).
- **No misleading names** -- if a test is called "verifies icon rotation" but only checks the icon renders, rename it to match what it actually asserts
- **Update names when behavior changes** -- when the implementation changes (e.g., from inference-based to backend-driven status), update test names to reflect the new behavior source

### 9. Extract Shared Test Data

When the same test data object appears in 3+ test cases within a describe block, extract it to a shared function or constant at the top of the block. This prevents copy-paste drift and reduces maintenance burden.

```typescript
// ❌ BAD — same object duplicated in 5 tests
it('test A', () => { const workflow = { name: 'test', input_schema: {...} } })
it('test B', () => { const workflow = { name: 'test', input_schema: {...} } })

// ✅ GOOD — shared builder at describe scope
function buildTestWorkflow(overrides = {}) {
  return { name: 'test', input_schema: { type: 'object' }, ...overrides }
}
it('test A', () => { const workflow = buildTestWorkflow() })
it('test B', () => { const workflow = buildTestWorkflow({ name: 'custom' }) })
```

### 10. Negative Assertions Must Be Meaningful

Do not assert that something is absent when the test setup never could have created it. Such assertions pass vacuously and provide no regression safety.

```typescript
// ❌ BAD — test data has no globe icon, so this always passes regardless of the fix
expect(screen.queryByTestId('globe-icon')).not.toBeInTheDocument()

// ✅ GOOD — test data explicitly creates the condition, then asserts the fix works
render(<ProviderIcon idpType="custom" />)
expect(screen.queryByTestId('globe-icon')).not.toBeInTheDocument()
```

### 11. Guard Against Tests That Silently Never Assert

When a test exercises an async code path (Promise, callback, conditional), assertions may never run — the test passes vacuously. Add a guard at the top:

```typescript
it('calls error handler on rejection', async () => {
  expect.hasAssertions() // fails if zero assertions fire

  await doThing().catch(err => {
    expect(err.message).toMatch(/network error/i)
  })
})

// Or when you know the exact count:
it('validates three required fields', async () => {
  expect.assertions(3)
  // ... 3 assertions must fire or the test fails
})
```

### 12. Use `toStrictEqual` When `undefined` Keys Matter

`toEqual` ignores `undefined` properties; `toStrictEqual` treats them as significant. Use `toStrictEqual` for API response shapes and data objects where presence/absence of a key is meaningful:

```typescript
// Passes with toEqual — may mask a missing field bug
expect({ a: undefined, b: 2 }).toEqual({ b: 2 })

// Fails with toStrictEqual — correctly catches the extra undefined key
expect({ a: undefined, b: 2 }).toStrictEqual({ b: 2 }) // ❌

// Practical use: asserting an API response shape
expect(workflowResponse).toStrictEqual({
  id: expect.any(String),
  name: 'My Workflow',
  description: undefined, // field must be explicitly absent
})
```

### 13. Avoid Three `waitFor` Anti-Patterns

```typescript
// ❌ Anti-pattern 1: Empty callback — next assertion runs at the wrong time
await waitFor(() => {})
expect(window.fetch).toHaveBeenCalledWith('/api') // race condition

// ✅ Correct: assertion belongs inside waitFor
await waitFor(() => expect(window.fetch).toHaveBeenCalledWith('/api'))


// ❌ Anti-pattern 2: Side effects inside waitFor — callback runs multiple times on retry
await waitFor(() => {
  fireEvent.keyDown(input, { key: 'ArrowDown' }) // fires multiple times!
  expect(screen.getAllByRole('option')).toHaveLength(3)
})

// ✅ Correct: side effect outside, assertion inside
fireEvent.keyDown(input, { key: 'ArrowDown' })
await waitFor(() => expect(screen.getAllByRole('option')).toHaveLength(3))


// ❌ Anti-pattern 3: Multiple assertions in one waitFor — hides which one failed
// and waits the full timeout before reporting
await waitFor(() => {
  expect(window.fetch).toHaveBeenCalledWith('/api')
  expect(window.fetch).toHaveBeenCalledTimes(1)
})

// ✅ Correct: only the async assertion inside; synchronous ones follow
await waitFor(() => expect(window.fetch).toHaveBeenCalledWith('/api'))
expect(window.fetch).toHaveBeenCalledTimes(1)
```

### 14. `vi.mock` Is Hoisted — Avoid Referencing Outer Variables in the Factory

Vitest hoists `vi.mock()` calls to the top of the file before any other code runs. Variables declared above `vi.mock()` are `undefined` when the factory executes:

```typescript
// ❌ WRONG — myMock is undefined when the factory runs
const myMock = vi.fn()
vi.mock('./api', () => ({ fetchWorkflows: myMock }))

// ✅ CORRECT option 1 — use vi.hoisted() to create refs before hoisting
const { myMock } = vi.hoisted(() => ({ myMock: vi.fn() }))
vi.mock('./api', () => ({ fetchWorkflows: myMock }))

// ✅ CORRECT option 2 — partial mock, preserving real exports
vi.mock('./api', async (importOriginal) => {
  const mod = await importOriginal<typeof import('./api')>()
  return { ...mod, fetchWorkflows: vi.fn() }
})
```

**Also: mocks do not auto-reset between tests.** Add `clearMocks: true` to `vitest.config.ts` to prevent cross-test contamination from stale `mockReturnValue` calls:

```typescript
// vitest.config.ts
export default defineConfig({
  test: {
    clearMocks: true,    // clears mock.calls and mock.results between tests
    unstubGlobals: true, // restores vi.stubGlobal() stubs between tests
    unstubEnvs: true,    // restores vi.stubEnv() stubs between tests
  },
})
```

---

## Browser Tab Title Tests

Use `expectPageTitle` from `src/test/pageTitle.ts` — takes the same segments array as `toPageTitle`:

```typescript
import { expectPageTitle } from '../../test/pageTitle'

it('sets the browser tab title', () => {
  render(<Workflows />, { wrapper })
  expectPageTitle(['Workflows'])
})
```

At least one unit test per page component should call `expectPageTitle`. For pages with distinct loading/error states, assert those too:

```typescript
it('shows a fallback title while loading', () => {
  render(<BuilderEdit />) // isLoading = true in mock
  expectPageTitle(['Loading workflow', 'Workflows'])
})
```

**E2E:** Static page titles are covered by `e2e/page-titles.spec.ts`. Add `expect(page).toHaveTitle(...)` to feature specs that already navigate to a page as part of their setup.

## Permission Gating Tests

### Unit test mocking pattern

When mocking `useCanI`, always include all three fields — `allowed`, `isChecking`, and `isError`:

```typescript
vi.mock('../../hooks/useCanI', () => ({
  useCanI: vi.fn(() => ({ allowed: true, isChecking: false, isError: false })),
}))

// Per-test override
vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })
```

When a component uses a domain hook (e.g. `useWorkflowPermissions`, `useUserPermissions`), mock the domain hook instead of `useCanI`:

```typescript
const { mockPermissions } = vi.hoisted(() => ({
  mockPermissions: { canCreate: true, canUpdate: true, canDelete: true, tooltips: { ... } },
}))
vi.mock('../useWorkflowPermissions', () => ({
  useWorkflowPermissions: () => mockPermissions,
}))

// Per-test override
mockPermissions.canCreate = false
```

### Testing disabled-with-tooltip actions

```typescript
const button = screen.getByRole('button', { name: /Create/i })
expect(button).toHaveAttribute('aria-disabled', 'true')

// For kebab menu items
const menuItem = screen.getByRole('menuitem', { name: /Edit/i })
expect(menuItem).toHaveAttribute('aria-disabled', 'true')
```

### Testing page-level access denied

```typescript
vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })
render(<ProtectedPage />)
expect(screen.getByRole('heading', { name: /Access denied/i })).toBeInTheDocument()
```

### E2E permission testing

Use role-specific fixtures from `e2e/fixtures.ts`:

- `app` — admin (all permissions)
- `viewerApp` — viewer (read-only on workflows/credentials/executions/approvals)
- `auditorApp` — auditor (all reads, no writes)
- `userApp` — user (limited reads, no writes)

For builder read-only tests, create workflows via `apiRequest` (API-based setup) rather than through the UI to keep tests focused on permission gating.

When testing pages that call `useCanI` (which queries the mock API asynchronously), use `mockCanIAllowed(app)` from `e2e/utils/mockData.ts` to intercept the `can_i` endpoint and avoid race conditions where actions render as disabled before the permission check resolves.

---

## Zod Schema Testing

Test Zod schemas as pure functions — independently from forms and API handlers. A schema test has no DOM, no render, no network: just input → output or input → error.

### `safeParse` vs `parse`

Use `safeParse` for invalid-input tests — no try/catch needed:

```typescript
// ✅ Use safeParse for asserting on errors
const result = cronTriggerSchema.safeParse({ scheduleType: 'cron', cron: '' })
expect(result.success).toBe(false)
if (!result.success) {
  expect(result.error.issues[0].path).toEqual(['cron'])
  expect(result.error.issues[0].message).toMatch(/invalid/i)
}

// ✅ Use parse (or safeParse) for asserting valid input
const valid = cronTriggerSchema.safeParse({ scheduleType: 'cron', cron: '0 9 * * 1-5' })
expect(valid.success).toBe(true)
```

Always assert `.path` alongside `.message` — the same message can appear on different fields.

### What to Test Per Schema

Test each rule in isolation. Do not pass multiple invalid fields at once — it masks which rule triggered:

```typescript
describe('workflowSchema', () => {
  it('accepts a valid workflow', () => {
    expect(workflowSchema.safeParse(validWorkflow).success).toBe(true)
  })

  it('rejects missing name', () => {
    const result = workflowSchema.safeParse({ ...validWorkflow, name: undefined })
    expect(result.success).toBe(false)
    expect(result.error!.issues[0].path).toEqual(['name'])
  })

  it('rejects empty name', () => {
    const result = workflowSchema.safeParse({ ...validWorkflow, name: '' })
    expect(result.success).toBe(false)
    expect(result.error!.issues[0].path).toEqual(['name'])
  })
})
```

### Boundary Values: `undefined` vs `null` vs Empty String

Zod treats these differently — test all three when a field could legitimately be any of them:

```typescript
// .optional() allows undefined but NOT null
// .nullable() allows null but NOT undefined
// .min(1) rejects empty string but allows whitespace — consider .trim()

it('distinguishes null from undefined', () => {
  expect(schema.safeParse({ field: undefined }).success).toBe(true)  // .optional()
  expect(schema.safeParse({ field: null }).success).toBe(false)      // not .nullable()
  expect(schema.safeParse({ field: '' }).success).toBe(false)        // .min(1)
})
```

### Testing `.refine()` and `.superRefine()`

Test both the passing and failing branch:

```typescript
describe('cron expression refinement', () => {
  it('passes for valid 5-field cron', () => {
    expect(schema.safeParse({ cron: '0 9 * * 1-5' }).success).toBe(true)
  })

  it('fails for 3-field cron', () => {
    const result = schema.safeParse({ cron: '* * *' })
    expect(result.success).toBe(false)
    expect(result.error!.issues[0].message).toMatch(/invalid cron/i)
  })
})
```

### Testing `.transform()`

Test input type and output type separately using `z.input<>` and `z.output<>`:

```typescript
type SchemaInput = z.input<typeof mySchema>    // pre-transform shape
type SchemaOutput = z.output<typeof mySchema>  // post-transform shape

it('transforms string to Date', () => {
  const result = dateSchema.safeParse('2026-06-23')
  expect(result.success).toBe(true)
  expect(result.data).toBeInstanceOf(Date)
})
```

### Fixture Drift Detection

Prevent mock data from silently diverging from the schema as the schema evolves:

```typescript
import { mockWorkflows } from '../mocks/mockData'

it.each(mockWorkflows)('mock fixture #%# conforms to workflowSchema', (fixture) => {
  expect(() => workflowSchema.parse(fixture)).not.toThrow()
})
```

### Async Schemas

If a schema uses `.refine(async fn)`, you must use `safeParseAsync()`. Calling `safeParse()` on an async schema throws synchronously — it does not skip the refinement silently:

```typescript
it('rejects non-unique names', async () => {
  const result = await asyncWorkflowSchema.safeParseAsync({ name: 'existing-name' })
  expect(result.success).toBe(false)
})
```

### Using `expect.schemaMatching` in Assertions

Vitest supports inline schema validation via `expect.schemaMatching`:

```typescript
// Assert a Zod schema inline without a separate test
expect(apiResponse).toEqual({
  id: expect.any(String),
  email: expect.schemaMatching(z.string().email()),
  createdAt: expect.schemaMatching(z.string().datetime()),
})
```

---

## Quick Reference

- **Components**: `render()`, `screen`, `userEvent` from Testing Library
- **Hooks**: `renderHook()` and wrap state changes in `act()`
- **Stores**: Reset state in `beforeEach`, test via `getState()` and actions
- **Mocking**: `vi.fn()` for callbacks, `vi.mock()` for modules

---

## Accessibility Testing — Three Levels

### Level 1: Lint-Time (eslint-plugin-testing-library)

`eslint-plugin-testing-library` is configured for all test files and enforces Testing Library best practices. Prefer accessible queries in priority order (see Rule #2 above). Rules with many pre-existing violations are set to `warn` (not `error`) to allow gradual migration. **New test code must produce zero warnings** -- these rules will be promoted to `error` once existing violations are cleaned up.

### Level 2: Unit Tests (vitest-axe)

The `toHaveNoViolations()` matcher is globally available via test setup.

- Every new component needs at least one axe test
- Test multiple states (default, error, loading)
- axe tests are async — always `await axe(container)`

### Level 3: E2E Tests (@axe-core/playwright)

`@axe-core/playwright` runs axe-core scans in real browser E2E tests. Tests live in `e2e/accessibility.spec.ts`.

```typescript
import AxeBuilder from '@axe-core/playwright'
import { type Page } from '@playwright/test'
import { test, expect, toAppUrl } from './fixtures'

const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] as const

async function expectNoA11yViolations(page: Page) {
  const results = await new AxeBuilder({ page }).withTags([...WCAG_TAGS]).analyze()
  expect(results.violations).toEqual([])
}

test('page has no a11y violations', async ({ app }) => {
  await app.goto(toAppUrl('/workflows'))
  await expect(app.getByRole('heading', { name: /workflows/i })).toBeVisible()

  await expectNoA11yViolations(app)
})
```

**Running accessibility E2E tests:**

```bash
npm run e2e                          # All E2E tests including accessibility
npm run e2e -- accessibility.spec.ts # Only accessibility tests
npm run e2e:ui                       # With Playwright UI for debugging
```

**Critical: `vitest-axe` does not work with `happy-dom`**

`happy-dom` has a known bug in its `Node.prototype.isConnected` implementation that breaks axe-core. Tests run silently with no violations even when violations exist. Always use `jsdom` as the Vitest environment for files that include axe tests:

```typescript
// vitest.config.ts
test: {
  environment: 'jsdom', // required for vitest-axe — happy-dom silently breaks axe
}

// Or per-file override at the top of the test file:
// @vitest-environment jsdom
```

**axe-core catches approximately 30% of real WCAG violations**

Automated scans are a floor, not a ceiling. The following require manual testing beyond vitest-axe and @axe-core/playwright:

| Check | vitest-axe (jsdom) | @axe-core/playwright | Manual required |
|---|---|---|---|
| ARIA roles and labels | ✅ | ✅ | — |
| Color contrast | ❌ (jsdom has no CSS) | ✅ | Supplement |
| Focus management (modals) | ❌ | Partial | ✅ |
| Keyboard navigation flow | ❌ | ❌ | ✅ |
| Screen reader announcement quality | ❌ | ❌ | ✅ |
| Dynamic/hidden content (post-interaction) | Only if pre-rendered | ✅ | — |
| Touch targets, WCAG 2.5.x | ❌ | ❌ | ✅ |

**Also inspect `results.incomplete`** — axe flags these as "needs manual review":

```typescript
const results = await axe(container)
expect(results).toHaveNoViolations()
// Optionally review ambiguous findings:
if (results.incomplete.length > 0) {
  console.warn('axe incomplete checks (need manual review):', results.incomplete.map(r => r.id))
}
```

**Suppress known jsdom false positives with `configureAxe`:**

```typescript
import { configureAxe } from 'vitest-axe'

// color-contrast always passes in jsdom (no CSS) — test it via Playwright instead
const axe = configureAxe({
  rules: { 'color-contrast': { enabled: false } },
})
```

---

## Industry Best Practices for Test Coverage

### Bare minimum (authoring target, ~80% on new files)

- **Happy path**: Test the most common user flow
- **Error cases**: Test at least one error scenario
- **Edge cases**: Test boundary conditions (empty, null, max values)
- **User interactions**: Test all clickable elements and form inputs

**Example — Button Component:**

```typescript
describe('Button', () => {
  it('renders with label', () => {
    /* ... */
  }) // Happy path
  it('calls onClick when clicked', () => {
    /* ... */
  }) // Interaction
  it('renders as disabled when disabled prop', () => {}) // Edge case
  it('shows loading state', () => {
    /* ... */
  }) // State variation
})
```

### Why aim for ~80% on new files?

- Industry standard (Google, Airbnb, Netflix use 80-90%)
- Catches most bugs without diminishing returns
- Balances thoroughness with development velocity
- Forces testing of critical paths without testing getters/setters

---

## Keep Mock Handlers in Sync with Contract Types

When a contract field is renamed, added, or removed, **update `packages/syntara-mock-api/src/handlers.ts` in the same PR.** Stale handler keys are silently ignored by browsers — the mock never exercises the new code path, so developers cannot trigger or test the behavior locally.

```typescript
// ❌ BAD: contract switched from warnings: string[] → warning?: string | null
// but the mock still returns the old shape — the warning toast is untestable
return HttpResponse.json({ ...workflow, warnings: [] })

// ✅ GOOD: keep the mock in sync with the new contract field
return HttpResponse.json({ ...workflow, warning: null })
```

**PR checklist item:** Any PR that renames or removes a response field must include a corresponding mock handler update. TypeScript won't catch this automatically because `HttpResponse.json()` is untyped — it's a manual discipline.
