# UI package scripts

Topic tooling lives in subfolders under this directory:

| Folder               | Purpose                                                                           |
| -------------------- | --------------------------------------------------------------------------------- |
| `route-baseline/`    | Route compatibility contract (`manifest.gen.json`), collectors, check/update CLIs |
| `visual-regression/` | Visual baseline coverage check, scoped `/update-screenshots`, noisy-diff filter   |

Root files here (for example `merge-coverage.js`) are shared utilities that are not topic-specific.
