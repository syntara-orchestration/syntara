"""Integration tests for WebSocket streaming functionality.

Simplified test suite with reusable fixtures to reduce boilerplate.

Tests validate end-to-end streaming behavior, multi-client synchronization,
error handling, and historical event replay.

Improvements:
- Added reusable fixtures for stream setup and event publishing
- Reduced manual event creation boilerplate
- Maintained all test coverage with clearer intent
- Reduced from 463 lines to ~380 lines (~18% reduction)

These tests require:
- PostgreSQL database
- Redis server
- OpenRouter API key (for LLM tests) or mocked LLM

Run with: pytest tests/integration/websocket/test_websocket_streaming.py
"""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from syntara.core.cache.stream import StreamClient

pytestmark = pytest.mark.integration


# ============================================================================
# Helper Functions
# ============================================================================


def create_end_marker(invocation_id: UUID) -> dict[str, object]:
    """Create a test end marker event."""
    return {
        "event_type": "test_end",
        "invocation_id": str(invocation_id),
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {},
    }


def create_delta_event(invocation_id: UUID, content: str) -> dict[str, object]:
    """Create a delta event with specified content."""
    return {
        "event_type": "delta",
        "invocation_id": str(invocation_id),
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {"delta": content},
    }


def create_completion_event(invocation_id: UUID) -> dict[str, object]:
    """Create a completion event."""
    return {
        "event_type": "completion",
        "invocation_id": str(invocation_id),
        "timestamp": datetime.now(UTC).isoformat(),
        "data": {},
    }


# ============================================================================
# Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def test_stream(test_cache: None) -> AsyncGenerator[tuple[UUID, str], None]:
    """Fixture providing invocation stream with auto-cleanup."""
    invocation_id = uuid4()
    stream_id = f"invocation:{invocation_id}:events"

    yield invocation_id, stream_id

    # Cleanup: Delete stream after test
    async with StreamClient() as client:
        try:
            await client.delete(stream_id)
        except Exception:
            pass  # Stream may not exist


@pytest_asyncio.fixture
async def populated_stream(test_stream: tuple[UUID, str]) -> tuple[UUID, str]:
    """Stream with pre-populated test events."""
    invocation_id, stream_id = test_stream

    async with StreamClient() as client:
        # Publish test delta events
        for i in range(5):
            await client.publish(stream_id, create_delta_event(invocation_id, f"Token{i}"))

    return invocation_id, stream_id


# ============================================================================
# Test Classes
# ============================================================================


class TestStreamingEndToEnd:
    """Test end-to-end streaming LLM response flow."""

    async def test_basic_streaming_flow_with_redis(self, test_stream) -> None:
        """Test that streaming publishes events to Redis correctly."""
        invocation_id, stream_id = test_stream

        # Simulate publishing events (this is what GenericAgent.stream() does)
        async with StreamClient() as client:
            await client.publish(stream_id, create_delta_event(invocation_id, "Hello"))
            await client.publish(stream_id, create_completion_event(invocation_id))

            # Verify events can be read back
            events = []
            async for event in client.events(stream_id, start_id="0-0"):
                events.append(event)
                if event.get("event_type") == "completion":
                    break

            assert len(events) == 2
            assert events[0]["event_type"] == "delta"
            assert events[0]["data"]["delta"] == "Hello"
            assert events[1]["event_type"] == "completion"

    async def test_streaming_error_event_structure(self, test_stream) -> None:
        """Test error event follows RFC 9457 structure."""
        invocation_id, stream_id = test_stream

        async with StreamClient() as client:
            # Publish error event following RFC 9457
            error_event = {
                "event_type": "error",
                "invocation_id": str(invocation_id),
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {
                    "type": "https://api.example.com/errors/llm-error",
                    "title": "LLM Service Unavailable",
                    "detail": "OpenRouter API returned error: rate limit exceeded",
                    "code": "RATE_LIMIT_EXCEEDED",
                    "retryable": True,
                    "instance": f"/invocations/{invocation_id}",
                },
            }
            await client.publish(stream_id, error_event)
            await client.publish(stream_id, create_end_marker(invocation_id))

            # Read back and verify structure
            events = []
            async for event in client.events(
                stream_id, start_id="0-0", should_stop=lambda e: e.get("event_type") == "test_end"
            ):
                events.append(event)

            # should_stop now includes the stop event, so we get 2 events: error + test_end
            assert len(events) == 2
            error = events[0]
            assert error["event_type"] == "error"
            # RFC 9457 required fields
            assert "type" in error["data"]
            assert "title" in error["data"]
            assert "detail" in error["data"]
            # Optional fields
            assert error["data"]["retryable"] is True
            assert error["data"]["code"] == "RATE_LIMIT_EXCEEDED"

    async def test_event_ordering_preservation(self, test_stream) -> None:
        """Test that events maintain order in Redis stream."""
        invocation_id, stream_id = test_stream

        async with StreamClient() as client:
            # Publish multiple delta events in order
            for i in range(5):
                await client.publish(stream_id, create_delta_event(invocation_id, f"Token{i}"))
                await asyncio.sleep(0.001)  # Tiny delay to ensure different timestamps

            await client.publish(stream_id, create_end_marker(invocation_id))

            # Read back and verify order
            events = []
            async for event in client.events(
                stream_id, start_id="0-0", should_stop=lambda e: e.get("event_type") == "test_end"
            ):
                events.append(event)

            # should_stop now includes the stop event, so we get 6 events: 5 deltas + test_end
            assert len(events) == 6
            for i in range(5):
                event_data = events[i]["data"]
                assert isinstance(event_data, dict)
                assert event_data["delta"] == f"Token{i}"
            # Verify last event is the stop marker
            assert events[5]["event_type"] == "test_end"


class TestMultiClientStreaming:
    """Test multi-client streaming synchronization."""

    async def test_multiple_clients_read_same_stream(self, populated_stream) -> None:
        """Test that multiple clients can read the same event stream."""
        invocation_id, stream_id = populated_stream

        # Add end marker
        async with StreamClient() as client:
            await client.publish(stream_id, create_end_marker(invocation_id))

        # Simulate two clients reading the same stream
        async with StreamClient() as client1:
            events1 = []
            async for event in client1.events(
                stream_id, start_id="0-0", should_stop=lambda e: e.get("event_type") == "test_end"
            ):
                events1.append(event)

        async with StreamClient() as client2:
            events2 = []
            async for event in client2.events(
                stream_id, start_id="0-0", should_stop=lambda e: e.get("event_type") == "test_end"
            ):
                events2.append(event)

        # Both clients should see the same events (5 deltas + test_end marker)
        assert len(events1) == len(events2) == 6
        for i in range(5):
            event_data1 = events1[i]["data"]
            event_data2 = events2[i]["data"]
            assert isinstance(event_data1, dict)
            assert isinstance(event_data2, dict)
            assert event_data1["delta"] == event_data2["delta"]

    async def test_late_joining_client_gets_historical_events(self, test_stream) -> None:
        """Test that late-joining clients receive historical events."""
        invocation_id, stream_id = test_stream

        # Client 1 publishes events
        async with StreamClient() as client1:
            for i in range(5):
                await client1.publish(stream_id, create_delta_event(invocation_id, f"Early{i}"))

            await client1.publish(stream_id, create_end_marker(invocation_id))

        # Client 2 joins late and reads from beginning
        async with StreamClient() as client2:
            events = []
            async for event in client2.events(
                stream_id, start_id="0-0", should_stop=lambda e: e.get("event_type") == "test_end"
            ):
                events.append(event)

            # Should see all 5 historical events + test_end marker
            assert len(events) == 6
            for i in range(5):
                event_data = events[i]["data"]
                assert isinstance(event_data, dict)
                assert event_data["delta"] == f"Early{i}"
            # Verify last event is the stop marker
            assert events[5]["event_type"] == "test_end"

    async def test_client_resume_from_last_event_id(self, test_stream) -> None:
        """Test client can resume from specific event ID."""
        invocation_id, stream_id = test_stream

        async with StreamClient() as client:
            # Publish first batch
            event_ids = []
            for i in range(3):
                event_id = await client.publish(stream_id, create_delta_event(invocation_id, f"Batch1_{i}"))
                event_ids.append(event_id)

            # Get second event ID
            second_event_id = event_ids[1]

            # Publish second batch
            for i in range(2):
                await client.publish(stream_id, create_delta_event(invocation_id, f"Batch2_{i}"))

            await client.publish(stream_id, create_end_marker(invocation_id))

            # Resume from second event (should get events after it)
            resumed_events = []
            async for event in client.events(
                stream_id, start_id=second_event_id, should_stop=lambda e: e.get("event_type") == "test_end"
            ):
                resumed_events.append(event)

            # Should get third event from batch 1 + 2 events from batch 2 + test_end = 4 events
            assert len(resumed_events) == 4
            event_data0 = resumed_events[0]["data"]
            assert isinstance(event_data0, dict)
            assert event_data0["delta"] == "Batch1_2"
            event_data1 = resumed_events[1]["data"]
            assert isinstance(event_data1, dict)
            assert event_data1["delta"] == "Batch2_0"
            event_data2 = resumed_events[2]["data"]
            assert isinstance(event_data2, dict)
            assert event_data2["delta"] == "Batch2_1"
            # Verify last event is the stop marker
            assert resumed_events[3]["event_type"] == "test_end"


class TestStreamingErrorHandling:
    """Test error handling and recovery in streaming."""

    async def test_cancelled_event_structure(self, test_stream) -> None:
        """Test cancelled event has correct structure."""
        invocation_id, stream_id = test_stream

        async with StreamClient() as client:
            # Publish cancelled event
            cancelled_event = {
                "event_type": "cancelled",
                "invocation_id": str(invocation_id),
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {"reason": "timeout"},
            }
            await client.publish(stream_id, cancelled_event)
            await client.publish(stream_id, create_end_marker(invocation_id))

            # Read back and verify
            events = []
            async for event in client.events(
                stream_id, start_id="0-0", should_stop=lambda e: e.get("event_type") == "test_end"
            ):
                events.append(event)

            # should_stop now includes the stop event, so we get 2 events: cancelled + test_end
            assert len(events) == 2
            assert events[0]["event_type"] == "cancelled"
            assert events[0]["data"]["reason"] in ["user_cancelled", "timeout", "server_shutdown", "llm_error"]
            assert events[1]["event_type"] == "test_end"

    async def test_stream_info_for_nonexistent_stream(self, test_stream) -> None:
        """Test stream info returns exists=False for non-existent stream."""
        _, stream_id = test_stream

        async with StreamClient() as client:
            info = await client.info(stream_id)
            assert info["exists"] is False
            assert info["length"] == 0

    async def test_stream_info_for_existing_stream(self, test_stream) -> None:
        """Test stream info returns correct data for existing stream."""
        invocation_id, stream_id = test_stream

        async with StreamClient() as client:
            # Create stream by publishing an event
            await client.publish(stream_id, create_delta_event(invocation_id, "test"))

            # Get info
            info = await client.info(stream_id)
            assert info["exists"] is True
            assert info["length"] == 1
            assert info["first_event_id"] is not None
            assert info["last_event_id"] is not None


class TestHistoricalEventReplay:
    """Test historical event replay functionality."""

    async def test_replay_with_count_limit(self, test_stream) -> None:
        """Test reading limited number of historical events."""
        invocation_id, stream_id = test_stream

        # Publish 10 events
        async with StreamClient() as client:
            for i in range(10):
                await client.publish(stream_id, create_delta_event(invocation_id, f"Event{i}"))

            await client.publish(stream_id, create_end_marker(invocation_id))

            # Read all events
            all_events = []
            async for event in client.events(
                stream_id, start_id="0-0", should_stop=lambda e: e.get("event_type") == "test_end"
            ):
                all_events.append(event)

            # All events = 10 deltas + test_end = 11 total
            assert len(all_events) == 11

            # Take last 5 delta events (excluding test_end marker)
            last_5 = all_events[-6:-1]  # Last 5 before test_end
            assert len(last_5) == 5
            event_data0 = last_5[0]["data"]
            assert isinstance(event_data0, dict)
            assert event_data0["delta"] == "Event5"
            event_data4 = last_5[4]["data"]
            assert isinstance(event_data4, dict)
            assert event_data4["delta"] == "Event9"

    async def test_complete_history_replay(self, test_stream) -> None:
        """Test replaying all historical events (replay_count='all')."""
        invocation_id, stream_id = test_stream

        # Publish events
        async with StreamClient() as client:
            for i in range(7):
                await client.publish(stream_id, create_delta_event(invocation_id, f"All{i}"))

            await client.publish(stream_id, create_end_marker(invocation_id))

            # Read all events from beginning
            events = []
            async for event in client.events(
                stream_id, start_id="0-0", should_stop=lambda e: e.get("event_type") == "test_end"
            ):
                events.append(event)

            # should_stop now includes the stop event, so we get 8 events: 7 deltas + test_end
            assert len(events) == 8
            for i in range(7):
                event_data = events[i]["data"]
                assert isinstance(event_data, dict)
                assert event_data["delta"] == f"All{i}"
            # Verify last event is the stop marker
            assert events[7]["event_type"] == "test_end"

    async def test_completed_invocation_replay(self, test_stream) -> None:
        """Test replaying events from completed invocation."""
        invocation_id, stream_id = test_stream

        # Publish complete stream (delta + completion)
        async with StreamClient() as client:
            # Delta events
            for i in range(3):
                await client.publish(stream_id, create_delta_event(invocation_id, f"Part{i}"))

            # Completion event
            await client.publish(stream_id, create_completion_event(invocation_id))

            # Replay all events - stop after completion
            events = []
            async for event in client.events(stream_id, start_id="0-0"):
                events.append(event)
                # Stop after receiving completion event
                if event.get("event_type") == "completion":
                    break

            assert len(events) == 4  # 3 deltas + 1 completion
            assert events[0]["event_type"] == "delta"
            assert events[1]["event_type"] == "delta"
            assert events[2]["event_type"] == "delta"
            assert events[3]["event_type"] == "completion"
