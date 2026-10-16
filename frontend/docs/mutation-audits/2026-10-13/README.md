# Mutation audit baseline: October 13–15, 2026

The full audit completed all 44 batches against revision
`bfeb0b45b396631fb317d565b19c82a08d35c4e5`, with a clean working tree.
It started at 2026-10-13 19:47:35 UTC and finished at 2026-10-15 20:38:50 UTC
(48 hours, 51 minutes). Static mutants were included.

| Package  | Files | Batches | Mutants | Mutation score (all) | Mutation score (covered) | Mutation coverage |
| -------- | ----: | ------: | ------: | -------------------: | -----------------------: | ----------------: |
| UI       | 1,075 |   43/43 |  60,791 |               64.95% |                   68.33% |            95.05% |
| Mock API |     5 |     1/1 |   6,551 |                1.14% |                   14.31% |             8.00% |

These are the scores reported by the audit index. Mutation coverage is not line
coverage. Completion means all batches finished; it does not mean all mutants
were killed. Surviving mutants, uncovered code, timeouts, and tool errors need
separate interpretation before setting a quality threshold.

The run used Node v24.13.0, npm 11.19.0, Vitest 4.1.10, and StrykerJS 10.0.0.
See the [per-file CSV](combined-summary.csv) for counts and scores.

## Preserved reports

The local archive `reports.tar.gz` preserves the entire local `mutation-reports/`
folder: the completed run `2026-10-13T19-47-35-492Z` and the initial failed
attempt `2026-10-13T19-46-01-651Z`. The earlier attempt's metadata still says
`running`; it is not the completed baseline. Original output is preserved
without rewriting statuses or paths.

The archive includes HTML reports, JSON reports, incremental data, logs, source
context, run metadata, indexes, and CSV summaries. It is compressed to keep the
backup in one file; routine generated reports remain Git-ignored.

The archive and its `SHA256SUMS` file are currently local only: the repository
blocks added files larger than 500 KB. They must be published separately or
explicitly exempted before the full reports have a remote backup.

Verify the checksum from this directory:

```sh
shasum -a 256 -c SHA256SUMS
```

Restore from the `frontend/` directory in a checkout without existing reports
using these run IDs:

```sh
tar -xzf docs/mutation-audits/2026-10-13/reports.tar.gz
```

Then open `mutation-reports/2026-10-13T19-47-35-492Z/index.md` and follow its
batch HTML links. The archive retains the original paths so those links work.
No mutation rerun is needed to inspect these results.

## Merge considerations

This snapshot records the tested revision, not the current target branch.
Keep this backup commit separate from tooling changes so the snapshot can be
retained on this branch even if the upstream PR takes only tooling and readable
summaries. The full audit remains manual; these results do not introduce a CI
threshold. Prioritize concrete missed behaviors and focused tests in later PRs.
