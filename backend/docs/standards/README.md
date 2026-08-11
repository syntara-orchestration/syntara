# Nexus Development Standards

This directory contains prescriptive standards for the Nexus project. Each document covers a specific domain and defines both tooling-enforced rules and conventions that require human/agent judgment.

## Standards Index

### Authoritative Documents (elsewhere in repo)

These existing documents define core standards and should be consulted first:

| Document | Scope |
|----------|-------|
| [Decision Records](../../decision-records.md) | Technology choices and rationale (Temporal, FastAPI, SQLModel, Redis, structlog, etc.) |
| [Error Handling Strategy](../error-handling-strategy.md) | RFC 9457 compliance, exception patterns, security |
| [AGENTS.md](../../AGENTS.md) | AI agent instructions, technology choices, development workflow |
| [CONTRIBUTING.md](../../CONTRIBUTING.md) | Human contributor guide, PR process |

### Standards in This Directory

| Document | Scope |
|----------|-------|
| [Access Control](access-control.md) | Authentication, RBAC (PermissionChecker/VisibilityFilter), compliance tests, exclusion lists |
| [Testing](testing.md) | Test organization, naming, fixtures, markers, infrastructure |
| [Imports and Modules](imports-and-modules.md) | Import ordering, `__init__.py` patterns, domain module structure |
| [Logging](logging.md) | structlog usage, log levels, structured context, security |
| [Dependency Management](dependency-management.md) | Version pinning, uv workflow, requirements sync |
| [Observability](observability.md) | Prometheus metrics, Segment telemetry, instrumentation patterns |
| [WebSocket](websocket.md) | Connection lifecycle, streaming handlers, message formats, close codes |
| [Redis](redis.md) | Stream operations, connection management, key naming, TTL policies |
| [Configuration](configuration.md) | Pydantic Settings patterns, env vars, constants module, adding new settings, testing |
| [API Response Format](api-response-format.md) | List responses, pagination, filtering, sorting, CRUD endpoint conventions, model naming, field validators |
| [Database](database.md) | Connection pooling, migrations, label filtering, GIN indexes, session management |
| [Services](services.md) | BaseService, extension mixins, dependency injection, middleware, periodic workers |
| [Exceptions](exceptions.md) | Exception naming, error handlers, PROBLEM_TYPES, @fastapi_exception, retry classification |
| [OpenAPI Spec Management](openapi-spec-management.md) | Sub-spec layout, bundling, drift detection, CI checks, AsyncAPI conventions |
| [UI-API Parity](ui-api-parity.md) | Typed clients, contract generation, full-stack PR workflow, WebSocket scope |
| [Static Analysis](static-analysis.md) | Dead code detection (Vulture), import cycle detection (pyan3), CI checks, allowlists |
| [Formatting](formatting.md) | Pre-commit as single source of truth, tool inventory, generated file cleanup, adding formatters |
| [Locks](locks.md) | Thread safety, lock types, best practices, state machines, protected counters, testing |
| [Questions](questions.md) | Open questions, inconsistencies, areas needing investigation |

### Tooling Configuration (enforces standards)

| File | What it enforces |
|------|-----------------|
| `pyproject.toml` | Ruff rules (ALL), mypy strict mode, pytest config, coverage thresholds, Vulture config |
| `.pre-commit-config.yaml` | Formatting, type checking, conventional commits, YAML, requirements sync |
| `.github/workflows/ci.yml` | CI gates: pre-commit, dead code check, cycle detection, tests (3.12 + 3.13), migration checks, coverage, E2E |
| `sonar-project.properties` | SonarCloud code quality scanning |
| `renovate.json` | Automated dependency updates (weekly, in-range-only) |

## How to Use These Standards

**For AI agents:** AGENTS.md references this directory. When working on Nexus, consult the relevant standard before making changes. Standards define what the codebase expects — follow them unless there's a documented reason to deviate.

**For developers:** These standards codify existing patterns. If you find the codebase diverges from a standard, either update the code to match or propose an amendment to the standard via PR.

**Adding a new standard:** Create a markdown file in this directory, add it to the index above, and reference it from AGENTS.md.
