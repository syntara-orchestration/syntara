# WebSocket Standards

Standards for implementing WebSocket endpoints in Syntara.

## When to Use WebSocket vs REST

Use WebSocket for:
- Streaming data (LLM responses, event feeds, real-time updates)
- Long-running operations that need incremental results
- Server-initiated messages (receive-only channels)

Use REST for:
- CRUD operations
- Request-response patterns
- Resource management
- One-time queries

## Core Framework

All WebSocket functionality is implemented in `src/syntara/core/websocket/`:

- `base_handler.py` - Template method pattern for streaming handlers
- `manager.py` - Connection lifecycle manager (singleton)
- `connection.py` - Simple connection tracking (legacy, deprecated)
- `schema_validator.py` - AsyncAPI 3.0 schema-driven message validation
- `endpoint_factory.py` - Factory for creating WebSocket endpoints
- `hooks.py` - Pre/post validation hooks for message processing
- `interceptor.py` - Bootstrap-time interceptors for validation
- `router.py` - WebSocket router with auto-discovery
- `utils.py` - Channel name normalization and receive-only detection
- `exceptions.py` - Custom exceptions (StreamingValidationError, EventsExpiredError, WaitForStreamTimeoutError)
- `close_codes.py` - RFC 6455 WebSocket close codes

## Connection Lifecycle

### State Transitions

Connections follow this lifecycle (ConnectionState enum):

```
CONNECTING -> ACTIVE -> CLOSED
              |
              v
           RECONNECTING -> ACTIVE
```

- `CONNECTING` - Initial handshake in progress
- `ACTIVE` - Successfully connected, consuming events
- `RECONNECTING` - Temporary disconnect, attempting reconnection
- `CLOSED` - Connection terminated

### Health Monitoring

The lifecycle manager (singleton) provides:

- Health checks via activity tracking (4-hour timeout, configurable via `WebSocketConfig.ACTIVITY_TIMEOUT`)
- Automatic cleanup of stale connections (30-second intervals, configurable via `WebSocketConfig.CLEANUP_INTERVAL`)
- Multi-client support (multiple connections per resource)
- Channel-based grouping
- Extensible metadata support

Activity timestamps are updated on:
- Message send
- Message receive (including invalid messages that trigger validation errors)

### Manager Usage

Use `get_connection_lifecycle_manager()` to access the singleton:

```python
from syntara.core.websocket.manager import get_connection_lifecycle_manager

manager = get_connection_lifecycle_manager()

# Add connection
lifecycle_conn_id = manager.add_connection(
    channel="invocations",
    client_ip="192.168.1.1:54321",
    websocket=websocket,  # Optional, for stale connection cleanup
    resource_id="550e8400-e29b-41d4-a716-446655440000",
    metadata={"replay_count": "10", "last_event_id": None}
)

# Activate after successful setup
manager.activate_connection(lifecycle_conn_id)

# Update activity on message send/receive
manager.update_activity(lifecycle_conn_id)

# Remove on disconnect
manager.remove_connection(lifecycle_conn_id, reason="normal_close")
```

### Background Monitoring

Start monitoring in application startup:

```python
manager = get_connection_lifecycle_manager()
manager.start_monitoring()
```

Stop in shutdown:

```python
manager.stop_monitoring()
```

## Message Format Conventions

### Event Structure

All events must include:

```json
{
  "event_type": "delta|completion|error|...",
  "resource_id": "UUID-string",
  "timestamp": "ISO-8601-timestamp",
  "event_id": "stream-event-id",
  "data": {}
}
```

- `event_id` is the Redis stream ID (e.g., "1234567890-0") used for resumption
- Error events have `event_id: null` (not resumable)

### Error Events

Follow RFC 9457 Problem Details structure:

```json
{
  "event_type": "error",
  "resource_id": "550e8400-...",
  "timestamp": "2026-04-06T12:34:56.789Z",
  "event_id": null,
  "data": {
    "type": "https://api.example.com/errors/llm-error",
    "title": "LLM Service Unavailable",
    "detail": "OpenRouter API returned error: rate limit exceeded",
    "code": "RATE_LIMIT_EXCEEDED",
    "retryable": true,
    "instance": "/invocations/550e8400-..."
  }
}
```

### Schema Validation

All WebSocket messages must be validated against AsyncAPI 3.0 specifications:

- Request messages validated by `before_receive` hook (default behavior)
- Response messages can optionally be validated by `before_send` hook
- Schema files located in `schemas/{component}/websocket-{handler}.{yaml|yml|json}`
- Validation uses lightweight dict-based validation (no Pydantic/SQLModel)

## Implementing a New Streaming Endpoint

### File Structure Convention

WebSocket endpoints use convention-based path mapping:

```
src/syntara/{component}/ws/{handler}.py -> schemas/{component}/websocket-{handler}.{yaml|yml|json}
```

Both files are required. Missing either will cause a startup failure.

### AsyncAPI Specification

Create spec at `schemas/{component}/websocket-{handler}.yaml`:

```yaml
asyncapi: 3.0.0
info:
  title: Example WebSocket API
  version: 1.0.0

channels:
  example_channel:
    address: /ws/example/v1/example-channel
    messages:
      ExampleRequest:
        $ref: '#/components/messages/ExampleRequest'
      ExampleResponse:
        $ref: '#/components/messages/ExampleResponse'

operations:
  receiveExamples:
    action: receive
    channel:
      $ref: '#/channels/example_channel'

components:
  messages:
    ExampleRequest:
      payload:
        type: object
        properties:
          input:
            type: string
        required:
          - input
    ExampleResponse:
      payload:
        type: object
        properties:
          output:
            type: string
          timestamp:
            type: string
```

### Bidirectional Channel Handler

Create handler at `src/syntara/{component}/ws/{handler}.py`:

```python
"""WebSocket handler for example channel."""

from fastapi import WebSocket

async def handle_example_channel(message: dict) -> dict:
    """Handle bidirectional example message.

    Args:
        message: Validated request message (ExampleRequest)

    Returns:
        Response dict (ExampleResponse)
    """
    input_text = message.get("input", "")
    return {
        "output": f"Echo: {input_text}"
        # timestamp added by before_send hook
    }
```

Handler functions for bidirectional channels:
- Named `handle_{normalized_channel_name}` (kebab-case becomes snake_case)
- Accept validated message dict
- Return response dict
- Optional: Accept `connection_id` parameter if needed for per-connection state

### Receive-Only Channel Handler

For server-initiated streaming (no client messages):

```python
"""WebSocket handler for invocation streaming."""

from fastapi import WebSocket
from syntara.core.cache.stream import StreamClient

async def on_connect_invocations(websocket: WebSocket, connection_id: str) -> None:
    """Start streaming events when client connects.

    Args:
        websocket: WebSocket connection
        connection_id: Unique connection identifier
    """
    invocation_id = # ... extract from query params or path
    stream_id = f"invocation:{invocation_id}:events"

    async with StreamClient() as client:
        async for event in client.events(
            stream_id=stream_id,
            start_id="0-0",
            block_ms=1000
        ):
            await websocket.send_json(event)
            if event.get("event_type") == "completion":
                break
```

Receive-only channels:
- Require `on_connect_{normalized_channel_name}` function
- Must define `operations` section in AsyncAPI spec with `action: receive`
- Do NOT require `handle_*` function
- Background task starts when client connects
- Connection stays open until task completes or client disconnects

### Streaming Handler Pattern (BaseWebSocketStreamingHandler)

For complex streaming with validation, replay, and lifecycle management:

```python
"""WebSocket streaming handler for invocations."""

from syntara.core.websocket.base_handler import BaseWebSocketStreamingHandler

class InvocationStreamingHandler(BaseWebSocketStreamingHandler):
    """Stream invocation events to WebSocket clients."""

    async def create_session_state(self, invocation_id: str, **params) -> dict:
        """Validate request and create session state.

        Raises:
            StreamingValidationError: If invocation not found or invalid
        """
        # Validate invocation exists
        async with self._session_factory() as session:
            invocation = await session.get(Invocation, invocation_id)
            if not invocation:
                raise StreamingValidationError(
                    ErrorData(...),
                    INTERNAL_ERROR
                )

        return {
            "invocation_id": invocation_id,
            "status": invocation.status
        }

    def get_stop_condition(self, session_state: dict) -> callable:
        """Return function that determines when to stop streaming."""
        return lambda event: event.get("event_type") in ("completion", "error")

    def get_resource_id(self, session_state: dict) -> str:
        """Get resource ID for connection lifecycle manager."""
        return session_state["invocation_id"]

    async def wait_for_stream_ready(self, stream_id: str, session_state: dict) -> None:
        """Wait for stream creation (optional override)."""
        await self._wait_for_stream_creation(
            stream_id=stream_id,
            resource_id=session_state["invocation_id"],
            resource_status=session_state["status"],
            resource_type="invocation",
            max_wait_seconds=30
        )

# Usage in endpoint
handler = InvocationStreamingHandler(session_factory=get_session, channel_name="invocations")

async def on_connect_invocations(websocket: WebSocket, connection_id: str) -> None:
    # Extract parameters from query params
    invocation_id = websocket.query_params.get("invocation_id")
    replay_count = websocket.query_params.get("replay_count", "10")
    last_event_id = websocket.query_params.get("last_event_id")

    stream_id = f"invocation:{invocation_id}:events"

    await handler.stream_events_to_websocket(
        websocket=websocket,
        stream_id=stream_id,
        invocation_id=invocation_id,
        replay_count=replay_count,
        last_event_id=last_event_id,
        connection_id=connection_id
    )
```

Template methods:
- `create_session_state()` (required) - Validate request, create per-connection state
- `get_stop_condition()` (required) - Define when to stop streaming
- `get_resource_id()` (required) - Return resource ID for lifecycle manager
- `wait_for_stream_ready()` (optional) - Wait for stream creation
- `get_replay_parameters()` (optional) - Custom replay logic
- `get_connection_metadata()` (optional) - Additional metadata for lifecycle manager

Replay parameters:
- `last_event_id` takes precedence (resume from specific event)
- `replay_count="all"` - replay from beginning (start_id="0-0")
- `replay_count="0"` - only new events (start_id="$")
- `replay_count=N` - replay last N events

## Error Handling and Close Codes

### Close Codes (RFC 6455)

Use standardized close codes from `syntara.core.websocket.close_codes`:

- `NORMAL_CLOSURE = 1000` - Successful operation complete
- `UNSUPPORTED_DATA = 1003` - Endpoint received data it cannot accept
- `POLICY_VIOLATION = 1008` - Connection terminated due to policy
- `INTERNAL_ERROR = 1011` - Unexpected condition encountered

### Exception Handling

Custom exceptions in `syntara.core.websocket.exceptions`:

```python
from syntara.core.websocket.exceptions import StreamingValidationError
from syntara.core.websocket.close_codes import INTERNAL_ERROR
from syntara.core.models.error import ErrorData

# Raise in validation methods
error_data = ErrorData(
    type="https://api.example.com/errors/resource-not-found",
    title="Invocation Not Found",
    detail=f"Invocation {invocation_id} does not exist",
    code="INVOCATION_NOT_FOUND",
    retryable=False,
    instance=f"/invocations/{invocation_id}"
)
raise StreamingValidationError(error_data, INTERNAL_ERROR)
```

StreamingValidationError:
- Caught by BaseWebSocketStreamingHandler
- Error event sent to client before close
- Connection closed with specified close code

EventsExpiredError:
- Events expired from Redis stream (TTL exceeded)
- Automatically formatted with RFC 9457 structure
- Closed with NORMAL_CLOSURE

WaitForStreamTimeoutError:
- Timeout waiting for stream creation
- Closed with INTERNAL_ERROR
- Retryable error

## Custom Hooks

Override default hook behavior in handler modules:

```python
"""Custom hooks for example channel."""

from datetime import UTC, datetime
from syntara.core.websocket.schema_validator import ValidationError

async def before_receive(data: dict, message_type: str, channel: str) -> dict:
    """Custom validation logic.

    Default validates against AsyncAPI schema.
    Override to add custom checks.
    """
    # Call default validation
    validate_message(data, message_type, spec_path)

    # Add custom validation
    if data.get("input", "").startswith("blocked_"):
        raise ValidationError(
            error_type="VALIDATION_ERROR",
            message="Input starts with blocked prefix"
        )

    return data

async def after_receive(data: dict, channel: str) -> dict:
    """Transform validated input before handler.

    Default is pass-through.
    """
    # Add computed fields
    data["processed_at"] = datetime.now(UTC).isoformat()
    return data

async def before_send(response: dict, channel: str) -> dict:
    """Transform handler response before sending.

    Default adds timestamp if missing.
    """
    response["timestamp"] = datetime.now(UTC).isoformat()
    response["channel"] = channel
    return response

async def on_validation_error(error: ValidationError, channel: str) -> dict:
    """Format validation errors.

    Default returns standard error format.
    """
    return {
        "error": error.error_type,
        "message": error.message,
        "timestamp": datetime.now(UTC).isoformat()
    }

async def on_handler_error(error: Exception, channel: str) -> dict:
    """Format handler errors.

    Default returns INTERNAL_ERROR format.
    """
    return {
        "error": "CUSTOM_ERROR",
        "message": str(error),
        "timestamp": datetime.now(UTC).isoformat()
    }
```

Hook execution order:
1. Client sends message
2. `before_receive` - Validate against schema
3. `after_receive` - Transform validated input
4. Handler function processes message
5. `before_send` - Transform response
6. Server sends response

Error hooks:
- `on_validation_error` - Called when `before_receive` validation fails
- `on_handler_error` - Called when handler raises exception

## Redis Stream Integration

### Publishing Events

Use StreamClient to publish events:

```python
from syntara.core.cache.stream import StreamClient

async with StreamClient() as client:
    event = {
        "event_type": "delta",
        "invocation_id": str(invocation_id),
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {"delta": "token"}
    }
    event_id = await client.publish(stream_id, event)
```

Event IDs:
- Redis stream ID in format "timestamp-sequence" (e.g., "1234567890-0")
- Used for resumption via `last_event_id` parameter
- Returned by `publish()` call

### Consuming Events

Use StreamClient.events() for iteration:

```python
async with StreamClient() as client:
    async for event in client.events(
        stream_id=stream_id,
        start_id="0-0",  # Start from beginning
        replay=None,  # Or number of events to replay
        should_stop=lambda e: e.get("event_type") == "completion",
        block_ms=1000,  # Block for 1 second waiting for new events
        count=10  # Read up to 10 events per iteration
    ):
        await websocket.send_json(event)
```

Parameters:
- `start_id` - Stream position ("0-0" start, "$" only new, specific ID to resume)
- `replay` - Number of events to replay from end (mutually exclusive with start_id)
- `should_stop` - Callback to determine when to stop consuming
- `block_ms` - How long to block waiting for new events (0 = non-blocking)
- `count` - Max events per iteration

### Stream Naming Convention

Stream IDs follow pattern: `{resource_type}:{resource_id}:events`

Examples:
- `invocation:550e8400-...:events`
- `execution:123e4567-...:events`
- `task:789abcde-...:events`

## Testing WebSocket Endpoints

### Integration Tests

Test full streaming flow with Redis and WebSocket:

```python
import pytest
from fastapi.testclient import TestClient
from syntara.core.cache.stream import StreamClient

@pytest.mark.integration
async def test_invocation_streaming(test_cache, test_db):
    """Test end-to-end invocation streaming."""
    invocation_id = uuid4()
    stream_id = f"invocation:{invocation_id}:events"

    # Create invocation in DB
    async with get_session() as session:
        invocation = Invocation(id=invocation_id, status="running")
        session.add(invocation)
        await session.commit()

    # Publish events to Redis
    async with StreamClient() as client:
        await client.publish(stream_id, {
            "event_type": "delta",
            "invocation_id": str(invocation_id),
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {"delta": "Hello"}
        })
        await client.publish(stream_id, {
            "event_type": "completion",
            "invocation_id": str(invocation_id),
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {}
        })

    # Connect and consume via WebSocket
    with TestClient(app) as client:
        with client.websocket_connect(
            f"/ws/invocations/v1/invocations?invocation_id={invocation_id}"
        ) as websocket:
            events = []
            while True:
                event = websocket.receive_json()
                events.append(event)
                if event["event_type"] == "completion":
                    break

    assert len(events) == 2
    assert events[0]["event_type"] == "delta"
    assert events[1]["event_type"] == "completion"
```

### Unit Tests

Test handler logic independently:

```python
async def test_create_session_state_validation():
    """Test session state validation."""
    handler = InvocationStreamingHandler()

    with pytest.raises(StreamingValidationError) as exc:
        await handler.create_session_state(invocation_id="nonexistent")

    assert exc.value.error_data.code == "INVOCATION_NOT_FOUND"
```

### Testing Hooks

Test custom hooks:

```python
async def test_before_receive_custom_validation():
    """Test custom validation in before_receive hook."""
    from my_component.ws.example import before_receive

    with pytest.raises(ValidationError) as exc:
        await before_receive(
            {"input": "blocked_content"},
            "ExampleRequest",
            "example"
        )

    assert "blocked prefix" in exc.value.message
```

Test fixtures commonly needed:
- `test_cache` - Redis instance for StreamClient
- `test_db` - PostgreSQL for database models
- `test_stream` - Fixture providing stream_id with auto-cleanup
- `populated_stream` - Pre-populated stream with test events

## Bootstrap and Auto-Discovery

WebSocket endpoints are automatically discovered and registered at application startup.

### Router Setup

In `src/syntara/api/main.py`:

```python
from syntara.core.websocket.router import build_websocket_router

# Build router with auto-discovery
ws_router = build_websocket_router()
app.include_router(ws_router)

# Start lifecycle monitoring
from syntara.core.websocket.manager import get_connection_lifecycle_manager
manager = get_connection_lifecycle_manager()
manager.start_monitoring()

@app.on_event("shutdown")
async def shutdown():
    manager.stop_monitoring()
```

### Discovery Process

1. Scans `src/syntara/{component}/ws/*.py` for handler files
2. Derives spec paths using convention: `schemas/{component}/websocket-{handler}.{yaml|yml|json}`
3. Validates handler/spec pairing (fail-fast if either is missing)
4. Loads AsyncAPI specs
5. Merges specs if component has multiple handler files
6. Creates endpoints via endpoint factory
7. Registers routes with FastAPI router
8. Runs validation interceptors

Validation includes:
- Channel names follow snake_case convention
- All `handle_*` and `on_connect_*` functions have corresponding channels
- All channels have corresponding handler functions (warning)
- No duplicate channels across specs in same component

## Channel Naming Conventions

AsyncAPI channel names:
- Use kebab-case in spec: `agent-events`, `invocations`, `coffee`
- Normalized to snake_case for Python: `agent_events`, `invocations`, `coffee`

Handler function names:
- Bidirectional: `handle_{normalized_name}` (e.g., `handle_agent_events`)
- Receive-only: `on_connect_{normalized_name}` (e.g., `on_connect_invocations`)

URL paths in spec `address`:
- Use kebab-case: `/ws/example/v1/agent-events`
- Include version: `/ws/{component}/v1/{channel-name}`

## Common Patterns

### Multi-Client Broadcasting

Multiple clients can connect to the same resource stream:

```python
manager = get_connection_lifecycle_manager()
connections = manager.get_connections_for_resource(resource_id)
for conn in connections:
    if conn.websocket and conn.is_active:
        await conn.websocket.send_json(event)
```

### Connection Metadata

Store per-connection data:

```python
manager.update_metadata(lifecycle_conn_id, "last_event_id", "1234567890-0")
manager.update_metadata(lifecycle_conn_id, "replay_count", "10")

# Retrieve
conn = manager.get_connection(lifecycle_conn_id)
last_id = conn.metadata.get("last_event_id")
```

### Channel-Specific Connection Counts

```python
manager = get_connection_lifecycle_manager()
count = manager.get_active_connection_count_for_channel("invocations")
```

### Resource-Specific Connection Counts

```python
count = manager.get_active_connection_count_for_resource(invocation_id)
```

## Tooling vs Convention

**Enforced by tooling:**

- AsyncAPI 3.0 schema validation (`schema_validator.py`) validates messages at runtime
- Handler/spec pairing validation at startup (fail-fast if either is missing)
- Channel name validation (snake_case convention enforced by interceptors)
- Duplicate channel detection across specs in same component
- Close code constants (`close_codes.py`) provide type-safe RFC 6455 codes

**Convention only:**

- Convention-based path mapping (`ws/{handler}.py` → `schemas/{component}/websocket-{handler}.yaml`)
- Handler function naming (`handle_*` for bidirectional, `on_connect_*` for receive-only)
- Message format (event_type, resource_id, timestamp, event_id structure)
- Error event format (RFC 9457 Problem Details in `data` field)
- Stream naming convention (`{resource_type}:{resource_id}:events`)
- Template method overrides in `BaseWebSocketStreamingHandler`

## Reference

| File | Purpose |
|---|---|
| `src/syntara/core/websocket/base_handler.py` | `BaseWebSocketStreamingHandler` template method pattern |
| `src/syntara/core/websocket/manager.py` | Connection lifecycle manager (singleton) |
| `src/syntara/core/websocket/schema_validator.py` | AsyncAPI 3.0 message validation |
| `src/syntara/core/websocket/endpoint_factory.py` | Factory for creating WebSocket endpoints |
| `src/syntara/core/websocket/router.py` | Auto-discovery and route registration |
| `src/syntara/core/websocket/hooks.py` | Pre/post validation hooks |
| `src/syntara/core/websocket/close_codes.py` | RFC 6455 close codes |
| `src/syntara/core/websocket/exceptions.py` | `StreamingValidationError`, `EventsExpiredError`, `WaitForStreamTimeoutError` |
| `schemas/` | AsyncAPI spec files per component |

Generated By: Claude Code (Claude Opus 4.6)
