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
- **kubectl** and either [Kind](https://kind.sigs.k8s.io/) or [Minikube](https://minikube.sigs.k8s.io/) (Execution Plane development)
- **Make** (orchestration)

## Quick Start

```bash
# One-time setup: install deps, generate secrets + TLS certs, build images,
# start infrastructure, migrate, and seed
make setup

# Host-based development: create/register the local EP cluster, then start
# the API, frontend, and standalone EP worker
make dev

# Or register the local EP cluster and run the full stack with a containerized
# EP worker
make -C backend run-all
```

## Common Commands

| Command | Description |
|---|---|
| `make install` | Install backend and frontend dependencies |
| `make dev` | Create/register the local EP cluster and start the backend, frontend, and standalone EP worker |
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
podman-compose up database redis temporal syntara
```

## Code Quality

Code quality and coverage are tracked via SonarCloud:

- **Backend**: [SonarCloud Dashboard](https://sonarcloud.io/project/overview?id=syntara-backend)
- **Frontend**: [SonarCloud Dashboard](https://sonarcloud.io/project/overview?id=syntara-frontend)

SonarCloud analysis runs automatically on all PRs. Quality gate results are **informational only**, pass/fail status is visible in the PR checks list but does not block merges. The required status checks for merge are `(Backend) Required Checks` and `(Frontend) Required Checks`, which cover linting, tests, type-checking, and builds.

## Contributing

* [Project wide guidelines](CONTRIBUTING.md)
* [Backend contributor guide](docs/backend-contributing.md)
* [Frontend contributor guide](docs/frontend-contributing.md).

## Community

Have a question or idea? Start a conversation in [GitHub Discussions](https://github.com/orgs/syntara-orchestration/discussions).

## AI Contributions

AI-assisted contributions are welcome and held to the same review and quality standards as any other contribution. Contributors take full responsibility for AI-assisted work and MUST disclose significant use of AI tools via a commit trailer, for example: `Assisted-by: Opus 4.6`. Grammar and stylistic corrections do not need disclosure.

See [AI_POLICY.md](.github/AI_POLICY.md) for the full policy.

## License

[Apache License 2.0](LICENSE)
