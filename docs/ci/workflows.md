# CI Workflows

This document describes the GitHub Actions workflows in `.github/workflows/` and their execution behavior.

## Overview

The CI system uses conditional execution and cost-saving gates to reduce runner usage while maintaining safety. The merge queue always runs comprehensive tests before code lands.

## Frontend CI (`ci-frontend.yml`)

### E2E UI Tests - Conditional Execution

The `test-compose-e2e` job runs Playwright E2E tests against the full stack (Podman Compose). This is the most expensive frontend CI job (~15-20 min on 8-core runners).

**When it runs:**

| Change Type               | `frontend` output | Event Type                  | E2E Behavior                          |
| ------------------------- | ----------------- | --------------------------- | ------------------------------------- |
| `frontend/` files         | `true`            | PR                          | ✅ **RUNS** after checks pass         |
| Backend-only              | `false`           | PR                          | ⏭️ **SKIPS** (saves CI costs)         |
| `ci-frontend.yml` changes | `true`            | PR                          | ✅ **RUNS** (workflow affects E2E)    |
| Other workflow files      | `false`           | PR                          | ⏭️ **SKIPS**                          |
| Any changes               | -                 | Merge queue                 | ✅ **ALWAYS RUNS** (safety gate)      |
| Any changes               | -                 | Manual `/run-podman-e2e-ui` | ✅ **ALWAYS RUNS** (on demand)        |
| Frontend changes          | `true`            | Push to `devel`             | ⏭️ **SKIPS** (merge queue handles it) |

**Pattern detection:**

```bash
# Frontend changes detected when files match:
^(frontend/|\.github/workflows/ci-frontend\.yml)
```

**Key behaviors:**

- **Conditional execution:** PRs with backend-only changes skip E2E UI tests during development
- **Merge queue safety:** Always runs all tests before code lands (safety preserved)
- **Manual trigger:** Available via `/run-podman-e2e-ui` comment for backend PRs or re-runs
- **Fast-fail gate:** E2E waits for lint and unit tests to pass first (fails fast in ~2-3 min instead of waiting for full E2E suite)

### Cost-Saving Gate (`frontend-checks-gate`)

The `frontend-checks-gate` job acts as a dependency for expensive jobs. It waits for fast checks to pass before starting expensive E2E tests.

**Dependencies:**

```yaml
frontend-checks-gate:
  needs: [changes, checks, unit-tests]
  # Blocks downstream jobs until these pass
```

**Downstream jobs that wait for the gate:**

- `test-compose-e2e` (E2E UI tests)
- `konflux-frontend-gate`
- `konflux-ui-tests-gate`

**Impact:**

- E2E starts ~2-3 min later (waits for checks to pass)
- Saves ~2 hours of 8-core runner time per failed lint/unit test
- Fails fast in ~2-3 min instead of waiting for full E2E suite

### Manual Triggers

#### `/run-podman-e2e-ui` - Manual E2E UI Test Runs

Manually trigger E2E UI tests on any PR by commenting:

```
/run-podman-e2e-ui
```

**Authorization:** Repository OWNER or MEMBER only (stricter than COLLABORATOR)

**When to use:**

- Backend-only PRs where you want to verify the UI still works
- Workflow or CI configuration changes
- Debugging test failures
- Re-running tests after transient failures

**Where results appear:** The listener dispatches `ci-frontend.yml` on the `devel` ref via `workflow_dispatch`. Runs show up under Actions → CI Frontend (event = `workflow_dispatch`), not as a PR check the way automatic `pull_request` E2E jobs do.

**Path filtering on manual runs:** The `changes` job uses `inputs.pr_number`, so other frontend jobs still respect the PR's changed paths. Only E2E is forced on by the `workflow_dispatch` condition. If the checks gate is skipped (e.g. docs-only PR), E2E still runs; if lint/unit failed, E2E stays blocked.

**Security:**

- Refuses fork PRs
- Validates PR ref matches actual PR head ref before checkout
- Re-commenting `/run-podman-e2e-ui` on the same PR cancels an in-progress manual run for that PR (PR-scoped concurrency)

**Implementation:** Listener workflow (`.github/workflows/run-podman-e2e-ui-listener.yml`) validates the comment and dispatches to `ci-frontend.yml` with PR metadata.

### Concurrency Control

Most jobs use concurrency groups to cancel in-progress runs when new commits are pushed:

```yaml
concurrency:
  group: <unique-key>-${{ github.head_ref || github.ref }}
  cancel-in-progress: true
```

Manual `/run-podman-e2e-ui` dispatches are keyed by PR number instead of `github.ref` (which would be `devel` for every dispatch), so they do not cancel each other or fight push-to-`devel` runs:

```yaml
concurrency:
  group: ci-frontend-${{ github.event_name == 'workflow_dispatch' && format('dispatch-{0}', inputs.pr_number) || github.ref }}
  cancel-in-progress: true
```

## Backend CI (`ci-backend.yml`)

(To be documented)

## Merge Queue Behavior

When PRs enter the merge queue (`merge_group` event):

- All tests run regardless of changed paths
- Path-based skipping is bypassed
- Gates are bypassed for comprehensive validation
- This is the final safety check before code lands

**Rationale:** Merge queue runs represent the last chance to catch issues before code reaches `devel`. Skipping tests here would compromise safety.

## Debugging CI Issues

### Check workflow runs

```bash
gh run list --workflow=ci-frontend.yml --limit=10
gh run view <run-id>
```

### Check E2E logs

```bash
gh run view <run-id> --log --job="(Frontend) Test Podman Compose E2E"
```

### Manually trigger E2E tests

Comment on the PR:

```
/run-podman-e2e-ui
```

### Konflux-specific failures

Konflux (Red Hat CI) runs in a restricted environment. See [`CLAUDE.md`](../../CLAUDE.md) for skip patterns:

- `@konflux-skip` tag for Playwright E2E tests
- `@requires_httpbin` marker for backend tests
- Graceful skips for network connectivity issues

## Future Improvements

- Apply conditional execution to other expensive jobs after validating the pattern
- Add more manual trigger commands for other test suites
- Document backend CI workflows
- Add workflow execution time metrics
