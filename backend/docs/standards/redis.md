# Redis Usage Standards

## Overview

Redis is the key/value store for the Nexus platform. It serves as a cache system for event streaming and multi-client synchronization (see decision-records.md, 2026-01-28).

Redis is NOT the primary data store. PostgreSQL is the source of truth for persistent data. Redis is used exclusively for:

- Event streaming via Redis Streams
- Temporary cache data with TTL-based expiration
- WebSocket event delivery coordination
- Settings L2 cache (shared across processes)
- Pub/Sub change notifications for runtime settings

## Client Architecture

### Singleton Client per Domain

Each domain has a single Redis client with one connection pool. Direct redis-py usage is discouraged.

- **`StreamClient`** — event streaming via Redis Streams (used by execution/invocation services)
- **`SettingsRedisClient`** — L2 key-value cache and Pub/Sub change notifications for runtime settings, combined in a single client to avoid multiple connection pools

All clients inherit from `BaseRedisClient` (`src/syntara/core/cache/base.py`), which provides shared connection lifecycle, automatic configuration from `CacheSettings`, and `redis_error_handler` for consistent error handling. See `src/syntara/core/cache/` for existing clients and reusable mixins.

## Connection Management

### Async Context Manager (Recommended)

```python
from syntara.core.cache.stream import StreamClient

async with StreamClient() as client:
    event_id = await client.publish(stream_id, data)
    async for event in client.events(stream_id):
        process(event)
```

The context manager automatically:

- Establishes connection on entry
- Closes connection on exit
- Handles cleanup in exception scenarios

### Manual Lifecycle (Advanced)

```python
client = StreamClient()
client.connect()
try:
    await client.publish(stream_id, data)
finally:
    await client.disconnect()
```

Only use manual lifecycle when:

- Multiple generators run concurrently
- The client is reused across operations
- Fine-grained control is required

### Connection Pooling

Connection pools are configured automatically via `CacheSettings`:

- `cache_connection_pool_size` (default: 50, configurable via `APP_CACHE_CONNECTION_POOL_SIZE`)
- Lazy connection on first operation
- Shared pool across all operations
- No manual pool management required
- Pool size must be ≥ 1 (validated at startup)

**Sizing guidance**: each long-lived Redis client (settings, rate-limit,
websocket tickets) opens its own pool. Under load, a single replica may hold
up to `pool_size × number_of_clients` connections. Size the pool relative to
Redis `maxclients` in shared environments.

## Configuration

All Redis configuration lives in `src/syntara/core/config/base.py` under `CacheSettings`:

```python
cache_host: str = "localhost"
cache_port: int = 6379
cache_db: int = 0
cache_password: SecretStr  # Required — no default; set via APP_CACHE_PASSWORD
cache_stream_ttl_seconds: int = 86400  # 24 hours
cache_connection_pool_size: int = 50  # Must be >= 1; validated at startup
```

`cache_password` has no default value — it must be provided via `APP_CACHE_PASSWORD` in all environments. For local development, set it in `.env`. For production, use secrets management. Ensure Redis is bound to internal networks and not exposed to the public internet.

Environment variables (prefix: `APP_`):

- `APP_CACHE_HOST`
- `APP_CACHE_PORT`
- `APP_CACHE_DB`
- `APP_CACHE_PASSWORD` — **required** (no default)
- `APP_CACHE_STREAM_TTL_SECONDS`
- `APP_CACHE_CONNECTION_POOL_SIZE`

Override via `.env` or environment. Never hardcode credentials.

## Key Naming Conventions

Use function-based stream ID generation for consistency:

```python
def get_execution_stream_id(execution_id: UUID) -> str:
    """Get Redis stream ID for an execution."""
    return f"execution:{execution_id}:events"
```

Pattern: `{resource_type}:{resource_id}:{data_type}`

Examples:

- `execution:550e8400-e29b-41d4-a716-446655440000:events`
- `invocation:7c9e6679-7425-40de-944b-e07fc1f90ae7:events`

Do NOT use ad-hoc string formatting. Define and reuse ID generator functions.

## Stream Operations

### Publishing Events

```python
event_id = await client.publish(
    stream_id="execution:uuid:events",
    data={"type": "update", "status": "running", "progress": 50}
)
```

Publish semantics:

- Auto-generated event ID via `XADD` with `*`
- JSON serialization of entire data dict into `data` field
- TTL reset on each publish via `EXPIRE`
- Returns Redis-generated event ID (e.g., `"1704103200000-0"`)

### Reading Events

#### Live Streaming

```python
async for event in client.events(stream_id):
    process(event)
```

Starts from current head. Blocks until new events arrive.

#### Replay from Beginning

```python
async for event in client.events(stream_id, start_id="0-0"):
    process(event)
```

Replays all events from stream start.

#### Replay Last N Events

```python
async for event in client.events(stream_id, replay=10):
    process(event)
```

Replays last 10 events, then continues with live streaming.

#### Conditional Termination

```python
async for event in client.events(
    stream_id,
    should_stop=lambda e: e.get("type") == "final_snapshot"
):
    process(event)
```

Stops after yielding the event where `should_stop` returns `True`.

### Stream Metadata

```python
info = await client.info(stream_id)
# {
#   "exists": True,
#   "length": 42,
#   "first_event_id": "1704103200000-0",
#   "last_event_id": "1704103300000-5"
# }
```

Use `info()` to check stream existence and size before operations.

### Stream Deletion

```python
deleted = await client.delete(stream_id)
# True if deleted, False if didn't exist
```

Use for cleanup in tests or explicit removal before TTL expiration.

## TTL Management

All streams have automatic TTL-based expiration:

- Default: 24 hours (`cache_stream_ttl_seconds`)
- TTL is reset on each `publish()`
- Streams expire after inactivity period
- No manual TTL management required

For workflows/executions:

- Publish events as they occur
- TTL resets with each event
- Active streams persist indefinitely
- Completed streams expire after 24h of inactivity

## Data Serialization

StreamClient handles serialization automatically:

- Input: Python dict
- Storage: JSON-encoded string in `data` field
- Output: Deserialized dict with `event_id` injected

Never manually serialize/deserialize. Trust the abstraction.

Event structure:

```python
# Published data
{"user_id": "123", "action": "login"}

# Retrieved data (event_id added automatically)
{"user_id": "123", "action": "login", "event_id": "1704103200000-0"}
```

The `event_id` field enables client-side resumption from last processed event.

## Error Handling

### Connection Errors

```python
from redis.exceptions import ConnectionError as RedisConnectionError

try:
    await client.publish(stream_id, data)
except RedisConnectionError:
    logger.exception("Redis connection failed")
    # Retry or fail gracefully
```

`BaseRedisClient` and its subclasses wrap network errors as `RedisConnectionError`.

### Stream Not Found

```python
from redis.exceptions import ResponseError

try:
    info = await client.info(stream_id)
except ResponseError as e:
    if "no such key" in str(e).lower():
        # Stream doesn't exist
        pass
```

Use `info()` to check existence without raising exceptions.

### Malformed Events

Malformed events (invalid JSON) are logged and skipped during iteration. StreamClient logs via structlog but does not raise exceptions.

## Testing with Redis

### Integration Tests

Use testcontainers for real Redis instance:

```python
import secrets

@pytest.fixture(scope="session")
def test_cache(worker_id: str):
    """Start Redis container for tests."""
    redis_image = os.getenv("REDIS_IMAGE", "public.ecr.aws/docker/library/redis:6")
    test_password = secrets.token_urlsafe(16)
    with RedisContainer(redis_image, password=test_password) as redis_container:
        # Patch settings
        yield
```

Pattern:

- Session-scoped Redis container
- Auto-cleanup on teardown
- Per-worker isolation for parallel tests
- Real Redis behavior (no mocks)

### Test Stream Cleanup

```python
@pytest_asyncio.fixture
async def stream_client_with_cleanup(redis_client, test_stream_id):
    """Create StreamClient with automatic cleanup."""
    client = StreamClient()
    yield client, test_stream_id
    await client.disconnect()
    await redis_client.delete(test_stream_id)
```

Always clean up test streams to prevent cross-test pollution.

### Unique Stream IDs

```python
@pytest_asyncio.fixture
async def test_stream_id() -> str:
    """Generate unique stream ID per test."""
    return f"test_stream_{uuid.uuid4()}"
```

Use unique IDs to avoid conflicts in parallel test execution.

## What Redis is NOT Used For

Redis is NOT:

- Primary data store (use PostgreSQL)
- Durable persistence layer (streams expire via TTL)
- Configuration storage (use environment variables)
- File storage (use filesystem or object storage)
- Task queue (use Temporal workflows)

Redis is ephemeral cache only. Plan for data loss after TTL expiration.

## Performance Considerations

### Batch Reading

StreamClient uses batching internally:

- `count=100` events per `XREAD` call (default)
- `block_ms=1000` blocking timeout (default)
- Automatically aggregates batches for iteration

Override only if profiling shows bottlenecks:

```python
async for event in client.events(stream_id, count=500, block_ms=5000):
    process(event)
```

### Concurrent Access

Redis Streams support multiple concurrent readers and writers:

- Multiple publishers to same stream: safe
- Multiple readers on same stream: safe
- Each reader sees all events independently
- No coordination required

### Replay Limits

Replay is capped at 1000 events internally to prevent memory exhaustion:

```python
async for event in client.events(stream_id, replay=5000):
    # Only replays last 1000 events (capped internally)
    pass
```

For large replays, use pagination with `start_id`.

## Backend Compatibility

StreamClient is abstracted to support Redis-compatible backends:

- Redis
- KeyDB
- Dragonfly
- Valkey

Implementation uses `redis-py` async client. No backend-specific features are used.

## Tooling vs Convention

**Enforced by tooling:**

- Pydantic validates `CacheSettings` field types and constraints at startup
- `StreamClient` enforces JSON serialization/deserialization automatically
- TTL is reset automatically on each `publish()` call
- Connection pooling is managed automatically via `CacheSettings`

**Convention only:**

- Key naming pattern (`{resource_type}:{resource_id}:{data_type}`)
- Using `StreamClient` abstraction over direct redis-py (not enforced)
- Function-based stream ID generation
- Test stream cleanup patterns
- Replay cap of 1000 events (internal implementation detail)

## Reference

| File | Purpose |
|---|---|
| `src/syntara/core/cache/` | `BaseRedisClient`, mixins, and composed clients |
| `src/syntara/core/cache/stream.py` | `StreamClient` for event streaming |
| `src/syntara/core/config/base.py` | `CacheSettings` configuration |
| `tests/conftest.py` | Redis testcontainer fixtures |

Generated By: Claude Code (Claude Opus 4.6)
