# Exception and Error Handling Standards

This document defines the naming conventions and structural patterns for exceptions, error handlers, and RFC 9457 error responses. For the architectural strategy (single exception boundary, router transparency, global handlers), see [Error Handling Strategy](../error-handling-strategy.md).

## Exception Hierarchy

All domain exceptions inherit from `NexusError`:

```
NexusError(Exception)
├── ApprovalError
│   ├── ApprovalNotFoundError
│   ├── ApprovalAlreadyDecidedError
│   └── ApprovalAlreadyRequestedError
├── FileError
│   ├── FileValidationError
│   ├── FileSizeExceededError
│   ├── FileNotReadableError
│   └── DocumentConversionError
│       ├── UnsupportedFormatError
│       └── ConversionFailureError
├── ToolManagerError
│   ├── ToolNotFoundError
│   ├── ProviderNotFoundError
│   ├── ProviderNameConflictError
│   ├── ToolRefreshError
│   └── ToolBulkUpdateValidationError
├── WorkflowError
│   ├── WorkflowNotFoundError
│   ├── WorkflowNameConflictError
│   ├── WorkflowDisabledError
│   ├── WorkflowVersionNotFoundError
│   └── ExecutionNotFoundError
├── AgentOrchestratorError
│   ├── LLMConfigurationError
│   └── TemporalUnavailableError
└── SafeValueError(ValueError, NexusError)
```

## Naming Conventions

### Exception Classes

**Pattern:** `{ResourceOrAction}{Condition}Error`

| Condition | When to use | Examples |
|---|---|---|
| `NotFound` | Resource does not exist | `WorkflowNotFoundError`, `ToolNotFoundError` |
| `NameConflict` | Unique name constraint violation | `WorkflowNameConflictError`, `ProviderNameConflictError` |
| `AlreadyDecided` / `AlreadyRequested` | Resource already in terminal state | `ApprovalAlreadyDecidedError` |
| `Disabled` | Resource exists but is disabled | `WorkflowDisabledError` |
| `Validation` | Business logic validation failure | `FileValidationError`, `ToolBulkUpdateValidationError` |
| `SizeExceeded` / `LimitExceeded` | Limit violation | `FileSizeExceededError`, `TokenLimitExceededError` |
| `Failure` | Operation failed | `ConversionFailureError` |
| `Configuration` | Missing or invalid configuration | `LLMConfigurationError` |
| `Unavailable` | External service unreachable | `TemporalUnavailableError` |

### Domain Base Exceptions

**Pattern:** `{Domain}Error(NexusError)`

Each domain module defines a base exception that all domain-specific exceptions inherit from:

```python
class ToolManagerError(NexusError):
    """Base exception for tool manager operations."""
```

### Error Handler Functions

**Pattern:** `{resource}_{condition}_handler`

Examples:
- `approval_not_found_handler`
- `workflow_name_conflict_handler`
- `tool_provider_not_found_handler`
- `file_validation_error_handler`

### Machine-Readable Error Codes

**Pattern:** `{DOMAIN}_{CONDITION}` in SHOUTING_SNAKE_CASE

Examples: `APPROVAL_NOT_FOUND`, `WORKFLOW_NAME_CONFLICT`, `VALIDATION_ERROR`, `TOOL_NOT_FOUND`

## Exception Constructor Patterns

### Simple (Most Common)

Inherit from `NexusError` — the base class stores `self.message`:

```python
class WorkflowNotFoundError(WorkflowError):
    """Exception raised when a workflow is not found."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
```

### With Context Attributes

Store resource identifiers and state for structured logging:

```python
class ApprovalNotFoundError(ApprovalError):
    """Exception raised when an approval request is not found."""

    def __init__(self, approval_id: UUID) -> None:
        self.approval_id = approval_id
        super().__init__(f"Approval request {approval_id} not found")
```

```python
class ApprovalAlreadyDecidedError(ApprovalError):
    """Exception raised when an approval has already been decided."""

    def __init__(self, approval_id: UUID, current_status: ApprovalRequestStatus) -> None:
        self.approval_id = approval_id
        self.current_status = current_status
        super().__init__(
            f"Approval request {approval_id} is already decided "
            f"with status '{current_status}'"
        )
```

The `message` attribute (set by `NexusError.__init__`) is used by error handlers to extract user-safe detail text.

## @fastapi_exception Decorator

Register exceptions with their handlers using the `@fastapi_exception` decorator with a **string-based handler reference**:

```python
from syntara.core.exception_registry import fastapi_exception

@fastapi_exception(handler="syntara.approvals.error_handlers.approval_not_found_handler")
class ApprovalNotFoundError(ApprovalError):
    """Exception raised when an approval request is not found."""
```

The string path is resolved via `importlib` at registration time. This avoids circular imports between `exceptions.py` and `error_handlers.py`. Do **not** import handler functions directly — use string references exclusively.

All decorated exceptions are automatically registered when `register_exceptions(app)` is called during app initialization.

For third-party exceptions that cannot be decorated, use manual registration in `main.py`:

```python
app.add_exception_handler(RPCError, temporal_rpc_error_handler)
```

## Error Handler Implementation

Handlers convert domain exceptions to RFC 9457 responses:

```python
def approval_not_found_handler(request: Request, exc: "ApprovalNotFoundError") -> JSONResponse:
    """Handle ApprovalNotFoundError with RFC 9457 format.

    Args:
        request: FastAPI request object.
        exc: The exception instance.

    Returns:
        JSONResponse with RFC 9457 Problem Details format.
    """
    logger.error("Approval request not found", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Approval Request Not Found",
        detail=exc.message,
        code="APPROVAL_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )
```

### create_problem_details_response Signature

```python
def create_problem_details_response(
    status_code: int,
    problem_type: str,
    title: str,
    detail: str,
    code: str,
    *,
    retryable: bool = False,
    instance: str | None = None,
) -> JSONResponse:
```

## PROBLEM_TYPES Registry

Defined in `syntara.core.error_handlers`:

```python
PROBLEM_TYPES = {
    "unauthorized": "https://api.example.com/errors/unauthorized",
    "forbidden": "https://api.example.com/errors/forbidden",
    "resource_not_found": "https://api.example.com/errors/resource-not-found",
    "name_conflict": "https://api.example.com/errors/name-conflict",
    "resource_conflict": "https://api.example.com/errors/resource-conflict",
    "validation_error": "https://api.example.com/errors/validation-error",
    "integrity_constraint": "https://api.example.com/errors/integrity-constraint",
    "service_unavailable": "https://api.example.com/errors/service-unavailable",
    "resource_disabled": "https://api.example.com/errors/resource-disabled",
    "provider_error": "https://api.example.com/errors/provider-error",
    "internal_error": "https://api.example.com/errors/internal-error",
}
```

Keys use `snake_case`. URI values use `kebab-case`. Add new entries when existing types do not cover a new error category.

## HTTP Status Code Mapping

| Status | Condition | Example exceptions |
|---|---|---|
| 400 | Bad request / business logic error | `ProviderError`, `ToolManagerError` |
| 404 | Resource not found | `WorkflowNotFoundError`, `ToolNotFoundError` |
| 409 | Conflict (name collision, state conflict) | `WorkflowNameConflictError`, `ApprovalAlreadyDecidedError` |
| 422 | Schema/request validation failure | `pydantic.ValidationError`, `RequestValidationError` |
| 503 | External service unavailable | `TemporalUnavailableError`, `LLMConfigurationError` |
| 500 | Unhandled / system error | `RPCError`, generic `Exception` |

## File Organization

Each domain module contains:

```
src/syntara/{domain}/
├── exceptions.py       # Domain base + specific exceptions
└── error_handlers.py   # Handler functions + logger
```

Core infrastructure:

| File | Purpose |
|---|---|
| `src/syntara/core/exceptions.py` | `NexusError` base class, `SafeValueError` |
| `src/syntara/core/exception_registry.py` | `@fastapi_exception` decorator, `register_exceptions()` |
| `src/syntara/core/error_handlers.py` | `PROBLEM_TYPES` dict, `create_problem_details_response()`, framework-level handlers |

## Adding Exceptions for a New Domain

### Step 1: Create Domain Base Exception

```python
# src/syntara/must_gather/exceptions.py
from syntara.core.exception_registry import fastapi_exception
from syntara.core.exceptions import NexusError
from syntara.must_gather.error_handlers import must_gather_not_found_handler


class MustGatherError(NexusError):
    """Base exception for must-gather operations."""


@fastapi_exception(handler=must_gather_not_found_handler)
class MustGatherNotFoundError(MustGatherError):
    """Exception raised when a must-gather resource is not found."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"MustGather '{name}' not found")
```

### Step 2: Create Error Handlers

```python
# src/syntara/must_gather/error_handlers.py
from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import status
from fastapi.responses import JSONResponse

from syntara.core.error_handlers import PROBLEM_TYPES, create_problem_details_response

if TYPE_CHECKING:
    from fastapi import Request

logger = structlog.stdlib.get_logger(__name__)


def must_gather_not_found_handler(
    request: Request, exc: "MustGatherNotFoundError",
) -> JSONResponse:
    """Handle MustGatherNotFoundError with RFC 9457 format."""
    logger.error("Must-gather resource not found", exc_info=exc)
    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Must-Gather Not Found",
        detail=exc.message,
        code="MUST_GATHER_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )
```

### Step 3: Ensure Module Is Imported

The `@fastapi_exception` decorator registers exceptions when the module is imported. If the module is not imported transitively (e.g., via router discovery), add an explicit import:

```python
# In main.py or a module that is always loaded
import syntara.must_gather.exceptions  # noqa: F401
```

## Router URL Prefix Conventions

Router prefixes use the domain module name directly:

```python
router = APIRouter(prefix="/workflows", tags=["workflows"])
router = APIRouter(prefix="/approvals", tags=["approvals"])
router = APIRouter(prefix="/tool_manager", tags=["tool_manager"])
```

**Current convention:** Prefixes match the Python module name. Single-word domains use the word directly (`/workflows`, `/approvals`, `/files`). Multi-word domains use underscores (`/tool_manager`).

**Known inconsistency:** This is documented in [Questions](questions.md). The Constitution mandates snake_case for API parameter names, but URL path segments are conventionally kebab-case in REST APIs. The codebase currently uses the module name as-is.

## Retry Error Classification

Transient errors (network failures, timeouts, rate limits) use retry logic with error classification. The retry system lives in `src/syntara/core/utils/retry.py`.

### `is_retryable_error(error)`

Classifies exceptions as retryable or non-retryable:

**Retryable (will trigger retry with backoff):**
- `openai.APIConnectionError`, `openai.APITimeoutError`, `openai.RateLimitError`
- `openai.APIStatusError` with 5xx status
- `httpx.HTTPStatusError` with 500, 502, 503, 504, 429
- `httpx.TimeoutException`, `httpx.ConnectTimeout`, `httpx.ReadTimeout`, `httpx.ConnectError`
- `asyncio.TimeoutError`

**Non-retryable (fail immediately):**
- `openai.AuthenticationError` (401), `openai.BadRequestError` (400)
- `openai.APIStatusError` with 4xx status (except 429)
- `ValueError`, `KeyError`, `AttributeError` (programming errors)

### `@retry_with_backoff` Decorator

Wraps async functions with exponential backoff:

```python
from syntara.core.utils.retry import retry_with_backoff

@retry_with_backoff
async def call_llm(invocation_id: str, turn_id: str) -> str:
    ...
```

Backoff formula: `initial * (growth_factor ** attempt)`, capped at `max_backoff`, with ±10% jitter. Configuration via `AdapterRetrySettings` in settings.

## Tooling vs Convention

**Enforced by tooling:**

- `register_exceptions(app)` scans and registers all `@fastapi_exception` decorated classes
- RFC 9457 response format enforced by `create_problem_details_response()`
- Pydantic validation errors are caught globally (built into FastAPI)
- `is_retryable_error()` classifies exceptions for retry decisions

**Convention only:**

- Exception naming (`{Resource}{Condition}Error`)
- Handler naming (`{resource}_{condition}_handler`)
- Error code format (`SHOUTING_SNAKE_CASE`)
- Domain base exception hierarchy
- `PROBLEM_TYPES` key naming
- Using `@retry_with_backoff` for LLM/external service calls

## Reference

| File | Purpose |
|---|---|
| `src/syntara/core/exceptions.py` | `NexusError` base, `SafeValueError` |
| `src/syntara/core/exception_registry.py` | Decorator and registration |
| `src/syntara/core/error_handlers.py` | `PROBLEM_TYPES`, `create_problem_details_response()` |
| `docs/error-handling-strategy.md` | Architectural strategy and principles |

Generated By: Claude Code (Claude Opus 4.6)
