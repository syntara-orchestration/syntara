---
description: "Playwright E2E testing guide — fixtures, patterns, test structure, and best practices for the frontend."
user-invocable: false
---

# Claude Skill: Playwright E2E Testing

Your goal is to author comprehensive, production-grade end-to-end tests using Playwright that follow the project's established patterns and cover critical user workflows.

---

## Quick Reference

### Existing Test Infrastructure

| Component     | Location                                     |
| ------------- | -------------------------------------------- |
| Config        | `frontend/packages/syntara-ui/playwright.config.ts`     |
| Test files    | `frontend/packages/syntara-ui/e2e/*.spec.ts`            |
| Fixtures      | `frontend/packages/syntara-ui/e2e/fixtures.ts`          |
| Helpers       | `frontend/packages/syntara-ui/e2e/helpers/workflows.ts` |
| Utils (API)   | `frontend/packages/syntara-ui/e2e/utils/api.ts`         |
| Utils (Mocks) | `frontend/packages/syntara-ui/e2e/utils/mockData.ts`    |

### Key Conventions (extracted from existing tests)

- **Imports:** `test, expect, toAppUrl`, and `type Page` from `'./fixtures'` (NOT `'@playwright/test'`) — the fixtures module re-exports all Playwright primitives; importing directly bypasses project conventions and is caught by ESLint
- **Fixture:** `{ app }` (NOT `{ page }`) — pre-navigated to base URL with nav visible
- **Navigation:** `toAppUrl('/path')` helper for all URLs
- **Unique names:** `buildUniqueName(prefix)` for all test data
- **Locators:** `getByRole` > `getByLabel` > `getByPlaceholder` > `getByText` > `getByTestId`
- **Helpers:** `createBasicWorkflow`, `addNodePanel` (opens **Add step** UI), `fillCodeEditor`, `closeNodeEditorPanel`

### Commands

```bash
npm run e2e        # Run headless (default: mock API + UI auto-started)
npm run e2e:ui     # Run with Playwright UI for debugging
```

---

## Test Suite Tags

The E2E suite uses Playwright tags to control which tests run in different environments. Tags appear in two forms:

```typescript
// Describe-level tag — applies to all tests in the block
test.describe('Integration filtering', { tag: '@pr-check' }, () => { ... })

// Individual test tag — applies to one test
test('my test', { tag: ['@konflux-skip'] }, async ({ app }) => { ... })
```

| Tag | What it marks | Runs in | Excluded from | Mechanism |
|---|---|---|---|---|
| `@pr-check` | Fast, reliable describe blocks covering the most critical user paths — intended as a quick PR gate subset | All CI environments (full suite always runs; `--grep @pr-check` selects this subset locally) | _(no current CI filter — tag exists for manual use and future CI optimization)_ | `--grep @pr-check` |
| `@konflux-skip` | Tests confirmed flaky in Konflux's specific execution environment (not flaky in GitHub Actions) | GitHub Actions `test-compose-e2e` job (runs normally) | Konflux `ao-ui-tests` Tekton pipelines | `.tekton/automation-orchestrator-ui-tests-*.yaml` passes `playwright-grep-invert: '@konflux-skip'` → `--grep-invert` |
| `@local-only` | Visual regression screenshot tests (`e2e/visual-regression/`) | Local development via `npm run e2e:visual-regression` | All CI | `playwright.config.ts` `testIgnore: **/visual-regression/**` + in-test `test.skip(!!process.env.CI)` |

### Tag rules

- **`@pr-check`** — Tag a `test.describe` when the tests inside are fast (under ~30 s total), reliable (no flaky backend dependencies), and cover the most critical user paths. Do NOT tag slow, data-dependent, or flaky describe blocks.
- **`@konflux-skip`** — Use only for a test confirmed flaky in Konflux's environment specifically. This is a last resort — fix the root cause first. Each tagged test must have a comment explaining the environment-specific cause. Discuss with the team before tagging additional tests.
- **`@local-only`** — Reserved for visual regression tests. Do not apply to functional tests.

### Never commit `test.fixme` as a long-term state

`test.fixme` marks a test as expected-to-fail, which shows up in CI reports as a "known failure" rather than a clean skip. It is appropriate only as a same-PR placeholder (a test whose fix is in the next commit). For environment-specific skipping use `@konflux-skip`; for data-dependent conditional skipping use `test.skip(!condition, 'reason')`.

---

## Prerequisites

### Default Mode (Mock API)

The Playwright config auto-starts both the mock API (port 3300) and UI (port 4173). No extra setup:

```bash
npm run e2e
```

Override ports if needed:

```bash
SYNTARA_E2E_PORT=5174 SYNTARA_E2E_API_PORT=3301 npm run e2e
```

**How the runner works:** `npm run e2e` executes `e2e/run-e2e.ts` via `tsx`, which probes for free ports (preferring 4173 / 3300, falling back to OS-assigned ports) and passes them to Playwright as `SYNTARA_E2E_PORT`, `SYNTARA_E2E_API_PORT`, and `SYNTARA_E2E_BASE_URL`. This means stale processes on the default ports are never silently reused — Playwright always starts fresh servers on confirmed-free ports.

If you bypass the runner (e.g. `SYNTARA_E2E_SKIP_WEB_SERVER=1`) and manage servers manually, make sure they are configured with `VITE_API_URL=http://localhost:<apiPort>` or API calls will return 404.

### Real Backend Mode

To test against the real Syntara backend instead of the mock API:

1. **Start the real backend** (see backend repo README):

   ```bash
   cd ../syntara
   # Follow backend setup instructions — runs on http://localhost:8000
   ```

2. **Start the UI** pointing to the real backend:

   ```bash
   VITE_API_URL=http://localhost:8000 npm run start:ui
   ```

3. **Run E2E tests** with web server auto-start disabled:

   ```bash
   SYNTARA_E2E_SKIP_WEB_SERVER=1 \
     SYNTARA_E2E_BASE_URL=http://localhost:5173 \
     npm run e2e
   ```

**Important:** When running against a real backend, test isolation and cleanup are critical — tests operate on a shared persistent database. The patterns in this skill (unique names, try-finally cleanup) ensure tests work reliably in both modes.

**Note on data-dependent tests:** Some tests (integration-filtering, approvals, pagination) require seed data that the mock API provides. Against a fresh real backend these tests skip automatically via `test.skip()` guards. Tests that CREATE their own data (builder, workflows, integrations) work in both modes.

---

## When to Use E2E vs Unit/Component Tests

| Use E2E (Playwright) when…                        | Use Unit/Component (Vitest) when…            |
| ------------------------------------------------- | -------------------------------------------- |
| Multi-step workflows crossing routes              | Testing a single component's rendering/logic |
| Builder interactions (drag, connect steps)        | Form validation rules                        |
| Verifying URL-based filter state / shareable URLs | Custom hook behavior                         |
| Testing real API persistence (real backend mode)  | Utility function input → output              |
| Accessibility scans across full pages             | Component accessibility (`vitest-axe`)       |

**Default to Vitest** unless you specifically need cross-route flows or full browser behavior — it's much faster.

---

## Phase 0 — Learn from Existing Tests

**Before writing ANY new tests, study the established conventions.**

### Step 1: Read existing test files

Read all files in `frontend/packages/syntara-ui/e2e/`:

- `fixtures.ts` — custom `{ app }` fixture definition and `toAppUrl` helper
- `helpers/workflows.ts` — `buildUniqueName`, `createBasicWorkflow`, `addNodePanel` (Add step panel), `fillCodeEditor`, `closeNodeEditorPanel`
- All `*.spec.ts` files — naming conventions, structure, assertion style, cleanup patterns

### Step 2: Extract conventions

From the existing tests, note:

- **File naming:** `feature-name.spec.ts` (kebab-case)
- **Test titles:** Descriptive, user-action-based ("user creates and saves a multi-step workflow")
- **Scoping:** Some files use `test.describe()` blocks (accessibility, filtering), others use top-level tests
- **Conditional skipping:** `test.skip(!condition, 'reason')` for data-dependent tests
- **Multi-tab testing:** Some tests use `{ app, context }` to test URL sharing across tabs

**CRITICAL:** New tests MUST match existing style. A reviewer should not be able to distinguish new tests from existing ones.

---

## Phase 0.5 — Use MCP Tools to Explore the App

**Before writing test code, use the available MCP servers to see the real application.**

This project ships with two MCP servers configured in `.mcp.json` that give you direct browser access. Use them to ground your tests in reality — discover real locators, verify page structure, and confirm user flows before writing a single line of test code.

### Available MCP Tools

| MCP Server          | What it does                                                                                          |
| ------------------- | ----------------------------------------------------------------------------------------------------- |
| **Playwright MCP**  | Navigate pages, take accessibility snapshots, click elements, fill forms — a real browser you control |
| **Chrome DevTools** | Inspect DOM structure, monitor network requests, read console output, evaluate JavaScript in the page |

### Workflow: Explore → Snapshot → Write

1. **Start the dev server** if not already running (`npm run start:ui`)
2. **Navigate to the page** you're writing tests for using `browser_navigate`
3. **Take an accessibility snapshot** (`browser_snapshot`) — this returns the page's accessibility tree, showing every role, name, and label. Use this to pick the right `getByRole`, `getByLabel`, and `getByText` locators
4. **Interact with the UI** — click buttons, fill forms, open menus using `browser_click` and `browser_type` to discover the exact flow a user follows
5. **Verify locators** — if unsure about a locator, snapshot after each interaction to see how the accessibility tree changes
6. **Write the test** using the real roles and names you observed, not guesses

### Example: Discovering Locators via Snapshot

Instead of guessing that a button is called "Save":

```
1. browser_navigate → http://localhost:5173/workflows/new
2. browser_snapshot → reveals: button[name="Save workflow"]
3. Write test:  await app.getByRole('button', { name: 'Save workflow' }).click()
```

### When to Use Each MCP

| Situation                                    | Use             |
| -------------------------------------------- | --------------- |
| Discovering locators for a new page          | Playwright MCP  |
| Verifying a multi-step user flow             | Playwright MCP  |
| Checking network requests/responses          | Chrome DevTools |
| Debugging why a locator doesn't match        | Playwright MCP  |
| Inspecting console errors on a page          | Chrome DevTools |
| Verifying CSS/layout before screenshot tests | Chrome DevTools |

### Important Notes

- **Snapshot over screenshot** — prefer `browser_snapshot` (accessibility tree) over `browser_take_screenshot` (image) for finding locators. The snapshot gives you exact roles and names
- **Don't skip this step** — writing tests without seeing the real page leads to wrong locator names, missed elements, and flaky tests
- **Use for debugging too** — when a test fails, navigate to the failing state with the MCP and snapshot to see what the page actually looks like

---

## Phase 1 — Understand the Application

**Do NOT start writing tests until you understand what you're testing.**

### Key information to gather

1. **Routes:** Read `frontend/packages/syntara-ui/src/app/AppRoute.tsx` and `frontend/packages/syntara-ui/src/app/navigationItems.tsx`
2. **Features:** Workflows, Builder, Executions, Credentials, Integrations, Approvals
3. **Critical paths:**
   - Create workflow → Add steps → Save → Execute → View results
   - Workflow builder (complex UI state management)
   - CRUD operations on all resource types
4. **Edge cases:** Empty states, validation errors, loading states, boundary conditions

### Document at the top of each test file

```typescript
/**
 * E2E Tests: [Feature Name]
 *
 * Critical paths covered:
 * - [List the key user workflows tested]
 *
 * Edge cases:
 * - [List boundary conditions and error scenarios]
 */
```

---

## Phase 2 — Test Authoring Rules

### Test Isolation — CRITICAL

Tests run with `fullyParallel: true` and must be completely independent.

#### Golden Rules

1. **NEVER hardcode resource names** — Always use `buildUniqueName(prefix)`

   ```typescript
   // ❌ BAD: Conflicts in parallel execution
   const workflowName = 'test-workflow'

   // ✅ GOOD: Unique per test run
   const workflowName = buildUniqueName('e2e-workflow')
   ```

2. **Each test creates its own data** — Never assume resources exist

   ```typescript
   // ❌ BAD: Assumes "Default Workflow" exists
   await app.goto(toAppUrl('/workflows/default-workflow'))

   // ✅ GOOD: Create what you need
   const workflowName = buildUniqueName('e2e-test')
   await createBasicWorkflow(app, workflowName, 'Test action')
   ```

3. **NEVER assume a clean database** — The backend may have pre-existing data

   ```typescript
   // ❌ BAD: Assumes exact row count from mock seed data
   await expect(app.getByText(/20 integrations/i)).toBeVisible()
   const rows = await app.getByRole('row').count()
   expect(rows).toBeGreaterThan(1)

   // ❌ BAD: Assumes created row is visible on first page without filtering
   await createBasicWorkflow(app, workflowName, 'Test action')
   await app.goto(toAppUrl('/workflows'))
   await expect(app.getByRole('row', { name: workflowName })).toBeVisible()

   // ✅ GOOD: Filter by unique name to find your data regardless of what else exists
   await createBasicWorkflow(app, workflowName, 'Test action')
   await app.goto(toAppUrl('/workflows'))
   await app.getByPlaceholder('Filter by name').fill(workflowName)
   await app.getByRole('button', { name: 'Apply filter' }).click()
   await expect(app.getByRole('row', { name: new RegExp(workflowName) })).toBeVisible()

   // ✅ GOOD: Assert on relative changes, not absolute counts
   const firstPageText = await footer.textContent()
   await nextButton.click()
   const secondPageText = await footer.textContent()
   expect(secondPageText).not.toBe(firstPageText) // Different page, different count
   ```

   **Why:** The real backend may have data from previous test runs, manual testing, or other users. Tests that hardcode counts like "20 integrations" or assume rows are visible without filtering break when the database isn't a clean slate.

4. **Clean up in try-finally** — Cleanup must run even if test fails

   ```typescript
   const workflowName = buildUniqueName('e2e-test')
   await createBasicWorkflow(app, workflowName, 'Test action')
   try {
     // assertions and further actions
   } finally {
     // cleanup — delete via UI or API
   }
   ```

5. **No shared state between tests** — No shared variables, no test ordering dependencies

6. **Tests must work in any order** — Run alone, in full suite, or shuffled

#### Why This Matters

With `fullyParallel: true`, Playwright runs tests concurrently. If tests share names or assume specific database states, they interfere with each other and fail randomly.

#### Checklist for Every Test

- [ ] Uses `buildUniqueName()` for all created resources
- [ ] Creates all resources it needs
- [ ] Cleans up created resources (try-finally for tests that mutate data)
- [ ] No shared state with other tests
- [ ] Works when run alone: `npx playwright test --grep "test name"`

---

### Test Structure — AAA Pattern with Custom Fixtures

```typescript
import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName, createBasicWorkflow } from './helpers/workflows'

test('user creates and verifies a workflow', async ({ app }) => {
  // Arrange — app is already navigated to base URL by fixture
  const workflowName = buildUniqueName('e2e-workflow')

  // Act — create workflow
  await createBasicWorkflow(app, workflowName, 'Test action')

  // Assert — verify workflow exists in list
  await app.goto(toAppUrl('/workflows'))
  await app.getByPlaceholder('Filter by name').fill(workflowName)
  await app.getByRole('button', { name: 'Apply filter' }).click()
  await expect(app.getByRole('row', { name: new RegExp(workflowName) })).toBeVisible()
})
```

**Key patterns:**

- ✅ Import from `'./fixtures'` (NOT `'@playwright/test'`)
- ✅ Use `{ app }` fixture (NOT `{ page }`)
- ✅ Use `toAppUrl('/path')` for navigation
- ✅ Use `buildUniqueName(prefix)` for unique test data
- ✅ Use existing helpers (`createBasicWorkflow`, `addNodePanel` for the **Add step** panel, etc.)

**Asserting API calls**


```typescript
// Register the response waiter BEFORE the action that triggers it
const responsePromise = app.waitForResponse('**/api/v1/workflows')
await app.getByRole('button', { name: 'Save' }).click()
const response = await responsePromise
expect(response.status()).toBe(200)

// Also useful for asserting request payload
const requestPromise = app.waitForRequest('**/api/v1/workflows')
await app.getByRole('button', { name: 'Save' }).click()
const request = await requestPromise
expect(request.postDataJSON()).toMatchObject({ name: workflowName })
```

**Parameterized Tests**


```typescript
// Run the same test block for multiple roles using forEach + describe
// Each describe gets its own beforeEach scope
;(['admin', 'viewer', 'auditor'] as const).forEach(role => {
  test.describe(`${role}: workflow list`, () => {
    test(`sees the workflows table`, async ({ app }) => {
      await app.goto(toAppUrl('/workflows'))
      await expect(app.getByRole('grid', { name: 'Workflows table' })).toBeVisible()
    })
  })
})
```

Note: placing `beforeEach` inside the `forEach`'s `describe` block scopes it per-iteration. Placing it outside runs it globally for all iterations.

**Grouping related tests:**

```typescript
test.describe('Workflow Filtering', () => {
  test('full user flow: add filters → view results → clear filters', async ({ app }) => {
    // ...
  })

  test('filter state persists across navigation', async ({ app }) => {
    // ...
  })
})
```

**Conditional skipping** for data-dependent tests:

```typescript
const hasRunning = await runningRow
  .waitFor({ state: 'visible', timeout: 5000 })
  .then(() => true)
  .catch(() => false)
test.skip(!hasRunning, 'Mock API has no running execution; seed data required')
```

**When `test.skip()` is and is not acceptable:**

```typescript
// ✅ ACCEPTABLE — data that is impossible to create programmatically
// (e.g., an approval that must have been approved by a human via the real backend)
test.skip(!hasApprovalData, 'Requires pre-existing human-approved records')

// ❌ NOT ACCEPTABLE — if the test can create the data itself, it must do so
// Do not skip because setup is complex; use beforeAll + API helpers instead
test.skip(!hasWorkflows, 'No workflows exist') // ❌ create them via API instead
```

---

### Locators — Accessibility-First

Follow this priority:

1. **`getByRole`** — buttons, headings, links, textboxes, grids, rows
2. **`getByLabel`** — form inputs with `<label>`
3. **`getByPlaceholder`** — inputs with placeholder text
4. **`getByText`** — visible text content
5. **`getByTestId`** — last resort when no accessible query works

```typescript
// ✅ BEST: Accessible queries
await app.getByRole('button', { name: 'Save' }).click()
await app.getByLabel('Name').fill('My Workflow')
await app.getByPlaceholder('Filter by name').fill('test')
await app.getByRole('heading', { name: /workflows/i })
await app.getByRole('grid', { name: 'Workflows table' })

// ⚠️ ACCEPTABLE: When no semantic alternative exists
await app.getByTestId('workflow-builder-canvas').click()

// ❌ BAD: CSS selectors — fragile, breaks on PF version bumps
await app.locator('.pf-v6-c-button').click()

// ❌ BAD: Internal PF BEM classes in assertions — same risk applies to expect() calls
await expect(app.locator('.pf-v6-c-alert__description')).toContainText('Error')

// ✅ GOOD: Role/text-based assertion — survives PF prefix changes
await expect(app.getByRole('alert').getByText('Error')).toBeVisible()
```

The CSS-selector ban applies equally to **locators** and **assertions**. Any `.pf-v6-c-*` class can silently stop matching when PatternFly bumps its prefix in a major release.

**Scoping locators to containers:**

```typescript
// ✅ Scoped to Add step panel (helper name is addNodePanel)
const panel = addNodePanel(app)
await panel.getByRole('button', { name: 'Action', exact: true }).click()

// ✅ Scoped to a row
const row = app.getByRole('row', { name: new RegExp(workflowName) })
await row.getByRole('button', { name: /Actions|Kebab toggle/i }).click()

// ✅ Filter chips via FilterBar (`helpers/patternfly.ts`)
const nameChipGroup = filterChipGroup(app, 'Name')
await expect(nameChipGroup.getByText('workflow')).toBeVisible()

// ✅ Table header "select all" — PatternFly `Th select` sets aria-label="Select all rows"
await table.getByRole('checkbox', { name: /select all/i }).check()
```

**Use heading level to avoid strict mode violations in empty states:**

```typescript
// ❌ BAD: Matches both h1 "Integrations" and h2 "No integrations..." in empty state
await expect(app.getByRole('heading', { name: 'Integrations' })).toBeVisible()

// ✅ GOOD: Targets only the h1 page title
await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()
```

**Use exact matching to avoid ambiguity:**

```typescript
// ✅ Exact match — won't match "Add step panel" or "Add step type"
await app.getByRole('button', { name: /^Add step$/ }).click()

// ✅ Exact flag
await panel.getByRole('button', { name: 'Script', exact: true }).click()
```

---

### Web-First Assertions

Playwright assertions auto-retry until the condition is met or timeout. Always use web-first assertions:

```typescript
// ✅ GOOD: Auto-retrying assertion — waits for element
await expect(app.getByRole('heading', { name: 'Workflows' })).toBeVisible()
await expect(app).toHaveURL(/workflow-builder\/.+/)
await expect(app.getByPlaceholder('Workflow name')).toHaveValue(workflowName)

// ❌ BAD: Manual check — no retry, flaky
const heading = await app.getByRole('heading').textContent()
expect(heading).toBe('Workflows')
```

**Common web-first assertions:**

| Assertion           | Use for                         |
| ------------------- | ------------------------------- |
| `toBeVisible()`     | Element is visible on page      |
| `toHaveText()`      | Element has exact/matching text |
| `toContainText()`   | Element contains text           |
| `toHaveValue()`     | Input has value                 |
| `toHaveURL()`       | Page URL matches                |
| `toHaveCount()`     | Number of matching elements     |
| `not.toBeVisible()` | Element disappeared             |

**Additional assertions teams commonly miss**


```typescript
// Accessibility assertions — critical for a11y-focused teams
await expect(locator).toHaveAccessibleName('Submit form')
await expect(locator).toHaveAccessibleDescription('Opens a modal dialog')
await expect(locator).toHaveRole('button')

// Viewport and layout
await expect(locator).toBeInViewport()

// Multi-select
await expect(locator).toHaveValues(['option-a', 'option-b'])

// ARIA snapshot — assert full accessibility tree structure
await expect(locator).toMatchAriaSnapshot(`
  - button "Save"
  - button "Cancel"
`)

// API responses
await expect(response).toBeOK() // status in 200–299
```

**Soft assertions — collect all failures before stopping**


```typescript
// Use when you want to see all broken fields at once (e.g., form validation)
await expect.soft(app.getByRole('textbox', { name: 'Name' })).toHaveValue('')
await expect.soft(app.getByRole('alert', { name: 'Name is required' })).toBeVisible()
await expect.soft(app.getByRole('alert', { name: 'Email is required' })).toBeVisible()
// All three failures are reported; the test doesn't stop at the first
```

**`expect.poll` — retry any async value until it passes**


```typescript
// Use instead of waitForTimeout when waiting for an external condition
await expect.poll(async () => {
  const response = await app.request.get('/api/v1/workflows')
  return response.status()
}, {
  message: 'API should return 200 after processing',
  timeout: 10_000,
  intervals: [1_000, 2_000, 5_000],
}).toBe(200)
```

---

### Auto-Waiting — Let Playwright Handle It

Playwright auto-waits for elements to be actionable before performing actions. **Do not add manual waits.**

```typescript
// ❌ BAD: Manual timeout — fragile, slow
await app.waitForTimeout(2000)
await app.getByRole('button', { name: 'Save' }).click()

// ✅ GOOD: Playwright auto-waits for button to be actionable
await app.getByRole('button', { name: 'Save' }).click()

// ✅ GOOD: Wait for specific UI condition before proceeding
await expect(app.getByRole('heading', { name: 'Select a trigger step' })).toBeVisible()
```

**When you need longer timeouts** (e.g., slow backend operations):

```typescript
await expect(app.getByText(/completed/i)).toBeVisible({ timeout: 30_000 })
```

**`test.slow()` — triple the configured timeout without hardcoding milliseconds**


```typescript
// test.slow() triples the configured timeout — simpler than hardcoding ms
// Use for tests that exercise genuinely slow operations without picking a magic number
test('executes a long-running workflow', async ({ app }) => {
  test.slow()
  // now has 3× the configured test timeout
})
```

**Critical: missing `await` causes silent test passes**


Forgetting `await` on a Playwright assertion means the assertion never runs — the test passes vacuously. Enable the ESLint rule `@typescript-eslint/no-floating-promises` to catch this at write time.

```typescript
// ❌ BAD — no await; assertion is never evaluated; test always passes
expect(app.getByText('Success')).toBeVisible()

// ✅ GOOD
await expect(app.getByText('Success')).toBeVisible()
```

---

### Cleanup Pattern

When tests create resources, clean up in try-finally so cleanup runs even if assertions fail:

```typescript
test('edits a workflow name', async ({ app }) => {
  const workflowName = buildUniqueName('e2e-edit')
  await createBasicWorkflow(app, workflowName, 'Initial task')

  try {
    await app.goto(toAppUrl('/workflows'))
    await app.getByPlaceholder('Filter by name').fill(workflowName)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await app.getByRole('button', { name: workflowName, exact: true }).click()

    const updatedName = `${workflowName}-updated`
    await app.getByPlaceholder('Workflow name').fill(updatedName)
    await app.getByRole('button', { name: 'Save' }).click()

    await app.goto(toAppUrl('/workflows'))
    await app.getByPlaceholder('Filter by name').fill(updatedName)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    await expect(app.getByRole('button', { name: updatedName, exact: true })).toBeVisible()
  } finally {
    // Delete via UI kebab menu
    await app.goto(toAppUrl('/workflows'))
    const searchTerm = workflowName.slice(0, 20)
    await app.getByPlaceholder('Filter by name').fill(searchTerm)
    await app.getByRole('button', { name: 'Apply filter' }).click()
    const row = app.getByRole('row', { name: new RegExp(workflowName) })
    if ((await row.count()) > 0) {
      await row
        .getByRole('button', { name: /Actions|Kebab toggle/i })
        .first()
        .click({ force: true })
      await app.getByRole('menuitem', { name: 'Delete workflow' }).click()
      await app.getByRole('button', { name: 'Delete' }).click()
    }
  }
})
```

**Read-only tests** (filtering, viewing, accessibility scans) that don't create resources don't need cleanup.

**Prefer API-based cleanup over UI-based cleanup.** If a test fails mid-flow before the resource is saved or visible in the list, navigating back and interacting with the table to delete is unreliable — the page state is undefined. Use the API client directly in `finally`:

```typescript
// ✅ GOOD: API-based cleanup — works regardless of UI state
let workflowId: string | undefined
try {
  workflowId = await createWorkflowViaApi({ name: workflowName })
  // ... test interactions
} finally {
  if (workflowId) await deleteWorkflowViaApi(workflowId)
}

// ❌ AVOID: UI-based cleanup when the test may have failed before saving
} finally {
  await app.goto(toAppUrl('/workflows'))
  await app.getByPlaceholder('Filter by name').fill(workflowName)
  // If the test failed on step 2, the workflow may not exist in the list
}
```

API helpers are in `e2e/utils/api.ts`. Use them for setup and teardown; reserve UI interactions for the assertions under test.

---

### Data-Dependent Tests — Skip When Seed Data Is Missing

Tests that depend on pre-existing data (filtering, pagination, approvals) must gracefully skip when that data isn't available. Use `test.skip()` with a condition:

```typescript
// Skip individual tests when required data is missing
const table = app.getByRole('grid', { name: 'Approvals table' })
const hasTable = await table
  .waitFor({ state: 'visible', timeout: 5000 })
  .then(() => true)
  .catch(() => false)
test.skip(!hasTable, 'No approval data available; seed data required')
```

For test suites that all depend on the same data, use `test.beforeEach`:

```typescript
test.describe('Integration Filtering', () => {
  test.beforeEach(async ({ app }) => {
    await app.goto(toAppUrl('/configuration/integrations'))
    await expect(app.getByRole('heading', { level: 1, name: 'Integrations' })).toBeVisible()
    const table = app.getByRole('grid', { name: 'Integrations table' })
    const hasTable = await table
      .waitFor({ state: 'visible', timeout: 5000 })
      .then(() => true)
      .catch(() => false)
    test.skip(!hasTable, 'No integration data available; seed data required')
  })

  test('keyword search: filter by name', async ({ app }) => {
    // Only runs when integrations exist
  })
})
```

This ensures tests work against both mock API (with seed data) and real backend (without seed data).

---

### Existing API Utilities (`e2e/utils/`)

#### `utils/api.ts` — Authentication & Resource Helpers

Core functions: `getAuthToken()`, `apiRequest()`, `ensureProject()`. Plus CRUD helpers for credentials, groups, and identity providers (create/delete/list/find variants). Used by 20+ test files for API-based setup/teardown.

#### `utils/mockData.ts` — Route Interception & Mock Data

Helpers: `fulfill()`, `mockUser()`, `mockUserIdentities()`, `mockAuthMe()`, `mockAuthProviders()`, `mockUsersList()`, `mockUserGroups()`, `mockCanIAllowed()`. Plus mock fixtures for users, identities, providers, and audit events. Used by user identity and auth tests.

#### `utils/roleSetup.ts` — Real Backend Role Provisioning

Creates test users with specific roles (viewer, auditor, user) on a real backend. Used by the worker-scoped `roleSetup` fixture in `fixtures.ts`. Returns credentials for each role and a cleanup function. See the "Permission Gating E2E Tests" section below.

---

### Permission Gating E2E Tests

Permission gating tests validate that navigation items, action buttons, tabs, and route guards behave correctly for different user roles. They run in **dual mode**: against both the mock API and a real backend.

#### Role-specific fixtures

`fixtures.ts` exports four page fixtures:

| Fixture      | Role    | Mock API                                          | Real backend                                              |
| ------------ | ------- | ------------------------------------------------- | --------------------------------------------------------- |
| `app`        | admin   | Cookie-based auto-login                           | Login with admin credentials                              |
| `viewerApp`  | viewer  | Intercepts `/auth/refresh` → `mock-token-viewer`  | Logs in as dynamically created user with viewer policies  |
| `auditorApp` | auditor | Intercepts `/auth/refresh` → `mock-token-auditor` | Logs in as dynamically created user with auditor role     |
| `userApp`    | user    | Intercepts `/auth/refresh` → `mock-token-user`    | Logs in as dynamically created user with limited policies |

For mock API tests, `loginAsRole` intercepts the `/auth/refresh` endpoint to return a role-scoped token (`mock-token-{role}`). The mock API's `can_i` handler extracts the username from this token and returns role-appropriate permission responses.

For real backend tests, the worker-scoped `roleSetup` fixture (via `roleSetup.ts`) creates test users with appropriate roles/policies at worker startup and cleans them up on teardown.

#### Writing permission gating tests

```typescript
import { test, expect, toAppUrl } from './fixtures'

test('viewer: create button is disabled with tooltip', async ({ viewerApp }) => {
  await viewerApp.goto(toAppUrl('/workflows'))
  const createBtn = viewerApp.getByRole('button', { name: /Create workflow/i })
  await expect(createBtn).toHaveAttribute('aria-disabled', 'true')
})

test('auditor: direct URL to Create User shows access denied', async ({ auditorApp }) => {
  await auditorApp.goto(toAppUrl('/system-administration/access-management/users/create'))
  await expect(auditorApp.getByRole('heading', { name: 'Access denied', level: 2 })).toBeVisible()
})
```

#### Self-contained tests with API setup

Permission tests that validate gated actions on existing resources must create those resources via API, not assume seed data:

```typescript
test('viewer: workflow kebab actions are disabled', async ({ app, viewerApp }) => {
  const workflowId = await createTestWorkflow(app)
  try {
    await viewerApp.goto(toAppUrl('/workflows'))
    // ... assert kebab actions are aria-disabled
  } finally {
    await deleteTestWorkflow(app, workflowId)
  }
})
```

Use `app` (admin) to create resources, then `viewerApp`/`auditorApp`/`userApp` to verify gating. Always clean up in `finally`.

#### Adding tests for new permission-gated features

1. Add role-aware `can_i` responses in `frontend/packages/syntara-mock-api/src/handlers.ts` for all 4 roles
2. Add test cases in `e2e/permission-gating.spec.ts` using the appropriate role fixture
3. For route guards, test both the admin positive case and the denied case for each restricted role
4. For action buttons, verify `aria-disabled="true"` and tooltip content

---

### Resource Utility Pattern (Recommended for Real Backend)

For faster test setup/teardown when running against a real backend, create API-based resource utilities in `frontend/packages/syntara-ui/e2e/utils/`.

**Add new resource-specific helpers alongside the existing utilities:**

```typescript
// packages/syntara-ui/e2e/utils/workflows.ts
import { type Page } from '@playwright/test'
import { buildUniqueName } from '../helpers/workflows'

const apiBaseUrl = process.env.VITE_API_URL ?? 'http://localhost:3300'

export const WorkflowResource = {
  api: {
    create: async (app: Page, options: { name?: string; description?: string } = {}) => {
      const name = options.name ?? buildUniqueName('e2e-workflow')
      const response = await app.request.post(`${apiBaseUrl}/api/v1/workflows`, {
        data: {
          name,
          description: options.description ?? 'Created via API for E2E testing',
          trigger: { type: 'manual' },
          actions: [],
        },
      })
      const workflow = (await response.json()) as { id: string; name: string }
      return { id: workflow.id, name: workflow.name }
    },

    delete: async (app: Page, workflowId: string) => {
      await app.request.delete(`${apiBaseUrl}/api/v1/workflows/${workflowId}`)
    },
  },
}
```

**Usage:**

```typescript
test('user executes a workflow', async ({ app }) => {
  // Fast API-based setup
  const { id } = await WorkflowResource.api.create(app)

  try {
    // Test via UI (what users actually do)
    await app.goto(toAppUrl(`/workflows/${id}`))
    await app.getByRole('button', { name: 'Execute' }).click()
    await expect(app.getByText(/execution started/i)).toBeVisible()
  } finally {
    // Fast API-based cleanup
    await WorkflowResource.api.delete(app, id)
  }
})
```

**Benefits:** Fast setup (skips UI), reliable cleanup, test what matters (use UI for assertions, API for setup/teardown).

**Keep API paths in sync:** The paths used in resource utilities (e.g., `/api/v1/workflows`) must match the real backend OpenAPI contract. When backend endpoints change, update these helpers to match. Run `npm run gen` to regenerate contracts and verify paths against the generated types in `@syntara/contracts`.

---

### Multi-Tab Testing

Some tests verify URL shareability by opening a URL in a new tab. Use the `context` fixture:

```typescript
test('shareable URLs: filters restored from URL', async ({ app, context }) => {
  // Apply filters...
  const urlWithFilters = app.url()

  // Open in new tab (simulate sharing URL)
  const newPage = await context.newPage()
  await newPage.goto(urlWithFilters)

  // Assert filters restored
  await expect(newPage.getByRole('heading', { name: 'Workflows' })).toBeVisible()
  // ...verify filter chips

  await newPage.close()
})
```

---

### Coverage Categories

| Category             | Description                     | Example                                          |
| -------------------- | ------------------------------- | ------------------------------------------------ |
| **Happy paths**      | Primary success flows           | Create workflow → save → verify in list          |
| **Edge cases**       | Boundary conditions             | Empty list, max-length names, special characters |
| **Error states**     | Validation and backend failures | Name conflicts, required field validation        |
| **Filtering/search** | URL-based filter state          | Apply filters → share URL → verify restored      |
| **Accessibility**    | WCAG compliance                 | axe-core scans on each page                      |
| **Multi-tab**        | Shareable URLs                  | Open filtered URL in new tab                     |

### Accessibility Testing with axe-core


**Scan components after interaction (modals, flyouts, dropdowns):**

```typescript
// Hidden content is not scanned — always trigger the state first
await app.getByRole('button', { name: 'Open settings' }).click()
await app.getByRole('dialog', { name: 'Settings' }).waitFor() // wait for it to render

const results = await new AxeBuilder({ page })
  .include('[role="dialog"]')   // scope to just the opened element
  .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
  .analyze()
expect(results.violations).toEqual([])
```

**Note on axe-core limitations:** axe-core catches approximately 30% of real WCAG violations automatically. The rest — keyboard navigation flow, screen reader announcement quality, cognitive accessibility, color contrast in jsdom — requires manual testing. Automated scans are a floor, not a ceiling.

---

## Phase 3 — Execution

### Running Tests

```bash
# Default mode (mock API auto-started)
npm run e2e

# With Playwright UI (debugging)
npm run e2e:ui

# Specific test file
cd packages/syntara-ui
npx playwright test e2e/workflows.spec.ts

# Specific test by name
npx playwright test --grep "user creates"

# Headed mode (see browser)
npx playwright test --headed

# Real backend mode (see Prerequisites)
SYNTARA_E2E_SKIP_WEB_SERVER=1 SYNTARA_E2E_BASE_URL=http://localhost:5173 npx playwright test
```

### Debugging Failures

```bash
# Playwright Inspector (step through test)
npx playwright test --debug e2e/workflows.spec.ts

# View trace after failure (traces saved on failure by config)
npx playwright show-trace test-results/*/trace.zip
```

**Common issues:**

| Problem                 | Cause                               | Fix                                                    |
| ----------------------- | ----------------------------------- | ------------------------------------------------------ |
| Locator not found       | Wrong role or element doesn't exist | Use Playwright Inspector to inspect the page           |
| Timeout                 | Slow response or missing element    | Check if element actually appears; increase timeout    |
| Parallel test conflicts | Hardcoded names                     | Use `buildUniqueName()` everywhere                     |
| Cleanup failed          | Resource already deleted            | Add `.count() > 0` guard or try-catch in finally block |
| Connection refused      | Backend/mock API not running        | Check webServer config or start services manually      |

---

## Common E2E Anti-Patterns

### Use `.click()`, Never `dispatchEvent`

**Enforced by ESLint:** `no-restricted-syntax` (error) in `e2e/**/*.spec.ts`. See `eslint.config.js`.

Playwright's `.click()` simulates a real user interaction (scrolls into view, hovers, clicks center). `dispatchEvent` fires a synthetic event that bypasses all of that and can mask real interaction bugs (element obscured, not scrolled into view, etc.).

```typescript
// ❌ BAD — synthetic event, bypasses real interaction
await app.locator('#submit').dispatchEvent('click')

// ✅ GOOD — real user interaction
await app.getByRole('button', { name: 'Submit' }).click()
```

### Register Route Handlers Before Navigation

When using `page.route()` to mock API responses, register handlers **before** the action that triggers navigation. If the click triggers navigation immediately, route handlers set up after the click may not be in place in time.

```typescript
// ❌ BAD — route handlers may miss the request
await app.getByRole('button', { name: 'Login' }).click()
await app.route('**/auth/login', handler)

// ✅ GOOD — handlers ready before navigation
await app.route('**/auth/login', handler)
await app.route('**/auth/providers', handler)
await app.getByRole('button', { name: 'Login' }).click()
```

### No Try-Catch to Silently Skip Assertions

When test data is mocked deterministically, assertions should fail naturally. Wrapping assertions in try-catch and silently continuing hides bugs in mock setup.

```typescript
// ❌ BAD — silently skips if mock data is wrong
try {
  await expect(toggle).toBeEnabled()
} catch {
  test.skip(true, 'Toggle not enabled')
}

// ✅ GOOD — fails clearly if mock data is wrong
await expect(toggle).toBeEnabled()
```

### Extract Shared Mock Fixtures

When mock data objects are copy-pasted between test files, extract to a shared fixture file. This prevents drift when the data shape changes.

```typescript
// ❌ BAD — same mockUsers object in login.spec.ts and admin.spec.ts
const mockUsers = [{ id: '1', username: 'admin', ... }]

// ✅ GOOD — shared fixture
// e2e/fixtures/mock-users.ts
export const mockAdminUser = { id: '1', username: 'admin', ... }

// e2e/login.spec.ts
import { mockAdminUser } from './fixtures/mock-users'
```

### Route handlers: `page.route()` vs `browserContext.route()`


```typescript
// page.route() — intercepts requests on this page only
await page.route('**/api/**', handler)

// browserContext.route() — intercepts requests on ALL pages in this context
// including popups and child pages opened from links
await app.context().route('**/api/**', handler)
// Use this when testing flows that open new tabs or popup windows
```

### Service Worker Interference


If the project uses Mock Service Worker (MSW) or any service worker, `page.route()` handlers may silently never fire because the service worker intercepts first. Block service workers in tests that use route interception:

```typescript
// playwright.config.ts or specific test
const context = await browser.newContext({ serviceWorkers: 'block' })
```

### Modifying Real API Responses (Partial Mocking)


When you need to patch one field rather than fully mock an endpoint:

```typescript
await app.route('**/api/v1/workflows', async route => {
  const response = await route.fetch()       // fetch the real response
  const json = await response.json()
  json.items.push({ id: 'injected', name: 'Extra workflow' }) // patch
  await route.fulfill({ response, json })    // original headers preserved
})
```

### WebSocket Testing


**Observing WebSocket traffic (without blocking):**
```typescript
app.on('websocket', ws => {
  ws.on('framesent',     e => console.log('→', e.payload))
  ws.on('framereceived', e => console.log('←', e.payload))
  ws.on('close', () => console.log('WebSocket closed'))
})
```

**Mocking WebSocket responses:**
```typescript
await app.routeWebSocket('wss://example.com/ws', ws => {
  ws.onMessage(message => {
    if (message === 'ping') ws.send('pong')
  })
})
```

**Intercepting and relaying to real server:**
```typescript
await app.routeWebSocket('wss://example.com/ws', ws => {
  const server = ws.connectToServer()
  ws.onMessage(msg => server.send(msg === 'status' ? 'status-v2' : msg))
  server.onMessage(msg => ws.send(msg))
})
```

### Assertion Anti-Patterns

**Don't hardcode counts or detail strings in assertions.** Fragile strings like `/1 issue found/` break the moment a second validation fires. Assert the meaningful label instead:

```typescript
// ❌ BAD: Breaks if a second validation error appears
await expect(app.getByText(/1 issue found/)).toBeVisible()

// ✅ GOOD: Asserts what the user cares about — independent of count
await expect(app.getByRole('heading', { name: /Verification failed/i })).toBeVisible()
await expect(app.getByTestId('validation-error-badge')).toBeVisible()
```

**Don't test sequential WebSocket/async state transitions.** Tests that assert `Pending → Running → Success` in order are inherently flaky — the intermediate states may resolve faster than the assertion can fire. Test the final outcome only, or `test.skip` with a clear explanation:

```typescript
// ❌ BAD: Racing against WebSocket update timing
await expect(app.getByText('Pending')).toBeVisible()
await expect(app.getByText('Running')).toBeVisible()
await expect(app.getByText('Success')).toBeVisible()

// ✅ GOOD: Assert only the final state
await expect(app.getByText('Success')).toBeVisible()

// ✅ ACCEPTABLE: Skip when live state depends on non-deterministic timing
test.skip('live status transitions', 'depends on WebSocket update timing — not reliably testable in E2E')
```

### No `waitForLoadState('networkidle')`

`networkidle` waits for 500ms of no network activity, which is unreliable in apps with polling, WebSockets, or long-running background requests — the wait can time out or resolve before the UI is actually ready. Use a web-first assertion on the specific element or state you're waiting for instead.

```typescript
// ❌ BAD — networkidle never resolves cleanly against polling/WebSocket traffic
await app.waitForLoadState('networkidle')

// ✅ GOOD — wait for the actual UI signal
await expect(app.getByRole('heading', { name: 'Workflows' })).toBeVisible()
```

---

## Constraints

**NEVER:**

- ❌ Import from `@playwright/test` directly (use `./fixtures`)
- ❌ Use `{ page }` fixture (use `{ app }`)
- ❌ Hardcode URLs (use `toAppUrl('/path')`)
- ❌ Hardcode resource names (use `buildUniqueName()`)
- ❌ Hardcode expected counts or assume a clean database (filter to find your data)
- ❌ Assert on rows being visible without filtering first (other data may push them off-page)
- ❌ Use `test.skip()` for data the test can create programmatically — create resources via API in `beforeAll` instead (see Data-Dependent Tests for the narrow exception: data impossible to create programmatically)
- ❌ Depend on pre-existing data from the mock API or any external source
- ❌ Share state between tests
- ❌ Use `page.waitForTimeout()` -- rely on auto-waiting and web-first assertions
- ❌ Use `dispatchEvent` for clicks -- use Playwright's `.click()` which simulates real user interaction (scroll, hover, click center)
- ❌ Use `{ timeout: 5000 }` on assertions -- 5000ms is the default Playwright timeout, restating it is redundant
- ❌ Use `.first()` when only one element should match -- make the locator specific enough to match exactly one element
- ❌ Use try-catch to silently skip assertions -- when mock data is deterministic, let assertions fail naturally to surface mock setup bugs
- ❌ Use raw CSS selectors or PF BEM classes (`.pf-v6-c-button`) in locators **or assertions** -- use `getByRole`, `getByLabel`, or `getByText`
- ❌ Include `.ts` extension in imports -- follow the codebase convention of extensionless imports
- ❌ Assert on CSS classes or internal state
- ❌ Access React internals via `page.evaluate()`
- ❌ Leave test data in database when testing against real backend
- ❌ Use `waitForLoadState('networkidle')` -- unreliable with polling/WebSocket traffic; assert on the specific UI signal instead
- ❌ Assert sequential async/WebSocket state transitions (`Pending → Running → Success`) -- race-prone; assert only the final state

**ALWAYS:**

- ✅ Import `{ test, expect, toAppUrl }` and `type Page` from `'./fixtures'`
- ✅ Prefer API-based cleanup (`e2e/utils/api.ts`) over UI-based cleanup when a test may fail before the resource is visible in the UI
- ✅ Use `{ app }` fixture
- ✅ Use `buildUniqueName(prefix)` for all test data
- ✅ Each test creates ALL resources it needs (fully self-contained)
- ✅ Each test deletes ALL resources it created in a `try-finally` block
- ✅ Filter by unique name before asserting on created data (never assume visibility on first page)
- ✅ Use semantic locators (`getByRole`, `getByLabel`)
- ✅ Prefer `getByRole` over `getByText` -- PF alerts render titles as h4 (`getByRole('heading', { name: '...' })`)
- ✅ Use web-first assertions (`expect(locator).toBeVisible()`)
- ✅ Register `page.route()` handlers **before** any click that triggers navigation
- ✅ Use camelCase for variable names (`enabledToggle`, not `enabled_toggle`)
- ✅ Extract shared mock data to `e2e/fixtures/` -- do not copy-paste between test files
- ✅ Use existing helpers before writing new ones
- ✅ Follow AAA pattern (Arrange, Act, Assert)
- ✅ Match existing test style and conventions

---

## Validation Checklist

Before considering tests complete:

### Test Quality

- [ ] Tests import `test, expect, toAppUrl`, and `type Page` from `'./fixtures'` (not `'@playwright/test'`)
- [ ] Tests use `{ app }` fixture (not `{ page }`)
- [ ] Navigation uses `toAppUrl('/path')`
- [ ] Semantic locators used (minimal `getByTestId`)
- [ ] Web-first assertions used (no manual waits)
- [ ] Tests follow AAA pattern
- [ ] TypeScript compiles with zero errors

### Test Isolation

- [ ] All resource names use `buildUniqueName()`
- [ ] Each test creates its own resources
- [ ] Resources cleaned up (try-finally for mutating tests)
- [ ] No shared state between tests
- [ ] No hardcoded counts or clean-slate assumptions
- [ ] Created resources found via filter (not by assuming page position)
- [ ] Tests work alone: `npx playwright test --grep "test name"`
- [ ] Tests work in full suite: `npm run e2e`
- [ ] Duplicated cleanup/setup logic extracted into `e2e/helpers/` or `e2e/utils/` resource helpers

### Permission Gating Tests

- [ ] New permission-gated features have tests in `e2e/permission-gating.spec.ts`
- [ ] Tests use role fixtures (`viewerApp`, `auditorApp`, `userApp`) — not `app`
- [ ] Route guard tests verify `Access denied` heading for denied roles
- [ ] Action button tests verify `aria-disabled="true"` attribute
- [ ] Tests create resources via admin `app` fixture and clean up in `finally`
- [ ] Mock API `can_i` handler updated for all 4 roles in `handlers.ts`

### Verification

```bash
npm run e2e

# Run specific test alone
cd packages/syntara-ui && npx playwright test --grep "specific test"

# TypeScript compiles
npm run tsc
```

---

## Deliverables

1. **Test files** — `frontend/packages/syntara-ui/e2e/*.spec.ts`
2. **Helpers** — Reusable functions in `frontend/packages/syntara-ui/e2e/helpers/`
3. **Resource utilities** — `frontend/packages/syntara-ui/e2e/utils/` (if creating API-based setup/teardown)
4. **Coverage summary** — Brief comment documenting features, edge cases, and known gaps
5. **Visual regression** — If the PR changes any UI layout or visual appearance, check whether a visual regression snapshot exists. See [`packages/syntara-ui/VISUAL_REGRESSION.md`](../packages/syntara-ui/VISUAL_REGRESSION.md) for the page registry, baseline update workflow, and CI screenshot comparison. Run `npm run e2e:visual-regression` to verify; run with `--update-snapshots` to update baselines.
