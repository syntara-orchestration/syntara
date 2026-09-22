# AI Agent Instructions

Syntara is a distributed multi-agent automation system. This monorepo contains a Python/FastAPI backend (`backend/`) and a React/TypeScript frontend (`frontend/`).

Upstream policy for AI agent configuration (no executable hooks; what may live
under `.claude/`; review expectations) is in
[`.github/AI_AGENT_POLICY.md`](.github/AI_AGENT_POLICY.md).

## Component-Specific Standards

- [backend/AGENTS.md](backend/AGENTS.md) — SQLModel, Alembic migrations, uv, pytest, mypy, domain standards
- [frontend/AGENTS.md](frontend/AGENTS.md) — React 19, TypeScript, PatternFly 6, Vitest, Playwright, PR checklist

## Key Commands

```bash
make setup          # First-time bootstrap (install, secrets, services, migrations, seed)
make dev            # Start backend API (port 8000) + frontend dev server (port 5173)
make test           # Run the default backend and frontend tests
make lint           # Lint both codebases
make format         # Format both codebases
make typecheck      # Type-check both codebases
make gen-contracts  # Regenerate frontend TypeScript types from backend OpenAPI specs
make services-up    # Start infrastructure (DB, Redis, Temporal, Temporal UI/worker, MCP)
make services-down  # Stop infrastructure
```

## Rules

- Run `make install` before any checks or tests
- Backend API schema changes require `make gen-contracts` — include regenerated types in the same PR
- The root `podman-compose.yml` is the unified compose file; use `uv run podman-compose` to invoke it
- Backend-specific targets: `make -C backend help`

## Repository Structure

```text
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

## Skills

Skills live in `.claude/skills/` at the repository root, prefixed by workspace:

- **`frontend-*`** — Frontend-specific skills (coding standards, PR review, PatternFly UX, testing, Playwright E2E, library references)
- **`backend-*`** — Backend-specific skills (API spec drift detection)

User-invocable skills: `/frontend-review-pr`, `/frontend-build-ui-feature`, `/frontend-run-e2e`, `/backend-fix-api-spec-drift`. Reference skills (coding standards, testing guidelines, and similar) are loaded on demand when working on relevant files.

## Backend-Specific Targets

Run `make -C backend help` for the full list. Key targets include:

```bash
make -C backend test-all      # All tests including integration
make -C backend db-seed-all   # Seed DB with dev sample data
make -C backend db-clean      # Reset database (destructive)
```

## Port Map

| Service | Port | Notes |
|---|---:|---|
| Backend API | 8000 | `make dev` or `make -C backend dev` (HTTPS with self-signed cert) |
| Frontend UI | 5173 | `npm start` from `frontend/` |
| Mock API | 3000 | Standalone frontend dev without backend |
| Temporal UI | 8081 | Workflow monitoring |
| PostgreSQL | 5432 | Main + audit databases |
| Redis | 6379 | Cache, auth sessions |
| Storybook | 5174 | Component library + MCP server |
| MCP Server | 8765 | Test MCP server |

## API Contract Generation

Backend OpenAPI specs live at `backend/src/syntara/schemas/`. Frontend TypeScript types are generated into `frontend/packages/syntara-contracts/src/`.

```bash
make gen-contracts
```

When a backend PR changes API schemas, run this and include the regenerated types in the same PR. The generation scripts read directly from the local tree; no cross-repository cloning is needed.

## Cross-Cutting Concerns

### Full-Stack PRs

Backend API changes and UI consumption can land in the same PR. When changing an API:

1. Update the backend schema/router.
2. Run `make gen-contracts` to regenerate TypeScript types.
3. Update the frontend to use the new types.
4. Include all changes in one PR.

### Podman Compose

The root `podman-compose.yml` defines the full stack. The UI builds from `frontend/` instead of pulling a pre-built image. Backend services (DB, Redis, Temporal) use the same configuration as the standalone backend compose.

```bash
uv run podman-compose up --build
uv run podman-compose up -d database redis temporal
```

## Konflux CI Environment

Konflux (the Red Hat CI pipeline) runs E2E tests in a restricted environment that differs from local and GitHub CI. When E2E tests fail only in Konflux, apply the appropriate skip pattern rather than modifying the test logic.

For a known flaky test that needs temporary quarantine from the pipeline, follow the [test quarantine workflow](docs/ci/test-quarantine.md).

**Key Konflux constraints:**

- Konflux does **not** set `CI=true`; guards like `test.skip(!!process.env.CI, ...)` have no effect.
- The Temporal worker runs in a separate network namespace and may not reach external URLs such as httpbin.org even when the test runner can.
- Cluster load causes 30-second timeouts and transient 502 Bad Gateway responses.

### Backend pytest skip patterns

**`@requires_httpbin` class marker:** Apply this at class level when all tests in a class call httpbin. It skips the class when httpbin is unreachable from the test runner, but does not handle a Temporal worker that cannot reach httpbin.

**Graceful skip for backend connectivity failures:** When the Temporal worker cannot reach an external URL, execution completes with `status == FAILED` but the activity output contains no `status_code`. Add a skip guard:

```python
if execution.status == ExecutionStatus.FAILED:
    output = _get_activity_output(execution, "api_call")
    if not output.get("status_code"):
        pytest.skip("Backend could not reach httpbin — network connectivity issue in this environment")
assert execution.status == ExecutionStatus.COMPLETED
```

**Graceful skip for transient 502:** Nginx briefly returns 502 when the backend restarts under load. Catch `UnexpectedResponseException` from `syntara_api_client.types` and skip on status 502:

```python
from syntara_api_client.types import UnexpectedResponseException

try:
    result = syntara_api.workflows.get(workflow_id=wf.id).assert_and_get()
except UnexpectedResponseException as exc:
    if exc.status_code == 502:
        pytest.skip("Backend returned 502 Bad Gateway — transient infrastructure issue")
    raise
```

## Technology Stack

**Backend:** Python 3.12+, FastAPI, SQLModel, PostgreSQL 15, Temporal, Redis, regopy, uv, Alembic, pytest, mypy, ruff

**Frontend:** React 19, TypeScript 5.9, Vite, PatternFly 6, TanStack Query, Zustand, ReactFlow, Vitest, Playwright, npm workspaces
