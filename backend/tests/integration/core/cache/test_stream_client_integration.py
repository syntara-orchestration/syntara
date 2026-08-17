"""Integration tests for StreamClient with real Redis instance.

Simplified test suite with improved fixture design.

These tests require a running Redis instance (configured via environment variables).
They test real interactions including:
- Publishing and reading events
- Stream info retrieval
- Replay functionality
- Concurrent read/write operations
- Error scenarios with real network

Improvements:
- Integrated automatic cleanup into stream_client_with_cleanup fixture
- Removed repetitive @pytest.mark.usefixtures("cleanup_stream") decorators
- Reduced from 445 lines to ~410 lines (~8% reduction)
- Cleaner test code with less boilerplate
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
import redis.asyncio as redis

from syntara.core.cache.stream import StreamClient
from syntara.core.config.base import get_settings

# ============================================================================
# Fixtures
# ============================================================================


@pytest_asyncio.fixture(scope="session")
async def redis_client(test_cache: None) -> AsyncGenerator[redis.Redis, None]:
    """Create a Redis client for integration tests.

    Uses settings from environment variables or defaults.
    Tests will fail with RedisConnectionError if service is unavailable.
    """
    settings = get_settings()

    client = redis.Redis(
        host=settings.cache_host,
        port=settings.cache_port,
        db=settings.cache_db,
        password=settings.cache_password.get_secret_value() if settings.cache_password else None,
        decode_responses=True,
    )

    yield client

    try:
        await client.aclose()
    except RuntimeError:
        # Event loop may be closed during session teardown - ignore
        pass


@pytest_asyncio.fixture
async def test_stream_id() -> str:
    """Generate a unique stream ID for each test to avoid conflicts."""
    return f"test_stream_{uuid.uuid4()}"


@pytest_asyncio.fixture
async def stream_client(test_cache: None) -> AsyncGenerator[StreamClient, None]:
    """Create a StreamClient for integration tests."""
    client = StreamClient()
    yield client

    # Cleanup: disconnect after test
    await client.disconnect()


@pytest_asyncio.fixture
async def stream_client_with_cleanup(
    redis_client: redis.Redis, test_stream_id: str
) -> AsyncGenerator[tuple[StreamClient, str], None]:
    """Create a StreamClient with automatic stream cleanup.

    This fixture combines stream_client and cleanup_stream to reduce boilerplate.
    Returns a tuple of (client, stream_id) for convenience.
    """
    client = StreamClient()

    yield client, test_stream_id

    # Cleanup: disconnect and delete stream
    await client.disconnect()
    try:
        await redis_client.delete(test_stream_id)
    except Exception:
        pass  # Ignore errors during cleanup


# ============================================================================
# Test Classes
# ============================================================================


class TestPublishAndRead:
    """Test publishing and reading events with real Redis."""

    @pytest.mark.asyncio
    async def test_publish_and_read_single_event(self, stream_client_with_cleanup) -> None:
        """Test publishing and reading a single event."""
        stream_client, test_stream_id = stream_client_with_cleanup

        # Publish event
        data = {"user_id": "123", "action": "login", "timestamp": "2024-01-01T10:00:00Z"}
        event_id = await stream_client.publish(test_stream_id, data)

        assert event_id is not None
        assert "-" in event_id  # Redis event IDs have format "timestamp-sequence"

        # Read event
        events = []
        async for event in stream_client.events(test_stream_id):
            events.append(event)
            break  # Stop after first event

        assert len(events) == 1
        # Verify event_id is added by StreamClient
        assert "event_id" in events[0]
        assert events[0]["event_id"] == event_id
        # Verify original data is preserved
        for key, value in data.items():
            assert events[0][key] == value

    @pytest.mark.asyncio
    async def test_publish_multiple_events(self, stream_client_with_cleanup) -> None:
        """Test publishing and reading multiple events."""
        stream_client, test_stream_id = stream_client_with_cleanup

        # Publish multiple events
        test_data = [
            {"seq": 1, "action": "start"},
            {"seq": 2, "action": "middle"},
            {"seq": 3, "action": "end"},
        ]

        event_ids = []
        for data in test_data:
            event_id = await stream_client.publish(test_stream_id, data)
            event_ids.append(event_id)

        assert len(event_ids) == 3
        assert all("-" in eid for eid in event_ids)

        # Read all events
        events = []
        async for event in stream_client.events(test_stream_id):
            events.append(event)
            if len(events) >= 3:
                break

        # Verify all events have event_id and match published data
        assert len(events) == len(test_data)
        for i, event in enumerate(events):
            assert "event_id" in event
            assert event["event_id"] == event_ids[i]
            # Verify original data preserved
            for key, value in test_data[i].items():
                assert event[key] == value

    @pytest.mark.asyncio
    async def test_publish_nested_complex_data(self, stream_client_with_cleanup) -> None:
        """Test publishing and reading complex nested data structures."""
        stream_client, test_stream_id = stream_client_with_cleanup

        data = {
            "user_id": "123",
            "metadata": {
                "ip": "192.168.1.1",
                "user_agent": "Mozilla/5.0",
                "nested": {"deep": "value", "array": [1, 2, 3]},
            },
            "tags": ["tag1", "tag2", "tag3"],
            "score": 42.5,
        }

        await stream_client.publish(test_stream_id, data)

        events = []
        async for event in stream_client.events(test_stream_id):
            events.append(event)
            break

        # Verify event_id is added by StreamClient
        assert "event_id" in events[0]
        # Verify original data is preserved
        for key, value in data.items():
            assert events[0][key] == value

    @pytest.mark.asyncio
    async def test_read_from_specific_position(self, stream_client_with_cleanup) -> None:
        """Test reading events from a specific position."""
        stream_client, test_stream_id = stream_client_with_cleanup

        # Publish 5 events
        event_ids = []
        for i in range(5):
            event_id = await stream_client.publish(test_stream_id, {"seq": i})
            event_ids.append(event_id)

        # Read from the 3rd event (index 2)
        events = []
        async for event in stream_client.events(test_stream_id, start_id=event_ids[2]):
            events.append(event)
            if len(events) >= 2:  # Should get events 3 and 4
                break

        assert len(events) == 2
        assert events[0]["seq"] == 3  # After event at index 2
        assert events[1]["seq"] == 4


class TestReplayFunctionality:
    """Test replay functionality for reading last N events."""

    @pytest.mark.asyncio
    async def test_replay_last_n_events(self, stream_client_with_cleanup) -> None:
        """Test replaying last N events from stream."""
        stream_client, test_stream_id = stream_client_with_cleanup

        # Publish 10 events
        for i in range(10):
            await stream_client.publish(test_stream_id, {"seq": i})

        # Replay last 3 events
        events = []
        async for event in stream_client.events(test_stream_id, replay=3):
            events.append(event)
            if len(events) >= 3:
                break

        # Should get events 7, 8, 9 (last 3)
        assert len(events) == 3
        assert events[0]["seq"] == 7
        assert events[1]["seq"] == 8
        assert events[2]["seq"] == 9

    @pytest.mark.asyncio
    async def test_replay_empty_stream(self, stream_client_with_cleanup) -> None:
        """Test replay on empty stream."""
        stream_client, test_stream_id = stream_client_with_cleanup

        # Try to replay from empty stream with timeout
        events = []

        async def read_with_timeout() -> None:
            try:
                async for event in stream_client.events(test_stream_id, replay=5):
                    events.append(event)
                    # Never reach here for empty stream
            except TimeoutError:
                pass

        # Wait max 2 seconds - should timeout since stream is empty
        try:
            await asyncio.wait_for(read_with_timeout(), timeout=2.0)
        except TimeoutError:
            pass  # Expected for empty stream

        # Should get no events from empty stream
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_replay_fewer_events_than_requested(self, stream_client_with_cleanup) -> None:
        """Test replay when stream has fewer events than requested."""
        stream_client, test_stream_id = stream_client_with_cleanup

        # Publish only 3 events
        for i in range(3):
            await stream_client.publish(test_stream_id, {"seq": i})

        # Try to replay last 10 events (more than available)
        events = []
        async for event in stream_client.events(test_stream_id, replay=10):
            events.append(event)
            if len(events) >= 3:
                break

        # Should get all 3 available events
        assert len(events) == 3
        assert [e["seq"] for e in events] == [0, 1, 2]


class TestStreamInfo:
    """Test stream metadata retrieval."""

    @pytest.mark.asyncio
    async def test_info_existing_stream(self, stream_client_with_cleanup) -> None:
        """Test getting info for existing stream with events."""
        stream_client, test_stream_id = stream_client_with_cleanup

        # Publish events
        for i in range(5):
            await stream_client.publish(test_stream_id, {"seq": i})

        # Get stream info
        info = await stream_client.info(test_stream_id)

        assert info["exists"] is True
        assert info["length"] == 5
        assert info["first_event_id"] is not None
        assert info["last_event_id"] is not None

    @pytest.mark.asyncio
    async def test_info_nonexistent_stream(self, stream_client: StreamClient) -> None:
        """Test getting info for non-existent stream."""
        nonexistent_id = f"nonexistent_{uuid.uuid4()}"
        info = await stream_client.info(nonexistent_id)

        assert info["exists"] is False
        assert info["length"] == 0
        assert info["first_event_id"] is None
        assert info["last_event_id"] is None


class TestConcurrentOperations:
    """Test concurrent read/write operations."""

    @pytest.mark.asyncio
    async def test_concurrent_publishers(self, stream_client_with_cleanup) -> None:
        """Test multiple concurrent publishers to same stream."""
        _, test_stream_id = stream_client_with_cleanup

        async def publisher(client_id: int, count: int) -> None:
            async with StreamClient() as client:
                for i in range(count):
                    await client.publish(test_stream_id, {"client": client_id, "seq": i})

        # Run 3 concurrent publishers
        await asyncio.gather(publisher(1, 5), publisher(2, 5), publisher(3, 5))

        # Verify all events published
        async with StreamClient() as client:
            info = await client.info(test_stream_id)
            assert info["length"] == 15  # 3 publishers * 5 events each

    @pytest.mark.asyncio
    async def test_concurrent_readers(self, stream_client_with_cleanup) -> None:
        """Test multiple concurrent readers on same stream."""
        stream_client, test_stream_id = stream_client_with_cleanup

        # Publish events first
        for i in range(10):
            await stream_client.publish(test_stream_id, {"seq": i})

        async def reader(reader_id: int) -> int:
            async with StreamClient() as client:
                count = 0
                async for _ in client.events(test_stream_id):
                    count += 1
                    if count >= 10:
                        break
                return count

        # Run 3 concurrent readers
        counts = await asyncio.gather(reader(1), reader(2), reader(3))

        # All readers should see all events
        assert all(c == 10 for c in counts)

    @pytest.mark.asyncio
    async def test_publish_while_reading(self, stream_client_with_cleanup) -> None:
        """Test publishing events while actively reading."""
        _, test_stream_id = stream_client_with_cleanup

        # Publish initial events
        async with StreamClient() as client:
            for i in range(5):
                await client.publish(test_stream_id, {"seq": i, "phase": "initial"})

        events_read = []

        reader_started = asyncio.Event()

        async def reader() -> None:
            async with StreamClient() as client:
                reader_started.set()
                async for event in client.events(test_stream_id):
                    events_read.append(event)
                    if len(events_read) >= 10:
                        break

        async def publisher() -> None:
            await reader_started.wait()
            async with StreamClient() as client:
                for i in range(5):
                    await client.publish(test_stream_id, {"seq": i + 5, "phase": "concurrent"})

        # Run reader and publisher concurrently
        await asyncio.gather(reader(), publisher())

        # Should read all 10 events
        assert len(events_read) == 10
        initial = [e for e in events_read if e.get("phase") == "initial"]
        concurrent = [e for e in events_read if e.get("phase") == "concurrent"]
        assert len(initial) == 5
        assert len(concurrent) == 5


class TestContextManager:
    """Test async context manager usage."""

    @pytest.mark.asyncio
    async def test_context_manager_lifecycle(self, stream_client_with_cleanup) -> None:
        """Test context manager properly manages connection lifecycle."""
        _, test_stream_id = stream_client_with_cleanup

        data = {"test": "value"}

        async with StreamClient() as client:
            # Connection should be established
            assert client._client is not None

            # Should be able to publish
            event_id = await client.publish(test_stream_id, data)
            assert event_id is not None

        # After exiting, connection should be closed
        assert client._client is None

    @pytest.mark.asyncio
    async def test_multiple_operations_in_context(self, stream_client_with_cleanup) -> None:
        """Test multiple operations within same context."""
        _, test_stream_id = stream_client_with_cleanup

        async with StreamClient() as client:
            # Publish multiple events
            for i in range(5):
                await client.publish(test_stream_id, {"seq": i})

            # Get info
            info = await client.info(test_stream_id)
            assert info["length"] == 5

            # Read events
            events = []
            async for event in client.events(test_stream_id):
                events.append(event)
                if len(events) >= 5:
                    break

            assert len(events) == 5


class TestShouldStop:
    """Test should_stop callback functionality."""

    @pytest.mark.asyncio
    async def test_should_stop_on_marker_event(self, stream_client_with_cleanup) -> None:
        """Test stopping on a marker event."""
        stream_client, test_stream_id = stream_client_with_cleanup

        # Publish events with an end marker
        test_data = [
            {"seq": 1, "type": "data"},
            {"seq": 2, "type": "data"},
            {"seq": 3, "type": "end"},  # Stop marker
            {"seq": 4, "type": "data"},  # Should not be read
        ]

        for data in test_data:
            await stream_client.publish(test_stream_id, data)

        # Read with should_stop callback
        events = []
        async for event in stream_client.events(test_stream_id, should_stop=lambda e: e.get("type") == "end"):
            events.append(event)

        # Should get first 2 data events plus the terminal "end" event (yielded before stopping)
        assert len(events) == 3
        assert events[0]["type"] == "data"
        assert events[1]["type"] == "data"
        assert events[2]["type"] == "end"

    @pytest.mark.asyncio
    async def test_should_stop_on_condition(self, stream_client_with_cleanup) -> None:
        """Test stopping on a custom condition."""
        stream_client, test_stream_id = stream_client_with_cleanup

        # Publish events
        for i in range(10):
            await stream_client.publish(test_stream_id, {"seq": i, "value": i * 2})

        # Stop when value > 10
        events = []
        async for event in stream_client.events(test_stream_id, should_stop=lambda e: e.get("value", 0) > 10):
            events.append(event)

        # Should include seq=0 through seq=6 (value=12), where seq=6 is the terminal event
        assert len(events) == 7
        assert events[-1]["seq"] == 6  # Terminal event (value=12) is yielded before stopping
        assert events[-1]["value"] == 12
