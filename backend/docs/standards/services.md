# Service Architecture Standards

This document defines the service layer patterns for the Syntara project — how services are structured, how they integrate with FastAPI, and how background workers operate.

## BaseService

All services MUST inherit from `BaseService` in `src/syntara/core/services/base.py`. This ensures consistent filtering, sorting, pagination, and label handling across the system.

```python
from syntara.core.services.base import BaseService

class WorkflowService(BaseService):
    def __init__(self, db: AsyncSession, current_user: User) -> None:
        super().__init__(db=db, current_user=current_user, model=Workflow)
```

### `list_resources()` — Unified Pagination

`BaseService.list_resources()` is the **only** way to handle list queries. It provides:

- Cursor-based keyset pagination (N+1 fetch pattern)
- Filter parsing and application
- Sort parsing with stable ordering (tiebreak on `id`)
- Label filtering via JSONB operators
- Optional total count

All services use this method for collection endpoints. Do not implement custom pagination.

## Extension Protocols

Services customize behavior by implementing `@runtime_checkable` Protocol mixins defined in `src/syntara/core/services/extensions.py`:

### EnrichQueryMixin

Customize SQL queries before execution (add eager loading, joins, etc.):

```python
class WorkflowService(BaseService, EnrichQueryMixin):
    def enrich(self, query):
        return query.options(selectinload(Workflow.versions))
```

### ConvertResourceMixin

Transform database models into response objects:

```python
class WorkflowService(BaseService, ConvertResourceMixin):
    def convert_resource(self, resource):
        return WorkflowRead.model_validate(resource)
```

### PostProcessingMixin

Async post-processing after query, before response (e.g., sync status from external services):

```python
class ExecutionService(BaseService, PostProcessingMixin):
    async def post_process(self, resources):
        await self._sync_temporal_statuses(resources)
```

Default implementations (`DefaultEnrichQueryMixin`, `DefaultConvertResourceMixin`, `DefaultPostProcessingMixin`) are no-ops. Services that don't implement a protocol get the default behavior automatically.

## Dependency Injection

### Provider Functions

Each domain router defines a provider function for its service:

```python
def get_workflow_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> WorkflowService:
    return WorkflowService(db, current_user)
```

### Usage in Endpoints

Services are injected via `Annotated` with `Depends()`:

```python
@router.get("")
async def list_workflows(
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
    params: Annotated[WorkflowListParams, Depends()],
) -> WorkflowListResponse:
    return await service.list(...)
```

This pattern centralizes service creation and ensures every endpoint gets a fresh service instance with the correct session and user.

## Application Lifecycle

### Lifespan Context Manager

Application startup and shutdown are managed via an `@asynccontextmanager` lifespan in `src/syntara/api/main.py`:

**Startup (before yield):**
1. Router auto-discovery and registration
2. WebSocket router registration
3. Telemetry initialization
4. WebSocket health monitoring start
5. Periodic workers start (`PeriodicCollector`, `CompletionPoller`, `MetricsCleanupWorker`)

**Shutdown (finally block):**
1. Stop periodic workers
2. Flush telemetry
3. Stop WebSocket monitoring
4. Dispose database engine (`engine.dispose()`)
5. Clean up lock files

### Middleware Stack

Middleware registration order and execution order are **reversed** in FastAPI (last registered = outermost = executes first).

**Registration order** (as written in `main.py`):
1. `CORSMiddleware`
2. `MetricsMiddleware` (Prometheus)
3. `AuditMiddleware` (audit events + Segment telemetry via dispatcher)

**Execution order** (at runtime):
1. `AuditMiddleware` — outermost, emits audit events (including `api_call` telemetry via `APICallTelemetryHandler`)
2. `MetricsMiddleware` — measures request duration, records Prometheus metrics
3. `CORSMiddleware` — handles CORS headers

## Periodic Workers

Background tasks use `PeriodicWorker` from `src/syntara/core/workers/periodic.py`.

### Pattern

```python
worker = PeriodicWorker(
    name="my-worker",
    interval_seconds=300,
    session_factory=AsyncSessionLocal,
    callback=my_async_work_function,
    cleanup_callback=my_cleanup_function,  # optional
    coordinate=True,                       # default
)
worker.start()       # launches asyncio background task
await worker.stop()  # cancels task, runs cleanup
```

### Cross-Instance Coordination

When `coordinate=True` (default), the worker acquires a PostgreSQL transaction-level advisory lock (`pg_try_advisory_xact_lock`) before each cycle. This ensures only one application process runs the callback per cycle across all replicas.

Set `coordinate=False` for tasks that must run in every process (e.g., per-process connection cleanup).

### Lifecycle

- `start()` is idempotent — calling it multiple times is safe
- `stop()` cancels the background task and runs the optional cleanup callback
- Cycle errors are logged but do not stop the worker
- Cancellation during backoff sleep is handled gracefully

### Active Workers

| Worker | Location | Interval | Coordinate | Purpose |
|---|---|---|---|---|
| `PeriodicCollector` | `src/syntara/telemetry/periodic_collector.py` | configurable | yes | Flush telemetry events to Segment |
| `CompletionPoller` | `src/syntara/metrics/completion_poller.py` | configurable | yes | Poll for workflow completion status |
| `MetricsCleanupWorker` | `src/syntara/metrics/cleanup.py` | configurable | yes | Clean up old metrics records |

## Tooling vs Convention

**Enforced by tooling:**

- `BaseService.list_resources()` handles all filtering/sorting/pagination logic
- `@runtime_checkable` Protocol validation at runtime for extension mixins
- `PeriodicWorker` advisory lock coordination prevents duplicate execution
- FastAPI `Depends()` manages service lifecycle per request

**Convention only:**

- Inheriting from `BaseService` for all services
- Provider function pattern (`get_{domain}_service()`)
- Extension mixin usage (EnrichQuery, ConvertResource, PostProcessing)
- Middleware registration order
- Worker lifecycle (start in lifespan entry, stop in finally)

## Reference

| File | Purpose |
|---|---|
| `src/syntara/core/services/base.py` | `BaseService` with `list_resources()` |
| `src/syntara/core/services/extensions.py` | Protocol mixins and default implementations |
| `src/syntara/core/workers/periodic.py` | `PeriodicWorker` base class |
| `src/syntara/api/main.py` | Lifespan context manager, middleware stack |
| `src/syntara/telemetry/periodic_collector.py` | Telemetry flush worker |
| `src/syntara/metrics/completion_poller.py` | Completion polling worker |
| `src/syntara/metrics/cleanup.py` | Metrics cleanup worker |
