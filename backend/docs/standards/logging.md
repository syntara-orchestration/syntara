# Logging Standards

## Overview

Nexus uses [structlog](https://www.structlog.org/en/stable/) for structured logging across all Python components. Structured logging ensures logs are machine-parsable, consistent, and enriched with context for debugging and observability.

This document defines the required patterns for logging in the Nexus codebase. All code MUST comply with these standards.

## Core Principles

1. **Structured over Formatted**: Never use string interpolation or f-strings for log messages. Pass context as keyword arguments.
2. **Context-Rich**: Every log statement must include relevant identifiers (IDs, correlation IDs, entity names).
3. **Security-First**: Never log secrets, tokens, passwords, API keys, or personally identifiable information (PII).
4. **Observability-First**: All critical paths must emit logs. Debug information must be available without code changes via log level configuration.

## Logger Creation

### Module-Level Logger

Create one logger per module immediately after imports:

```python
import structlog

logger = structlog.stdlib.get_logger(__name__)
```

**Rules:**
- Use `structlog.stdlib.get_logger(__name__)` — not `structlog.get_logger()`. The stdlib variant integrates with Python's logging infrastructure.
- Place the logger at module level, never inside functions.
- Never use `logging.getLogger()` directly (use structlog's stdlib wrapper).

**Exception:** `BaseAgent` (`src/syntara/agent_orchestrator/agents/base_agent.py`) uses `self.logger = structlog.stdlib.get_logger(self.__class__.__name__)` to bind the concrete agent class name rather than the module name. This is the only sanctioned class-level logger pattern. Do not replicate it in other domains without justification.

**Example:**

```python
# src/syntara/workflows/services/execution_service.py
"""Execution service for managing workflow executions."""

from uuid import UUID

import structlog

from syntara.workflows.models import Execution

logger = structlog.stdlib.get_logger(__name__)


class ExecutionService:
    async def start_execution(self, workflow_id: UUID) -> Execution:
        logger.info("Starting execution", workflow_id=workflow_id)
        # ...
```

## Configuration

Logging is configured centrally in `src/syntara/core/logging/logging.py` via `configure_structlog()`.

This function is called:
- At application startup in `src/syntara/__init__.py`
- In test setup in `tests/conftest.py`

**Do not configure structlog in individual modules.** Use the global configuration.

## Log Levels

### debug

**When to use**: Detailed execution flow for development and debugging.

**Examples:**
- Individual activity delta events
- Internal state transitions
- Variable values at specific points in execution
- Loop iterations in performance-sensitive code

```python
logger.debug(
    "Processing activity delta",
    activity_id=activity_id,
    delta_type=delta.type,
    sequence_number=delta.sequence,
)
```

### info

**When to use**: Normal operations, expected events, successful state transitions.

**Examples:**
- Service startup
- Request handling start/completion
- Workflow/execution state changes (started, completed)
- Successful operations
- Connection establishment

```python
logger.info(
    "Executing streaming orchestration for invocation",
    invocation_id=invocation_id,
)

logger.info(
    "Starting activity monitoring for execution",
    execution_id=execution_id,
    temporal_workflow_id=temporal_workflow_id,
)
```

### warning

**When to use**: Unexpected but recoverable situations, degraded functionality, or potential issues.

**Examples:**
- Failed to fetch optional data (fallback used)
- Deprecated API usage
- Invalid user input (validation failed)
- Retry attempts

```python
logger.warning(
    "Failed to fetch workflow history for failure details",
    error=str(e),
)

logger.warning(
    "Invalid query parameters",
    validation_error=str(e),
)
```

### error

**When to use**: Error conditions without exception context (when not in an except block).

**Examples:**
- Business logic errors that are logged but not raised
- Errors detected outside exception handlers
- Conditions that should not occur but did

```python
logger.error(
    "Monitoring task for execution failed",
    execution_id=execution_id,
    error=str(task.exception()),
)
```

### exception

**When to use**: Error paths with full traceback (use inside except blocks only).

**Critical:** Always use `logger.exception()` inside except blocks to capture full traceback.

```python
try:
    workflow_def = WorkflowDefinition(**workflow_def_dict)
except ValidationError as e:
    logger.exception(
        "Invalid workflow definition",
        workflow_name=workflow_name,
        error_type=type(e).__name__,
    )
    raise
```

**Rules:**
- MUST be inside an except block
- Automatically includes exception traceback
- Pass additional context as keyword arguments
- Do NOT pass `exc_info=True` manually (exception() handles this)

## Structured Context

### Always Use Keyword Arguments

Never use string formatting, f-strings, or concatenation for log messages:

```python
# WRONG - String formatting
logger.info(f"Starting workflow {workflow_id}")
logger.info("Starting workflow {}".format(workflow_id))
logger.info("Starting workflow %s" % workflow_id)

# CORRECT - Keyword arguments
logger.info("Starting workflow", workflow_id=workflow_id)
```

### Rich Context

Pass all relevant identifiers and state:

```python
logger.info(
    "Executing streaming orchestration for invocation",
    invocation_id=invocation_id,
    user_id=user_id,
    workflow_name=workflow_name,
)
```

### Consistent Naming

Use consistent keyword argument names across the codebase:

| Entity | Keyword |
|--------|---------|
| Workflow ID | `workflow_id` |
| Execution ID | `execution_id` |
| Activity ID | `activity_id` |
| User ID | `user_id` |
| Invocation ID | `invocation_id` |
| Request ID | `request_id` |
| Error type | `error_type` |
| Error message | `error` or `error_message` |
| Temporal workflow ID | `temporal_workflow_id` |
| Temporal run ID | `temporal_run_id` |

## What to Log vs What Not to Log

### Always Log

- Service lifecycle events (startup, shutdown)
- Request/response boundaries (API calls, workflow starts)
- State transitions (workflow started, completed, failed)
- Business logic decisions (condition evaluated, branch taken)
- External service calls (database queries, HTTP requests, Temporal workflows)
- Error conditions with full context

### Never Log

**Security-sensitive data:**
- Passwords, API keys, tokens, secrets
- Authentication credentials
- Encryption keys
- PII (email addresses, phone numbers, SSNs) unless explicitly required and approved

**Internal implementation details in user-facing error paths:**
- Database table names or schemas
- Internal file paths
- Stack traces in API responses (log internally, return generic message)

**Example - Logging vs Response:**

```python
async def workflow_not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log full details for debugging
    logger.info("Workflow not found", exc_info=exc)

    # Return generic, safe message to client
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="The requested workflow was not found",  # Generic
    )
```

## Error Logging Patterns

### Exception Handling

**Pattern 1: Log and re-raise**

```python
try:
    result = await dangerous_operation()
except SpecificError as e:
    logger.exception(
        "Operation failed",
        operation="dangerous_operation",
        context_id=context_id,
    )
    raise  # Re-raise to let caller handle
```

**Pattern 2: Log and convert**

```python
try:
    result = await external_service_call()
except ExternalServiceError as e:
    logger.exception(
        "External service call failed",
        service="example_api",
        endpoint=endpoint,
    )
    raise ServiceUnavailableError("External service unavailable") from e
```

**Pattern 3: Log and suppress (rare)**

```python
try:
    optional_data = await fetch_optional_metadata()
except MetadataNotFoundError:
    logger.warning(
        "Optional metadata not found, using defaults",
        entity_id=entity_id,
    )
    optional_data = None  # Suppress and continue
```

### Error Context

Always include:
- `error_type=type(e).__name__` for exception type
- Entity IDs related to the error
- Operation that failed
- Any relevant state

```python
logger.exception(
    "Streaming orchestration failed",
    invocation_id=invocation_id,
    error_type=type(e).__name__,
)
```

## Testing with Structlog

Nexus uses standard pytest logging fixtures to capture logs in tests.

### Reading Logs in Tests

Use pytest's `caplog` fixture:

```python
import logging


def test_execution_logging(caplog):
    """Test that execution start logs correctly."""
    caplog.set_level(logging.INFO)

    service = ExecutionService()
    service.start_execution(workflow_id="test-workflow")

    # Assert log was emitted
    assert "Starting execution" in caplog.text

    # Assert structured fields present
    records = [r for r in caplog.records if "Starting execution" in r.message]
    assert len(records) == 1
    # Note: accessing structured context in tests requires log processor inspection
```

### Testing Log Levels

```python
def test_debug_logging_disabled_by_default(caplog):
    """Test that debug logs are not emitted at INFO level."""
    caplog.set_level(logging.INFO)

    logger.debug("This should not appear", context="test")

    assert "This should not appear" not in caplog.text


def test_debug_logging_enabled_at_debug_level(caplog):
    """Test that debug logs appear at DEBUG level."""
    caplog.set_level(logging.DEBUG)

    logger.debug("This should appear", context="test")

    assert "This should appear" in caplog.text
```

### Testing Exception Logging

```python
def test_exception_logging(caplog):
    """Test that exceptions are logged with traceback."""
    caplog.set_level(logging.ERROR)

    try:
        raise ValueError("Test error")
    except ValueError:
        logger.exception("Caught error", context="test")

    assert "Caught error" in caplog.text
    assert "ValueError: Test error" in caplog.text
    assert "Traceback" in caplog.text
```

## Adding Logging to a New Domain

When adding a new domain or module to Nexus, follow these steps:

### 1. Create Module Logger

In the main service or handler file:

```python
# src/syntara/my_domain/services/my_service.py
"""My service for doing domain operations."""

import structlog

from syntara.my_domain.models import MyEntity

logger = structlog.stdlib.get_logger(__name__)


class MyService:
    async def create_entity(self, name: str) -> MyEntity:
        logger.info("Creating entity", name=name)
        # ...
```

### 2. Add Logging to Key Operations

Instrument all critical paths:

```python
async def create_entity(self, name: str) -> MyEntity:
    logger.info("Creating entity", name=name)

    try:
        entity = await self._persist_entity(name)
        logger.info("Entity created", entity_id=entity.id, name=name)
        return entity
    except IntegrityError as e:
        logger.exception(
            "Failed to create entity",
            name=name,
            error_type=type(e).__name__,
        )
        raise EntityConflictError(f"Entity '{name}' already exists") from e
```

### 3. Add Structured Context

Ensure all logs in the domain use consistent keyword names:

```python
# Domain-specific keyword standards
logger.info("Processing entity", entity_id=entity.id, entity_type=entity.type)
logger.debug("Entity state transition", entity_id=entity.id, from_state=old, to_state=new)
```

### 4. Test Logging

Add tests to verify logging behavior:

```python
def test_entity_creation_logs(caplog):
    """Test that entity creation emits expected logs."""
    caplog.set_level(logging.INFO)

    service = MyService()
    entity = await service.create_entity(name="test")

    # Verify creation started
    assert "Creating entity" in caplog.text

    # Verify creation completed
    assert "Entity created" in caplog.text
```

### 5. Document Domain-Specific Keywords

If your domain introduces new entity types or concepts, document the keyword conventions in this file via PR.

## Common Patterns

### Service Initialization

```python
class MyService:
    def __init__(self, config: Config):
        logger.info("Initializing service", service="MyService", config_env=config.env)
        self.config = config
```

### Request Boundaries

```python
@router.post("/entities")
async def create_entity(request: EntityCreate) -> Entity:
    logger.info("Received entity creation request", name=request.name)

    entity = await service.create_entity(request.name)

    logger.info("Entity creation completed", entity_id=entity.id)
    return entity
```

### Background Tasks

```python
async def monitor_execution(execution_id: UUID):
    logger.info("Starting execution monitoring", execution_id=execution_id)

    try:
        while not execution.is_complete:
            logger.debug("Polling execution status", execution_id=execution_id)
            await asyncio.sleep(1)

        logger.info("Execution monitoring completed", execution_id=execution_id)
    except Exception as e:
        logger.exception(
            "Execution monitoring failed",
            execution_id=execution_id,
            error_type=type(e).__name__,
        )
        raise
```

### Conditional Logging

```python
if response.status_code != 200:
    logger.warning(
        "Unexpected status code from external service",
        service="external_api",
        status_code=response.status_code,
        expected=200,
    )
```

## Compliance

All code merged into Nexus MUST:
1. Use module-level structlog loggers
2. Pass context as keyword arguments (never string formatting)
3. Use appropriate log levels
4. Never log secrets or PII
5. Include full context (IDs, state, error types) in log statements
6. Use `logger.exception()` inside except blocks

Violations of these standards will be flagged in code review and must be corrected before merge.

## Output Formats

Nexus supports two log output formats, controlled by `APP_LOG_OUTPUT_FORMAT`:

### Text Mode (`text`)

Human-readable console output via structlog's `ConsoleRenderer`. Used in local development.

### JSON Mode (`json`)

Machine-parsable JSON via `SyntaraLogRecordRenderer` (extends `JSONRenderer`). Used in production.

The custom renderer recursively converts non-JSON-serializable objects to strings via `__repr__()`. This prevents serialization failures from crashing the logging pipeline:

```python
class SyntaraLogRecordRenderer(JSONRenderer):
    def _make_serializable(self, obj: object) -> object:
        # Primitives pass through
        # Dicts and lists are recursed
        # Everything else: try json.dumps(), fall back to repr()
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return repr(obj)
```

### Shared Processor Pipeline

Both modes share the same processor chain (configured in `build_syntara_shared_formatters()`):

1. `merge_contextvars` — merge thread-local context
2. `add_log_level` — inject log level
3. `ExtraAdder` — include extra fields
4. `TimeStamper(fmt="iso")` — ISO 8601 timestamps
5. `format_exc_info` — format exception tracebacks

## Tooling vs Convention

**Enforced by tooling:**

- structlog configuration via `configure_structlog()` (centralized, called at startup)
- Log level filtering (Python logging infrastructure)
- `make lint` catches f-string usage in log calls (Ruff G004 rule)
- `SyntaraLogRecordRenderer` prevents JSON serialization failures via `__repr__` fallback

**Convention only:**

- Module-level logger creation (`structlog.stdlib.get_logger(__name__)`)
- Keyword argument naming consistency (entity ID conventions)
- Log level selection (debug vs info vs warning)
- Security-sensitive data exclusion (no tooling enforcement)
- Exception logging pattern (`logger.exception()` in except blocks)
- Output format selection (text vs json) per environment

## Reference

| File | Purpose |
|---|---|
| `src/syntara/core/logging/logging.py` | Central structlog configuration (`configure_structlog()`), `SyntaraLogRecordRenderer` |
| `src/syntara/__init__.py` | Application startup logging init |
| `tests/conftest.py` | Test logging setup |

**External:**

- [structlog Documentation](https://www.structlog.org/en/stable/)
- [Error Handling Strategy](../error-handling-strategy.md) — How logging integrates with exception handling
- [Decision Records](../../decision-records.md) — Why structlog was chosen

Generated By: Claude Code (Claude Opus 4.6)
