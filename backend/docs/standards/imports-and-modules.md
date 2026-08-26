# Imports and Modules Standards

This document defines standards for Python imports and module structure in the Syntara monorepo.

## Import Ordering

All Python files must organize imports in three sections, each alphabetically sorted:

```python
# 1. Standard library imports
import asyncio
import json
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID

# 2. Third-party package imports
import httpx
import structlog
from fastapi import FastAPI, HTTPException, Request, status
from pydantic import ConfigDict, ValidationError
from sqlalchemy import BigInteger, String, Text, text
from sqlmodel import Column, DateTime, Field, Index

# 3. Local syntara imports (organized by domain, alphabetically)
from syntara.agent_orchestrator.models.agent_state import AgentState
from syntara.core.config.base import get_settings
from syntara.core.models import User, UserRole
from syntara.workflows.models import Execution, ExecutionStatus, Workflow
```

**Rules:**

- Blank line separates each section
- Within each section: alphabetical order by module path
- Group `import` statements before `from ... import` statements within each section
- Local syntara imports are sorted alphabetically by full module path (e.g., `syntara.agent_orchestrator` before `syntara.core`)
- No arbitrary grouping or domain-specific subsections within the local import block

**Tooling Enforcement:**

This is automatically enforced by `make format` via Ruff with isort (I) rules enabled:

```toml
[tool.ruff.lint]
select = ["ALL"]  # Includes isort (I) rules
```

Violations of import order will be caught by `make lint` and auto-fixed by `make format`.

## Native Import Order: regopy Loads First

`src/syntara/__init__.py` imports `regopy` before anything else, on purpose. Do not remove or reorder this preload.

**Mechanism:** regopy's native library (`librego_shared.so`, from rego-cpp) statically links the snmalloc allocator and wrongly exports `operator new`/`operator delete` with default visibility. Whichever native library loads first wins the libstdc++ allocator symbol bindings for the whole process. When greenlet (pulled in by SQLAlchemy async) or temporalio's Rust bridge loads before regopy, allocations and frees inside rego evaluations cross two allocators and every `Interpreter.query()` permanently leaks ~69 KB of native memory — about 2.5 MB per cache-missing authorization request, which OOM-killed the backend (2 Gi limit) under E2E load. With regopy loaded first, the same workload leaks ~0.1 KB per evaluation.

**Guards, in order of firing:**

1. **The preload itself** (`src/syntara/__init__.py`) — guarded `import regopy`. Only two failures are tolerated and recorded in `syntara._REGOPY_PRELOAD_ERROR`: regopy not installed, and the known UBI E2E-image gap where `libatomic.so.1` is missing (PR #560). Any other loader failure raises immediately.
2. **Startup tripwire** (`syntara/authz/evaluator.py`) — `RegoEvaluator.start()` logs a WARNING if greenlet or temporalio's Rust bridge (`temporalio.bridge.temporal_sdk_bridge`) ended up before regopy in `sys.modules` insertion order, including the recorded preload error.
3. **Unit tests** (`tests/unit/authz/test_regopy_import_order.py`) — subprocess tests assert the preload order and both guard branches.
4. **Leak canary** (`tests/integration/authz/test_regopy_leak_canary.py`) — measures RSS growth over 800 in-app evaluations; a regression fails at ~55 MB against a 25 MB threshold.


## `__init__.py` Conventions

### No Re-exports

Syntara is not a library — it has no external consumers or public API to maintain. `__init__.py` files should **not** re-export symbols. Re-exports introduce circular import risks and add complexity without value.

**Standard:** Use full import paths to the defining module:

```python
# Correct — import from the defining module
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.execution import Execution, ExecutionStatus

# Wrong — import via __init__.py re-export
from syntara.workflows.models import Workflow, Execution
```

Full import paths improve code readability, make it easier to trace where symbols are defined, and eliminate circular import issues.

**`__init__.py` files should be empty or minimal.** If a docstring is needed to describe the package, that is acceptable, but do not add re-exports or `__all__` definitions.

New code must use full import paths from the start.

## Exception Handler Imports

Exception modules (`exceptions.py`) wire themselves to error handlers via the `@fastapi_exception` decorator. Use **string-based handler references** to avoid circular imports between `exceptions.py` and `error_handlers.py`:

```python
# Correct — string reference, no import of error_handlers needed
@fastapi_exception(handler="syntara.aap.error_handlers.aap_not_configured_handler")
class AAPNotConfiguredError(SyntaraError): ...

# Wrong — direct import creates exceptions ↔ error_handlers cycle
from syntara.aap.error_handlers import aap_not_configured_handler

@fastapi_exception(handler=aap_not_configured_handler)
class AAPNotConfiguredError(SyntaraError): ...
```

The `@fastapi_exception` decorator resolves string paths via `importlib` at registration time. See `src/syntara/auth/exceptions.py` for the reference implementation. See `src/syntara/core/exception_registry.py` line 59.

All domains use string-based handler references. The only remaining import cycle edge is `auth.__init__` ↔ `auth.dependencies` (accepted — public API boundary).

## TYPE_CHECKING Pattern

Use `TYPE_CHECKING` to avoid circular imports and reduce runtime import overhead.

**When to use:**

- Type hints that would cause circular imports
- Type hints for expensive-to-import modules (especially in hot paths)
- Forward references that aren't needed at runtime

**Pattern:**

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID
    from syntara.workflows.models.workflow import Workflow
    from syntara.workflows.models.workflow_version import WorkflowVersion
```

**Example (from `src/syntara/workflows/models/execution.py`):**

```python
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID

from pydantic import ConfigDict
from sqlalchemy import BigInteger, String, Text, text
from sqlmodel import Column, DateTime, Field, Index, Relationship

if TYPE_CHECKING:
    from syntara.workflows.models.activity_execution import ActivityExecution
    from syntara.workflows.models.workflow import Workflow
    from syntara.workflows.models.workflow_version import WorkflowVersion


class Execution(UserOwnedResource, SoftDeletableResource, table=True):
    """Execution SQLModel for workflow runtime instances."""

    # Relationships (TYPE_CHECKING imports used here)
    workflow: "Workflow" = Relationship(back_populates="executions")
    workflow_version: "WorkflowVersion" = Relationship(back_populates="executions")
    activities: list["ActivityExecution"] = Relationship(back_populates="execution")
```

**Key points:**

- Imports inside `if TYPE_CHECKING:` blocks are only loaded during type checking (mypy, IDE)
- Use deferred evaluation (quoted annotations) for type hints: `workflow: "Workflow"` instead of `workflow: Workflow` — this avoids runtime evaluation of the import
- This breaks circular dependencies between models that reference each other

## Enum and StrEnum over Literal

Prefer `Enum` or `StrEnum` over `Literal` for defining fixed sets of values. `Enum` types are extensible, introspectable, and produce clearer error messages than `Literal` unions.

```python
# Correct — use StrEnum
from enum import StrEnum

class ExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

# Wrong — avoid Literal for fixed value sets
from typing import Literal
ExecutionStatus = Literal["pending", "running", "completed", "failed"]
```

This does not affect the use of quoted annotations for deferred evaluation (e.g., `workflow: "Workflow"` for `TYPE_CHECKING` imports).

## Domain Module Structure

Each domain follows a consistent structure:

```
src/syntara/{domain}/
├── __init__.py           # Empty or minimal (no re-exports)
├── router.py             # FastAPI routes (auto-discovered by core.router_discovery)
├── models/
│   ├── __init__.py       # Package marker only (no re-exports)
│   ├── {entity}.py       # One model per file
│   └── ...
├── services/
│   └── {domain}_service.py
├── exceptions.py         # Domain-specific exceptions (optional)
├── error_handlers.py     # FastAPI exception handlers (optional)
├── utils/                # Domain-specific utilities (optional)
└── ws/                   # WebSocket handlers (optional)
```

**Router Auto-Discovery:**

Routers are automatically discovered and registered by `syntara.core.router_discovery` if they:

1. Are located at `src/syntara/{domain}/router.py` or `src/syntara/api/v1/{module}.py`
2. Export a router via one of these (tried in order):
   - A `router` variable (an `APIRouter` instance) — most common
   - A `build_router()` function that returns an `APIRouter`
   - A `build_{module}_router()` function that returns an `APIRouter`

**Example (`src/syntara/workflows/router.py`):**

```python
"""Workflow API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.api.auth import get_current_user
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.workflows.models import WorkflowListParams
from syntara.workflows.services import WorkflowService

router = APIRouter(prefix="/workflows", tags=["workflows"])
```

**Models Organization:**

- One entity per file: `models/workflow.py`, `models/execution.py`, `models/activity_execution.py`
- Use SQLModel for both database tables and API schemas (no separate Pydantic models)
- Import models from their defining module, not via `__init__.py` (see [No Re-exports](#no-re-exports))

**Services:**

- Domain-specific business logic lives in `services/{domain}_service.py`
- Services are dependency-injected via FastAPI `Depends()`

## When to Create a New Module

**Create a new domain module when:**

- Adding a new API resource with distinct business logic
- Introducing a new bounded context (DDD-style domain boundary)
- The functionality doesn't naturally fit into existing domains

**Extend an existing module when:**

- Adding related entities to an existing domain (e.g., `WorkflowVersion` to `workflows`)
- Adding new operations to existing resources
- Implementing additional API endpoints for existing entities

**Guidelines:**

- Prefer fewer, well-organized modules over many small modules
- Avoid creating modules for single classes unless they represent a distinct domain
- Follow the existing pattern: if similar functionality exists in another domain, mirror that structure

## Tooling vs Convention

**Automatically enforced by tooling:**

- Import ordering (Ruff isort rules via `make format` and `make lint`)
- Unused imports in non-`__init__.py` files (Ruff F401)
- Import style (Ruff I rules)
- Import cycle detection (`make check-cycles` — see [Static Analysis](/docs/standards/static-analysis.md))
- Orphan module detection (`make check-orphans`)

**Enforced by convention (code review):**

- No re-exports in `__init__.py` files
- String-based handler references in `@fastapi_exception` (not direct imports)
- Proper use of `TYPE_CHECKING` for circular import avoidance
- Module structure (one entity per file, router auto-discovery)
- Domain organization and module boundaries

**Validation:**

Run these commands before committing:

```bash
make format    # Auto-fix import order
make lint      # Check all code quality rules
make typecheck # Verify type hints (mypy strict mode)
```

## Reference

| File | Purpose |
|---|---|
| `pyproject.toml` | Ruff isort configuration, per-file ignores for `__init__.py` |
| `src/syntara/core/router_discovery.py` | Router auto-discovery logic |
| `src/syntara/workflows/models/__init__.py` | Example of `__all__` re-export pattern |

Generated By: Claude Code (Claude Opus 4.6)
