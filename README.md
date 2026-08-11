# Syntara Monorepo

Monorepo combining the Syntara backend (Python/FastAPI) and frontend (React/TypeScript) into a single development and deployment environment.

## Repository Structure

```
syntara/
├── backend/          # Python 3.12+ / FastAPI API server, Temporal workflows
├── frontend/         # React 19 / TypeScript UI (npm workspaces)
├── Makefile          # Root orchestration (delegates to backend/ and frontend/)
├── podman-compose.yml # Full-stack local development
└── .env.example      # Combined environment variables
```

See [backend/README.md](backend/README.md) and [frontend/README.md](frontend/README.md) for component-specific documentation.

## Prerequisites

- **Python 3.12+** and [uv](https://docs.astral.sh/uv/) (backend)
- **Node.js 22+** and npm (frontend)
- **Podman** or Docker (container-based development)
- **Make** (orchestration)

## Quick Start

```bash
# One-time setup: install deps, generate secrets + TLS certs, build images, start services, migrate, seed
make setup

# Start full-stack development (backend API + frontend UI)
make dev

# Or use containers for the full stack
make -C backend run-all
```

## Common Commands

| Command | Description |
|---|---|
| `make install` | Install backend and frontend dependencies |
| `make dev` | Start backend and frontend dev servers |
| `make test` | Run backend and frontend tests |
| `make test-all` | Run all tests including integration |
| `make lint` | Lint both codebases |
| `make format` | Format both codebases |
| `make typecheck` | Type-check both codebases |
| `make gen-contracts` | Regenerate TypeScript types from backend OpenAPI specs |

## Contract Generation

TypeScript API types are generated from the backend's OpenAPI specifications. In this monorepo, the specs are read directly from the local tree — no cross-repo cloning needed:

```bash
make gen-contracts
```

This reads specs from `backend/src/syntara/schemas/` and generates types in `frontend/packages/syntara-contracts/src/`.

## Container Development

The root `podman-compose.yml` provides the full stack: PostgreSQL, Redis, Temporal, the Syntara API, and the UI. The UI service builds from `frontend/` instead of pulling a pre-built image.

```bash
# Start all services
podman-compose up --build

# Start specific services
podman-compose up database redis temporal nexus
```

## Code Quality

Code quality and coverage are tracked via SonarCloud:

- **Backend**: [SonarCloud Dashboard](https://sonarcloud.io/project/overview?id=syntara-backend)
- **Frontend**: [SonarCloud Dashboard](https://sonarcloud.io/project/overview?id=syntara-frontend)

SonarCloud analysis runs automatically on all PRs. Quality gate results are **informational only**, pass/fail status is visible in the PR checks list but does not block merges. The required status checks for merge are `(Backend) Required Checks` and `(Frontend) Required Checks`, which cover linting, tests, type-checking, and builds.

## Contributing

* [Project wide guidelines](CONTRIBUTING.md)
* [backend/CONTRIBUTING.md](backend/CONTRIBUTING.md)
* [frontend/CONTRIBUTING.md](frontend/CONTRIBUTING.md).

## AI Contributions

The use of AI tools MUST be explicitly disclosed by the author when a significant part of the contribution is taken from the AI tools output without significant changes. Grammar, spelling, and stylistic corrections do not need disclosure.

We recommend using the following statement as a disclosure: `Assisted-by:` followed by any information about the contributor’s use of AI tools that they consider relevant, for example:

      i. `Assisted-by: gpt-5.4`
      ii. `Assisted-by: Opus 4.6`
      iii. `Assisted-by: locally trained model`


See [AI_POLICY.md](.github/AI_POLICY.md) for more details.

## License

[Apache License 2.0](LICENSE)
