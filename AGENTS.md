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
make test           # Run all tests
make lint           # Lint both codebases
make format         # Format both codebases
make typecheck      # Type-check both codebases
make gen-contracts  # Regenerate frontend TypeScript types from backend OpenAPI specs
make services-up    # Start infrastructure (DB, Redis, Temporal, Temporal UI/worker, MCP)
```

## Rules

- Run `make install` before any checks or tests
- Backend API schema changes require `make gen-contracts` — include regenerated types in the same PR
- The root `podman-compose.yml` is the unified compose file; use `uv run podman-compose` to invoke it
- Backend-specific targets: `make -C backend help`
