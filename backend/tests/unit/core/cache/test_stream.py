"""Unit tests for Redis StreamClient.

Simplified test suite focusing on:
- Terminal event stopping behavior (should_stop callback)
- Error resilience (malformed JSON handling)
- Basic integration tests for core operations
"""

from unittest.mock import AsyncMock, patch

import pytest

from syntara.core.cache.stream import StreamClient

pytestmark = pytest.mark.unit


async def test_events_stops_on_terminal_event() -> None:
    """Test that events() stops when should_stop callback returns True.

    Note: The terminal event IS yielded before stopping.
    """
    with patch("syntara.core.cache.base.redis.Redis") as mock_redis:
        mock_response = [
            [
                "test:stream",
                [
                    ["1-0", {"data": '{"event_type":"delta","data":{"delta":"word1"}}'}],
                    ["2-0", {"data": '{"event_type":"completion","data":{}}'}],
                    ["3-0", {"data": '{"event_type":"delta","data":{"delta":"word2"}}'}],
                ],
            ]
        ]

        mock_client = AsyncMock()
        mock_client.xread = AsyncMock(return_value=mock_response)
        mock_redis.return_value = mock_client

        async with StreamClient() as client:
            stream_id = "test:stream"
            events = []

            # Stop when we see completion event
            def should_stop(event: dict[str, object]) -> bool:
                return event.get("event_type") == "completion"

            async for event in client.events(stream_id, start_id="0-0", should_stop=should_stop):
                events.append(event)

            # Should get delta and completion, but not the delta after
            assert len(events) == 2
            assert events[0]["event_type"] == "delta"
            assert events[0]["data"]["delta"] == "word1"
            assert events[1]["event_type"] == "completion"


async def test_events_handles_malformed_json() -> None:
    """Test that malformed JSON events are skipped with warning."""
    with patch("syntara.core.cache.base.redis.Redis") as mock_redis:
        mock_response = [
            [
                "test:stream",
                [
                    ["1-0", {"data": '{"event_type":"delta","data":{"delta":"good"}}'}],
                    ["2-0", {"data": "invalid json {{{"}],  # Malformed JSON
                    ["3-0", {"data": '{"event_type":"delta","data":{"delta":"also_good"}}'}],
                ],
            ]
        ]

        mock_client = AsyncMock()
        mock_client.xread = AsyncMock(return_value=mock_response)
        mock_redis.return_value = mock_client

        async with StreamClient() as client:
            stream_id = "test:stream"
            events = []

            async for event in client.events(stream_id, start_id="0-0"):
                events.append(event)
                if len(events) >= 2:
                    break

            # Should skip malformed event and continue
            assert len(events) == 2
            assert events[0]["event_type"] == "delta"
            assert events[0]["data"]["delta"] == "good"
            assert events[1]["event_type"] == "delta"
            assert events[1]["data"]["delta"] == "also_good"


async def test_on_idle_called_when_xread_returns_empty() -> None:
    """Test that on_idle callback fires when XREAD returns no events."""
    with patch("syntara.core.cache.base.redis.Redis") as mock_redis:
        mock_client = AsyncMock()
        call_count = 0

        async def xread_side_effect(*_a: object, **_kw: object) -> list[object]:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return []
            return [
                [
                    "test:stream",
                    [["1-0", {"data": '{"event_type":"completion","data":{}}'}]],
                ]
            ]

        mock_client.xread = AsyncMock(side_effect=xread_side_effect)
        mock_redis.return_value = mock_client

        idle_calls = 0

        async def on_idle() -> None:
            nonlocal idle_calls
            idle_calls += 1

        async with StreamClient() as client:
            events = []
            async for event in client.events(
                "test:stream",
                start_id="0-0",
                should_stop=lambda e: e.get("event_type") == "completion",
                on_idle=on_idle,
            ):
                events.append(event)

            assert len(events) == 1
            assert idle_calls == 2


async def test_on_idle_exception_stops_stream() -> None:
    """Test that an exception raised by on_idle aborts the event stream."""
    with patch("syntara.core.cache.base.redis.Redis") as mock_redis:
        mock_client = AsyncMock()
        mock_client.xread = AsyncMock(return_value=[])
        mock_redis.return_value = mock_client

        async def on_idle_raises() -> None:
            msg = "cancelled"
            raise RuntimeError(msg)

        async with StreamClient() as client:
            with pytest.raises(RuntimeError, match="cancelled"):
                async for _event in client.events("test:stream", start_id="0-0", on_idle=on_idle_raises):
                    pass


async def test_info_existing_stream() -> None:
    """Test getting stream info for existing stream."""
    with patch("syntara.core.cache.base.redis.Redis") as mock_redis:
        mock_info = {
            "length": 42,
            "first-entry": ["1234567890-0", {"data": "..."}],
            "last-entry": ["1234567999-99", {"data": "..."}],
            "last-generated-id": "1234567999-99",
        }

        mock_client = AsyncMock()
        mock_client.xinfo_stream = AsyncMock(return_value=mock_info)
        mock_redis.return_value = mock_client

        async with StreamClient() as client:
            stream_id = "test:stream"
            info = await client.info(stream_id)

            # Verify info structure
            assert info is not None
            assert info["length"] == 42
            assert info["last_event_id"] == "1234567999-99"
