# CI/CD Secrets Inventory

Complete inventory of all secrets and credentials used across GitHub Actions
workflows.

---

## GitHub Actions Secrets

| Secret | Classification | Storage | Workflows | Scope Justification | Rotation |
|--------|---------------|---------|-----------|---------------------|----------|
| `GITHUB_TOKEN` (automatic) | Shared | Auto-generated per job | 10+ workflows | Ephemeral, per-job scoped by GitHub | Automatic (per-run) |
| `RH_REGISTRY_USER` | Downstream-only | Org | `_build-backend-image`, `ci-backend`, `ci-frontend` | Pull base images from registry.redhat.io | Annual (service account) |
| `RH_REGISTRY_TOKEN` | Downstream-only | Org | `_build-backend-image`, `ci-backend`, `ci-frontend` | Paired with RH_REGISTRY_USER | Annual (service account) |
| `QUAY_TOKEN` | Shared | Org | `build-frontend-image-devel`, `upload-backend-image` | Push built images to quay.io/ansible/* | Annual (robot account) |
| `SNYK_TOKEN` | Downstream-only | Org | `sast-snyk`, `sca-snyk` | SAST and SCA vulnerability scanning | Annual (Snyk org token) |
| `OPENROUTER_API_KEY` | Shared | Repo | `ci-backend` | E2E tests for LLM integration features | Per vendor policy |
| `CURRENTS_PROJECT_ID` | Shared | Repo | `ci-frontend` | Currents.dev E2E test reporting project identifier | N/A (identifier, not credential) |
| `CURRENTS_RECORD_KEY` | Shared | Repo | `ci-frontend` | Currents.dev E2E test result recording | Annual |
| `CURRENTS_API_KEY` | Shared | Repo | `ci-frontend` | Currents.dev API access for test orchestration | Annual |
| `RAPIDAST_GCP_KEY` | Downstream-only | Repo | `dast` | GCP service account for uploading DAST results | Annual (GCP SA key) |
| `SONAR_TOKEN` | Shared | Repo | `ci-backend`, `ci-frontend`, `sonarcloud-backend`, `sonarcloud-frontend` | SonarCloud code quality and security analysis | Annual |
| `SLACK_CI_MONITORING_WEBHOOK_URL` | Shared | Repo or Org | `merge-queue-health-poll`, `merge-queue-dequeue-alert` | Slack webhook for merge queue health alerts | N/A (webhook URL, not rotatable credential) |

### Classification Key

- **Shared**: Required in both upstream and downstream orgs
- **Downstream-only**: Only needed in the downstream org

---

## GitHub Actions Variables

| Variable | Storage | Workflows | Purpose |
|----------|---------|-----------|---------|
| `QUAY_ROBOT_USERNAME` | Org | `build-frontend-image-devel`, `upload-backend-image` | Quay.io robot account username (paired with `QUAY_TOKEN`) |
| `SONAR_TOKEN_SECRET_NAME` | Repo | `ci-backend`, `ci-frontend`, `sonarcloud-backend`, `sonarcloud-frontend` | Indirection: holds the name of the secret containing the SonarCloud token |
| `SONAR_PROJECT_KEY_BACKEND` | Repo | `ci-backend`, `sonarcloud-backend` | SonarCloud project key for backend analysis |
| `SONAR_PROJECT_KEY_FRONTEND` | Repo | `ci-frontend`, `sonarcloud-frontend` | SonarCloud project key for frontend analysis |
| `SONAR_ORG` | Org | `ci-backend`, `ci-frontend`, `sonarcloud-backend`, `sonarcloud-frontend` | SonarCloud organization identifier |

---

## Elevated Access Justifications

| Workflow | Elevated Permission | Justification |
|----------|-------------------|---------------|
| `konflux-requirements-sync.yml` | `contents: write` via `pull_request_target` | Auto-syncs `requirements.txt` when MintMaker updates `uv.lock`. Guarded by actor check (`red-hat-konflux-kflux-prd-rh03[bot]`) and branch prefix (`konflux/mintmaker`). No fork code execution. |
| `sonarcloud-backend.yml` | `read-all` via `workflow_run` | Checks out fork PR code for SonarCloud analysis. Only the pinned SonarCloud action runs — no user-controlled code execution. |
| `sonarcloud-frontend.yml` | `read-all` via `workflow_run` | Same pattern as backend SonarCloud workflow. |
| `update-visual-baselines.yml` | `contents: write`, `pull-requests: write` | Commits updated visual baseline screenshots back to the PR branch via GitHub API. Uses signed commits (blob/tree/commit API). |
| `dast.yml` | GCP key written to `${{ runner.temp }}` | Writes `RAPIDAST_GCP_KEY` to a temp file for the RapiDAST container. Runner temp is cleaned up after job completion. |
