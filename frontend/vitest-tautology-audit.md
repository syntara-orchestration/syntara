# Frontend Vitest tautology audit

Date: 2026-09-21

## Scope and method

The pre-repair audit covered all 904 files under `frontend/` whose names ended
in `.test.ts` or `.test.tsx` (901 `syntara-ui` files and 3
`syntara-mock-api` files). The review compared each assertion with the test
setup and the implementation under test. Five irredeemable test files were
removed during the repair pass, leaving 899 such files in the working tree.

The report distinguishes two levels:

* **Strict/degenerate cases:** the test only checks data or logic created by
  the test itself, derives both sides of an assertion from the same source, or
  transforms both sides so the claimed behavior disappears.
* **Shared-oracle coupling:** the test does exercise the production path, but
  computes the expected value with the same production helper. These are not
  guaranteed tautologies, but a regression in that helper can make both sides
  wrong in the same way.

## Strict/degenerate findings

### 1. Runtime assertion on a test-created object (1 case)

**File:** [`src/routes/access/types.test.ts:11`](./packages/syntara-ui/src/routes/access/types.test.ts:11)

**Case:** `supports PermissionRow objects used by assignment tables`

The test constructs `row` itself, including `sourceEndpoint: 'role-assignments'`,
then asserts `row.sourceEndpoint` has that same literal value at line 26. The
imported `types.ts` module contains only type declarations, so no runtime
implementation is exercised.

### 2. Expected value is another call to the same function (1 case)

**File:** [`src/routes/access-management/roleAssignmentColumns.test.ts:179`](./packages/syntara-ui/src/routes/access-management/roleAssignmentColumns.test.ts:179)

**Case:** `returns all columns for empty array`

```ts
expect(getVisibleColumns([])).toEqual(getVisibleColumns())
```

Both sides are produced by `getVisibleColumns`; no independent expected
column set is asserted.

### 3. Sorting both results removes the behavior under test (1 case)

**File:** [`src/stores/useWorkflowStore.reorderActivities.test.ts:195`](./packages/syntara-ui/src/stores/useWorkflowStore.reorderActivities.test.ts:195)

**Case:** `produces consistent order for nodes at same level`

The test compares `run1.sort()` with `run2.sort()`. Sorting both outputs erases
the ordering difference the case claims to verify. A no-op implementation that
preserved each input order would still pass.

### 4. Same function supplies both sides of the equality (1 case)

**File:** [`src/routes/builder/panels/utils/tableHelpers.test.ts:55`](./packages/syntara-ui/src/routes/builder/panels/utils/tableHelpers.test.ts:55)

**Case:** `produces identical keys for rows with identical values`

The assertion compares `buildRowKey(row1, ...)` with `buildRowKey(row2, ...)`.
Since the rows and columns are identical, any deterministic result—including a
constant empty string—passes. It does not independently establish the key
format or contents.

### 5. Redundant assertion of a production alias (1 case)

**File:** [`src/routes/approvals/useApprovalsData.test.tsx:245`](./packages/syntara-ui/src/routes/approvals/useApprovalsData.test.tsx:245)

**Case:** `preserves API order in sortedApprovals`

The assertion compares `sorted` with `result.current.enrichedApprovals`. The
implementation defines `const sortedApprovals = enrichedApprovals`, so this
equality is guaranteed by the alias. The preceding ID assertions are
independent; this finding applies to the alias assertion only.

### 6. BuilderFlow execution tests reimplement the SUT (31 cases)

**File:** [`src/routes/builder/BuilderFlow.execution.test.tsx:12`](./packages/syntara-ui/src/routes/builder/BuilderFlow.execution.test.tsx:12)

The file explicitly says “Mock the actual implementation for testing purposes”
and defines local `hasDownstreamPendingNodes`, `shouldMarkAsSkipped`, and
`shouldMarkAsCompleted` functions. None of the 31 cases imports `BuilderFlow`,
`WorkflowTraversal`, or the execution-state production utilities; every case
calls those local copies (or repeats the render-comparison logic inline).
Consequently, changes or complete breakage in the production execution logic
can leave all 31 cases green. The affected groups are:

* `shouldMarkAsSkipped` (7 cases, lines 161–344)
* `shouldMarkAsCompleted` (7 cases, lines 349–532)
* `Edge Status Integration` (1 case, lines 538–572)
* `Downstream Pending Node Detection` (5 cases, lines 575–769)
* `Default Pending State for Conditional/Approval Nodes` (5 cases, lines 772–899)
* `Multi-Parent Node Skip Detection` (3 cases, lines 903–1012)
* `Performance: Empty-to-Populated ActivityStates Transition` (3 cases, lines 1014–1146)

### 7. ConvergeNodeDetails integration tests duplicate `handleSubmit` (4 cases)

**File:** [`src/routes/builder/node-details/ConvergeNodeDetails.integration.test.tsx:8`](./packages/syntara-ui/src/routes/builder/node-details/ConvergeNodeDetails.integration.test.tsx:8)

The file does not import `ConvergeNodeDetails`. Instead it defines
`simulateHandleSubmit` with the same snake_case mapping logic and asserts that
helper's output in all four cases (`n_required`, `on_timeout`, and the two
strategy branches). The production component can regress without affecting
these tests.

### 8. LoopNodeDetails integration tests duplicate `handleSubmit` (5 cases)

**File:** [`src/routes/builder/node-details/LoopNodeDetails.integration.test.tsx:9`](./packages/syntara-ui/src/routes/builder/node-details/LoopNodeDetails.integration.test.tsx:9)

The file does not import `LoopNodeDetails`. Its local `simulateHandleSubmit`
copies the component's type selection, field merge, and undefined-field removal
logic. All five cases assert that local helper, not the component's submit
handler.

### 9. useDuplicateWorkflow tests are entirely self-authored (7 cases)

**File:** [`src/routes/workflows/useDuplicateWorkflow.test.tsx:19`](./packages/syntara-ui/src/routes/workflows/useDuplicateWorkflow.test.tsx:19)

The file never imports `useDuplicateWorkflow` or calls the hook:

* The three approval-transformation cases copy the mapping algorithm into the
  test body and assert that copy (lines 27–110).
* The three error cases only assert that test-created fixtures lack `id`,
  `project_id`, or `workflow_definition` (lines 116–137); no guard, API call,
  or error path runs.
* The timestamp case builds `expectedPattern` in the test and matches that
  locally built string against a regex (lines 141–147); no duplicate-name code
  runs.

### 10. Mock API output fields compared with one another (2 cases)

**File:** [`packages/syntara-mock-api/src/utils/convertYamlToWorkflow.test.ts:53`](./packages/syntara-mock-api/src/utils/convertYamlToWorkflow.test.ts:53)

Cases `seeds the workflow and its version with the same creator` and `seeds
workflow updated_by as a UserReference for table timestamp columns` compare
`workflow.version.created_by` or `workflow.updated_by` with
`workflow.created_by`, all read from the same converter result. A converter
that populated all three fields with the same incorrect value would satisfy
these cases. The separate shape assertion at line 46 is independent; this
finding concerns the two same-output comparisons.

## Shared-oracle coupling (not strict tautologies)

These cases still exercise production code, but their expected values are
computed with helpers also used by that production code.

### A. Page-title helper is used on both sides (9 call sites)

**Helper:** [`src/test/pageTitle.ts:6`](./packages/syntara-ui/src/test/pageTitle.ts:6)

`expectPageTitle` compares `document.title` with `toPageTitle(segments)`. The
rendered [`SynPageTitle.tsx`](./packages/syntara-ui/src/components/SynPageTitle.tsx:15)
also calls `toPageTitle`, so a formatting regression can affect both actual and
expected values. The helper is used in `BuilderEdit`, `BuilderNew`,
`BuilderWorkflowPageHeader`, `Workflows`, `Executions`, and `Credentials` tests.

### B. Credential expiration tests reuse the production date formatter (8 call sites)

**File:** [`src/routes/access-management/service-accounts/useCredentialExpirationDate.test.ts:5`](./packages/syntara-ui/src/routes/access-management/service-accounts/useCredentialExpirationDate.test.ts:5)

The hook uses `formatDateYMD` to initialize, update, and reset values, while
the test imports the same helper for expected values and valid-date input at
lines 22, 40, 47, 55, 106, 109, 142, and 196. Date arithmetic is independent,
but formatter regressions can be hidden by this shared oracle.

### C. Switch port mapping expected values use the production port builder (4 assertions)

**File:** [`src/routes/builder/node-details/SwitchNodeDetails.test.tsx:205`](./packages/syntara-ui/src/routes/builder/node-details/SwitchNodeDetails.test.tsx:205)

The component uses `buildSwitchCasePort` when constructing new ports and its
mapping; the two submit cases use the same helper to build fixture ports and
expected map keys/values. Port-name regressions can therefore be masked.

### D. Switch placeholder expected value uses the same port helper (1 assertion)

**File:** [`src/routes/builder/utils/edgeConnectionHelpers.test.ts:190`](./packages/syntara-ui/src/routes/builder/utils/edgeConnectionHelpers.test.ts:190)

The test creates `sourceHandle` with `buildSwitchCasePort(0)` and expects a
template containing another call to that helper. The production code also uses
the helper to classify switch handles.

### E. Built-in workflow tooltip expectations call the production helper (5 cases)

**File:** [`src/routes/workflows/workflowRowActions.test.tsx:79`](./packages/syntara-ui/src/routes/workflows/workflowRowActions.test.tsx:79)

The five built-in-project tooltip cases call `builtinProjectTooltip(...)` in
the expected value, while `buildWorkflowRowActions` calls that same helper to
construct the actual tooltip. The cases still independently check the disabled
state, but the tooltip text assertion is shared-oracle coupled.

## Repair pass status

The findings above were used as the repair queue. The strict/degenerate cases
were resolved as follows:

* Removed the type-only `routes/access/types.test.ts` file.
* Removed the three local-logic files for BuilderFlow execution,
  ConvergeNodeDetails, and LoopNodeDetails; production-backed execution utility
  and component tests already cover those paths.
* Removed `useDuplicateWorkflow.test.tsx`; `Workflows.test.tsx` exercises the
  real duplication hook through the user flow.
* Replaced same-function, same-output, and sort-both-sides assertions with
  independent literal expectations.
* Replaced shared helper-derived page-title, tooltip, switch-port, and date
  expectations with independent literals or date-fns formatting.
* Strengthened the mock API converter test with independent audit-field and
  workflow-definition expectations.

No test from the strict/degenerate findings remains unchanged.

## Conclusion

The original count of five was too narrow. The expanded audit identified **54
strict/degenerate test cases across 10 findings** and five shared-oracle groups.
The repair pass removed or rewrote all of those identified cases so the
remaining assertions exercise production behavior with independent oracles.
