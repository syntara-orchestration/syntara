# Testing Guide

## Quick Start

```bash
# Standard tests (fast, jsdom)
npm test                    # Run all tests with linting and type checking
npm run vitest              # Run tests only
npm run test:coverage       # Run tests with coverage

# Playwright E2E tests (real browser)
npm run e2e                   # Run E2E tests headless
npm run e2e:ui                # Run E2E tests with Playwright UI
```

## Coverage Requirements

**CI (blocks merge):** merged coverage must be **85% statements**
(`nyc check-coverage --statements 85` via `scripts/merge-coverage.js`). Global,
not per-file. There is no `scripts/check-pr-coverage.js`.

**Authoring target:** ~80% statements/branches/functions/lines on new files so
the global gate does not regress. Utilities 90%+.

### How It Works

1. **Write your code** - Create or modify source files in `src/`
2. **Write tests** - Aim for 80%+ coverage on new files
3. **Run coverage locally** - `npm run test:coverage`
4. **CI merges shards** - `(Frontend) Coverage Report` fails the PR below 85% statements overall

Existing code can improve gradually. Unimported files are missing from the
report unless `coverage.include` lists `src/**/*.{ts,tsx}`.

## Test File Naming

- **Standard tests**: `*.test.ts`, `*.test.tsx` (uses jsdom)
- **E2E tests**: `packages/syntara-ui/e2e/*.spec.ts`

## When to Use Playwright E2E

Use Playwright E2E when testing:

- **End-to-end flows**: Create/edit/save/delete workflows
- **Routing**: Multi-page navigation across screens
- **Integration**: Mock API or real backend behavior
- **Smoke tests**: Critical paths before releases

**Default to jsdom** for everything else - it's much faster.

**Why?** jsdom simulates browser behavior in Node.js (fast), while E2E runs in real browsers (slower but more accurate). E2E eliminates cross-page and integration gaps.

## Industry Best Practices (80% Coverage)

### What to Test

1. **Happy path** - Most common user flow
2. **Error cases** - At least one error scenario
3. **Edge cases** - Boundary conditions (empty, null, max values)
4. **User interactions** - All clickable elements and form inputs

### Example

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

### AAA Pattern

Structure all tests with:

```typescript
it('should do something', async () => {
  // Arrange - Set up test data
  const user = userEvent.setup()
  render(<Component />)

  // Act - Perform the action
  await user.click(screen.getByRole('button'))

  // Assert - Verify the outcome
  expect(screen.getByText('Result')).toBeInTheDocument()
})
```

## Coverage Targets by Type

| Type      | Coverage Target | Focus                              |
| --------- | --------------- | ---------------------------------- |
| Component | 80%+            | User interactions, rendering, a11y |
| Hook      | 80%+            | State transitions, return values   |
| Store     | 80%+            | Actions, edge cases                |
| Utility   | 90%+            | Input/output, boundary conditions  |

## What NOT to Test

- Implementation details (internal state, private methods)
- Third-party library behavior
- Static content that doesn't change
- Generated files (\*.d.ts, mockData, API contracts)

## Why 80%?

- **Industry standard**: Google, Airbnb, Netflix use 80-90%
- **Catches most bugs**: Diminishing returns beyond 80%
- **Balanced**: Thoroughness without slowing development
- **Focuses on value**: Critical paths over trivial code

## CI Integration

### CI Strategy

**Every PR:**

```bash
npm run test:coverage  # jsdom tests with coverage report
```

**E2E Tests (Selective):**
Run E2E tests only when needed:

- Multi-step user journeys
- Integration with the mock API or real backend
- Manual validation before releases

### Why Not Run Browser Tests on Every Commit?

**Performance:**

- jsdom: ~5-15 seconds
- Browser: ~30-60 seconds (Playwright overhead)

**Coverage:**

- 90%+ of tests work in jsdom
- Keep E2E focused on critical workflows
- Avoid duplicating component-level jsdom tests

### CI Workflow

See [.github/workflows/pull-request.yml](../../.github/workflows/pull-request.yml) for:

- Standard tests with coverage on every PR
- Container build validation

Coverage reports are generated in CI. View them locally with `npm run test:coverage`.

## Playwright E2E Details

### Configuration

E2E tests use Playwright config in `packages/syntara-ui/playwright.config.ts`:

- **Browser**: Chromium
- **Headless**: Yes (by default)
- **Screenshots**: On failure
- **Pattern**: `packages/syntara-ui/e2e/*.spec.ts`

### Playwright E2E Example

```typescript
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

For more examples and guidance, see:

- [Frontend testing guidelines](../../../.claude/skills/frontend-testing-guidelines/SKILL.md)
- [Comprehensive Playwright E2E Skill](../../../.claude/skills/frontend-playwright-e2e/SKILL.md)

## Visual Regression Testing

Full-page screenshots for every route, compared against committed baselines. See [`VISUAL_REGRESSION.md`](VISUAL_REGRESSION.md) for the complete guide.

```bash
# Compare screenshots against baselines
npx playwright test e2e/visual-regression/page-screenshots

# Update baselines after intentional UI changes
npx playwright test e2e/visual-regression/page-screenshots --update-snapshots

# Check all routes have baselines
npm exec tsx -- scripts/check-visual-baselines.ts
```

Key points:

- **Page registry** (`e2e/visual-regression/page-registry.ts`) lists every route to screenshot
- **Linux-only baselines** — CI (Ubuntu) is the source of truth; macOS snapshots are gitignored
- **New routes** must be added to the page registry with a baseline, or the enforcement script will fail
- **Frozen clock** — `Date.now()` is fixed for deterministic timestamps across runs

## Troubleshooting

### Coverage check fails for unmodified file

- Verify file was actually modified: `git status`
- Check if file is in `.gitignore`
- Ensure tests are running: `npm run test:coverage`

### E2E tests timeout

- Increase timeout in test: `test.setTimeout(10000)`
- Check if element selectors are correct
- Run UI mode to debug: `npm run e2e:ui`

### Coverage report missing

- Run coverage first: `npm run test:coverage`
- Check for `coverage/coverage-summary.json`
- Ensure tests actually ran

## Resources

- [Vitest Documentation](https://vitest.dev/)
- [Testing Library](https://testing-library.com/docs/react-testing-library/intro/)
- [Frontend testing guidelines](../../../.claude/skills/frontend-testing-guidelines/SKILL.md)

## Playwright Integration Tests

Playwright integration tests live in `packages/syntara-ui/e2e` and exercise full user workflows.

### Environment

Tests run against the **mock backend by default**.
The Playwright config starts:

- UI on port `4173`
- Mock API on port `3300`

Override ports:

```bash
SYNTARA_E2E_PORT=5174 SYNTARA_E2E_API_PORT=3301 npm run e2e
```

### Real Backend Mode

To test against the real backend instead of the mock API:

1. Start the real backend (see backend repo README)
2. Run tests:
   ```bash
   SYNTARA_E2E_SKIP_WEB_SERVER=1 \
     SYNTARA_E2E_BASE_URL=http://localhost:8000 \
     SYNTARA_E2E_PASSWORD=<admin-password> \
     npm run e2e
   ```

**Environment variables for real backend mode:**

| Variable                      | Required | Description                                                                                                            |
| ----------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------- |
| `SYNTARA_E2E_SKIP_WEB_SERVER` | Yes      | Set to `1` to skip starting the mock API and UI                                                                        |
| `SYNTARA_E2E_BASE_URL`        | Yes      | URL of the running UI (e.g. `http://localhost:8000`)                                                                   |
| `SYNTARA_E2E_PASSWORD`        | Yes      | Password for the `admin` user. In CI this is read from `.secrets/admin-password` generated by `make secrets-generate`. |

See [`.claude/skills/frontend-playwright-e2e/SKILL.md`](../../../.claude/skills/frontend-playwright-e2e/SKILL.md) for comprehensive setup instructions.

### Running E2E Tests

```bash
# From repository root
npm run e2e        # Run headless (mock API auto-started)
npm run e2e:ui     # Run with Playwright UI

# Override ports if needed
SYNTARA_E2E_PORT=5174 SYNTARA_E2E_API_PORT=3301 npm run e2e
```

### Test Isolation (CRITICAL)

**Tests run in parallel** and must be completely independent. Each test must work in any order.

**Golden Rules:**

1. **NEVER hardcode names** — Always use `buildUniqueName(prefix)`
2. **Create your own resources** — Don't assume data exists
3. **Clean up in try-finally** — Cleanup must run even if test fails
4. **No shared state** — Each test is isolated

```typescript
// ❌ BAD: Hardcoded name + no cleanup
test('test', async ({ app }) => {
  const name = 'my-workflow' // Conflicts in parallel execution!
  await createWorkflow(app, name)
  // No cleanup - pollutes database!
})

// ✅ GOOD: Unique name + try-finally cleanup
test('test', async ({ app }) => {
  const name = buildUniqueName('e2e-workflow')
  await createWorkflow(app, name)
  try {
    // Test logic
  } finally {
    await deleteWorkflow(app, name) // Always runs
  }
})
```

**Why this matters:** With `fullyParallel: true`, tests run concurrently. Without unique names and cleanup, tests interfere with each other and fail randomly.

### Selector Strategy (Required)

- Prefer `getByRole`, `getByLabel`, `getByText`
- Use `getByPlaceholder` only when no label exists
- Add `aria-label` to UI elements when a semantic locator is missing
- Avoid `data-testid` unless absolutely necessary
- No CSS/XPath selectors in integration tests

### Example Pattern (AAA)

```ts
import { test, expect, toAppUrl } from './fixtures'
import { buildUniqueName } from './helpers/workflows'

test('user creates a workflow', async ({ app }) => {
  // Arrange - Start from the list
  const workflowName = buildUniqueName('e2e-test')

  try {
    // Act - Create a workflow with unique name
    await app.goto(toAppUrl('/workflows'))
    await app.getByRole('button', { name: 'Create workflow' }).click()
    await app.getByPlaceholder('Workflow name').fill(workflowName)
    await app.getByRole('button', { name: 'Save' }).click()

    // Assert - Saved workflow appears
    await expect(app.getByText('Workflow created successfully')).toBeVisible()
  } finally {
    // Cleanup — delete created resources (especially when testing against real backend)
    // ... cleanup logic
  }
})
```

**Important:**

- Use `{ app }` fixture (not `{ page }`) — pre-configured with base URL
- Import from `'./fixtures'` (not `'@playwright/test'`)
- Clean up created resources when testing against real backend (persistent database)

For comprehensive E2E testing guidance, see [`.claude/skills/frontend-playwright-e2e/SKILL.md`](../../../.claude/skills/frontend-playwright-e2e/SKILL.md).
