# E2E Test Deduplication Rules

When reviewing, writing, or auditing E2E tests in `packages/syntara-ui/e2e/`, apply these rules to identify tests that can be safely removed without losing coverage.

> **IMPORTANT:** Never delete `test.skip(...)` or `test.fixme(...)` tests. Skipped tests document known-broken or in-progress scenarios and serve as a backlog. Convert them to `{ tag: ['@konflux-skip'] }` when appropriate, but do not remove them from the codebase.

## Before writing a new test — search first

**CRITICAL: Before adding any E2E test, grep for existing tests covering the same scenario.** Many duplication incidents happen because the author didn't know a parallel test already existed in a different spec file. Run:

```bash
grep -r "test(" packages/syntara-ui/e2e/ | grep -i "<keyword>"
```

and read the top candidates before writing new tests.

## Removable patterns

1. **Assertion-free test bodies** — if a test adds nodes or performs actions but has no `expect()` call, it proves nothing. Remove it; the covered path is implicit in tests that share the same setup.

## Duplicate-coverage patterns (remove the weaker test)

2. **Strict-subset assertion** — if test A asserts a strict subset of what test B asserts and both exercise the same UI path, remove A. Prefer the stricter, more complete test.
3. **Same scenario in multiple spec files** — when two spec files both test the same flow (e.g., an empty-state-filter, save-and-reload, navigation step, or modal flow), keep the canonical spec and remove the copy.
4. **Unit-level coverage duplicated at E2E level** — if a component unit test already covers a behavior exhaustively (e.g., date-format consistency, form validation), the E2E test adds no unique confidence. Remove the E2E copy.
5. **Journey test whose sub-steps each have their own spec** — a 90-second "search, view, and delete" journey is redundant when filtering, table, and destructive-modal specs each cover one step individually. Remove the composite journey.
6. **Navigation sub-step already covered by a superset test** — if test A navigates to page X and asserts heading + URL, and test B does the same navigation PLUS additional assertions, remove A. The superset's execution already validates the sub-step.
7. **Parallel "same pattern, different resource" over-testing** — shared infrastructure behaviors (URL-based filter persistence, shareable URL round-trips, cursor-based pagination) are implemented once by a shared hook (`useCursorPagination`). Do not duplicate these cross-cutting tests for every resource type. One representative spec per behavior pattern is enough; additional resource-type copies only add CI time with no additional confidence.

## Ineffective CI guards (fix, don't remove)

8. **`test.skip(!!process.env.CI, ...)`** — this has no effect in Konflux because Konflux does **not** set `CI=true`. Replace with `{ tag: ['@konflux-skip'] }` directly on the test. Do not use describe-level `test.skip(condition)` calls — they are ignored in Konflux. See the `@konflux-skip` tag documentation in the Essential Commands section.

## Temporal / external-URL patterns (apply `@konflux-skip`, not deletion)

9. **Tests that wait for Temporal to complete a real execution** — approval flows, multi-step runs, execution-status polling over 25 s are unreliable under Konflux cluster load. Tag with `@konflux-skip` rather than deleting if the test is otherwise useful locally.
10. **Tests where the Temporal worker must reach an external URL** (httpbin, LLM APIs, webhook endpoints) — the Temporal worker's network is more restricted than the test runner. Tag with `@konflux-skip`.

## Decision process

When you find a `test.skip` or `test.fixme`:

1. **Never delete it.** Skipped tests are intentional — they track broken or incomplete scenarios.
2. **Read the skip reason.** Does it require Temporal execution, external URLs, or LLM credentials that are unavailable in CI? Tag with `@konflux-skip` so it still runs locally.
3. **Fix the CI guard if needed.** Replace `test.skip(!!process.env.CI, ...)` with `{ tag: ['@konflux-skip'] }`.
4. **Run Prettier after editing.** Always run `npx --prefix .. prettier --write <file>` after modifying test blocks — Playwright's multi-argument test signatures can reformat to multi-line.

When writing a new test:

1. **Search first.** Grep for tests covering the same flow before writing.
2. **Prefer adding to an existing spec** over creating a new file when the scenario fits an existing describe block.
3. **Don't clone filter/pagination/URL-persistence tests** for a new resource type unless the resource has a genuinely different implementation; the shared hook is already covered elsewhere.
