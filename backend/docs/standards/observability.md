# Observability Standards

## Overview

Syntara implements a two-system observability architecture:

1. **Metrics** - Performance monitoring via Prometheus (technical operations)
2. **Telemetry** - Product analytics via Segment.com (business intelligence)

Both systems follow the fire-and-forget principle: observability code MUST NEVER cause business logic to fail.

## System Architecture

### Metrics System (Prometheus)

**Purpose:** Monitor system performance, resource utilization, and operational health.

**Location:** `src/syntara/metrics/`

**Endpoint:** `/metrics` (OpenMetrics/Prometheus format)

**Components:**
- `MetricsRecorder` - Central recording API
- `MetricsStore` - In-memory retention (configurable, default 24h)
- `OrchestratorPrometheusMetrics` - Prometheus instrument registry
- `MetricsMiddleware` - ASGI middleware for HTTP request metrics

**Metrics tracked:**
- Request latency and throughput
- HTTP error rates (classified by type: timeout, rate_limit, validation, internal)
- LLM call duration, token usage (input/output), Time-To-First-Token (TTFT)
- Workflow execution duration, completion rate
- Activity execution success rate
- Database query response time, connection pool utilization
- Tool execution duration and success rate

### Telemetry System (Segment.com)

**Purpose:** Capture product usage patterns for data-driven product improvement.

**Location:** `src/syntara/telemetry/`

**Components:**
- `AuditEventDispatcher` - Routes domain events to registered handlers (shared with audit system)
- `AuditEventHandler[T]` - Base class for telemetry handlers (side-effect-only, return `None`)
- `TelemetryClientRegistry` - Singleton registry managing Segment client lifecycle
- `TelemetryMiddleware` - ASGI middleware for API call telemetry
- Domain events - Lightweight dataclasses dispatched from business logic
- Telemetry handlers - Located in `src/syntara/telemetry/handlers/`, auto-discovered at startup

**Events collected:**
- Workflow execution (start, completion with status/duration/error)
- Activity execution (type, status, duration, error type)
- Workflow version operations (created, restored, published, unpublished, exported)
- API calls (endpoint, method, status, response time, payload size)

**Configuration:**
- `APP_SEGMENT_WRITE_KEY` - Segment.com write key
- `APP_SEGMENT_ENDPOINT` - Segment.com endpoint URL
- `APP_ENTITLEMENT_ID` - Optional entitlement identifier (included in all events)

**Privacy:** No PII collected. No credentials collected.

## When to Use Which System

| Use Case | System | Rationale |
|----------|--------|-----------|
| Response latency | Metrics | Operational health, alerting |
| Error rate by endpoint | Metrics | Operational health, alerting |
| LLM token usage | Metrics | Cost tracking, performance |
| Workflow completion rate | Both | Metrics for ops, Telemetry for product |
| User behavior patterns | Telemetry | Product intelligence |
| Feature adoption | Telemetry | Product intelligence |
| Resource utilization | Metrics | Infrastructure scaling |

## Fire-and-Forget Principle

Observability code MUST follow the fire-and-forget pattern. The audit framework enforces this automatically — `AuditEventDispatcher.dispatch()` never raises, and handler exceptions are caught and logged separately. For any custom observability code outside the audit framework, apply the same principle manually:

**Requirements:**
- Exceptions MUST be caught and logged, NEVER propagated
- Business logic MUST NOT depend on observability success
- Failure to record metrics/telemetry MUST NOT block operations
- Log observability failures at DEBUG or WARNING level, not ERROR

## Adding Metrics

### 1. Define the Metric Type

Add to `src/syntara/metrics/types.py`:

```python
class MetricType(str, Enum):
    MY_NEW_METRIC = "my_new_metric"
```

### 2. Register Prometheus Instrument

For component-level metrics, add to `_COMPONENT_METRIC_MAP` in `src/syntara/metrics/recorder.py`:

```python
_COMPONENT_METRIC_MAP: dict[MetricType, tuple[str, str, tuple[str, ...]]] = {
    MetricType.MY_NEW_METRIC: ("my_new_metric_seconds", "histogram", ("label_name",)),
}
```

Tuple format: `(prometheus_attribute_name, action, extra_label_keys)`
- Actions: `"gauge"`, `"histogram"`, `"counter"`

For system-wide metrics, add dispatch logic to `_dispatch_prometheus` in `src/syntara/metrics/recorder.py`.

### 3. Record the Metric

```python
from syntara.metrics.recorder import MetricsRecorder
from syntara.metrics.types import MetricType

recorder = MetricsRecorder()

# Simple recording
recorder.record(
    MetricType.MY_NEW_METRIC,
    value=245.5,
    unit="ms",
    labels={"component": "tool_manager", "label_name": "value"},
)

# Context manager for timing
with recorder.time(MetricType.MY_NEW_METRIC, labels={"component": "tool_manager"}):
    result = perform_operation()
```

### 4. LLM Instrumentation

Use `record_llm_call` wrapper for invoke-style calls:

```python
from syntara.metrics.instrumentation import record_llm_call

result = await record_llm_call(
    recorder,
    lambda: llm.ainvoke(messages),
    model="anthropic/claude-3.5-sonnet",
)
```

For streaming calls, use `LLMStreamTracker`:

```python
from syntara.metrics.instrumentation import LLMStreamTracker

tracker = LLMStreamTracker(recorder, model="gpt-4")
async for event in graph.astream_events(...):
    tracker.process_event(event)
```

## Adding Telemetry Events

Telemetry events are emitted through the **Audit Framework**. Business logic dispatches a lightweight domain event, and the framework routes it to one or more handlers — an audit handler that produces a structured log entry and/or a telemetry handler that sends an event to Segment.

### 1. Define the Domain Event

Create a dataclass in the appropriate `audit/` package (e.g., `src/syntara/workflows/audit/`):

```python
from dataclasses import dataclass, field
from uuid import UUID

@dataclass
class MyFeatureEvent:
    """Domain event fired when my feature is used."""

    feature_id: UUID
    action: str
    duration_ms: int | None = field(default=None)
    request_id: UUID | None = field(default=None)
```

Domain events are plain dataclasses — no base class needed. They carry only the raw data describing what happened.

### 2. Create an Audit Handler (optional — only if you need audit log entries)

This step is only required if you want to produce structured audit log entries (persisted to the database). Skip this step if you only need telemetry (Segment events). See [Audit Framework](/docs/audit.md) for full details.

Create a handler in the same `audit/` package. It maps the domain event to a normalized `AuditEvent`:

```python
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData

class MyFeatureHandler(AuditEventHandler[MyFeatureEvent]):
    """Maps MyFeatureEvent to an AuditEvent for the audit log."""

    def handle(self, event: MyFeatureEvent) -> AuditEvent:
        data = AuditContextData(
            data_type="my-feature-used",
            action=event.action,
            duration_ms=event.duration_ms,
        )
        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action="my_feature_used",
            event_message=f"Feature used: {event.action}",
            source_component="syntara.my_feature",
            structured_data=data,
            resource_urn=f"urn:syntara:feature:{event.feature_id}",
        )
```

### 3. Create a Telemetry Handler (for Segment events)

Create a handler in `src/syntara/telemetry/handlers/`. Telemetry handlers are side-effect-only — they return `None`:

```python
import structlog
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import AuditEvent
from syntara.telemetry.client import get_telemetry_registry

logger = structlog.stdlib.get_logger(__name__)

class MyFeatureTelemetryHandler(AuditEventHandler[MyFeatureEvent]):
    """Emits a Segment telemetry event (side-effect only)."""

    def handle(self, event: MyFeatureEvent) -> AuditEvent | None:
        try:
            registry = get_telemetry_registry()
            if not registry.is_initialized():
                return None

            registry.send_event(
                MyFeatureTelemetryEvent(
                    feature_id=str(event.feature_id),
                    action=event.action,
                    duration_ms=event.duration_ms,
                    entitlement_id=registry.entitlement_id,
                    request_id=event.request_id,
                )
            )
        except Exception:
            logger.warning("Failed to emit my_feature telemetry (non-fatal)", exc_info=True)

        return None  # Side-effect only, no audit log entry
```

### 4. Dispatch the Event

From business logic, dispatch the domain event. The framework routes it to all registered handlers:

```python
from syntara.audit.dispatcher import AuditEventDispatcher

AuditEventDispatcher.dispatch(
    MyFeatureEvent(
        feature_id=feature_id,
        action="created",
        duration_ms=elapsed_ms,
        request_id=request_id,
    )
)
```

### Handler Discovery and Registration

Handlers are discovered automatically at startup. Ensure the handler's package is imported and passed to `discover_handlers()` in the application entrypoint (e.g., `worker.py` or `main.py`):

```python
import syntara.telemetry.handlers  # Package scanned by discover_handlers()
from syntara.audit.discovery import discover_handlers
from syntara.audit.dispatcher import AuditEventDispatcher

registry = discover_handlers(syntara.telemetry.handlers)
AuditEventDispatcher.register(registry)
```

**Requirements for handler discovery:**
- Handlers MUST be zero-arg constructable (no constructor parameters)
- Handlers that need collaborators should resolve them lazily inside `handle()`
- Each handler class must be a concrete subclass of `AuditEventHandler[T]`
- Multiple handlers can handle the same event type (e.g., one for audit log, one for telemetry)

## What to Instrument

### Critical Paths (MUST instrument)

- All public API endpoints (automatically handled by `MetricsMiddleware`)
- LLM calls (use `record_llm_call` or `LLMStreamTracker`)
- Workflow execution start/completion
- Activity execution
- Tool execution
- Database queries (long-running or high-volume)

### Error Paths (MUST instrument)

- All exception handlers in critical paths
- Validation failures
- Rate limiting events
- Timeout events
- External service failures

### Performance-Sensitive Operations (SHOULD instrument)

- Cache operations (hits, misses, lookup duration)
- Serialization/deserialization (workflows, activities)
- Template resolution
- Complex graph traversals

## What NOT to Instrument

### Privacy and Security

**NEVER record:**
- Personally Identifiable Information (PII)
- Credentials (passwords, API keys, tokens)
- User-generated content verbatim (summarize or hash)
- Internal IP addresses or hostnames (use aggregated identifiers)

### Cardinality Concerns

**AVOID unbounded labels:**
- User IDs (use hashed/anonymized identifiers or omit)
- UUIDs in metric labels (use as request IDs in logs, not labels)
- Raw file paths (use normalized paths or component names)
- Arbitrary user input

**Correct cardinality:**
- Endpoint templates (`/api/v1/executions/{execution_id}`) not raw paths
- Fixed set of status codes
- Component names from `COMPONENT_LABELS`
- Model names (provider-prefixed, e.g., `anthropic/claude-3.5-sonnet`)

### Label Limits

Prometheus labels create a combinatorial explosion of time series:
- Keep label count per metric under 5
- Ensure each label has a bounded set of values (preferably < 100)
- Use structured logs for high-cardinality data (request IDs, stack traces)

## Middleware Patterns

### HTTP Metrics Middleware

`MetricsMiddleware` is applied globally in `src/syntara/api/main.py`:

```python
from syntara.metrics.middleware import MetricsMiddleware

app.add_middleware(MetricsMiddleware, recorder=metrics_recorder)
```

**Automatic metrics:**
- Request duration with endpoint template, method, status, and **interface** (`api` or `ui`)
- Error classification (timeout, rate_limit, validation, internal) with interface label
- Request ID validation and `X-Request-Id` header echo

**Excluded paths:**
- `/metrics` (avoid self-instrumentation loops)
- `/healthz/live`, `/healthz/ready` (high-volume, low-signal)

### Interface Tagging (API vs UI)

Every HTTP request is classified as originating from the **UI** or an **external API consumer** (CLI, CI/CD pipeline, script, MCP client). The detected value is stored in the `interface` label on `REQUEST_DURATION` and `ERROR` metrics, and propagated via a request-scoped `ContextVar` for downstream instrumentation.

**Detection** (`src/syntara/metrics/interface_tag.py`):

| Condition | Classification |
|---|---|
| `X-Orchestrator-Client: ui` header present (case-insensitive) | `ui` |
| Header absent, empty, or any other value | `api` |

**UI clients** send the header automatically:

- Typed `openapi-fetch` clients in `syntara-ui` use `interfaceTagMiddleware` (sets `X-Orchestrator-Client: ui` on every request).
- Pre-auth raw `fetch` call sites (login, CSRF, providers) use `orchestratorUiClientHeaders()` from `utils/orchestratorClientHeader.ts`.

**External API consumers** should **omit** the header (default is `api`). Do not send `X-Orchestrator-Client: ui` unless the client is the Syntara UI.

**Reading the interface downstream:**

```python
from syntara.metrics.interface_tag import interface_context_var

interface = interface_context_var.get()  # "api" or "ui"
```

`MetricsMiddleware` sets this `ContextVar` at the start of each request, before routing and handler execution. Any middleware or instrumentation running inside the same async context can read it without explicit parameter passing.

**Label cardinality:** The `interface` label has exactly two values (`api`, `ui`), so it adds no cardinality risk.

### Custom Middleware

For component-specific telemetry, dispatch domain events through the audit framework:

```python
from syntara.audit.dispatcher import AuditEventDispatcher

class MyFeatureMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        feature_id = extract_feature_id(scope)

        try:
            await self.app(scope, receive, send)
            AuditEventDispatcher.dispatch(
                MyFeatureEvent(feature_id=feature_id, action="completed")
            )
        except Exception:
            AuditEventDispatcher.dispatch(
                MyFeatureEvent(feature_id=feature_id, action="failed")
            )
            raise
```

## Testing Observability Code

### Unit Testing Metrics

Use isolated Prometheus registry:

```python
import pytest
from prometheus_client import CollectorRegistry
from syntara.metrics.recorder import MetricsRecorder

@pytest.fixture
def recorder() -> MetricsRecorder:
    """Fresh MetricsRecorder with isolated Prometheus registry."""
    return MetricsRecorder(
        retention_seconds=3600,
        max_records=10_000,
        prometheus_registry=CollectorRegistry(),
    )

def test_my_metric_recording(recorder):
    recorder.record(MetricType.MY_METRIC, 42.0, labels={"component": "test"})

    # Query recorded metrics
    records = list(recorder.query(metric_types={MetricType.MY_METRIC}))
    assert len(records) == 1
    assert records[0].value == 42.0
```

### Unit Testing Telemetry Handlers

Test handlers directly by calling `handle()` and verifying the side effects:

```python
from unittest.mock import MagicMock, patch
from uuid import uuid4

def test_my_feature_telemetry_handler():
    event = MyFeatureEvent(feature_id=uuid4(), action="created")

    with patch("syntara.telemetry.handlers.my_feature.get_telemetry_registry") as mock_get:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "test-entitlement"
        mock_get.return_value = registry

        handler = MyFeatureTelemetryHandler()
        result = handler.handle(event)

        assert result is None  # Side-effect only
        registry.send_event.assert_called_once()
        sent = registry.send_event.call_args[0][0]
        assert sent.action == "created"
```

### Unit Testing Audit Handlers

Test that audit handlers produce the correct `AuditEvent`:

```python
def test_my_feature_audit_handler():
    event = MyFeatureEvent(feature_id=uuid4(), action="created", duration_ms=150)

    handler = MyFeatureHandler()
    audit_event = handler.handle(event)

    assert audit_event is not None
    assert audit_event.event_action == "my_feature_used"
    assert audit_event.structured_data.duration_ms == 150
```

### Integration Testing

Enable observability in test fixtures, verify no exceptions:

```python
@pytest.mark.integration
async def test_workflow_execution_telemetry(test_client, db_session):
    """Verify workflow execution emits telemetry without errors."""
    response = await test_client.post(
        "/api/v1/workflows/execute",
        json={"workflow_id": "test-workflow"},
    )
    assert response.status_code == 200

    # Telemetry should not cause failures
    # Verify via log inspection or test registry if needed
```

### Disabling Observability in Tests

To reduce noise in unrelated tests:

```python
@pytest.fixture
def recorder() -> MetricsRecorder:
    return MetricsRecorder(enabled=False)
```

## Component Label Registry

Valid component labels are defined in `src/syntara/metrics/types.py`:

```python
COMPONENT_LABELS: dict[str, str] = {
    "api_service": "api_service",
    "workflow_engine": "workflow_engine",
    "temporal_worker": "temporal_worker",
    "execution_service": "execution_service",
    "invocation_service": "invocation_service",
    "routing_service": "routing_service",
    "tool_manager": "tool_manager",
    "database": "database",
    "system_wide": "system_wide",
}
```

When adding a new component:
1. Add to `COMPONENT_LABELS`
2. Update metrics map if needed
3. Use consistently across all metrics for that component

## Request IDs

**Tracing:** Clients can pass an `X-Request-Id` header (UUID) on any HTTP request. The value is validated, stored in a ContextVar, echoed back in the response, and automatically included in every telemetry event emitted during that request. Use `request_id` for end-to-end request tracing.

## Best Practices Summary

1. **Fire-and-forget:** Observability failures MUST NOT propagate.
2. **Label cardinality:** Use bounded sets of label values (< 100 per label).
3. **Privacy first:** No PII, no credentials, ever.
4. **Template endpoints:** Use route templates (`/api/v1/users/{id}`) not raw paths.
5. **Test isolation:** Use isolated registries for unit tests.
6. **Consistent naming:** Follow existing patterns (snake_case, descriptive).
7. **Documentation:** Add docstrings to new metrics and events.
8. **Constitutional compliance:** Instrument all critical paths and error paths.

## Tooling vs Convention

**Enforced by tooling:**

- `MetricsMiddleware` automatically instruments all HTTP endpoints (except `/metrics`, `/healthz/*`)
- `TelemetryMiddleware` automatically captures API call telemetry
- `AuditEventDispatcher` enforces fire-and-forget (never raises, logs failures)
- `discover_handlers()` auto-discovers and registers handlers at startup
- Prometheus client validates metric names and label combinations at registration time
- Pydantic validates telemetry event models

**Convention only:**

- Fire-and-forget pattern (catch-and-log in observability code)
- Label cardinality limits (< 100 values per label, < 5 labels per metric)
- `COMPONENT_LABELS` registry maintenance
- Privacy rules (no PII, no credentials)
- Request ID propagation via structured logging
- Choosing metrics vs telemetry for a given use case

## Reference

| File | Purpose |
|---|---|
| `src/syntara/metrics/recorder.py` | `MetricsRecorder` central recording API |
| `src/syntara/metrics/types.py` | `MetricType` enum, `COMPONENT_LABELS` |
| `src/syntara/metrics/middleware.py` | `MetricsMiddleware` ASGI middleware |
| `src/syntara/metrics/interface_tag.py` | API-vs-UI interface detection and `interface_context_var` |
| `src/syntara/metrics/instrumentation.py` | `record_llm_call`, `LLMStreamTracker` |
| `src/syntara/audit/dispatcher.py` | `AuditEventDispatcher` event routing |
| `src/syntara/audit/handler.py` | `AuditEventHandler[T]` base class |
| `src/syntara/audit/discovery.py` | Auto-discovery of handler classes |
| `src/syntara/telemetry/handlers/` | Telemetry handlers (side-effect-only) |
| `src/syntara/telemetry/events/` | Telemetry event models (Segment payloads) |
| `tests/unit/metrics/` | Metrics test suite |
| `tests/unit/telemetry/` | Telemetry test suite |

Generated By: Claude Code (Claude Opus 4.6)
