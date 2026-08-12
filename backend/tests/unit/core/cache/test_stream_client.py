"""Unit tests for StreamClient.

Simplified test suite focusing on:
- Conditional termination (should_stop callback)
- Error resilience (malformed JSON, connection errors)
- Input validation edge cases
- Replay functionality business logic
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError

from syntara.core.cache.stream import StreamClient
from syntara.core.exceptions import SafeValueError

pytestmark = pytest.mark.unit

# Error message for tests that expect exceptions before loop execution
_SHOULD_NOT_ITERATE = "Should not reach this point - exception expected before iteration"


@pytest.mark.parametrize(
    ("stream_id", "replay", "expected_error"),
    [
        ("", None, "stream_id cannot be empty"),
        ("valid", 0, "replay must be a positive integer"),
        ("valid", -1, "replay must be a positive integer"),
    ],
    ids=["empty_stream_id", "zero_replay", "negative_replay"],
)
async def test_events_input_validation(stream_id: str, replay: int | None, expected_error: str) -> None:
    """Test input validation for events() method."""
    with patch("syntara.core.cache.base.redis.Redis"):
        client = StreamClient()
        with pytest.raises(SafeValueError, match=expected_error):
            await anext(client.events(stream_id, replay=replay))


async def test_events_mutually_exclusive_params() -> None:
    """Test that start_id and replay parameters are mutually exclusive."""
    with patch("syntara.core.cache.base.redis.Redis"):
        client = StreamClient()
        with pytest.raises(SafeValueError, match="mutually exclusive"):
            await anext(client.events("test_stream", start_id="123-0", replay=10))


async def test_events_should_stop_conditional_termination() -> None:
    """Test should_stop callback for conditional stream termination.

    Note: The terminal event that triggers should_stop IS yielded before stopping.
    """
    mock_client = AsyncMock()
    mock_client.xread = AsyncMock(
        side_effect=[
            [
                (
                    "test_stream",
                    [
                        ("1234567890-0", {"data": json.dumps({"type": "start"})}),
                        ("1234567890-1", {"data": json.dumps({"type": "middle"})}),
                        ("1234567890-2", {"data": json.dumps({"type": "end"})}),
                    ],
                )
            ]
        ]
    )

    with patch("syntara.core.cache.base.redis.Redis", return_value=mock_client):
        async with StreamClient() as client:
            events = []
            async for event in client.events("test_stream", should_stop=lambda e: e.get("type") == "end"):
                events.append(event)

            # Should include the terminal "end" event before stopping
            assert len(events) == 3
            assert events[0]["type"] == "start"
            assert events[1]["type"] == "middle"
            assert events[2]["type"] == "end"


async def test_events_malformed_json_skipped() -> None:
    """Test that malformed JSON events are skipped and processing continues."""
    mock_client = AsyncMock()
    mock_client.xread = AsyncMock(
        side_effect=[
            [
                (
                    "test_stream",
                    [
                        ("1234567890-0", {"data": "invalid json{"}),
                        ("1234567890-1", {"data": json.dumps({"valid": "data"})}),
                    ],
                )
            ],
            [],
        ]
    )

    with patch("syntara.core.cache.base.redis.Redis", return_value=mock_client):
        async with StreamClient() as client:
            events = []
            async for event in client.events("test_stream"):
                events.append(event)
                if len(events) >= 1:
                    break

            # Should skip malformed event and only return valid one
            assert len(events) == 1
            # Event should include original data plus event_id from Redis
            assert events[0] == {"valid": "data", "event_id": "1234567890-1"}


async def test_events_replay_calculation() -> None:
    """Test replay functionality calculates correct start position.

    Replay should fetch count+1 events and start from the oldest,
    ensuring exactly 'count' events are replayed.
    """
    mock_client = AsyncMock()

    # Mock XREVRANGE to return 4 events (count+1) in reverse order
    mock_client.xrevrange = AsyncMock(
        return_value=[
            ("1234567893-0", {"data": json.dumps({"seq": 4})}),
            ("1234567892-0", {"data": json.dumps({"seq": 3})}),
            ("1234567891-0", {"data": json.dumps({"seq": 2})}),
            ("1234567890-0", {"data": json.dumps({"seq": 1})}),  # This should be the start position
        ]
    )

    mock_client.xread = AsyncMock(
        side_effect=[
            [("test_stream", [("1234567891-0", {"data": json.dumps({"seq": 2})})])],
            [],
        ]
    )

    with patch("syntara.core.cache.base.redis.Redis", return_value=mock_client):
        async with StreamClient() as client:
            events = []
            async for event in client.events("test_stream", replay=3):
                events.append(event)
                break

            # Verify XREVRANGE was called to get count+1 (4) events
            mock_client.xrevrange.assert_called_once_with("test_stream", count=4)

            # Verify XREAD started from the oldest event (seq 1)
            # This ensures XREAD will return events AFTER this ID, giving us exactly 3 events
            call_args = mock_client.xread.call_args_list[0]
            assert call_args[0][0]["test_stream"] == "1234567890-0"


async def test_events_replay_empty_stream() -> None:
    """Test replay on empty stream starts from beginning."""
    mock_client = AsyncMock()

    # Mock XREVRANGE returns empty for empty stream
    mock_client.xrevrange = AsyncMock(return_value=[])

    mock_client.xread = AsyncMock(
        side_effect=[
            [("test_stream", [("1234567890-0", {"data": json.dumps({"seq": 0})})])],
            [],
        ]
    )

    with patch("syntara.core.cache.base.redis.Redis", return_value=mock_client):
        async with StreamClient() as client:
            events = []
            async for event in client.events("test_stream", replay=10):
                events.append(event)
                if len(events) >= 1:
                    break

            # Should start from "0-0" when replay finds no events
            call_args = mock_client.xread.call_args_list[0]
            assert call_args[0][0]["test_stream"] == "0-0"
            assert len(events) == 1


async def test_publish_input_validation() -> None:
    """Test input validation for publish() method."""
    with patch("syntara.core.cache.base.redis.Redis"):
        client = StreamClient()
        with pytest.raises(SafeValueError, match="stream_id cannot be empty"):
            await client.publish("", {"key": "value"})


@pytest.mark.parametrize(
    ("exception_type", "error_message"),
    [
        (RedisConnectionError, "Connection lost"),
        (ResponseError, "Invalid stream"),
    ],
    ids=["connection_error", "response_error"],
)
async def test_publish_error_propagation(exception_type: type[Exception], error_message: str) -> None:
    """Test that Redis errors during publish are propagated."""
    mock_client = AsyncMock()
    mock_client.xadd = AsyncMock(side_effect=exception_type(error_message))

    with patch("syntara.core.cache.base.redis.Redis", return_value=mock_client):
        async with StreamClient() as client:
            with pytest.raises(exception_type, match=error_message):
                await client.publish("test_stream", {"key": "value"})


async def test_events_connection_error_propagates() -> None:
    """Test that connection errors during read are propagated."""
    mock_client = AsyncMock()
    mock_client.xread = AsyncMock(side_effect=RedisConnectionError("Connection lost"))

    with patch("syntara.core.cache.base.redis.Redis", return_value=mock_client):
        async with StreamClient() as client:
            with pytest.raises(RedisConnectionError, match="Connection lost"):
                await anext(client.events("test_stream"))


async def test_info_existing_stream() -> None:
    """Test getting info for existing stream."""
    mock_client = AsyncMock()
    mock_client.xinfo_stream = AsyncMock(
        return_value={
            "length": 10,
            "last-generated-id": "1234567890-9",
            "first-entry": ["1234567890-0", {"data": "..."}],
        }
    )

    with patch("syntara.core.cache.base.redis.Redis", return_value=mock_client):
        async with StreamClient() as client:
            info = await client.info("test_stream")

            assert info["exists"] is True
            assert info["length"] == 10
            assert info["last_event_id"] == "1234567890-9"
            assert info["first_event_id"] == "1234567890-0"


async def test_info_nonexistent_stream() -> None:
    """Test getting info for non-existent stream."""
    mock_client = AsyncMock()
    mock_client.xinfo_stream = AsyncMock(side_effect=ResponseError("ERR no such key"))

    with patch("syntara.core.cache.base.redis.Redis", return_value=mock_client):
        async with StreamClient() as client:
            info = await client.info("nonexistent_stream")

            assert info["exists"] is False
            assert info["length"] == 0
            assert info["last_event_id"] is None
            assert info["first_event_id"] is None


async def test_info_error_handling() -> None:
    """Test that non-'no such key' response errors are propagated."""
    mock_client = AsyncMock()
    mock_client.xinfo_stream = AsyncMock(side_effect=ResponseError("WRONGTYPE"))

    with patch("syntara.core.cache.base.redis.Redis", return_value=mock_client):
        async with StreamClient() as client:
            with pytest.raises(ResponseError, match="WRONGTYPE"):
                await client.info("test_stream")
