# Proposed Vitest mutation testing workflow

Updated 2026-10-13. StrykerJS is the selected tool. This PR adds the first stage: a local full-suite audit that runs in batches and saves reports as it goes. It does not add a CI check. The later sections describe how to add a focused PR check after the baseline is ready.

## Recommendation

Run a full baseline audit of the frontend unit tests, then introduce an automatically selected PR check for new or changed behavior. Run broader audits on a schedule. Gradually tighten the PR policy while existing gaps remain visible in the full report.

There is no manually maintained list of enrolled modules or suites. One shared configuration identifies handwritten source and eligible tests, with exclusions for generated code, stories, fixtures, and test infrastructure.

Stryker mutates production code and runs tests against each mutation. A surviving mutation is a candidate missing assertion, equivalent change, or tool error. Mutation results require some judgment, but source discovery, execution, report generation, and enforcement can be automated.

## Current setup

- The UI and mock API have separate Vitest configurations. The audit runs each package with its own configuration.
- StrykerJS and its Vitest runner are installed in the frontend workspace.
- The runner finds eligible production files and puts them into batches of 25 files by default.
- Stryker runs one batch at a time, with two workers inside the active batch.
- The [audit guide](vitest-mutation-audit.md) has the one-command start and resume instructions.
- Reports are local files under `frontend/mutation-reports/<run-id>/`. The folder is ignored by Git.
- The UI and mock API audit both produce reports. Browser and Playwright E2E tests remain outside this workflow.

## 1. Audit the whole suite

Run a full manual audit of all eligible source in the UI and mock API packages. Keep uncovered mutations visible rather than limiting the audit to already-covered lines. A scheduled job can be added after the local run is measured.

Automatically divide source into deterministic, disjoint batches of 25 files by default. Run batches one at a time, with Stryker limited to two workers inside each batch. Each batch uses the package's Vitest configuration and related tests. Write an index, a combined per-file summary, and each batch's HTML/JSON report. This source partitioning and report aggregation are repository tooling; they are not assumed to be native Stryker sharding commands. The batch size can be adjusted after measured timings.

From the repository root, start a fresh audit with:

```sh
npm --prefix frontend run mutation:audit
```

The command prints the full batch list, then runs batches one after another. Stryker shows progress for the active batch. After each batch, the command writes its HTML and JSON reports and updates `index.md`, `combined-summary.csv`, `run.json`, and `audit.log`. Use the run ID printed by the command to resume an interrupted run. Finished batches stay saved; the interrupted batch starts again from the beginning. The runner checks that the source, tests, and configuration have not changed before resuming.

For the mutation audit only, the runner sets `SYNTARA_MUTATION_VITEST_TIMEOUT_MS=60000`, applying a 60-second default to Vitest tests and hooks while Stryker instruments the code. Normal Vitest commands keep their existing timeout defaults. The value is recorded in `run.json` and must match when resuming a run.

For a quicker diagnostic pass, use a separate run ID and set `SYNTARA_MUTATION_IGNORE_STATIC=1`:

```bash
SYNTARA_MUTATION_RUN_ID=fast-preview SYNTARA_MUTATION_IGNORE_STATIC=1 npm --prefix frontend run mutation:audit
```

Stryker marks static mutants as `Ignored` in that run. Its scores describe the executed mutants only, so this preview does not replace the full audit; run again without that setting for the complete result.

Record:

- Files with surviving or uncovered mutations, and the exact source changes missed.
- Tests associated with those mutations where the runner provides that information.
- Tool failures, mutation timeouts, and actual batch runtimes.
- Commit SHA, package/tool versions, exclusions, and whether every source batch completed.

A full audit may take many hours. The manual command keeps progress visible and saves each completed batch, so an interruption does not discard finished reports. A partial run is labeled incomplete; a completed audit covers every eligible source file. The audit does not run in CI or delay ordinary PR checks.

The full report measures the combined suite's ability to detect source defects. It does not assign a definitive quality score to every individual test: several tests can exercise the same behavior.

## 2. Select PR work automatically

A repository script reads the Git diff against the actual target branch's merge base and generates Stryker source/test selection.

| PR change                                                                      | Automatic action                                                                                         |
| ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| New production file                                                            | Mutate the whole new file and run related tests.                                                         |
| Changed production file                                                        | Mutate new/changed source ranges and run related tests.                                                  |
| Added or changed test file                                                     | Discover the handwritten code it exercises and produce a focused mutation report using those test files. |
| Deleted tests                                                                  | Rerun the affected existing source against remaining tests and check for lost detections.                |
| Shared test setup, package dependencies, configuration, or ambiguous selection | Run a broader affected scope; show an incomplete result if selection cannot be resolved.                 |
| No relevant frontend change                                                    | Publish an explicit no-applicable-work result.                                                           |

Use Vitest import relationships and a targeted coverage run to discover source exercised by changed tests. Filter shared setup and test infrastructure out of that source scope. Import discovery alone cannot resolve every runtime-generated import, so ambiguous cases need a broader fallback.

Stryker accepts source paths/ranges, eligible test files, related test discovery, and individual covering-test selection. The script converts Git changes and coverage into these inputs. Sources: [Stryker source ranges](https://stryker-mutator.io/docs/stryker-js/configuration/#mutate-string), [test file selection](https://stryker-mutator.io/docs/stryker-js/configuration/#testfiles-string), [official Vitest runner](https://stryker-mutator.io/docs/stryker-js/vitest-runner/), [Vitest related tests](https://vitest.dev/guide/cli.html#vitest-related), [Vitest coverage](https://vitest.dev/guide/coverage.html).

For a test-only addition, evaluate mutations in the statements or behavior exercised by those tests. A test for one branch should not receive failures for unrelated functions in the same module. Conversely, for changed production behavior, uncovered mutations belong in the score; choosing only covered code would hide missing tests.

Initially select added/modified test files as a whole. Isolating only newly added individual `it(...)` cases requires additional test identity and source-diff analysis, especially for parameterized cases and edited shared setup. Do not claim that file-level selection measures each newly added case independently.

Cancel older runs when another commit arrives. Aim for five-minute feedback, initially with a ten-minute job limit, then adjust from measurements. Larger changes can be split into automatic batches. A required check must wait for its complete scope or fail; a manual future run cannot substitute for a passing required check.

## 3. Introduce gating gradually

Start with automatic reporting for every relevant PR, after a short setup and repeatability smoke test. The smoke test validates the tool; it does not restrict the subsequent whole-suite audit.

Promote these rules in stages:

1. Require a mutation score for new production files and changed production behavior. Trial an 80% target in reporting mode, then set the enforced target from actual findings and runtime.
2. For test changes on unchanged existing source, detect losses of previously killed mutations using the normal relevant suite. Compare fresh base and head results for the same unchanged source/mutants and compatible configuration. A stale full-audit score is not an exact PR baseline.
3. Publish the focused changed-test-file score alongside the suite result. After confirming that its automatically selected scope is fair and repeatable, consider making the target for newly added test files required too. Modified existing test files can initially use a comparable no-regression policy so improving old tests does not force immediate repayment of every old gap.

These are two different measurements: whether the relevant suite protects a source change, and whether the changed test files alone detect faults in the behavior they exercise. Label them separately in reports. A test-only no-regression rule protects existing behavior but does not by itself prove that a newly added test adds value.

Implement one stable required check, such as `Frontend mutation quality`, on every PR and merge queue event. It aggregates applicable required results, fails on policy violations or incomplete/error runs, and passes explicitly when no required scope applies. Uncertain merge queue selection should run a broader scope. Enable the requirement only after the upstream reliability concern below and local repeatability are resolved.

Equivalent mutation exclusions need a specific reviewed reason. Avoid blanket exclusions or lowering the requirement simply to merge a failing PR. No applicable mutations means no score is available, not a reported 100% score.

## 4. Make the report actionable automatically

For full audits, publish a per-file summary ordered by surviving/uncovered mutations, with direct links into HTML reports. Keep counts alongside percentages so a file with one mutant is distinguishable from a large module. Preserve existing gaps as visible baseline debt.

For PRs, show only the selected changes, scores, baseline regressions, and mutations causing a policy failure. The author opens the linked source change, adds an assertion for a real missed behavior, and reruns. A reviewed exclusion handles an equivalent mutation. A tool defect is investigated as a tool defect.

Generating the reports and selecting the failing findings is automatic. Interpreting equivalent mutations and writing useful tests remains normal engineering work. There is no requirement to manually assign every module, enroll new contributions, or triage every old survivor before enabling a useful PR gate.

## Implemented in this PR

- `frontend/packages/syntara-ui/stryker.config.mjs`: UI source selection, Vitest setup, progress output, and report settings.
- `frontend/packages/syntara-mock-api/stryker.config.mjs`: matching setup for the mock API.
- `frontend/scripts/run-mutation-audit.mjs`: source discovery, sequential batches, resume support, console progress, and report summaries.
- `frontend/docs/vitest-mutation-audit.md`: the start and resume commands.

## Later work

- Add focused PR mutation selection and a single stable required check.
- Add a scheduled full audit only after local runtime and report quality are measured.
- Choose a CI threshold from completed audit data. This PR does not add that threshold or CI workflow.

Keep the Stryker core and official Vitest runner versions matched in the frontend lockfile. Each audit records the Node and npm versions it used. The frontend requires Node.js 22.18 or newer.

Start with fresh mutation results. Incremental mode still requires an initial run and has limitations around supporting files, dependencies, snapshots and static mutations. Later assess cache reuse with explicit invalidation and regular fresh audits. [Incremental limitations](https://stryker-mutator.io/docs/stryker-js/incremental/).

Before adding a required check, run repeatability checks against the locked Vitest and Stryker versions and inspect any tool errors separately from surviving mutants.

This PR does not run a new full audit or report new mutation scores. Run the manual command to create a fresh baseline.
