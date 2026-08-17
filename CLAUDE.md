# Syntara Monorepo — Claude Agent Instructions

Syntara is a distributed multi-agent automation system. This monorepo contains the Python/FastAPI backend and the React/TypeScript frontend.

## Repository Structure

```
syntara/
├── backend/           # Python 3.12+ / FastAPI API, Temporal workflows, PostgreSQL
│   ├── src/syntara/   # Main Python package (domain-driven, auto-discovered routers)
│   ├── src/api_client/# Auto-generated Python API client (syntara-api-client)
│   ├── test-sdk/      # Shared pytest plugin (nexus-test-sdk) — installable via pip from git
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
| Frontend React/TypeScript | [frontend/CLAUDE.md](frontend/CLAUDE.md) — PatternFly patterns, 31-item PR checklist, architecture guides |
| Both (E2E, contracts, infra) | This file |

### Skills

Upstream AI agent policy (no executable hooks; private local settings; who may
change `.claude/`) is documented in
[`.github/AI_AGENT_POLICY.md`](.github/AI_AGENT_POLICY.md).

Skills live in `.claude/skills/` at the repo root, prefixed by workspace:

- **`frontend-*`** — Frontend-specific skills (coding standards, PR review, PatternFly UX, testing, Playwright E2E, library references)
- **`backend-*`** — Backend-specific skills (API spec drift detection)

User-invocable skills: `/frontend-review-pr`, `/frontend-build-ui-feature`, `/backend-fix-api-spec-drift`. Reference skills (coding standards, testing guidelines, etc.) are loaded automatically by Claude when working on relevant files.

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

### Technology Stack

**Backend**: Python 3.12+, FastAPI, SQLModel, PostgreSQL 15, Temporal, Redis, regopy, uv, Alembic, pytest, mypy, ruff

**Frontend**: React 19, TypeScript 5.9, Vite, PatternFly 6, TanStack Query, Zustand, ReactFlow, Vitest, Playwright, npm workspaces
