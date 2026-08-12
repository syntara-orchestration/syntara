# Testing Standards

This document defines the testing conventions for the Nexus project. These standards ensure consistency, maintainability, and reliability across the test suite.

## Directory Structure

All tests reside under `tests/` and are organized by test type:

```
tests/
├── __init__.py
├── cli/                 # CLI tests (orchestrator-cli package)
│   ├── test_spec.py
│   └── test_generated_client_lazy_imports.py
├── e2e/                 # End-to-end tests (full stack required)
│   ├── approvals/
│   ├── auth/
│   ├── authz/
│   ├── credentials/
│   ├── integrations/
│   ├── service_accounts/
│   ├── settings/
│   ├── tool_manager/
│   └── workflows/
├── helpers/             # Test helper utilities
├── integration/         # Integration tests (database, services)
│   ├── admin/
│   ├── agent_orchestrator/  # Includes context_manager/, services/, token_manager/, tool_manager/
│   ├── api/             # API endpoint tests
│   ├── approvals/       # Approvals tests (contract tests for API endpoints)
│   ├── audit/           # Includes retention/
│   ├── authz/           # Authorization tests
│   ├── core/            # Includes auth/, cache/, database/, websocket/, workers/
│   ├── credentials/     # Credentials tests
│   ├── files/           # Includes document_conversion/
│   ├── integrations/    # Integration tests
│   ├── invocations/     # Invocation tests (includes contract tests)
│   ├── metrics/         # Metrics tests
│   ├── projects/        # Projects tests
│   ├── settings/        # Settings tests
│   ├── telemetry/       # Telemetry tests (includes contract tests)
│   ├── tool_manager/    # Tool manager tests
│   ├── users/           # User management tests
│   ├── websocket/       # WebSocket tests
│   └── workflows/       # Includes examples/, fixtures/, services/, workflow_engine/
├── performance/         # Performance tests (opt-in via --run-performance)
│   ├── agent_orchestration/
│   ├── agent_orchestrator/
│   ├── api_service/
│   ├── audit/
│   ├── authentication/
│   ├── chat_window/
│   ├── cli/
│   ├── cost_tracking/
│   ├── database/
│   ├── e2e_agentic/
│   ├── execution_service/
│   ├── files/
│   ├── invocation_service/
│   ├── llm_model/
│   ├── model_management/
│   ├── routing_service/
│   ├── system_wide/
│   ├── telemetry/
│   ├── temporal_worker/
│   ├── tool_manager/
│   ├── websocket/
│   └── workflow_engine/
└── unit/                # Unit tests (isolated, no external deps)
    ├── aap/                 # Includes models/, services/
    ├── admin/
    ├── agent_orchestrator/  # Includes agents/, audit/, clients/, context_manager/, executor/, models/, services/, token_manager/, tool_manager/, utils/, ws/
    ├── orchestrator_admin/
    ├── api/                 # Includes v1/
    ├── approvals/           # Includes clients/, models/
    ├── audit/               # Includes events/, export/, models/, outbox/, retention/, services/
    ├── auth/
    ├── authz/               # Includes audit/, services/
    ├── core/                # Includes auth/, cache/, config/, database/, lib/, logging/, models/, router/, services/, utils/, websocket/, workers/
    ├── credentials/         # Includes audit/, cli/, lib/, services/
    ├── files/               # Includes audit/, document_conversion/, models/, retrievers/, validators/
    ├── identity_providers/  # Includes audit/, models/, services/
    ├── integrations/        # Includes models/, services/
    ├── invocations/         # Includes audit/, models/, services/
    ├── metrics/
    ├── projects/            # Includes services/
    ├── schemas/
    ├── service_accounts/
    ├── settings/            # Includes audit/, cache/, models/, services/
    ├── telemetry/           # Includes events/, handlers/
    ├── tool_manager/        # Includes audit/, lib/, models/, services/
    ├── users/               # Includes models/, services/
    └── workflows/           # Includes activities/, audit/, clients/, models/, services/, signals/, utils/, validators/, workflow_engine/, ws/
```

**Organization Rules:**

- Test directory structure mirrors `src/syntara/` hierarchy within each test category
  - Example: `tests/unit/agent_orchestrator/` maps to `src/syntara/agent_orchestrator/`
- Domain-specific conftest files provide domain-specific fixtures at appropriate hierarchy levels
- Sample test files (PDFs, images, documents) live in `tests/fixtures/files/` and are accessed via `get_fixtures_dir()` from `tests.fixtures.files`
- Shared unit/integration fixtures live in `tests/fixtures/` (settings, files, encryption, tls, temporal helpers)
- Integration-only factory helpers (e.g. `WorkflowFactory`, `ApprovalsFactory`) live in `tests/integration/helpers/`
- Unit-only fixtures and mocks (e.g. `MockMCPProvider`) live in `tests/unit/fixtures/`
- Reusable test utilities go in `tests/helpers/`

## File Naming

- Test files MUST use `test_*.py` prefix pattern exclusively
- NEVER use `*_test.py` suffix pattern
- Test file names should clearly indicate what is being tested
  - Good: `test_user_model.py`, `test_workflows_get.py`
  - Bad: `user_tests.py`, `workflows.py`

## Test Type Definitions

### Unit Tests (`tests/unit/`)

**Scope:** Test a single unit of code in isolation.

**Characteristics:**
- No external dependencies (no database, network, file system)
- Use mocks for all external interfaces
- Fast execution (milliseconds)
- Function-scoped fixtures only
- Test internal logic, edge cases, validation
- **Do not use `user_factory` or other database-persisting fixtures** — construct model objects directly. Session-scoped seeders (e.g., `run_seeders` in `session_app`) pre-populate the database with system data (service principals, admin user, default groups). Using factories that INSERT rows with seeded IDs causes `IntegrityError` under parallel execution when the test lands on a worker where the seeder has already run.

**Marker:** `@pytest.mark.unit` (optional, inferred by location)

**Example:**
```python
"""Unit tests for User model.

Tests cover:
- User creation with required fields
- Soft delete behavior
- Role enum validation
"""

def test_create_user_with_required_fields(
    default_user_data: dict[str, Any],
) -> None:
    """Test creating a user with all required fields."""
    user = User(id=uuid4(), **default_user_data)

    assert user.id is not None
    assert user.username == default_user_data["username"]
```

### Integration Tests (`tests/integration/`)

**Scope:** Test interaction between multiple components.

**Characteristics:**
- Uses real database (testcontainers)
- Tests API endpoints, repository layer, service integration
- Slower than unit tests (seconds)
- Session-scoped database fixtures, function-scoped sessions
- Tests component interactions, data persistence

**Marker:** `@pytest.mark.integration` (optional, inferred by location)

**Example:**
```python
"""Integration tests for GET /api/v1/workflows endpoint.

Tests for listing workflows with filtering and pagination.
"""

async def test_get_workflows_empty_list(base_client: AsyncClient) -> None:
    """Test getting workflows when none exist.

    Expected: 200 OK with empty array
    """
    response = await base_client.get("/api/v1/workflows")
    assert response.status_code == 200
    data = response.json()
    assert "resources" in data
    assert isinstance(data["resources"], list)
```

### Contract Tests (Organized by Domain)

**Scope:** Verify API contracts (request/response schemas, status codes, error formats).

**Location:** Contract tests are now integrated into domain directories within `tests/integration/`:
- `tests/integration/approvals/` - Approval API contract tests
- `tests/integration/invocations/` - Invocation API contract tests  
- `tests/integration/telemetry/` - Telemetry API contract tests
- `tests/integration/workflows/` - Workflow API contract tests

**Characteristics:**
- Tests API shape, not business logic
- Validates OpenAPI compliance
- Tests error cases and edge cases comprehensively
- Uses real or test database
- Fast feedback on API breaking changes
- Authz evaluator mocking provided automatically by root integration conftest

**Marker:** None (location-based)

**Example:**
```python
"""Contract tests for invocation file upload API.

Tests MUST FAIL before implementation (TDD approach).
"""

async def test_file_upload_invalid_file_type(base_client: AsyncClient) -> None:
    """Test file upload with invalid file type.

    Expected: 400 Bad Request with error details
    """
    # Test implementation
```

### End-to-End Tests (`tests/e2e/`)

**Scope:** Test complete user workflows across the entire system.

**Characteristics:**
- Requires full stack running (Nexus API, Temporal, MCP server, OpenRouter)
- Uses production-like configuration
- Tests real user scenarios end-to-end
- Slowest execution (minutes)
- Uses auto-generated API client (`syntara-api-client`)

**Marker:** `@pytest.mark.e2e` (REQUIRED)

**Running E2E Tests:**
- Auto-starts services if `APP_BASE_URL` not set: `make test-e2e`
- Uses existing services if `APP_BASE_URL` is set

**API Client Rules (REQUIRED):**

- All API calls MUST use the auto-generated client under `src/api_client/syntara_api_client/` — do NOT call HTTP libraries (e.g., `requests`, `httpx`) directly in test files
- All API calls MUST go through the `syntara_api` fixture (type: `SyntaraApiRegistry`)
- Use the typed property for the relevant API group: `syntara_api.workflows`, `syntara_api.executions`, `syntara_api.approvals`, `syntara_api.invocation`, `syntara_api.tool_manager`, `syntara_api.files`, `syntara_api.default`

**Example:**
```python
"""E2E tests for GET endpoints: workflows and approvals."""

import pytest
from syntara_api_client.api import SyntaraApiRegistry

pytestmark = pytest.mark.e2e

class TestWorkflows:
    """E2E tests for workflow GET endpoints."""

    def test_list_workflows(self, syntara_api: SyntaraApiRegistry) -> None:
        workflows = syntara_api.workflows.list().assert_and_get()
        assert isinstance(workflows.resources, list)
```

### Performance Tests (`tests/performance/`)

**Scope:** Measure and validate performance characteristics.

**Characteristics:**
- Excluded from default test runs
- Opt-in via `--run-performance` flag or `make test-performance`
- Tests response times, throughput, resource usage
- May use specialized fixtures (performance_db_engine)

**Marker:** `@pytest.mark.performance` (REQUIRED)

**Example:**
```python
import pytest

@pytest.mark.performance
async def test_workflow_execution_performance(base_client: AsyncClient) -> None:
    """Test workflow execution completes within acceptable time."""
    # Performance test implementation
```

## conftest.py Hierarchy

The project uses a two-level conftest structure. Base fixtures come from the `orchestrator-test-sdk` plugin (installed as a `pytest11` entry point) — no root `tests/conftest.py` is needed.

**`orchestrator-test-sdk` plugin (registered via `pytest_plugins` in `plugin.py`):**
- Session-scoped database engine and Redis cache (testcontainers)
- Temporal test environment and worker fixtures
- FastAPI test clients (`base_client`, `auth_client`, `jwt_client`, `session_app`)
- Model factories: users, workflows, groups, tools, credentials, executions
- Mock fixtures: `mock_openrouter_llm`, `mock_websocket`
- Pytest hooks: performance test filtering, lock file cleanup, `worker_id`
- E2E helpers: `ExecutionsFactory`, `create_minimal_workflow_definition`, `ExampleMCPServer`

**Local shared fixtures (`tests/fixtures/`)** — import directly, no plugin needed:
- `settings.py` — `FakeSettingsCache`, `override_settings`, `override_runtime_settings`, `fast_retry_settings`
- `files.py` — `generate_large_file`, `get_fixtures_dir` (sample files in `tests/fixtures/files/`)
- `encryption.py` — `OLD_KEY`, `NEW_KEY`, `WRONG_KEY`, `ZEROS_KEY` constants
- `tls.py` — `generate_self_signed_cert`, `generate_server_cert`, `generate_crl`
- `temporal.py` — `CompleteAsyncError` alias

**Integration-only factory helpers (`tests/integration/helpers/`):**
- `workflow.py` — `WorkflowFactory`, `ActivitiesFactory` (DB-backed creation)
- `approval.py` — `ApprovalsFactory` (DB-backed approval creation)

**Unit-only fixtures (`tests/unit/fixtures/`):**
- `approval.py` — `create_test_approval_request`, `create_approved_approval_request`
- `mock_mcp_provider.py` — `MockMCPProvider`

**Test-type conftest files:**
- `tests/integration/conftest.py` — template-based DB isolation (PostgreSQL `TEMPLATE` restore per test), authz evaluator mock, moto S3 mock, `test_project_id`
- `tests/unit/conftest.py` — authz cache reset, encryption key env var, resource-actions registry init

**Domain-level conftest files:**
- Provide domain-specific fixtures (e.g., TLS bypass, seeded authz data, credential types)
- Override SDK fixtures where integration semantics differ (e.g., `test_db_session` uses real commits in integration, rollback in unit)
- Keep fixtures close to tests that use them

**Fixture Scoping Rules:**

- **Session scope:** Expensive resources shared across all tests
  - Database engine (`test_db_engine`)
  - Temporal environment (`temporal_env`)
  - Redis container
- **Function scope:** Test isolation (default)
  - Database sessions (`test_db_session`)
  - Test clients (`base_client`, `authenticated_client`)
  - Test data (users, workflows, tools)
- **Module scope:** Rare, use only when necessary for performance

**Fixture Location Guidelines:**

1. If used by e2e or performance tests (and possibly integration) → `orchestrator-test-sdk` plugin
2. If shared between unit and integration tests → `tests/fixtures/` module (import directly)
3. If only needed by integration tests as a factory helper → `tests/integration/helpers/`
4. If only needed by unit tests → `tests/unit/fixtures/`
5. If specific to a domain (workflows, agents, tools) → domain conftest
6. If used in one test file → define in that file

## Pytest Markers

Configure markers in `pyproject.toml` under `[tool.pytest.ini_options]`.

**Available Markers:**

- `slow` — Tests that take >5 seconds (deselect with `-m "not slow"`)
- `integration` — Integration tests (inferred by location)
- `unit` — Unit tests (inferred by location)
- `mcp` — Tests requiring MCP server infrastructure (deselect with `-m "not mcp"`)
- `performance` — Performance tests (excluded by default, run with `--run-performance`)
- `e2e` — End-to-end tests (required for tests in `tests/e2e/`)
- `pipeline(test_phase=str)` — E2E test phase classification for PR filtering (e.g., `test_phase="pr-check"`)

**When to Apply Markers:**

- `@pytest.mark.e2e` — REQUIRED for all tests in `tests/e2e/`
- `@pytest.mark.performance` — REQUIRED for all tests in `tests/performance/`
- `@pytest.mark.mcp` — REQUIRED for tests that start MCP test servers
- `@pytest.mark.pipeline(test_phase="pr-check")` — Optional, for E2E tests that should run on PRs (see Shift-Left E2E Testing section)
- `@pytest.mark.slow` — Optional, for any test taking >5 seconds
- `@pytest.mark.integration`, `@pytest.mark.unit` — Optional, inferred by location

**Marker Enforcement:**

- Strict markers enabled: `--strict-markers`
- Undefined markers cause test failures
- Add new markers to `pyproject.toml` before use

## Shift-Left E2E Testing (Pipeline Marker)

The `@pytest.mark.pipeline(test_phase="pr-check")` marker enables shift-left testing by running a critical subset of E2E tests on every PR, catching deployment issues early while keeping CI fast.

### Overview

The `pipeline` marker classifies E2E tests by execution phase:
- **`pr-check`**: Critical tests that run on every PR (fast, high-value)
- **No marker**: Tests that run in full E2E suite only (comprehensive coverage)

**Note:** The pipeline marker only applies to E2E tests (`tests/e2e/`). Unit and integration tests are unaffected.

### Marker Syntax

```python
import pytest

# Mark a single test for PR checks
@pytest.mark.pipeline(test_phase="pr-check")
async def test_workflow_create_minimal(syntara_api):
    """Test minimal workflow creation - runs on PRs."""
    pass

# Mark an entire test class for PR checks
@pytest.mark.pipeline(test_phase="pr-check")
class TestWorkflowCRUD:
    """All tests in this class run on PRs."""

    async def test_create(self, syntara_api):
        pass

    async def test_delete(self, syntara_api):
        pass

# No marker - runs in full suite only
async def test_workflow_complex_validation(syntara_api):
    """Complex test - full suite only."""
    pass
```

### Running Tests

```bash
# Run only PR check tests (critical subset)
make test-e2e-pr-check

# Run tests excluding PR checks (for validation)
make test-e2e-exclude-pr-check

# Direct pytest commands
uv run pytest tests/e2e/ --test-phase=pr-check
uv run pytest tests/e2e/ --exclude-test-phase=pr-check
uv run pytest tests/e2e/ --test-phase=pr-check --collect-only  # List what would run
```

### Selection Guidelines

Mark tests with `test_phase="pr-check"` if they cover:

✅ **Critical user workflows**
- Login/logout
- Core CRUD operations
- Main navigation paths

✅ **Security-critical paths**
- Authentication flows
- Authorization checks
- Session management
- Token revocation

✅ **Infrastructure validation**
- Database connectivity
- API availability
- Basic deployment health

✅ **Sufficient code coverage**
- Executes meaningful code paths that serve as "canary" tests
- Detects early when something is broken (deployment config, database migrations, API changes)
- Covers core user journeys end-to-end

**Note on execution time:** While faster tests are preferred for better CI feedback, the primary criterion is coverage of critical paths that catch deployment issues early. Choose tests based on what they validate, not solely on speed.

❌ **Exclude from PR checks**
- High-volume data permutations
- Edge case scenarios
- Complex multi-stage setups
- Flaky or slow tests

### Example: Documenting Selection Rationale

```python
@pytest.mark.pipeline(test_phase="pr-check")
async def test_create_workflow_minimal(syntara_api: SyntaraApiRegistry) -> None:
    """Test minimal workflow creation.

    Marked for PR checks because:
    - Core CRUD operation all users perform
    - Validates API connectivity and database interaction
    - Fast execution (~2s)
    - Catches deployment configuration issues early
    """
    workflow = await syntara_api.workflows.create(
        name="Test Workflow",
        description="E2E test workflow"
    ).assert_and_get()

    assert workflow.name == "Test Workflow"
    assert workflow.id is not None
```

### Troubleshooting

**Marker not recognized:**
```bash
# Verify marker is registered
uv run pytest --markers | grep pipeline
```

**No tests collected:**
```bash
# List what tests would run
uv run pytest tests/e2e/ --test-phase=pr-check --collect-only

# If empty, no tests are marked yet - this is expected before domain expert selection
```

**Tests not filtering correctly:**
```bash
# Check if test has the marker
uv run pytest tests/e2e/path/to/test.py --markers -v
```

## Test Infrastructure

### Testcontainers

Tests use testcontainers for PostgreSQL and Redis:

**Container Runtime:**
- Prefers Podman (local dev)
- Falls back to Docker (CI)
- Detects container socket automatically

**Container Management:**
- One container per xdist worker for full isolation
- Session-scoped fixtures auto-start containers
- Ryuk disabled via `TESTCONTAINERS_RYUK_DISABLED=true`
- Custom images via `POSTGRES_IMAGE` and `REDIS_IMAGE` environment variables

**Database Migrations:**
- Applied automatically via Alembic in session fixture
- Tests run against fully migrated schema
- Function-scoped sessions get clean state via table truncation

### Temporal Test Environment

Workflow tests use Temporal's time-skipping test environment:

**Features:**
- Fast-forward time for workflow timers/sleep
- Full workflow execution without waiting
- Worker registration for activities and workflows

**Usage:**
```python
async def test_workflow_execution(temporal_env: WorkflowEnvironment) -> None:
    """Test workflow executes successfully."""
    async with Worker(
        temporal_env.client,
        task_queue="test-queue",
        workflows=[DynamicWorkflow],
        activities=[execute_api_request, execute_python_script],
    ):
        result = await temporal_env.client.execute_workflow(...)
```

### Parallel Execution

Tests run in parallel via pytest-xdist:

**Configuration:**
- `-n auto` uses all CPU cores
- Each worker gets isolated database container
- Worker ID available via `worker_id` fixture
- Session fixtures shared within worker, isolated across workers

## Async Test Patterns

**asyncio_mode = "auto":**
- All `async def test_*` functions auto-detected
- No need for `@pytest.mark.asyncio` (but doesn't hurt)
- Event loop managed automatically

**Async Fixtures:**
```python
@pytest_asyncio.fixture
async def test_data(test_db_session: AsyncSession) -> MyModel:
    """Create test data."""
    model = MyModel(...)
    test_db_session.add(model)
    await test_db_session.commit()
    await test_db_session.refresh(model)
    return model
```

**Best Practices:**
- Use `async with` for resource cleanup
- Await all async operations
- Use `AsyncClient` for HTTP requests
- Use `AsyncSession` for database operations

## Capturing structlog Output in Tests

This project uses structlog with `cache_logger_on_first_use=True`. Under pytest-xdist, cached bound loggers from earlier tests on the same worker bypass any handler or processor changes made during a later test. This makes `caplog` unreliable for capturing structlog output — `caplog.text` will be empty when the logger was cached before caplog injected its handler.

**Use `structlog.testing.capture_logs()` with a fresh logger:**

```python
import structlog
from syntara.some_module import target_module

@patch("syntara.some_module.emitter._do_emit")
async def test_logs_warning(self, mock_emit: Mock) -> None:
    old_logger = target_module.logger
    try:
        with structlog.testing.capture_logs() as captured:
            # Create fresh logger INSIDE capture_logs() context
            # so it binds to the capture processor chain
            target_module.logger = structlog.get_logger("syntara.some_module")
            do_something_that_logs()
    finally:
        target_module.logger = old_logger

    assert any("expected message" in e.get("event", "") for e in captured)
```

**Why this pattern is necessary:**

1. `capture_logs()` replaces structlog's processor chain with a list collector
2. But `cache_logger_on_first_use=True` means already-cached loggers still use the old chain
3. Creating a fresh logger *inside* `capture_logs()` binds it to the capture chain
4. Restoring the original logger in `finally` avoids polluting other tests

**Do not use:**

- Bare `caplog.text` with structlog — unreliable under xdist due to logger caching
- `caplog.at_level()` — same caching issue; stdlib handler injection doesn't help when structlog's bound logger bypasses it
- Patching with a plain stdlib logger — structlog's `logger.warning(msg, key=value)` passes kwargs as structured fields, which stdlib's `_log()` rejects as unexpected keyword arguments

## Tooling Enforcement vs Convention

**Enforced by Tooling:**

- Test file discovery (`test_*.py` only)
- Strict markers (undefined markers fail)
- Strict config (invalid config fails)
- Coverage threshold (80% required, fails under)
- Performance test filtering (auto-skipped without flag)
- Async mode (auto-detected)
- Parallel execution (xdist)
- Linter rules (S101, ANN001, etc. ignored for tests)

**Convention Only:**

- Directory organization (mirrors src structure)
- Fixture scoping strategy
- Test type boundaries (unit vs integration)
- Docstring style for tests
- Helper vs fixture distinction

**Ruff Overrides for Tests:**

The following lint rules are relaxed for test code (`tests/**/*.py` and `test-sdk/**/*.py`):

- `S101` — Allow `assert` statements
- `ANN001`, `ANN201` — No type annotations required for test args/returns
- `D102` — No docstrings required for test methods
- `PLR2004` — Allow magic values
- `ARG001` — Allow unused fixture arguments
- `SLF001` — Allow private member access (for unit testing internal state)
- Additional overrides listed in `pyproject.toml`

`test-sdk/` also relaxes `TC002`/`TC003` (TYPE_CHECKING guard enforcement) because e2e fixtures are imported at runtime, not just for type checking.

## Make Targets

**Primary Test Commands:**

```bash
make test              # Unit tests only (default)
make test-unit         # Explicit unit tests
make test-integration  # Integration tests (excludes MCP)
make test-e2e-mcp      # MCP E2E tests (auto-starts services)
make test-all          # All tests with coverage (excludes e2e, performance)
make test-e2e          # End-to-end tests (auto-starts services)
make test-performance  # Performance tests only
make test-coverage     # Coverage report (XML + terminal)
make test-fast         # Fail-fast mode with short traceback
```

**Test Execution Pattern:**

All test commands (except e2e, performance) use the `run-tests` make function:
1. Detect container runtime (Podman preferred, Docker fallback)
2. Set environment variables (DOCKER_HOST, TESTCONTAINERS_RYUK_DISABLED, etc.)
3. Run `uv run pytest` with specified arguments
4. Parallel execution via `-n auto` (when appropriate)

## Coverage Requirements

**Configuration (`pyproject.toml`):**
- Minimum coverage: 80% (`fail_under = 80`)
- Source: `src/`
- Omit: `*/tests/*`, `*/__init__.py`, `tools/*`, `src/api_client/*`, `src/cli/*`

**Known Inconsistency:**
- Constitution specifies 90% coverage
- `pyproject.toml` enforces 80%
- This discrepancy is documented in `questions.md`

**Excluded Lines:**
- `pragma: no cover`
- `def __repr__`
- Debug-only code
- Abstract methods
- NotImplementedError
- Main blocks

### Coverage Reporting by Test Layer

The project supports separate coverage reporting for each test layer:

**Make Targets:**

```bash
# Combined coverage (all tests except e2e)
make test-coverage         # XML report (for CI)
make test-coverage-report  # HTML report → htmlcov/

# Per-layer coverage reports
make test-unit-coverage        # Unit tests → htmlcov-unit/
make test-cli-coverage         # CLI tests → htmlcov-cli/
make test-integration-coverage # Integration → htmlcov-integration/
```

**Use Cases:**

- **Development**: Use layer-specific coverage to focus on the tests you're writing
- **Code Review**: Check coverage impact of new unit tests vs integration tests
- **CI/CD**: Use `make test-coverage` for combined XML report
- **Investigation**: Compare coverage across layers to identify testing gaps

**Coverage Report Directories:**

All HTML coverage reports are gitignored via the `htmlcov-*/` pattern:
- `htmlcov/` - Combined coverage from all test layers
- `htmlcov-unit/` - Unit test coverage only
- `htmlcov-cli/` - CLI test coverage only
- `htmlcov-integration/` - Integration test coverage only

## Adding Tests for a New Domain

When adding a new domain (e.g., `src/syntara/new_domain/`):

**Step 1: Create Test Directory Structure**

```bash
mkdir -p tests/unit/new_domain
mkdir -p tests/integration/new_domain
touch tests/unit/new_domain/__init__.py
touch tests/integration/new_domain/__init__.py
```

**Step 2: Add conftest.py (if needed)**

Only add if domain needs specific fixtures:

```python
# tests/unit/new_domain/conftest.py
"""Domain-specific test fixtures."""

import pytest
from syntara.new_domain.models import DomainModel

@pytest.fixture
def domain_model_data() -> dict[str, Any]:
    """Factory data for DomainModel."""
    return {"field": "value"}
```

**Step 3: Write Unit Tests**

```python
# tests/unit/new_domain/test_model.py
"""Unit tests for DomainModel."""

async def test_create_domain_model(domain_model_data: dict[str, Any]) -> None:
    """Test creating a domain model."""
    model = DomainModel(**domain_model_data)
    assert model.field == domain_model_data["field"]
```

**Step 4: Write Integration Tests**

```python
# tests/integration/new_domain/test_repository.py
"""Integration tests for DomainRepository."""

async def test_repository_create(
    test_db_session: AsyncSession,
    domain_model_data: dict[str, Any]
) -> None:
    """Test repository create operation."""
    repo = DomainRepository(test_db_session)
    model = await repo.create(domain_model_data)
    assert model.id is not None
```

**Step 5: Run Tests**

```bash
# Run new domain unit tests
make test-unit tests/unit/new_domain/

# Run new domain integration tests
make test-integration tests/integration/new_domain/

# Run all tests with coverage
make test-all
```

**Step 6: Verify Coverage**

```bash
make test-coverage
# Check coverage report for new domain
# Ensure >= 80% coverage
```

## Test Documentation

**File-Level Docstrings:**

Every test file should have a module docstring explaining:
- What is being tested
- Test coverage scope
- Special considerations (if any)

**Example:**
```python
"""Unit tests for User model.

Tests cover:
- User creation with required fields
- Soft delete behavior
- Role enum validation
- Unique constraint violations
"""
```

**Test Function Docstrings:**

Test functions should have concise docstrings:
- What is being tested
- Expected outcome (for contract tests)

**Example:**
```python
def test_create_user_with_required_fields() -> None:
    """Test creating a user with all required fields."""
```

## Common Patterns

**Exception Test Pattern:**

Only one invocation that could throw should appear inside a `pytest.raises` block.
Move object construction, `uuid4()`, `AsyncMock()`, and other setup calls
outside the block so the test pinpoints exactly which call raised.

```python
# Bad — uuid4() and MyModel() could also raise inside the block
with pytest.raises(NotFoundError):
    await service.get(uuid4())

with pytest.raises(ValidationError):
    await service.create(MyModel(name="x"), project_id=uuid4())

# Good — only the method under test can raise
fake_id = uuid4()
with pytest.raises(NotFoundError):
    await service.get(fake_id)

model = MyModel(name="x")
project_id = uuid4()
with pytest.raises(ValidationError):
    await service.create(model, project_id=project_id)
```

**Database Test Pattern:**

```python
async def test_database_operation(test_db_session: AsyncSession) -> None:
    """Test database operation."""
    # Arrange
    model = MyModel(field="value")
    test_db_session.add(model)
    await test_db_session.commit()
    await test_db_session.refresh(model)

    # Act
    result = await some_operation(model)

    # Assert
    assert result.status == "expected"
```

**API Test Pattern:**

```python
async def test_api_endpoint(base_client: AsyncClient) -> None:
    """Test API endpoint behavior."""
    # Act
    response = await base_client.get("/api/v1/resource")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert "resources" in data
```

**Mock Pattern:**

```python
async def test_with_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test with mocked external dependency."""
    mock_service = Mock(return_value="mocked_value")
    monkeypatch.setattr("module.path.function", mock_service)

    result = await function_under_test()

    assert result == "expected"
    mock_service.assert_called_once()
```

## Reference

**Primary Test Configuration:**
- `pyproject.toml` — Pytest, coverage, markers
- `tests/conftest.py` — Root fixtures
- `Makefile` — Test execution targets

**Key Dependencies:**
- `pytest` — Test framework
- `pytest-asyncio` — Async test support
- `pytest-xdist` — Parallel execution
- `pytest-cov` — Coverage reporting
- `testcontainers` — Container management
- `temporalio` — Workflow testing
- `httpx` — HTTP client testing
- `respx` — HTTP mocking

Generated By: Claude Code (Claude Sonnet 4.5)
