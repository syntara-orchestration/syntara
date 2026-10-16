# Run the frontend mutation audit

Run the full manual audit from the repository root:

```sh
npm --prefix frontend run mutation:audit
```

Install project dependencies first if this is a new checkout:

```sh
make install
```

The audit checks eligible production code in the UI and mock API packages with their Vitest suites. It runs one batch at a time. The command first lists every batch, then shows the active batch, Stryker's progress, elapsed time, and each completed batch. After each batch, it saves any HTML and JSON reports Stryker produced and refreshes the combined summary and index with that batch's status.

The command prints the report folder. Open its `index.md` to see every batch's status and links to finished reports. The run records Node, npm, Vitest, and Stryker versions in `run.json`. The frontend requires Node.js 22.18 or newer.

## Resume an interrupted run

The command prints the run ID. Reuse that ID to resume the same audit:

```sh
SYNTARA_MUTATION_RUN_ID=<run-id> npm --prefix frontend run mutation:audit
```

Finished batches stay saved. The interrupted batch starts again from the beginning. Keep the source files, tests, lockfile, and dependencies unchanged while resuming. Do not run two copies of the same run ID at once.

This command creates a local report only. It does not run in CI or block pull requests.

## Preserved baseline

The [October 13–15, 2026 baseline](mutation-audits/2026-10-13/README.md)
contains the completed audit summary and per-file CSV, and documents the local
archive of the original reports. It records the audited revision and restore
instructions, so inspecting the results does not require another full run.
