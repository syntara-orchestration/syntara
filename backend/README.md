# Syntara

A distributed multi-agent system. Syntara enables coordinated AI agents to work together on complex tasks.
[![Maintained](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://GitHub.com/syntara-orchestration/syntara/graphs/commit-activity)
[![CI](https://github.com/syntara-orchestration/syntara/actions/workflows/ci.yml/badge.svg)](https://github.com/syntara-orchestration/syntara/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue.svg)](https://pypi.python.org/pypi/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

## Architecture

Nexus is built with Python 3, FastAPI, SQLModel, and PostgreSQL.

The system follows a domain-driven design with automatic router discovery and standardized patterns.

### Key Technologies

- [**Python 3**](https://www.python.org/) - Core language
- [**FastAPI**](https://fastapi.tiangolo.com/) - Web framework with automatic OpenAPI generation
- [**SQLModel**](https://sqlmodel.tiangolo.com/) - Unified data modeling (combines Pydantic + SQLAlchemy)
- [**PostgreSQL 15**](https://www.postgresql.org/) - Primary database with async support
- [**Temporal**](https://temporal.io/) - Workflow orchestration engine for reliable multi-step task coordination
- [**uv**](https://docs.astral.sh/uv/) - Package management and execution
- [**Alembic**](https://alembic.sqlalchemy.org/) - Database migrations

### Project Structure

```
src/
└── nexus/
    ├── agent_orchestrator/    # Agent lifecycle management and request routing
    ├── api/                   # Legacy FastAPI routes (favour use of "domains")
    ├── audit/                 # Audit event tracking for system activities and user actions
    ├── core/                  # Base models, router discovery, database, utilities
    ├── example/               # Example implementations and WebSocket demos
    ├── files/                 # File management and document processing
    ├── invocations/           # Agent invocation tracking and execution
    ├── schemas/               # OpenAPI schema definitions for all domains
    ├── telemetry/             # Telemetry event collection and transmission
    ├── tool_manager/          # Tool provider interfaces and configuration
    ├── workflows/             # Temporal workflow definitions and engine
    └── ws/                    # WebSocket connection handling
```

### Domains

Each domain represents a set of related functionality and follows a consistent structure:

**Current domains:**
- **agent_orchestrator** - Manages agent lifecycle and routing requests to appropriate agents
- **audit** - Audit event tracking for system activities and user actions
- **files** - File management and storage operations
- **invocations** - Agent invocation tracking and execution history
- **tool_manager** - Tool provider interfaces and configuration
- **workflows** - Temporal workflow definitions and execution

```
src/syntara/{domain}/
├── router.py              # FastAPI routes (auto-discovered)
├── models/                # SQLModel classes
└── services/              # Business logic
```

**Router Discovery**: Routers in `src/syntara/{domain}/router.py` or `src/syntara/api/v1/{module}.py` are automatically discovered and registered.

## Developer Workflow

This project uses `uv` for dependency management and provides a comprehensive Makefile for development tasks.

### Prerequisites

- Python (3.12 or 3.13)
- `uv` package manager
- [Podman](https://podman.io/docs/installation) (for rootless containers)

### Installation

1. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Clone and setup the project**:
   ```bash
   git clone git@github.com:syntara-orchestration/syntara.git
   cd syntara/backend
   make install
   ```

### Dependency Management

This project uses `uv` for dependency management with two key files:

- **`uv.lock`** - The source of truth for exact dependency versions (managed by uv)
- **`requirements.txt`** - Production dependencies exported from `uv.lock` (for hermetic container builds)

**Keeping files in sync:**

The `requirements.txt` file **must always be in sync** with `uv.lock`. This is enforced automatically:

```bash
# Manually sync requirements.txt (if needed)
make sync-requirements

# Pre-commit hook automatically does the sync when uv.lock changes and CI will fail if requirements.txt is out of sync
```

### Quick Start

**Option 1: Full Stack with Containers (Recommended)**

**NOTE**: The UI image is private and requires authentication to the Quay Container Registry (quay.io) and read permissions.

You can authenticate with:

```bash
podman login quay.io -u <your_quay_username> -p <your_quay_password>
```

**IMPORTANT**: Before starting the services for the first time, you must build the container images:

```bash
# Build container images (required before first run)
make build-images
```

```bash
# Start all services (API, UI, Database, Temporal, Worker)
make run-all
```

**Option 2: Local Development**
```bash
# Install dependencies and setup project
make install

# Start the database (Terminal 1)
make db-run

# Start the cache/Redis (Terminal 2 — required for authentication)
make cache-run

# Start the development server (Terminal 3)
make dev

# Run tests
make test-all

# Check code quality
make lint
```

> **Note:** The API server requires Redis (`make cache-run`) for authentication and streaming. Authorization is evaluated in-process via regopy from `src/syntara/authz/rego/authz.rego`.

### Database Setup

The project includes a PostgreSQL 17 database for local development.

**Start database** (runs in foreground):
```bash
make db-run
# Press Ctrl+C to stop
```

**Reset database** (removes all data):
```bash
make db-clean
```

> **Schema baseline:** Alembic history was flattened into a single baseline. Databases
> created with the old revision chain cannot be upgraded in place — run `make db-clean`
> (or `podman compose down -v` for the full stack), then bring services back up so
> `alembic upgrade head` and seed run on an empty database.
> See [docs/standards/database.md](docs/standards/database.md#baseline).

**Database Configuration**:
The application uses these environment variables (with defaults):
- `APP_DB_USER` (default: `admin`)
- `APP_DB_PASSWORD` (default: `admin`)
- `APP_DB_HOST` (default: `localhost`)
- `APP_DB_PORT` (default: `5432`)
- `APP_DB_NAME` (default: `syntara_api`)
- `APP_DB_POOL_SIZE` (default: `10`)
- `APP_DB_MAX_OVERFLOW` (default: `20`)
- `APP_DB_POOL_TIMEOUT_SECONDS` (default: `30`)

You can override individual variables or set `APP_DATABASE_URL` directly:
```bash
export APP_DATABASE_URL="postgresql+asyncpg://user:pass@host:port/dbname?sslmode=require"
```

**Troubleshooting**:
- **Port conflict**: Copy `.env.example` to `.env` and change `APP_DB_PORT` to another value (e.g., 5433)
- **Container won't start**: Check the logs in the terminal where `make db-run` is running
- **Reset everything**: Stop the running database (Ctrl+C), then run `make db-clean`

### Data Modeling with SQLModel

**Important**: Nexus uses SQLModel as the single source of truth for both API schemas and database tables. **Never create separate Pydantic models** - SQLModel serves both purposes.

Most domain models should extend the `Resource` base class:

```python
from syntara.core.models import Resource

class ToolProvider(Resource, table=True):
    """Extends Resource with provider-specific fields."""
    __tablename__ = "tool_providers"

    enabled: bool = Field(default=True)
    configuration: dict[str, Any] = Field(sa_type=JSONB)
    # Inherits: id, name, description, timestamps, ownership, labels
```


### Temporal Workflow Engine Setup

The project uses Temporal for workflow orchestration. You can run Temporal locally with PostgreSQL backend.

**Start Temporal server and UI** (runs in foreground):
```bash
make temporal-run
# Press Ctrl+C to stop
```

**Start all services** (database + temporal + temporal UI + worker in background - recommended):
```bash
make services-run
# View logs: make services-logs
# Stop services: make services-stop
```

**Run Temporal worker separately** (for development without containers):
```bash
uv run python -m syntara.workflows.worker
# Or use: make worker-run
```

**Temporal Configuration**:
The application uses these environment variables (with defaults):
- `APP_TEMPORAL_ADDRESS` (default: `localhost:7233`)
- `APP_TEMPORAL_NAMESPACE` (default: `default`)
- `APP_TEMPORAL_PORT` (default: `7233`)
- `APP_TEMPORAL_UI_PORT` (default: `8081`)
- `APP_TASK_QUEUE` (default: `orchestrator-workflow-queue`)

**Access Temporal UI** (Development/Debugging Only):
Once Temporal is running, access the web UI at: http://localhost:8081

The UI is for **local development and debugging only**. The local UI allows you to:
- Monitor workflow executions in real-time
- View workflow history and activity details
- Debug failed workflows
- Query and filter workflows

**View individual service logs**:
```bash
make db-logs          # Database logs
make temporal-logs    # Temporal server and worker logs (containerized)
make temporal-ui-logs # Temporal UI logs
```

**Clean up Temporal data**:
```bash
make temporal-clean  # Stop Temporal server and UI only
make services-clean  # Stop and remove all data (database + temporal)
```

### Containerized Deployment

Nexus provides a complete containerized stack using `podman-compose` for easy deployment and development.

#### Available Services

The `podman-compose.yml` defines the following services:

| Service | Description | Port | Image |
|---------|-------------|------|-------|
| **database** | PostgreSQL 15 database | 5432 | `postgres:15` |
| **redis** | Cache service | 6379 | `redis-6-c9s` |
| **temporal** | Temporal workflow engine | 7233 | `temporalio/auto-setup:1.25.1` |
| **temporal-ui** | Temporal web UI (dev only) | 8081 | `temporalio/ui:2.31.2` |
| **temporal-worker** | Temporal workflow worker | - | Built from `containers/syntara/Containerfile` |
| **syntara** | Syntara API service | 8000 | Built from `containers/syntara/Containerfile` |
| **syntara-ui** | Syntara web interface | 8080 | Built from `../frontend/packages/syntara-ui/Containerfile` |

#### Container Commands

**Build container images** (required before first run):
```bash
make build-images
```

**Start all services** (foreground):
```bash
make run-all
# Access:
# - API: http://localhost:8000
# - UI: http://localhost:8080
# - Temporal UI: http://localhost:8081
# - Database: postgresql://admin:admin@localhost:5432/syntara_api
```

**Start all services** (background):
```bash
make services-run         # Start all services
make services-logs        # View logs from all services
make services-stop        # Stop all services
make services-clean       # Stop and remove all data (destructive)
```

**Individual service logs**:
```bash
make db-logs              # Database logs
make temporal-logs        # Temporal server and worker logs
make temporal-ui-logs     # Temporal UI logs
```

#### Running Multiple Instances

You can run multiple isolated instances of Nexus simultaneously using the `PODMAN_PROJECT` environment variable. This is useful for:
- Running different feature branches side-by-side
- Maintaining separate dev/staging environments locally
- Testing interactions between multiple Nexus instances

**Example: Running two instances**:
```bash
# Terminal 1: Run default instance
make services-run
# Containers: syntara_database_1, syntara_temporal_1, etc.

# Terminal 2: Run a separate dev instance
PODMAN_PROJECT=syntara-dev make services-run
# Containers: syntara-dev_database_1, syntara-dev_temporal_1, etc.
```

**Note**: Each instance requires unique ports. Configure ports via `.env` file or environment variables to avoid conflicts:
```bash
# For the second instance
export PODMAN_PROJECT=syntara-dev
export APP_DB_PORT=5433
export APP_API_PORT=8001
export APP_UI_PORT=8081
export APP_TEMPORAL_PORT=7234
export APP_TEMPORAL_UI_PORT=8082
export APP_CACHE_PORT=6380
make services-run
```

**Environment Variables**:

All services can be configured via `.env` file or environment variables:
Set `APP_ENV_FILE_PATH` to point at an alternate `.env` file if you want Nexus to load settings from a non-default location.

```bash
# Project Configuration
PODMAN_PROJECT=syntara  # Project name for container orchestration (default: syntara)
                      # Use this to run multiple isolated instances of Nexus
                      # Example: PODMAN_PROJECT=syntara-dev make services-run

# API Configuration
APP_API_PORT=8000

# UI Configuration
APP_API_URL=http://localhost:8000
APP_UI_PORT=8080
APP_UI_IMAGE=ghcr.io/syntara-orchestration/syntara-ui
APP_UI_VERSION=latest

# Database Configuration
APP_DB_HOST=localhost
APP_DB_PORT=5432
APP_DB_USER=admin
APP_DB_PASSWORD=admin
APP_DB_NAME=syntara_api
APP_DB_POOL_SIZE=10
APP_DB_MAX_OVERFLOW=20
APP_DB_POOL_TIMEOUT_SECONDS=30

# Cache Configuration
APP_CACHE_PORT=6379

# Temporal Configuration
APP_TEMPORAL_ADDRESS=localhost:7233
APP_TEMPORAL_PORT=7233
APP_TEMPORAL_UI_PORT=8081
APP_TEMPORAL_NAMESPACE=default
APP_TASK_QUEUE=orchestrator-workflow-queue

# Logging
APP_FALLBACK_LOG_LEVEL=INFO
```

### LLM and Agent Configuration

Nexus uses LangChain with OpenRouter for intelligent agent responses. The GenericAgent handles information queries using various LLMs.

**OpenRouter Setup**:

1. **Get your API key** from [https://openrouter.ai/keys](https://openrouter.ai/keys)

2. **Configure environment variables**:
   ```bash
   # Copy the example environment file
   cp .env.example .env

   # Edit .env (LLM credentials are configured on workflow agentic nodes)
   APP_OPENROUTER_MODEL=anthropic/claude-sonnet-4  # default model
   APP_OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
   ```

3. **Available models** (see [https://openrouter.ai/models](https://openrouter.ai/models)):
   - `anthropic/claude-3.5-sonnet` - Best for complex reasoning (default)
   - `openai/gpt-4` - OpenAI's most capable model
   - `google/gemini-pro` - Google's flagship model
   - `meta-llama/llama-3-70b` - Open source alternative
   - Many more available through OpenRouter

**Agent Routing**:

Nexus automatically routes requests to the appropriate agent:
- **GenericAgent**: Information queries, questions, explanations
  - Uses LangChain + OpenRouter LLM
  - Returns natural language responses
  - Example: "What tools are available for deployment?"

- **WorkflowGeneratorAgent**: Workflow creation requests
  - Uses Temporal workflows
  - Returns structured workflow results
  - Example: "Deploy customer service app to production"

**LLM Configuration**:

LLM API keys are provided through the credential system — attach an LLM Provider
credential to the workflow's agentic node. No global API key env var is needed.

**Environment Variables**:
- `APP_OPENROUTER_MODEL` (default: `anthropic/claude-sonnet-4`)
- `APP_OPENROUTER_BASE_URL` (default: `https://openrouter.ai/api/v1`)

**Example API Usage**:

First, ensure database migrations have been run:
```bash
uv run alembic upgrade head
```

Then you can invoke agents:

```bash
# 1. Create an information query (routes to GenericAgent)
curl -X POST http://localhost:8000/api/v1/invocations \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is Docker?", "createdBy": "550e8400-e29b-41d4-a716-446655440000", "sessionId": "session-456"}'

# Response includes the invocation ID and result:
# {
#   "id": "4e51166b-f57f-4f19-a04a-69ae9afc6e2f",
#   "status": "completed",
#   "result": {
#     "type": "answer",
#     "content": "Docker is a platform that packages applications...",
#     "metadata": {"model": "anthropic/claude-3.5-sonnet"}
#   },
#   ...
# }

# 2. Get invocation details by ID (NOTE: This endpoint is for testing/debugging)
# Use the "id" field from the response above
curl 'http://localhost:8000/api/v1/invocations/4e51166b-f57f-4f19-a04a-69ae9afc6e2f'

# 3. Workflow request (routes to WorkflowGeneratorAgent)
curl -X POST http://localhost:8000/api/v1/invocations \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Deploy customer service app to production", "createdBy": "550e8400-e29b-41d4-a716-446655440000", "sessionId": "session-789", "contextData": {"environment": "production"}}'

# 4. List all completed invocations
curl 'http://localhost:8000/api/v1/invocations?status=completed'
```

**NOTE**: The GET `/api/v1/invocations/{id}` endpoint is designed for **testing and debugging**. In production, you would typically use WebSockets or Server-Sent Events for real-time result streaming instead of polling this endpoint.

**Field Names**: The API uses camelCase field names per the OpenAPI contract:
- `createdBy` (UUID) - user identifier (previously `user_id`)
- `sessionId` (string) - session identifier (previously `session_id`)
- `contextData` (object) - additional context (previously `context`)
- Response fields: `id`, `createdAt`, `updatedAt`, `startedAt`, `completedAt`, etc.

### Development Commands

| Command | Description |
|---------|-------------|
| `make help` | Show all available commands |
| `make build-images` | Build container images (required before first run) |
| `make install` | Complete setup from scratch |
| `make dev` | Run development server with auto-reload |
| `make test-all` | Run all tests |
| `make check-migrations` | Validate migrations (chain, heads, pending, round-trip) |
| `make lint` | Run linting and type checking |
| `make format` | Format code |
| `make init-worktree` | Initialize a new git worktree for parallel development |

### Running Tests

```bash
# Run all tests
make test-all

# Run only unit tests
make test-unit

# Run only integration tests
make test-integration

# Run only CLI tests
make test-cli

# Validate migrations (spins up a temporary DB via testcontainers)
make check-migrations
```

### Coverage Reporting

```bash
# Run all tests with combined coverage report (HTML)
make test-coverage-report

# Run all tests with coverage report (XML for CI)
make test-coverage

# Run tests by layer with separate coverage reports
make test-unit-coverage        # Unit tests only → htmlcov-unit/
make test-cli-coverage         # CLI tests only → htmlcov-cli/
make test-integration-coverage # Integration tests only → htmlcov-integration/
```

### Running End to End Tests

```bash
make test-e2e
```

If `APP_BASE_URL` is not set, the target automatically starts the database and dev server, waits for the API to be ready, runs the tests, then tears everything down. If `APP_BASE_URL` is already set, it runs the tests against that instance directly.

> **Note:** The E2E tests use an auto-generated Python API client. If you change the OpenAPI schema, regenerate the client with `make generate-api-client` before running E2E tests.

### Nexus Test SDK

Reusable pytest fixtures for integration and E2E tests live in `test-sdk/`. The package is a pytest plugin (`pytest11` entry point), so fixtures are available automatically once installed — no `conftest.py` imports needed.

**Integration fixtures** (from `orchestrator_test_sdk.app.*`):

| Fixture | What it provides |
|---|---|
| `test_db_engine` / `test_db_session` | PostgreSQL testcontainer + per-test session |
| `test_cache` | Redis testcontainer |
| `session_app` / `base_client` / `auth_client` | FastAPI ASGI test clients |
| `jwt_client` / `jwt_access_token` | Real JWT authentication |
| `test_user` / `user_factory` / `admin_user` | User model fixtures |
| `test_group` / `group_with_members` | Group model fixtures |
| `test_workflow` / `test_execution` | Workflow model fixtures |
| `temporal_env` / `temporal_worker` | Temporal time-skipping environment |
| `mock_openrouter_llm` / `mock_websocket` | Mock infrastructure |
| `credential_factory` / `integration_factory` | DB-backed factory helpers |

**Local shared fixtures** (import directly — not from the SDK):

| Module | What it provides |
|---|---|
| `tests.fixtures.settings` | `FakeSettingsCache`, `override_settings`, `override_runtime_settings`, `fast_retry_settings` |
| `tests.fixtures.files` | `generate_large_file`, `get_fixtures_dir` (sample files in `tests/fixtures/files/`) |
| `tests.fixtures.encryption` | `OLD_KEY`, `NEW_KEY`, `WRONG_KEY`, `ZEROS_KEY` constants |
| `tests.fixtures.tls` | `generate_self_signed_cert`, `generate_server_cert`, `generate_crl` |
| `tests.fixtures.temporal` | `CompleteAsyncError` alias |
| `tests.integration.helpers.workflow` | `WorkflowFactory`, `ActivitiesFactory` (DB-backed) |
| `tests.integration.helpers.approval` | `ApprovalsFactory` (DB-backed) |
| `tests.unit.fixtures.approval` | `create_test_approval_request`, `create_approved_approval_request` |
| `tests.unit.fixtures.mock_mcp_provider` | `MockMCPProvider` |

**E2E fixtures** (from `orchestrator_test_sdk.e2e.*` — module-scoped, auto-cleanup):

| Fixture | What it creates |
|---|---|
| `create_user` | Local user → `(user_id, username, password)` |
| `create_group` | Group → `(group_id, name)` |
| `create_project` | Project → `(project_id, name)` |
| `create_project_role` | Project-scoped role → role name |
| `assign_project_role_to_user` / `_to_group` | Project role assignment → assignment id |
| `create_role` | System-scoped role → role name |
| `assign_system_role` | System role assignment → assignment id |
| `create_policy` | Deny policy → policy name |
| `create_credential` | HTTP Bearer Token credential → `(id, name, dict, secret)` |
| `create_workflow` | Minimal workflow → `(workflow_id, name)` |
| `identity_provider_factory` | OIDC identity provider → provider object |

**Installing in another repository**:

Both `syntara-api-client` (the generated API client) and `orchestrator-test-sdk` live in this repo and can be installed directly from git using pip's subdirectory syntax:

```toml
# pyproject.toml — uv / pip
dependencies = [
    "syntara-api-client @ git+https://github.com/syntara-orchestration/syntara.git#subdirectory=backend/src/api_client",
    "orchestrator-test-sdk @ git+https://github.com/syntara-orchestration/syntara.git#subdirectory=backend/test-sdk",
]
```

Or one-off installs:

```bash
pip install "git+https://github.com/syntara-orchestration/syntara.git#subdirectory=backend/src/api_client"
pip install "git+https://github.com/syntara-orchestration/syntara.git#subdirectory=backend/test-sdk"
```

To pin to a specific commit or branch, append `@<ref>` before `#subdirectory`:

```
git+https://github.com/syntara-orchestration/syntara.git@main#subdirectory=backend/test-sdk
```

### Code Quality

This project enforces strict code quality standards. All formatting tools are pinned in `.pre-commit-config.yaml`, which is the single source of truth for tool versions. See [Formatting Standards](docs/standards/formatting.md) for details.

```bash
# Format code (modifies files)
make format

# Verify linting, formatting, and types (may update generated files on first run)
make lint

# Run only type checking
make typecheck
```

**Type checking is mandatory** — all code must pass mypy in strict mode.

**Expected workflow:** `make format` then `make lint`. If lint fails due to generated file drift (OpenAPI spec, API client), run `make lint` again to confirm convergence.

### Commit Message Format

This project requires commit messages to follow the [Conventional Commits](https://www.conventionalcommits.org/) specification. Examples:

```
feat: add user authentication system
fix: resolve database connection timeout
docs: update API documentation
refactor: simplify error handling logic
```

### Development Server

```bash
# Start development server (auto-reload enabled)
make dev
```

### Project Configuration

- **Dependencies**: Managed with `uv` (see `pyproject.toml`)
- **Code formatting**: Ruff
- **Type checking**: MyPy with strict configuration
- **Testing**: Pytest with coverage reporting

### Troubleshooting

**Dependencies not found?**
```bash
make install
```

**Server won't start?**
```bash
make check-deps
```

**Need to clean everything?**
```bash
make clean
make install
```

For more information, run `make help` to see all available commands.

## Telemetry

Telemetry is always enabled and collects workflow execution metrics for product improvement. No PII or credentials are collected.

### Collected Data

**Workflow execution events:**

- `workflow_execution_id` -- unique execution identifier (UUID v4)
- `status` -- final execution status (completed, failed, cancelled)
- `duration_ms` -- execution duration in milliseconds
- `activity_count` -- total number of activities executed
- `error_count` -- number of activities that failed
- `error_type` -- categorized error type (if failed)

**Activity execution events:**

- `workflow_execution_id` -- parent workflow execution identifier
- `activity_type` -- type of activity (task, parallel, sequence, condition, loop, converge, approval)
- `activity_hash` -- SHA-256 hash of the activity definition (anonymized)
- `status` -- execution outcome (completed, failed, skipped, cancelled)
- `duration_ms` -- activity duration in milliseconds
- `action_type` -- action type for task activities
- `inbound_activities` -- hashes of preceding activities in the execution graph
- `outbound_activities` -- hashes of following activities in the execution graph
- `error_type` -- categorized error type (if failed)

**API call events:**

- `endpoint` -- request path
- `http_method` -- HTTP request method
- `status_code` -- HTTP response status code
- `response_time_ms` -- response time in milliseconds
- `request_payload_size` -- request body size in bytes

### Configuration

Telemetry is configured via environment variables:

- `APP_SEGMENT_WRITE_KEY` -- Segment.com write key for event transmission
- `APP_SEGMENT_ENDPOINT` -- Segment.com endpoint URL

## Observability & Metrics

Nexus exposes two metrics surfaces: a Prometheus-compatible scrape endpoint for production monitoring, and an internal JSON API for ad-hoc performance testing.

### `GET /metrics` — Prometheus / OpenMetrics

A standard Prometheus text-exposition endpoint. Point any Prometheus-compatible scraper at it to collect counters, histograms, and gauges covering request traffic, LLM calls, workflow execution, cache performance, database queries, and more.

Metrics are **per-instance and in-memory** — each service instance maintains its own counters and histograms, and they reset to zero on restart. A Prometheus-compatible scraper should poll this endpoint at a regular interval to capture data before it is lost.

**Enabled by default.** Disable via environment variable:

```bash
APP_METRICS_OPENMETRICS_ENABLED=false   # returns 404 when disabled
```

**Example scrape:**

```bash
curl http://localhost:8000/metrics
```

### `/_internal/metrics/*` — Performance-Testing JSON API

A set of hidden JSON endpoints for querying raw, in-memory metric records during performance-testing or debugging sessions. These routes are **not** listed in `/docs` or `/openapi.json`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/_internal/metrics/summary` | GET | Totals, retention window, record counts by type |
| `/_internal/metrics/records` | GET | Paginated raw `MetricRecord` list (filterable by type, category, labels) |
| `/_internal/metrics/kpis` | GET | Full KPI dashboard with percentiles, rates, and distributions per component |
| `/_internal/metrics/kpis/{component}` | GET | KPI summary for a single component (e.g. `llm`, `database`, `api_service`) |
| `/_internal/metrics/reset` | POST | Clear the in-memory store and counters |

**Disabled by default.** Enable at runtime through the Settings API — no restart required:

```bash
# Enable via the Settings API (requires setting:write permission)
curl -X PATCH http://localhost:8000/api/v1/settings/metrics.perf_test_mode \
  -H "Content-Type: application/json" \
  -d '{"value": true}'
```

When the setting is toggled back to `false`, the in-memory store is automatically flushed.

## Code Quality

Code quality and coverage are tracked via SonarCloud. SonarCloud analysis runs automatically on all PRs with coverage reports from unit, CLI, and integration test suites.

## Further reading

- 📖 **[Developer Getting Started Guide](docs/developer-getting-started.md)** - Architecture deep dive with examples
- 📖 **[Development with Worktrees Guide](docs/development-with-worktrees.md)** - Parallel development setup
- 📖 **[Architecture Decision Records](decision-records.md)** - Design rationale and decisions
