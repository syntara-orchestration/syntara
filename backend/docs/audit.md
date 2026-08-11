# Audit Framework

> **Developer Guide** — Understanding and using the Nexus audit system

## Table of Contents

1. [The Audit Framework](#1-the-audit-framework)
   - [Overview](#overview)
   - [Core Components](#core-components)
   - [Data Models](#data-models)
   - [Event Flow](#event-flow)
   - [Instrumentation Tools](#instrumentation-tools)
   - [Data Protection](#data-protection)
2. [Domain Integration Guide](#2-domain-integration-guide)
   - [Integration Pattern](#integration-pattern)
   - [Step-by-Step Integration](#step-by-step-integration)
   - [Domain Event Flow](#domain-event-flow)
3. [Example: Auth Domain Implementation](#3-example-auth-domain-implementation)
   - [Domain Events](#domain-events)
   - [Event Handlers](#event-handlers)
   - [Usage in Code](#usage-in-code)

---

## 1. The Audit Framework

### Overview

The audit framework provides **comprehensive, type-safe event tracking** for capturing system activities, user actions, and operational events across the Nexus platform. It follows an event-driven architecture with:

- **Guaranteed delivery** via transactional outbox pattern
- **Automatic CRUD capture** via PostgreSQL database triggers
- **PII sanitization** and payload size enforcement
- **Flexible actor detection** with 6-level priority cascade
- **Multiple instrumentation methods** (decorators, context managers, middleware, domain events, database triggers)
- **Fail-safe execution** that never breaks business operations

### Core Components

```mermaid
graph TB
    subgraph "Event Sources"
        A1[Domain Events]
        A2["@audit Decorator"]
        A3[audit_context Manager]
        A4[AuditMiddleware]
        A5[Database Triggers<br/>CRUD Operations]
    end

    subgraph "Event Processing"
        B1[AuditEventDispatcher]
        B2[AuditEventHandler]
        B3[emit_audit_event]
    end

    subgraph "Data Protection"
        C1[EventSanitizer<br/>PII Redaction]
        C2[Payload Truncation<br/>10KB Limit]
    end

    subgraph "Transactional Outbox"
        D1[Structured Logs<br/>stdout]
        D2[audit_outbox Table<br/>Atomic Commit]
        D3[AuditOutboxWorker<br/>Background Publisher]
        D5[OTEL Collector<br/>All Events]
    end

    A1 --> B1
    A2 --> B1
    A3 --> B1
    A4 --> B1
    A5 --> D2
    B1 --> B2
    B2 --> B3
    B3 --> C1
    C1 --> C2
    C2 --> D1
    C2 --> D2
    D2 --> D3
    D3 --> D5
```

#### Component Descriptions

| Component | Purpose | Location |
|-----------|---------|----------|
| **AuditEvent** | In-memory event envelope | `audit/models/audit_event.py` |
| **AuditOutboxRecord** | Transactional outbox table | `audit/outbox/models.py` |
| **AuditTableMetadata** | Audit configuration per table | `audit/outbox/models.py` |
| **AuditEventSource** | Event routing enum (BUSINESS_EVENT, CRUD_EVENT) | `audit/outbox/models.py` |
| **AuditContextData** | Universal structured data (extra=allow) | `audit/models/structured_data.py` |
| **AuditEventDispatcher** | Type-based event router | `audit/dispatcher.py` |
| **AuditEventHandler** | Domain event → AuditEvent mapper | `audit/handler.py` |
| **emit_audit_event** | Central emission point, writes to outbox | `audit/emitter.py` |
| **@audit** | Function decorator | `audit/decorators.py` |
| **FunctionExecutionEvent** | Domain event for @audit | `audit/events/function_execution.py` |
| **FunctionExecutionHandler** | Maps FunctionExecutionEvent → AuditEvent | `audit/events/function_execution.py` |
| **audit_context** | Context manager | `audit/context_managers.py` |
| **AuditContextEvent** | Domain event for audit_context | `audit/events/audit_context.py` |
| **AuditContextHandler** | Maps AuditContextEvent → AuditEvent | `audit/events/audit_context.py` |
| **AuditMiddleware** | HTTP request tracking | `audit/middleware.py` |
| **HTTPRequestEvent** | Domain event for HTTP requests | `audit/events/http_request.py` |
| **HTTPRequestHandler** | Maps HTTPRequestEvent → AuditEvent | `audit/events/http_request.py` |
| **audit_crud_operation()** | PostgreSQL trigger function for CRUD capture | Baseline revision `b69ef9067e66` |
| **set_audit_context()** | Before-flush hook, propagates context to Postgres | `core/database/session.py` |
| **EventSanitizer** | PII redaction | `audit/sanitization.py` |
| **AuditOutboxWorker** | Background outbox publisher | `audit/outbox/worker.py` |
| **AuditEventService** | Read-only query service | `audit/services/audit_event_service.py` |
| **seed_audit_metadata()** | Audit metadata seeder (populates audit_table_metadata and attaches triggers) | `audit/seed.py` |

### Data Models

#### Entity Relationship Diagram

```mermaid
erDiagram
    AuditEvent ||--|| AuditContextData : "has structured_data"
    AuditEvent ||--|| AuditOutboxRecord : "persisted via outbox"

    AuditEvent {
        UUID event_id PK
        EventCategory event_category
        EventSeverity event_severity
        EventStatus event_status
        string event_action
        UUID actor_id FK
        ActorType actor_type
        string actor_username
        string source_component
        string resource_urn "RFC 8141 URN, validated"
        string resource_name "Human-readable name"
        UUID workflow_id FK
        string activity_id
        UUID execution_id FK
        string event_message
        AuditContextData structured_data
    }

    AuditContextData {
        string data_type "UI discriminator field"
        string error_type "optional"
        string error_message "optional"
        any extra_fields "model_config extra=allow"
    }
```

**Note on `AuditEvent` fields:**

**`resource_urn`**: RFC 8141 compliant URN (format: `urn:<nid>:<nss>`). The field includes a Pydantic validator that checks URN format. Invalid URNs are logged as warnings and set to `None` (fail-safe behavior - audit emission never fails due to invalid URN format). PostgreSQL triggers automatically build URNs for CRUD events using the pattern `urn:syntara:<ModelName>:<uuid>`.

**`AuditContextData`:**  
All audit events use the same structured data type (`AuditContextData`) with `model_config = {"extra": "allow"}`. This allows handlers to include domain-specific fields alongside the base fields (`data_type`, `error_type`, `error_message`).

The `data_type` field is a string that identifies the event source for UI/frontend purposes:
- `"function"` - from `@audit` decorator (includes `function_args`, `function_result`)
- `"context"` - from `audit_context` manager (includes arbitrary `**context_data`)
- `"request_completed"` - from `AuditMiddleware` (includes `method`, `path`, `status_code`, `query_params`, `user_role`)
- Domain events set custom `data_type` values based on their needs

**Actor Identity Integrity:**  
The `actor_username` field is stored alongside `actor_id` and `actor_type` to provide complete actor identity. To ensure these fields remain synchronized and prevent potential security issues from id/username mismatches:

- `AuditContextEvent` accepts `actor_context: AuditActorContext` instead of discrete actor fields
- The handler extracts `actor_id`, `actor_type`, and `actor_username` atomically from the User object
- This guarantees the three fields always come from the same source record
- Domain events populate username from User objects or JWT payloads to maintain integrity
- `actor_username` is queryable via the `/api/v1/audit` endpoint for filtering and analysis

#### Key Enums

```python
class EventCategory(StrEnum):
    USER_ACTION = "user_action"
    WORKFLOW_EVENT = "workflow_event"
    AGENT_INTERACTION = "agent_interaction"
    LLM_INTERACTION = "llm_interaction"
    LLM_TOOL_CALL = "llm_tool_call"
    LLM_REASONING = "llm_reasoning"
    API_EXECUTION = "api_execution"
    SYSTEM_OPERATION = "system_operation"
    SECURITY_EVENT = "security_event"

class EventSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class EventStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"

class ActorType(StrEnum):
    USER = "user"
    SYSTEM = "system"
    SERVICE = "service"
```

### Event Flow

#### Complete Event Processing Pipeline

```mermaid
sequenceDiagram
    participant Code as Instrumented Code
    participant Dispatcher as AuditEventDispatcher
    participant Handler as AuditEventHandler
    participant Emitter as emit_audit_event()
    participant Sanitizer as EventSanitizer
    participant Truncator as Payload Truncation
    participant Logger as Structured Logger
    participant Outbox as audit_outbox Table
    participant Txn as Business Transaction

    Code->>Code: Create domain event<br/>(FunctionExecutionEvent,<br/>AuditContextEvent,<br/>HTTPRequestEvent, etc.)
    Code->>Dispatcher: dispatch(domain_event)

    Note over Dispatcher: Type-based routing<br/>via handler registry

    Dispatcher->>Handler: handle(domain_event)
    Note over Handler: Map domain event<br/>to AuditEvent

    Handler->>Handler: Build AuditContextData<br/>with data_type + extra fields
    Handler-->>Dispatcher: return AuditEvent

    Dispatcher->>Emitter: emit_audit_event(AuditEvent, session)

    Note over Emitter: Inject context vars<br/>(actor_id, workflow_id, etc.)

    Emitter->>Sanitizer: sanitize(structured_data)
    Sanitizer-->>Sanitizer: Redact passwords, tokens, secrets
    Sanitizer-->>Sanitizer: Redact email addresses
    Sanitizer-->>Sanitizer: Handle circular refs
    Sanitizer-->>Emitter: Sanitized data

    Emitter->>Truncator: enforce_payload_limit(data, 10KB)
    Truncator-->>Truncator: Collect string leaves
    Truncator-->>Truncator: Truncate largest if over limit
    Truncator-->>Emitter: Size-enforced data

    Emitter->>Logger: logger.info("audit_event", **event_dict)
    Logger-->>Logger: Write to stdout

    Emitter->>Outbox: session.add(AuditOutboxRecord)
    Note over Emitter,Outbox: Written within business transaction<br/>Guaranteed atomic commit

    Txn->>Txn: COMMIT
    Note over Txn: Both business data<br/>AND audit event<br/>committed atomically

    Note over Code: Business logic continues<br/>Audit never blocks
```

#### Transactional Outbox Architecture

This diagram shows the complete audit event flow from two different sources through the transactional outbox pattern to the OTEL Collector:

```mermaid
sequenceDiagram
    participant Source1 as Explicit Event Sources<br/>(Middleware, @audit, audit_context, DomainEvents)
    participant Source2 as PostgreSQL Triggers<br/>(CRUD Operations)
    participant Dispatcher as AuditEventDispatcher
    participant Handler as AuditEventHandler
    participant Emitter as emit_audit_event()
    participant BeforeFlush as set_audit_context()<br/>(before_flush hook)
    participant Session as Database Session
    participant Outbox as audit_outbox Table
    participant BusinessDB as Business Database
    participant Worker as AuditOutboxWorker<br/>(Background)
    participant OTEL as OTEL Collector<br/>(All Events)

    rect rgb(230, 240, 250)
        Note over Source1,Emitter: Explicit Event Path (BUSINESS_EVENT)
        Source1->>Dispatcher: dispatch(domain_event)
        Dispatcher->>Handler: handle(domain_event)
        Handler->>Handler: Map to AuditEvent
        Handler-->>Dispatcher: return AuditEvent
        Dispatcher->>Emitter: emit_audit_event(event, session)
        Emitter->>Emitter: Inject context, sanitize, truncate
        Emitter->>Session: session.add(AuditOutboxRecord)<br/>event_source=BUSINESS_EVENT
    end

    rect rgb(240, 250, 230)
        Note over Source2,BeforeFlush: CRUD Event Path (CRUD_EVENT)
        Session->>BeforeFlush: Before flush hook
        BeforeFlush->>BeforeFlush: Read actor/workflow context<br/>from ContextVars
        BeforeFlush->>Session: SET LOCAL app.actor_id = '...'<br/>SET LOCAL app.workflow_id = '...'
        Note over Session: Context propagated<br/>to Postgres session
    end

    rect rgb(255, 250, 240)
        Note over Session,BusinessDB: Transactional Outbox (Atomic Commit)
        Session->>BusinessDB: FLUSH changes
        BusinessDB->>Source2: AFTER INSERT/UPDATE/DELETE triggers fire
        Source2->>Source2: audit_crud_operation() function<br/>reads app.actor_id, app.workflow_id
        Source2->>Source2: Build AuditEvent JSON<br/>with changes/resource_data
        Source2->>Outbox: INSERT INTO audit_outbox<br/>event_source=CRUD_EVENT
        Session->>BusinessDB: COMMIT
        Note over BusinessDB: Business data,<br/>business audit events,<br/>AND CRUD audit events<br/>all committed atomically
    end

    rect rgb(250, 240, 255)
        Note over Worker,OTEL: Background Publishing (Guaranteed Delivery)
        Worker->>Worker: Poll every N seconds
        Worker->>Outbox: SELECT * FROM audit_outbox<br/>FOR UPDATE SKIP LOCKED
        Outbox-->>Worker: Unpublished events

        Worker->>Worker: Build ReadableLogRecord batch<br/>(with audit.event_source discriminator)
        Worker->>OTEL: OTLPLogExporter.export(batch)<br/>(synchronous, built-in retry)

        alt Export SUCCESS
            Worker->>Outbox: DELETE FROM audit_outbox
            Note over Worker: Events confirmed delivered<br/>Outbox cleaned up
        else Export FAILURE
            Note over Worker: Records retained in outbox<br/>Will retry next cycle
        end
    end

    Note over Source1,OTEL: Guarantees:<br/>✓ At-least-once delivery (survives crashes)<br/>✓ Confirmed delivery before WAL deletion<br/>✓ Atomic commit (business + audit)<br/>✓ No blocking (async worker)<br/>✓ Complete coverage (CRUD + explicit events)<br/>✓ Dual routing (business → audit DB + OTEL, CRUD → OTEL only)<br/>✓ Event source discrimination (audit.event_source field)
```

**Key architectural properties:**

1. **Transactional Outbox**: Audit events are written to `audit_outbox` within the same database transaction as business data, guaranteeing atomicity. If the transaction rolls back, both business changes and audit events are discarded together.

2. **Dual Event Paths**:
   - **Explicit events** (middleware, decorators, domain events) → dispatcher/handler pipeline → `emit_audit_event()` → outbox with `event_source=BUSINESS_EVENT`
   - **CRUD events** (database mutations) → PostgreSQL triggers → outbox with `event_source=CRUD_EVENT` (bypasses dispatcher/handler)

3. **Context Propagation**: The `set_audit_context()` before-flush hook reads actor/workflow context from ContextVars and writes them as Postgres session variables (`SET LOCAL app.actor_id`, etc.) so triggers can access them.

4. **Automatic CRUD Capture**: PostgreSQL triggers (`audit_crud_operation()`) observe all INSERT/UPDATE/DELETE operations on auditable tables without requiring developers to manually instrument code, guaranteeing audit trail completeness.

5. **OTEL Export**: The background worker exports events directly via `OTLPLogExporter.export()` (synchronous with built-in retry+backoff) with an `audit.event_source` discriminator (`business` or `crud`). Outbox records are only deleted after confirmed delivery.

6. **Guaranteed Delivery**: The background worker polls the outbox and publishes to the OTEL Collector. Events survive process crashes between business commit and audit publication. On export failure, records are retained in the outbox for retry on the next polling cycle.

7. **Non-Blocking**: Business transactions never wait for OTEL export. The worker processes events asynchronously in the background.

#### Trigger-Based CRUD Audit System

The automatic CRUD audit trail is implemented using **PostgreSQL triggers** that fire on INSERT/UPDATE/DELETE operations and write directly to the `audit_outbox` table.

**Architecture Components:**

1. **AuditTableMetadata Table**
   - Stores audit configuration for each table (populated by seeder, not migration)
   - Fields: `table_name`, `model_name`, `audit_level`, `auditable_fields`
   - Allows the trigger function to determine if a table should be audited
   - **Clean-slate approach:** Seeder deletes all existing records and triggers, then recreates from current models
   - This ensures removed models don't leave orphaned metadata or triggers

2. **AuditLevel Enum** (on Python models)
   ```python
   class AuditLevel(str, Enum):
       FULL = "full"   # Capture all columns
       META = "meta"   # Capture only metadata fields + __auditable_fields__
       NONE = "none"   # Skip auditing entirely
   ```

3. **Model Configuration** (class variables on SQLModel)
   ```python
   from syntara.core.models.base.base_resource import AuditLevel, BaseResource

   class Credential(BaseResource, table=True):
       # Audit trail: metadata only (no secret_id to prevent exposure)
       __auditable__: ClassVar[AuditLevel] = AuditLevel.META
       __auditable_fields__: ClassVar[list[str]] = [
           "name",
           "description",
           "credential_type_id",
           "enabled",
           "project_id",
       ]
   ```

4. **audit_crud_operation() Trigger Function**
   - Generic trigger attached to all auditable tables
   - Reads audit configuration from `audit_table_metadata`
   - Reads actor/workflow context from Postgres session variables (set by `set_audit_context()` hook)
   - Builds AuditEvent JSON with operation-specific payload:
     - **INSERT**: captures `resource_data` (full snapshot or metadata-only)
     - **UPDATE**: captures `changes` (field-by-field diff, old → new)
     - **DELETE**: captures `resource_data` (snapshot before deletion)
   - Writes to `audit_outbox` with `event_source=CRUD_EVENT`
   - **Never raises** - catches all exceptions and logs warnings to prevent breaking business transactions

5. **set_audit_context() Before-Flush Hook**
   - Executes before SQLAlchemy flushes changes to database
   - Reads actor/workflow/execution/activity context from ContextVars
   - Propagates context to Postgres session variables using `SET LOCAL`:
     ```sql
     SET LOCAL app.actor_id = 'uuid';
     SET LOCAL app.actor_username = 'username';
     SET LOCAL app.actor_type = 'user';
     SET LOCAL app.workflow_id = 'uuid';
     SET LOCAL app.execution_id = 'uuid';
     SET LOCAL app.activity_id = 'string';
     ```
   - Session variables are transaction-scoped and auto-clear on COMMIT/ROLLBACK

**Trigger Lifecycle:**

```mermaid
sequenceDiagram
    participant App as Application Code
    participant Session as SQLAlchemy Session
    participant Hook as set_audit_context()<br/>(before_flush)
    participant PG as PostgreSQL
    participant Trigger as audit_crud_operation()
    participant Meta as audit_table_metadata
    participant Outbox as audit_outbox

    App->>Session: user.name = "new_name"
    App->>Session: session.commit()

    Session->>Hook: Fire before_flush event
    Hook->>Hook: Read actor_context_var,<br/>workflow_id_context_var,<br/>execution_id_context_var,<br/>activity_id_context_var
    Hook->>PG: SET LOCAL app.actor_id = '...'<br/>SET LOCAL app.actor_username = '...'<br/>SET LOCAL app.actor_type = '...'<br/>SET LOCAL app.workflow_id = '...'<br/>SET LOCAL app.execution_id = '...'<br/>SET LOCAL app.activity_id = '...'

    Session->>PG: FLUSH UPDATE user SET name = '...'

    PG->>Trigger: AFTER UPDATE trigger fires
    Trigger->>Meta: SELECT model_name, audit_level, auditable_fields<br/>FROM audit_table_metadata<br/>WHERE table_name = 'user'
    Meta-->>Trigger: model_name='User', audit_level='full', fields=NULL

    Trigger->>PG: SELECT current_setting('app.actor_id', true)::uuid<br/>SELECT current_setting('app.actor_username', true)<br/>SELECT current_setting('app.actor_type', true)
    PG-->>Trigger: actor_id='...', actor_username='...', actor_type='user'

    Trigger->>Trigger: Build changes JSON:<br/>{"name": {"old": "alice", "new": "new_name"}}
    Trigger->>Trigger: Build AuditEvent JSON with:<br/>- event_id (gen_random_uuid())<br/>- resource_urn (urn:syntara:User:uuid)<br/>- resource_name (if 'name' field exists)<br/>- actor fields from session vars<br/>- workflow/execution/activity IDs

    Trigger->>Outbox: INSERT INTO audit_outbox<br/>(event_source='crud_event', event_payload=...)

    PG->>Session: COMMIT (all changes atomic)
```

**Key Properties:**

- **Zero instrumentation**: No code changes needed in business logic - triggers fire automatically
- **Selective capture**: `AuditLevel.META` mode captures only safe fields (e.g., exclude `secret_id` from Credential)
- **Context-aware**: Triggers access actor/workflow context via Postgres session variables
- **Fail-safe**: Trigger exceptions are caught and logged, never break business transactions
- **Atomic**: CRUD audit events written in same transaction as business data

#### OTEL Event Source Discriminator

All events emitted to the OTEL Collector include an `audit.event_source` discriminator field that identifies whether the event originated from business logic or database triggers:

- **`audit.event_source: "business"`** — Explicit events from middleware, decorators, context managers, and domain events
- **`audit.event_source: "crud"`** — Automatic CRUD events captured by PostgreSQL triggers

This discriminator allows downstream OTEL processors and observability platforms to:
- Filter events by source type
- Route business events to different processing pipelines than CRUD events
- Apply different retention policies based on event source
- Build separate dashboards for business vs infrastructure events

**Implementation details:**

The `_build_otel_log_record()` function in `src/syntara/audit/outbox/worker.py` builds a `ReadableLogRecord` with the discriminator injected as an attribute. The worker then exports records directly via `OTLPLogExporter.export()` — bypassing the logging pipeline's `BatchLogRecordProcessor` which ignores export results and would cause silent event loss:

```python
def _build_otel_log_record(
    audit_event: AuditEvent, event_date: datetime, event_source: AuditEventSource
) -> ReadableLogRecord:
    # json.loads(model_dump_json()) for asyncpg UUID type safety
    event_dict = json.loads(audit_event.model_dump_json())
    # Inject event source attribute for event type discrimination
    event_dict["audit.event_source"] = event_source.value
    return ReadableLogRecord(
        timestamp=int(event_date.timestamp() * 1e9),
        body=json.dumps(event_dict),
        severity_number=SeverityNumber.INFO,
        resource=create_otel_resource(),
    )
```

The worker builds log records with the appropriate `event_source` value based on the record's origin, using `obr.created_at` as the event timestamp. Outbox records are only deleted on export success:
- Business events: `_build_otel_log_record(audit_event, obr.created_at, event_source=AuditEventSource.BUSINESS_EVENT)`
- CRUD events: `_build_otel_log_record(audit_event, obr.created_at, event_source=AuditEventSource.CRUD_EVENT)`

#### Actor Context Propagation

```mermaid
sequenceDiagram
    participant Request as HTTP Request
    participant Middleware as AuditMiddleware
    participant Handler as Endpoint Handler
    participant Decorator as @audit
    participant Dispatcher as AuditEventDispatcher
    participant ContextVar as ContextVar Storage
    participant Emitter as emit_audit_event()

    Request->>Middleware: X-Request-Id header
    Middleware->>ContextVar: Set request_id_context_var

    Note over Handler: Business logic begins

    Handler->>Handler: with actor_context(actor=user)
    Handler->>ContextVar: Set actor_context_var
    Handler->>ContextVar: Set workflow_id_context_var (optional)
    Handler->>ContextVar: Set activity_id_context_var (optional)
    Handler->>ContextVar: Set execution_id_context_var (optional)

    Handler->>Decorator: Decorated function called
    Decorator->>ContextVar: Extract current context
    Note over Decorator: Capture context early<br/>(nested decorator safety)
    Decorator->>Dispatcher: dispatch(FunctionExecutionEvent)
    Dispatcher->>Dispatcher: Route to FunctionExecutionHandler
    Dispatcher->>Emitter: emit_audit_event(AuditEvent)

    Emitter->>ContextVar: Read actor_context_var
    Emitter->>ContextVar: Read workflow_id_context_var
    Note over Emitter: Inject context into event<br/>if not already set

    Emitter-->>Decorator: Event emitted
    Decorator->>ContextVar: Reset actor context vars

    Handler-->>Middleware: Response returned
    Middleware->>Dispatcher: dispatch(HTTPRequestEvent)
    Dispatcher->>Dispatcher: Route to HTTPRequestHandler
    Dispatcher->>Emitter: emit_audit_event(AuditEvent)
    Middleware->>ContextVar: Reset request_id_context_var
```

### Instrumentation Tools

#### 1. @audit Decorator

**Purpose:** Automatic function instrumentation with flexible actor detection.

**Features:**
- Emits 1 event via `FunctionExecutionEvent` → `FunctionExecutionHandler` → `AuditEventDispatcher`
- Event action is the function name (or custom `event_action`)
- Event status is SUCCESS or ERROR based on function outcome
- 6-level actor detection priority cascade
- Selective argument/result capture
- Auto-escalates severity on exceptions (handled by `FunctionExecutionHandler`)
- Nested decorator safe (captures actor context early)

**Usage:**

```python
from syntara.audit.decorators import audit
from syntara.audit.models.audit_event import EventCategory, EventSeverity

@audit(
    EventCategory.USER_ACTION,
    event_action="create_workflow",
    source_component="syntara.workflows",
    event_severity=EventSeverity.INFO,
    capture_args={"user_id", "workflow_name"},
    capture_result={"id", "status"},
    actor_param="current_user",
)
async def create_workflow(
    current_user: User,
    workflow_name: str,
    description: str,
) -> Workflow:
    workflow = Workflow(...)
    return workflow
```

**Actor Detection Priority:**

1. **Current context variable** (from `actor_context` manager)
2. **FastAPI dependency injection** (`current_user`, `user_context` kwargs)
3. **Explicit `actor_param`** specification
4. **Auto-detect** common parameter names
5. **Fallback** `ActorContext`
6. **System actor** (default)

#### 2. audit_context Context Manager

**Purpose:** Manual audit event emission with custom context data.

**Features:**
- Emits 1 event via `AuditContextEvent` → `AuditContextHandler` → `AuditEventDispatcher`
- Supports arbitrary `**context_data` via `extra="allow"`
- Sets actor context for nested operations
- Auto-escalates severity on exceptions
- Event action is success (`{action}`) or error (`{action}_error`)
- Atomic actor extraction: Accepts `actor: User | None` parameter to ensure `actor_id`, `actor_type`, and `actor_username` are extracted from a single source, preventing potential id/username mismatches

**Usage:**

```python
from syntara.audit.context_managers import audit_context
from syntara.audit.models.audit_event import EventCategory, EventSeverity

# With User actor (extracts actor_id, actor_type, actor_username atomically)
with audit_context(
    event_category=EventCategory.USER_ACTION,
    event_action="export_data",
    source_component="syntara.exports",
    actor=current_user,  # User object - ensures id/username integrity
    event_severity=EventSeverity.INFO,
    export_format="csv",
    record_count=5000,
):
    # Perform operation
    export_data()

# Or with SYSTEM actor (actor=None)
with audit_context(
    event_category=EventCategory.SYSTEM_OPERATION,
    event_action="backup_database",
    source_component="syntara.maintenance",
    actor=None,  # SYSTEM actor
    event_severity=EventSeverity.INFO,
    database_name="production",
    backup_size_mb=1024,
):
    # Perform operation
    backup_database()
# Event emitted in finally block with all context_data
```

#### 3. AuditMiddleware

**Purpose:** Automatic HTTP request/response audit trail.

**Features:**
- Emits 1 event per HTTP request via `HTTPRequestEvent` → `HTTPRequestHandler` → `AuditEventDispatcher`
- Captures method, path, status code, query params, response time, request payload size, user context
- Sets event severity based on status code (5xx=ERROR, 4xx=WARNING, 2xx/3xx=INFO)
- Excludes health/metrics endpoints (see `EXCLUDED_PATHS` in `syntara.api.constants`)
- Propagates `X-Request-Id` header via context var
- **Unverified JWT decode for audit logging:** Extracts actor information from JWT without signature verification for performance (crypto overhead eliminated). If token is forged, endpoint authentication will reject it with 401, and the audit log still captures the failed attempt. This avoids double-authentication overhead (middleware + endpoint).
- **Context ID resolution:** Matches request path against FastAPI routes to extract `workflow_id`, `execution_id`, `activity_id` from URL path parameters **before** routing occurs, making these IDs available to route handlers via context variables.

**No manual usage required** - automatically registered in FastAPI app middleware stack.

### Implementation Patterns

#### Atomic Actor Extraction

**Critical for audit integrity:** Actor identity fields (`actor_id`, `actor_username`, `actor_type`) must always be extracted atomically from a single source to prevent mismatched id/username pairs that could compromise audit trail trustworthiness.

**Pattern:**
```python
from syntara.audit.emitter import AuditActorContext
from syntara.audit.models.audit_event import ActorType
from syntara.core.models.user import User

# ✅ CORRECT: Atomic extraction from User object
def extract_actor_from_user(user: User | None) -> AuditActorContext:
    """Extract actor context atomically from User object.

    All three fields (id, username, type) are extracted together
    in the same scope, preventing potential race conditions or
    partial updates that could cause mismatches.
    """
    if user is None:
        return AuditActorContext()  # Empty context for SYSTEM actor

    return AuditActorContext(
        actor_id=user.id,
        actor_username=user.username,
        actor_type=ActorType.USER,
    )

# ❌ WRONG: Separate field extraction creates race condition risk
def extract_actor_wrong(user: User | None) -> tuple:
    actor_id = user.id if user else None
    # ... other code could modify user here ...
    actor_username = user.username if user else None
    return (actor_id, actor_username)  # Could be mismatched!
```

**Where this pattern is enforced:**
- `audit_context` manager: Accepts `actor: User | None` parameter
- `actor_extractor.py`: All extraction strategies return `AuditActorContext`
- `middleware.py`: JWT claims extracted together
- Domain event handlers: Extract username atomically when mapping to AuditEvent

**Why it matters:** Without atomic extraction, concurrent modifications or context variable race conditions could lead to `actor_id` belonging to one user while `actor_username` belongs to another, rendering audit logs untrustworthy for forensic analysis and non-repudiation.

#### Async-Safe Context Variable Management

**Critical for async safety:** Context variables must use token-based reset in try/finally blocks to prevent context leakage between concurrent requests.

**Pattern:**
```python
from contextvars import ContextVar
from syntara.audit.emitter import actor_context_var, AuditActorContext

# ✅ CORRECT: Token-based reset with try/finally
async def process_request(user: User) -> Response:
    # Capture token BEFORE try block
    actor_context = AuditActorContext(
        actor_id=user.id,
        actor_username=user.username,
        actor_type=ActorType.USER,
    )
    actor_token = actor_context_var.set(actor_context)

    try:
        # Business logic - context is set
        result = await handle_request()
        return result
    finally:
        # Always reset, even on exception
        actor_context_var.reset(actor_token)

# ❌ WRONG: No token capture - cannot reset properly
async def process_request_wrong(user: User) -> Response:
    actor_context_var.set(AuditActorContext(...))
    # Missing finally block - context leaks to next request!
    return await handle_request()
```

**Token-based reset protocol:**
1. **Capture token immediately** after `set()` call
2. **Set context variables BEFORE try block** (not inside)
3. **Reset in finally block** using captured token
4. **Always use try/finally** - never rely on normal return paths

**Where this pattern is enforced:**
- `middleware.py`: actor, workflow, execution, activity, request_id contexts
- `decorators.py`: actor context in @audit decorator
- `context_managers.py`: all context managers

**Why it matters:** Python's `contextvars` are designed for async isolation, but without proper token-based reset, context variables can leak across concurrent requests in asyncio event loops. This could cause audit events to show incorrect actor attribution or context IDs from previous requests.

**Nested decorator safety:** The `@audit` decorator explicitly captures actor context early (line 100-101 comment: "This is critical for nested @audit decorators...") to avoid reading stale values from ContextVars after inner decorators reset them.

### Data Protection

**PII Sanitization:** Automatic redaction of passwords, secrets, tokens, emails  
**Payload Truncation:** 10KB limit per event, truncates largest string leaves

---

## 2. Domain Integration Guide

### Choosing Your Instrumentation Strategy

The audit framework provides **four cascading layers** of instrumentation, each trading less code intrusion for less semantic richness. Understanding this gradient helps you choose the right tool for each auditing need.

#### The Intrusion & Burden Gradient

```mermaid
graph LR
    A[0. Database Triggers<br/>Zero Intrusion] --> B[1. Middleware<br/>Zero Intrusion]
    B --> C[2. @audit<br/>Minimal Intrusion]
    C --> D[3. audit_context<br/>Moderate Intrusion]
    D --> E[4. DomainEvents<br/>High Intrusion]
```

Each layer can coexist — a single HTTP request may generate events from **all five layers** (database trigger for CRUD + middleware + decorator + domain events). See [Auth Domain Example](#3-example-auth-domain-implementation) where login generates multiple audit events from different layers.

#### Layer Comparison

| Layer | Code Changes | Developer Burden | Semantic Richness | When to Use |
|-------|-------------|------------------|-------------------|-------------|
| **0. Database Triggers** | None (model config only) | Set `__auditable__` class var | CRUD metadata (changes, snapshots) | Automatic - covers all database mutations |
| **1. Middleware** | None | None (automatic) | HTTP metadata only | Always active - no choice needed |
| **2. @audit** | One line decorator | Configure parameters | Function-level execution | Track important function calls without business context |
| **3. audit_context** | Wrap blocks with `with` | Provide context data | Operation-level with custom fields | Track complex operations spanning multiple functions |
| **4. DomainEvents** | Define events, handlers, dispatch calls | Architectural decisions | Business semantics | Capture business-meaningful events (login failures, state transitions) |

#### Layer Details

##### 0. Database Triggers (Zero Intrusion)

**What it captures:**
- INSERT/UPDATE/DELETE operations on all auditable tables
- Field-level changes (old value → new value for UPDATE)
- Full resource snapshots (for INSERT/DELETE)
- Actor context (from Postgres session variables set by before-flush hook)

**Pros:**
- ✅ Zero code changes (only model config)
- ✅ Automatic coverage of all database mutations
- ✅ Selective field capture (FULL vs META mode)
- ✅ Guaranteed capture (triggers can't be forgotten)
- ✅ Routed to OTEL Collector

**Cons:**
- ❌ No business semantics (just CRUD metadata)
- ❌ Cannot classify error types (business vs technical)
- ❌ Requires model annotation (`__auditable__`, `__auditable_fields__`)

**Example use-case:**
```python
# Set on model class - no other code needed
from syntara.core.models.base.base_resource import AuditLevel, BaseResource

class Credential(BaseResource, table=True):
    __auditable__: ClassVar[AuditLevel] = AuditLevel.META
    __auditable_fields__: ClassVar[list[str]] = [
        "name",
        "description",
        "credential_type_id",
        "enabled",
    ]
    # Trigger automatically captures changes to these fields
```

**When to use:**
- Automatic - triggers fire for all models with `__auditable__ != AuditLevel.NONE`
- Use `AuditLevel.META` for sensitive models (e.g., Credential) to exclude secret fields
- Use `AuditLevel.FULL` for most models to capture complete snapshots

**Seeder Workflow (Critical):**
After running migrations, you **must** run the audit seeder to populate metadata and attach triggers:

```bash
# After alembic upgrade head
uv run python -m syntara.seed --only audit
```

The seeder:
1. Checks if `audit_table_metadata` table exists (skips gracefully if not)
2. Deletes **all** existing metadata records and drops **all** audit triggers
3. Discovers all SQLModel tables from `syntara.core.database.migrations.models.ALL_MODELS`
4. Filters to `BaseResource` subclasses with `__auditable__ != AuditLevel.NONE`
5. Inserts fresh metadata records for each auditable table
6. Creates `audit_trigger_<table>` for each auditable table

This **clean-slate approach** ensures removed models don't leave orphaned metadata/triggers. The seeder is idempotent and safe to run multiple times.

##### 1. Middleware (Zero Intrusion)

**What it captures:**
- HTTP method, path, status code
- Query parameters
- Request duration
- User context from authentication

**Pros:**
- ✅ Zero code changes
- ✅ Automatic coverage of all endpoints
- ✅ Consistent HTTP-level observability

**Cons:**
- ❌ Generic HTTP data only
- ❌ No business semantics
- ❌ Cannot capture mid-request state

**Example use-case:**
```
All HTTP requests automatically tracked - no action needed
```

##### 2. @audit Decorator (Minimal Intrusion)

**What it captures:**
- Function execution success/failure
- Selected arguments and return values
- Actor context (6-level priority cascade)
- Exception details

**Pros:**
- ✅ Minimal code changes (one line)
- ✅ Automatic actor detection
- ✅ Captures function inputs/outputs
- ✅ Auto-escalates severity on exceptions

**Cons:**
- ❌ Limited to function boundaries
- ❌ Generic success/failure only (no business error classification)
- ❌ Requires wrapping entire functions

**Example use-case:**
```python
# Track important operations without writing custom events
@audit(
    EventCategory.SYSTEM_OPERATION,
    event_action="database_backup",
    source_component="syntara.maintenance",
    capture_args={"database_name"},
    capture_result={"backup_size_mb", "duration_seconds"},
)
async def backup_database(database_name: str) -> BackupResult:
    # Business logic unchanged
    ...
```

**When to use:**
- Track important function calls (mutations, integrations, operations)
- Don't need business error classification (BAD_PASSWORD vs UNKNOWN_USER)
- Want automatic actor detection
- Function already has clean boundaries

##### 3. audit_context ContextManager (Moderate Intrusion)

**What it captures:**
- Arbitrary structured data via `**context_data`
- Operation-level success/failure
- Actor context for nested operations
- Exception details

**Pros:**
- ✅ Custom structured data (any fields)
- ✅ Wraps code blocks (not limited to function boundaries)
- ✅ Sets actor context for nested calls
- ✅ Auto-escalates severity on exceptions

**Cons:**
- ❌ Alters code structure (indentation, `with` blocks)
- ❌ Requires manual context data collection
- ❌ Generic success/failure only

**Example use-case:**
```python
# Track complex operations spanning multiple steps
async def provision_infrastructure(user: User, config: InfraConfig):
    with audit_context(
        event_category=EventCategory.SYSTEM_OPERATION,
        event_action="provision_infrastructure",
        source_component="syntara.infra",
        actor=user,  # User object - ensures atomic actor field extraction
        region=config.region,
        instance_count=config.instance_count,
        estimated_cost_usd=config.estimated_cost,
    ):
        # Multi-step operation
        network = await create_network(config.network_spec)
        instances = await create_instances(config.instance_spec)
        await configure_loadbalancer(network, instances)
        # Event emitted in finally block with all context
```

**When to use:**
- Track operations that span multiple functions
- Need custom structured data beyond function args/results
- Operation doesn't align with function boundaries
- Want to set actor context for nested operations

##### 4. DomainEvents (High Intrusion)

**What it captures:**
- Business-semantic events (LoginAttemptEvent, PaymentProcessedEvent)
- Domain-specific error classification (LoginErrorReason.BAD_PASSWORD)
- Rich business context (payment method, failure reason, state transitions)
- Typed event contracts enforced by dataclasses

**Pros:**
- ✅ Rich business semantics
- ✅ Type-safe event contracts
- ✅ Classified errors (business vs technical)
- ✅ Domain-driven event modeling
- ✅ Enables business analytics (e.g., "show me all BAD_PASSWORD failures")

**Cons:**
- ❌ High code intrusion (dispatch calls throughout business logic)
- ❌ Requires architectural decisions (what events exist?)
- ❌ Must define events, handlers, registration
- ❌ Most developer burden

**Example use-case:**
```python
# Define domain event
@dataclass
class LoginAttemptEvent:
    username: str
    method: LoginMethod
    user_id: UUID | None = None
    error_type: LoginErrorReason | str | None = None  # Business vs technical errors

# Define handler
class LoginAttemptHandler(AuditEventHandler[LoginAttemptEvent]):
    def handle(self, event: LoginAttemptEvent) -> AuditEvent:
        if isinstance(event.error_type, LoginErrorReason):
            # Business error - classify as WARNING
            category = EventCategory.SECURITY_EVENT
            severity = EventSeverity.WARNING
        elif event.error_type:
            # Technical error - classify as ERROR
            category = EventCategory.SECURITY_EVENT
            severity = EventSeverity.ERROR
        else:
            # Success
            category = EventCategory.USER_ACTION
            severity = EventSeverity.INFO

        return AuditEvent(
            event_category=category,
            event_severity=severity,
            # ... structured_data with domain fields
        )
```
```
# In main.py startup:
registry = discover_handlers(syntara.yourmodule.audit)
AuditEventDispatcher.register(registry)

# In business logic:
AuditEventDispatcher.dispatch(YourDomainEvent(...))
```
```
# Dispatch throughout business logic
@router.post("/login")
async def login(body: LoginRequest) -> AccessTokenResponse:
    user = await find_user(body.username)

    if not user:
        # Dispatch business event - UNKNOWN_USER
        AuditEventDispatcher.dispatch(
            LoginAttemptEvent(
                username=body.username,
                method=LoginMethod.PASSWORD,
                error_type=LoginErrorReason.UNKNOWN_USER,
            )
        )
        raise AuthenticationRequiredError

    if not verify_password(body.password, user.password_hash):
        # Dispatch business event - BAD_PASSWORD
        AuditEventDispatcher.dispatch(
            LoginAttemptEvent(
                username=body.username,
                method=LoginMethod.PASSWORD,
                user_id=user.id,
                error_type=LoginErrorReason.BAD_PASSWORD,
            )
        )
        raise AuthenticationRequiredError

    # Success
    AuditEventDispatcher.dispatch(
        LoginAttemptEvent(
            username=body.username,
            method=LoginMethod.PASSWORD,
            user_id=user.id,
        )
    )
    return AccessTokenResponse(...)
```

**When to use:**
- Need business-meaningful event classification (error reasons, state transitions)
- Building analytics/dashboards on audit data ("show failed logins by reason")
- Domain has rich state machine (workflow states, payment statuses)
- Compliance requires semantic audit trails (financial transactions, PII access)

#### Decision Tree

```mermaid
graph TD
    Start[Need to audit something?] --> Q0{Database mutation?}
    Q0 -->|Yes| A0[Database Triggers<br/>✓ Automatic CRUD capture]
    Q0 -->|No| Q1{HTTP request already?}

    Q1 -->|Yes| A1[Middleware handles it<br/>✓ Done]
    Q1 -->|No| Q2{Need business semantics?}

    Q2 -->|Yes, business classification needed| A4[Use DomainEvents<br/>Define typed events + handlers]
    Q2 -->|No, just track execution| Q3{Aligns with function boundary?}

    Q3 -->|Yes| A2[Use @audit decorator<br/>Minimal intrusion]
    Q3 -->|No, spans multiple functions| A3[Use audit_context manager<br/>Wrap code block]
```

#### Layering Example: Login Request

For a single login request, you may see **all five layers** fire:

```python
# Layer 0: Database Trigger - CRUD capture
# Automatically fires when session.create() inserts RefreshSession row
# → event_action="refreshsession_create", changes={...}, event_source=CRUD_EVENT

# Layer 4: DomainEvent - Business semantics
AuditEventDispatcher.dispatch(
    LoginAttemptEvent(user_id=user.id, error_type=LoginErrorReason.BAD_PASSWORD)
)
# → event_action="login", event_category=SECURITY_EVENT, severity=WARNING

# Layer 2: Decorator - Function execution
@audit(EventCategory.SECURITY_EVENT, event_action="authenticate_user")
async def login(body: LoginRequest): ...
# → event_action="authenticate_user", event_status=ERROR, captures exception

# Layer 1: Middleware - HTTP request
# → event_action="request_completed", method=POST, path=/api/v1/auth/login, status=401
```

**Result:** 4 audit events for one failed login, each providing different semantic layers (CRUD, business, function, HTTP).


---

## 3. Example: Auth Domain Implementation

### Domain Events

**LoginAttemptEvent:** Tracks authentication attempts
- Fields: `username`, `method`, `user_id`, `error_type`
- `error_type` can be: `None` (success), `LoginErrorReason` enum (business error), or `str` (technical error)
- The `username` field is mapped to `actor_username` in the resulting AuditEvent

**OIDCFlowEvent:** Tracks OIDC authorize/callback stages
- Fields: `provider_id`, `stage`, `user_id`, `username`, `error_type`
- Dynamic action based on stage: `oidc_authorize`, `oidc_callback`
- The `username` field is populated during successful callback and mapped to `actor_username`

**SessionLifecycleEvent:** Tracks session create/revoke/refresh
- Fields: `action`, `user_id`, `username`, `jti`, `idp`, `error_type`
- Dynamic action based on lifecycle: `session_created`, `session_revoked`, `session_refreshed`
- The `username` field is populated from User object or JWT payload and mapped to `actor_username`  

### Login Flow Example

```python
@router.post("/login")
async def login(body: LoginRequest, ...) -> AccessTokenResponse:
    user = await db.exec(select(User).filter(...))

    if not user:
        AuditEventDispatcher.dispatch(
            LoginAttemptEvent(
                username=username,
                method=LoginMethod.PASSWORD,
                error_type=LoginErrorReason.UNKNOWN_USER,
            )
        )
        raise AuthenticationRequiredError

    if not verify_password(body.password, user.password_hash):
        AuditEventDispatcher.dispatch(
            LoginAttemptEvent(
                username=username,
                method=LoginMethod.PASSWORD,
                error_type=LoginErrorReason.BAD_PASSWORD,
                user_id=user.id,
            )
        )
        raise AuthenticationRequiredError

    # Create session
    store = create_session_store(db)
    await store.create(jti=jti, user_id=user.id, ...)

    AuditEventDispatcher.dispatch(
        SessionLifecycleEvent(
            action=SessionAction.CREATE,
            user_id=user.id,
            jti=jti,
            idp="local",
        )
    )

    # Success - error_type=None (implicit), username populated
    AuditEventDispatcher.dispatch(
        LoginAttemptEvent(
            username=user.username,
            method=LoginMethod.PASSWORD,
            user_id=user.id,
        )
    )

    return AccessTokenResponse(access_token=access_token)
```

### Event Handlers

```python
class LoginAttemptHandler(AuditEventHandler[LoginAttemptEvent]):
    """Maps a LoginAttemptEvent to a normalized AuditEvent."""

    def handle(self, event: LoginAttemptEvent) -> AuditEvent:
        """Map a LoginAttemptEvent to a normalized AuditEvent.

        The error_type field can be:
        - None: Success (no error)
        - LoginErrorReason: Business error (e.g., BAD_PASSWORD, UNKNOWN_USER)
        - str: Technical exception class name (e.g., "RedisConnectionError")
        """
        action = "login"
        actor_type = ActorType.USER if event.user_id else ActorType.SYSTEM
        is_error = event.error_type is not None

        if is_error:
            if isinstance(event.error_type, LoginErrorReason):
                # Business/classified error
                category = EventCategory.SECURITY_EVENT
                severity = EventSeverity.WARNING
                status = EventStatus.ERROR
                message = f"Login attempt failed ({event.error_type.value})"
                error_message = message
                error_type_str = None
            else:
                # Technical exception
                category = EventCategory.SECURITY_EVENT
                severity = EventSeverity.ERROR
                status = EventStatus.ERROR
                message = "Login failed due to system error"
                error_message = "Look at the Operational Logs for full diagnosis"
                error_type_str = event.error_type
        else:
            # Success
            category = EventCategory.USER_ACTION
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"User logged in via {event.method}"
            error_message = None
            error_type_str = None

        return AuditEvent(
            event_category=category,
            event_severity=severity,
            event_status=status,
            event_action=action,
            event_message=message,
            source_component="syntara.auth.login",
            structured_data=AuditContextData(
                data_type="login-context",
                error_type=error_type_str,
                error_message=error_message,
                method=event.method.value,
            ),
            actor_id=event.user_id,
            actor_type=actor_type,
            actor_username=event.username,  # Top-level field for actor identity
        )
```

### Complete Audit Trail

For a successful login:
1. `refreshsession_create` — Database trigger (event_source=CRUD_EVENT, captures RefreshSession INSERT)
2. `session_created` — SessionLifecycleEvent (event_status=SUCCESS)
3. `login` — LoginAttemptEvent (event_status=SUCCESS, error_type=None)
4. `login` — @audit decorator via FunctionExecutionEvent (event_status=SUCCESS, event_category=SECURITY_EVENT)
5. `request_completed` — AuditMiddleware

For a failed login (bad password):
1. `login` — LoginAttemptEvent (event_status=ERROR, error_type=LoginErrorReason.BAD_PASSWORD)
2. `login` — @audit decorator via FunctionExecutionEvent (event_status=ERROR, event_category=SECURITY_EVENT)
3. `request_completed` — AuditMiddleware (401)

**Note:** The `@audit` decorator now emits a single event per function call. The `FunctionExecutionHandler` determines the event_status (SUCCESS or ERROR) and escalates severity on exceptions. Domain events (LoginAttemptEvent, SessionLifecycleEvent) provide semantic context, while @audit provides function-level execution tracking.

---

## Summary

The Nexus audit framework provides:

✅ **Guaranteed delivery** - Transactional outbox pattern ensures audit events survive process crashes  
✅ **Automatic CRUD capture** - PostgreSQL triggers track all database mutations without manual instrumentation  
✅ **Dual event paths** - Explicit events via dispatcher/handler pipeline, CRUD events via triggers (bypasses dispatcher)  
✅ **Dual routing** - Business events → audit DB, CRUD events → OTEL Collector  
✅ **Context propagation** - `set_audit_context()` hook propagates actor/workflow context to Postgres session variables  
✅ **Selective auditing** - `AuditLevel.FULL` (all fields), `AuditLevel.META` (metadata only), `AuditLevel.NONE` (skip)  
✅ **Universal structured data** - Single `AuditContextData` type with `extra="allow"` for all audit events  
✅ **Type-safe domain events** - Strongly typed domain events mapped to normalized AuditEvent via handlers  
✅ **Multiple instrumentation methods** - Database triggers, decorators, context managers, middleware, and custom domain events  
✅ **Automatic PII sanitization** and payload size enforcement (10KB limit)  
✅ **Fail-safe execution** that never blocks business operations  
✅ **Multi-layer coverage** - CRUD operations, domain semantics, function execution, and HTTP request tracking  
✅ **Auto-discovery** of handlers with zero-configuration  

**For new domains:** Follow the step-by-step integration guide to add domain-specific audit events.

**For questions:** Review existing implementations in `src/syntara/auth/audit/` or consult `/docs/standards/`.
