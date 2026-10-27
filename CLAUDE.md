# Syntara Monorepo — Claude Agent Instructions

Syntara is a distributed multi-agent automation system. This monorepo contains the Python/FastAPI backend and the React/TypeScript frontend.

## Repository Structure

```
syntara/
├── backend/           # Python 3.12+ / FastAPI API, Temporal workflows, PostgreSQL
│   ├── src/syntara/   # Main Python package (domain-driven, auto-discovered routers)
│   ├── src/api_client/# Auto-generated Python API client (syntara-api-client)
│   ├── test-sdk/      # Shared pytest plugin (orchestrator-test-sdk) — installable via pip from git
│   ├── tests/         # pytest: unit, integration, contract, E2E, performance
│   ├── containers/    # Containerfiles for API and MCP server
│   └── Makefile       # Backend-specific targets (run make -C backend help)
├── frontend/          # React 19 / TypeScript / PatternFly 6 (npm workspaces)
│   ├── packages/
│   │   ├── syntara-ui/          # Main UI application
│   │   ├── syntara-contracts/   # Generated TypeScript types from backend OpenAPI specs
│   │   └── syntara-mock-api/    # MSW-based mock API server
│   └── package.json           # Workspace root (E2E tests at packages/syntara-ui/e2e/)
├── podman-compose.yml # Full-stack local dev (all services)
├── Makefile           # Root orchestration (run make help)
└── .env.example       # Combined environment config
```

## Component-Specific Instructions

Read the component docs when working in that area — they contain detailed standards, patterns, and gotchas:

| Working on... | Read |
|---|---|
| Backend Python code | [backend/AGENTS.md](backend/AGENTS.md) — SQLModel patterns, Alembic migrations, testing standards, 12+ domain-specific standards docs |
| Frontend React/TypeScript | [frontend/AGENTS.md](frontend/AGENTS.md) — PatternFly patterns, 36-item PR checklist, architecture guides |
| Both (E2E, contracts, infra) | This file |

### Skills

Upstream AI agent policy (no executable hooks; private local settings; who may
change `.claude/`) is documented in
[`.github/AI_AGENT_POLICY.md`](.github/AI_AGENT_POLICY.md).

Canonical skill files live in `.agents/skills/` at the repo root, prefixed by
workspace. `.claude/skills/` contains tracked relative symlinks to those
directories for Claude Code:

- **`frontend-*`** — Frontend-specific skills (coding standards, PR review, PatternFly UX, testing, Playwright E2E, library references, a11y audit)
- **`backend-*`** — Backend-specific skills (API spec drift detection)
- **`podman-compose-spinup-pr`** — Spin up the full podman-compose environment to locally test a specific PR (OS-agnostic, with automatic Windows workarounds)
- **`podman-compose-teardown`** — Tear down any running podman-compose environment and clean up containers (pass `--purge` to also remove volumes/data)

User-invocable skills: `/frontend-review-pr`, `/frontend-build-ui-feature`, `/frontend-a11y-audit`, `/backend-fix-api-spec-drift`, `/podman-compose-spinup-pr`, `/podman-compose-teardown`. Reference skills (coding standards, testing guidelines, a11y audit methodology, etc.) are loaded automatically by Claude when working on relevant files. Load triggers are listed in `frontend/AGENTS.md` and component `AGENTS.md` files.

## Development Workflow

### First-Time Setup

```bash
make setup    # Installs deps, generates secrets + TLS certs, builds images, starts services, runs migrations, seeds DB
make dev      # Starts backend API (HTTPS, port 8000) + Temporal worker + frontend dev server (port 5173)
```

### Day-to-Day

```bash
make dev            # Start backend API + Temporal worker + frontend dev server
make test           # Run backend + frontend tests
make lint           # Lint both codebases
make format         # Format both codebases
make typecheck      # Type-check both codebases
make gen-contracts  # Regenerate TypeScript types from backend OpenAPI specs
make services-up    # Start infrastructure (DB, Redis, Temporal, etc.)
make services-down  # Stop infrastructure
```

### Backend-Specific Targets

Run `make -C backend help` for the full list. Key ones:

```bash
make -C backend test-all      # All tests including integration
make -C backend db-seed-all   # Seed DB with dev sample data
make -C backend db-clean      # Reset database (destructive)
```

## Port Map (Local Development)

| Service | Port | Notes |
|---|---|---|
| Backend API | 8000 | `make dev` or `make -C backend dev` (HTTPS with self-signed cert) |
| Frontend UI | 5173 | `npm start` from frontend/ |
| Mock API | 3000 | Standalone frontend dev without backend |
| Temporal UI | 8081 | Workflow monitoring |
| PostgreSQL | 5432 | Main + audit databases |
| Redis | 6379 | Cache, auth sessions |
| Storybook | 5174 | Component library + MCP server |
| MCP Server | 8765 | Test MCP server |

## Contract Generation

Backend OpenAPI specs live at `backend/src/syntara/schemas/`. Frontend TypeScript types are generated into `frontend/packages/syntara-contracts/src/`.

```bash
make gen-contracts
```

When a backend PR changes API schemas, run this and include the regenerated types in the same PR. The gen scripts read directly from the local tree — no cross-repo cloning.

## Commit Messages and PR Titles

Commit subjects **and pull request titles** must follow [Conventional Commits](https://www.conventionalcommits.org/). The `conventional-pre-commit` hook enforces this for commit messages. PR titles become the squash-merge commit subject, so they must use the same format.

```
<type>(<scope>): <description>
```

- `type` is one of: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.
- `scope` is optional. If you include it, wrap it in **parentheses**, e.g. `fix(auth): handle expired tokens`. If you leave it out, leave out the parentheses too, e.g. `fix: handle expired tokens`. Never write empty `()`.
- **Never use square brackets** in the subject: `fix[auth]: …` and `[AAP-12345] fix: …` are invalid. Reference the Jira key in the PR description instead (see below).
- Add `!` before the colon for breaking changes, e.g. `feat(api)!: drop v1 endpoints`.
- Write the description in the imperative mood, lowercase, with no trailing period. Keep the whole subject to 72 characters or fewer.

Automated or agent-generated PRs (including bug-resolution pipelines) must check or normalize the title against this format before opening the PR.

**Enforced in CI** by the `PR title` check in the `PR Metadata` workflow (`.github/workflows/pr-metadata.yml`). Structural problems fail the check, and a suggested fix is posted when one is safe. Length, casing and trailing-period issues are warnings only.

## No Jira References in Code or Docs

Code and docs in this repo are read by people who can't open the internal Jira, so Jira references must not appear in source files or documentation.

- **Do not put** Jira issue keys (e.g. `AAP-12345`, `ANSTRAT-1934`), Jira URLs or phrases like "per the Jira ticket" in:
  - code comments, docstrings and `TODO`/`FIXME` notes
  - test names, test descriptions and `pytest.skip`/`test.skip` reasons
  - log, error and user-facing messages
  - Markdown docs, ADRs and skill files
- **Instead**, explain the *why* in plain language, e.g. `# Retry once: the upstream API returns 409 while the lock is released`, not `# Workaround for AAP-12345`.
- **The PR description must reference the Jira work item** the PR addresses **by its plain key**, e.g. `Related to AAP-12345` (see the General Checklist in the PR template). Never paste a Jira URL; the `PR description` check in the `PR Metadata` workflow fails when it finds one. PRs without one count as community contributions and get the `community` label. Jira keys are also fine in branch names and commit message bodies/footers (e.g. `Refs: AAP-12345`), but not in the commit subject or PR title (see above).

This applies to code written by hand, by agents, and by automated pipelines (including the agentic bug-resolution pipeline). Pipelines can keep tracking issues in Jira, but generated code and docs must contain no Jira references.

**Enforced in CI** by the `Jira References` workflow (`.github/workflows/jira-references.yml`). It scans only the PR diff, never the PR description, and fails when lines *added* by the PR contain `AAP-`/`ANSTRAT-` keys or Jira URLs (the hosts are listed in `JIRA_HOSTS` in `.github/scripts/src/lib/jira.ts`). Don't write Jira URLs anywhere in the repo, not even as examples. Existing references only need cleaning up when you touch those lines. Use a placeholder such as `PROJ-123` for examples. The few allowed paths are listed in `JIRA_CHECK_EXCLUDED_PATHS` in `.github/scripts/src/lib/jira.ts`.

## Cross-Cutting Concerns

### Full-Stack PRs

Backend API changes and UI consumption can land in the same PR. When changing an API:
1. Update the backend schema/router
2. Run `make gen-contracts` to regenerate TypeScript types
3. Update the frontend to use the new types
4. Include all changes in one PR

### Podman Compose

The root `podman-compose.yml` defines the full stack. The UI builds from `frontend/` instead of pulling a pre-built image. Backend services (DB, Redis, Temporal) use the same config as the standalone backend compose.

```bash
uv run podman-compose up --build    # Full stack
uv run podman-compose up -d database redis temporal  # Just infrastructure
```

### Konflux CI Environment

Konflux (the Red Hat CI pipeline) runs E2E tests in a restricted environment that differs from local and GitHub CI in several important ways. When E2E tests fail only in Konflux, apply the appropriate skip pattern rather than modifying the test logic.

For a known flaky test that needs temporary quarantine from the pipeline, see
[the test quarantine workflow](docs/ci/test-quarantine.md).

**Key Konflux constraints:**
- Does **not** set `CI=true` — guards like `test.skip(!!process.env.CI, ...)` have no effect.
- The Temporal worker runs in a separate network namespace; it may not reach external URLs even when the test runner can. E2E HTTP Request tests therefore use the in-cluster httpbin Service (`http://httpbin:8080`) that [aap-dev](https://github.com/ansible/aap-dev) deploys next to AO. `HTTPBIN_URL` defaults to that URL when `KUBERNETES_SERVICE_HOST` is set; local and GitHub CI still default to `https://httpbin.org`.
- That in-cluster URL is HTTP because aap-dev's go-httpbin Service has no TLS. That is an accepted trade-off for ephemeral CI: the cluster is torn down after the run, traffic stays on the cluster overlay, and credentials sent to httpbin are synthetic E2E fixtures, not production secrets. Do not add TLS or NetworkPolicies just for this test fixture.
- `http://httpbin:8080` resolves to a ClusterIP. Workflow HTTP Request nodes SSRF-block private IPs unless `httpbin` is on `spec.workflowHttpRequestAllowedHosts` (`APP_WORKFLOW_HTTP_REQUEST_ALLOWED_HOSTS` on the worker). aap-dev's AO CR already lists it. A Konflux `configure-ao` step that replaces that list with only `myao-backend` produces `error: "SSRF blocked: private IP range"` (no `status_code`) and must not be treated as a connectivity skip.
- Cluster load causes 30-second timeouts and transient 502 Bad Gateway responses.

#### Backend pytest skip patterns (`backend/tests/e2e/`)

**Graceful skip for backend connectivity failures**: When the Temporal worker can't reach an external URL, the execution completes with `status == FAILED` but the activity output contains no `status_code` (only an `error: "HTTP request failed: ReadTimeout"` key). Add a skip guard. If `error` is `"SSRF blocked: private IP range"`, that is an allowlist misconfiguration (`httpbin` missing from `workflowHttpRequestAllowedHosts`), not a connectivity skip — fix CI rather than skipping.

```python
if execution.status == ExecutionStatus.FAILED:
    output = _get_activity_output(execution, "api_call")
    if not output.get("status_code"):
        pytest.skip("Backend could not reach httpbin — network connectivity issue in this environment")
assert execution.status == ExecutionStatus.COMPLETED
```

**Graceful skip for transient 502**: Nginx briefly returns 502 when the backend restarts under load. Catch `UnexpectedResponseException` from `syntara_api_client.types` and skip on status 502:

```python
from syntara_api_client.types import UnexpectedResponseException

try:
    result = syntara_api.workflows.get(workflow_id=wf.id).assert_and_get()
except UnexpectedResponseException as exc:
    if exc.status_code == 502:
        pytest.skip("Backend returned 502 Bad Gateway — transient infrastructure issue")
    raise
```

### Technology Stack

**Backend**: Python 3.12+, FastAPI, SQLModel, PostgreSQL 15, Temporal, Redis, regopy, uv, Alembic, pytest, mypy, ruff

**Frontend**: React 19, Vite, PatternFly 6, TanStack Query, Zustand, ReactFlow, Vitest, Playwright, npm workspaces
