"""Generic Cache Stream client for arbitrary event data.

This module provides a flexible, generic interface for publishing and reading
arbitrary dictionary data to/from cache Streams. Unlike EventPublisher which
is tied to specific StreamingEvent objects, StreamClient accepts any dict data.

Abstracted to support redis-compatible backends (Redis, KeyDB, Dragonfly, Valkey).

Usage:
    from syntara.core.cache.stream import StreamClient

    # Recommended: Use as async context manager for automatic cleanup
    async with StreamClient() as client:
        # Publish arbitrary data
        event_id = await client.publish(
            stream_id="user_actions",
            data={"user_id": "123", "action": "login"}
        )

        # Read events from beginning
        async for event in client.events("user_actions"):
            print(event)

        # Replay last 10 events from current head
        async for event in client.events("user_actions", replay=10):
            print(event)

    # Alternative: Manual lifecycle management
    client = StreamClient()
    await client.connect()
    try:
        event_id = await client.publish("stream", {"key": "value"})
    finally:
        await client.disconnect()
"""

import asyncio
import json
from collections.abc import AsyncGenerator, Callable
from typing import Any

import structlog
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import MaxConnectionsError, ResponseError

from syntara.core.cache.base import BaseRedisClient, redis_operation_with_backoff
from syntara.core.exceptions import SafeValueError

logger = structlog.stdlib.get_logger(__name__)

# Error message constants
_STREAM_ID_EMPTY_ERROR = "stream_id cannot be empty"


class StreamClient(BaseRedisClient):
    """Generic Cache Stream client for publishing and reading arbitrary event data.

    This client provides a simple, flexible interface for working with cache Streams
    without being tied to specific event schemas. It automatically handles JSON
    serialization/deserialization and provides both publish and async generator-based
    reading capabilities.

    Recommended usage is as an async context manager for automatic resource cleanup.
    """

    _client_name = "stream"

    async def publish(self, stream_id: str, data: dict[str, Any]) -> str:
        """Publish arbitrary event data to a cache stream.

        Automatically serializes the data dictionary to JSON and publishes it
        to the specified stream using XADD. The entire dict is stored in a
        single 'data' field for simplicity.

        Retries XADD on ``MaxConnectionsError`` only (pool full before the
        command reaches Redis — safe to retry, no duplicate risk). Other
        ``RedisConnectionError`` subtypes indicate a mid-flight drop where
        Redis may have accepted the write; they are never retried.

        **Scope note**: callers currently create a fresh ``StreamClient``
        (and therefore a fresh pool) per publish via ``async with
        StreamClient()``. A brand-new pool cannot hit ``MaxConnectionsError``
        for a single XADD, so this retry path is effectively a no-op today.
        It exists as a forward-compatible safety net for when publish callers
        adopt a shared singleton ``StreamClient`` (see
        ``docs/standards/redis.md § Singleton Client per Domain``), at which
        point a long-lived pool *can* saturate. Until then, pool-exhaustion
        recovery primarily benefits the long-lived singleton clients
        (``SettingsRedisClient``, rate-limit, websocket tickets) via
        ``cache_setex`` / ``cache_delete``.

        EXPIRE is best-effort: single attempt, warning on failure. The event
        is durably written by the time EXPIRE runs; a missed TTL only delays
        cleanup and never justifies a second XADD.

        Args:
            stream_id: Stream identifier
            data: Arbitrary dictionary data to publish

        Returns:
            The stream-generated event ID (e.g., "1234567890123-0")

        Raises:
            RedisConnectionError: If XADD fails after retries exhausted
            TypeError: If data contains values not serializable to JSON
            ResponseError: If XADD operation fails
            ValueError: If stream_id is empty

        Example:
            >>> async with StreamClient() as client:
            ...     event_id = await client.publish(
            ...         stream_id="user_actions",
            ...         data={"user_id": "123", "action": "login", "timestamp": "2024-01-01T10:00:00Z"}
            ...     )
            ...     print(event_id)
            "1704103200000-0"

        """
        if not stream_id:
            msg = _STREAM_ID_EMPTY_ERROR
            raise SafeValueError(msg)

        client = self._ensure_connected()

        try:
            # Serialize the entire data dict to JSON for storage
            json_data = json.dumps(data)
        except TypeError:
            logger.exception("Failed to serialize data for stream", stream_id=stream_id)
            raise

        async def _xadd() -> str:
            try:
                # XADD to stream - store in 'data' field, '*' for auto-generated ID
                event_id = await client.xadd(stream_id, {"data": json_data})
                return str(event_id)  # Explicitly cast to str for type safety
            except ResponseError:
                logger.exception("Cache error publishing to stream", stream_id=stream_id)
                raise
            except OSError as e:
                msg = f"Network error: {e}"
                raise RedisConnectionError(msg) from e

        event_id = await redis_operation_with_backoff(
            _xadd, "stream_publish", retry_on=(MaxConnectionsError,), stream_id=stream_id
        )

        try:
            await client.expire(stream_id, self._settings.cache_stream_ttl_seconds)
        except (RedisConnectionError, ResponseError, OSError) as e:
            # Event is durably written; failed TTL only delays cleanup, never justifies re-running XADD.
            logger.warning("stream_expire_failed", stream_id=stream_id, event_id=event_id, error=str(e))

        logger.debug(
            "Published event to stream",
            stream_id=stream_id,
            event_id=event_id,
            ttl_seconds=self._settings.cache_stream_ttl_seconds,
        )
        return event_id

    def _validate_events_params(self, stream_id: str, start_id: str | None, replay: int | None) -> None:
        """Validate parameters for the events method.

        Args:
            stream_id: The stream identifier to read from
            start_id: Starting position in stream
            replay: Number of events to replay from current head

        Raises:
            ValueError: If parameters are invalid

        """
        if not stream_id:
            msg = _STREAM_ID_EMPTY_ERROR
            raise SafeValueError(msg)

        if start_id is not None and replay is not None:
            msg = "Cannot specify both start_id and replay - they are mutually exclusive"
            raise SafeValueError(msg)

        if replay is not None and replay <= 0:
            msg = "replay must be a positive integer"
            raise SafeValueError(msg)

    async def _determine_start_position(self, stream_id: str, start_id: str | None, replay: int | None) -> str:
        """Determine the starting position for reading events.

        Args:
            stream_id: The stream identifier to read from
            start_id: Explicit starting position (takes priority)
            replay: Number of events to replay from current head

        Returns:
            The starting event ID for XREAD

        Raises:
            RedisConnectionError: If client not connected
            ResponseError: If stream operation fails (other than non-existence)

        """
        client = self._ensure_connected()

        # Honor explicit start_id first
        if start_id is not None:
            return start_id

        # Calculate starting position from replay count
        if replay is not None:
            # Cap replay at 1000 to prevent excessive memory usage
            replay = min(replay, 1000)

            try:
                # Fetch count+1 events to determine proper starting position
                # XREAD returns events AFTER the given ID, so we need to account for this
                # by fetching one extra event
                events = await client.xrevrange(stream_id, count=replay + 1)

                if not events:
                    # Stream is empty, start from beginning
                    return "0-0"
                if len(events) > replay:
                    # Got count+1 events, use the oldest as start
                    # This will give us exactly 'replay' events when XREAD processes
                    return str(events[-1][0])
                # Got replay or fewer events, start from beginning to include all
                return "0-0"
            except ResponseError as e:
                if "no such key" in str(e).lower():
                    # Stream doesn't exist yet, start from beginning
                    return "0-0"
                logger.exception("Error calculating replay position for stream", stream_id=stream_id)
                raise

        # Default to beginning
        return "0-0"

    def _process_event_batch(
        self,
        stream_id: str,
        result: list[tuple[str, list[tuple[str, dict[str, str]]]]],
        should_stop: Callable[[dict[str, Any]], bool] | None,
    ) -> tuple[str | None, list[dict[str, Any]], bool]:
        """Process a batch of events from XREAD result.

        Args:
            stream_id: The stream identifier
            result: The XREAD result containing events
            should_stop: Optional callback to determine when to stop reading

        Returns:
            Tuple of (last_event_id, list_of_deserialized_events, should_stop_triggered)
            - last_event_id: The ID of the last processed event (or None if no events)
            - list_of_deserialized_events: Events including the stop event if triggered
            - should_stop_triggered: True if should_stop condition was met

        """
        last_id: str | None = None
        events: list[dict[str, Any]] = []

        # Result format: [(stream_name, [(event_id, {field: value}), ...])]
        for _stream_name, event_list in result:
            for event_id, fields in event_list:
                last_id = event_id

                # Deserialize the JSON data
                try:
                    data = json.loads(fields.get("data", "{}"))
                    # Add stream-generated event_id to enable client resumption
                    data["event_id"] = event_id
                except json.JSONDecodeError:
                    logger.exception("Failed to deserialize event from stream", event_id=event_id, stream_id=stream_id)
                    # Skip malformed events
                    continue

                events.append(data)

                # Check if we should stop after adding this event
                if should_stop and should_stop(data):
                    logger.debug(
                        "Stopping event stream (should_stop returned True)", stream_id=stream_id, event_id=event_id
                    )
                    # Return events including the stop event, signal to stop
                    return last_id, events, True

        return last_id, events, False

    async def _read_event_stream(
        self,
        stream_id: str,
        current_id: str,
        should_stop: Callable[[dict[str, Any]], bool] | None,
        block_ms: int,
        count: int,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Read events from stream in a loop.

        Args:
            stream_id: The stream identifier
            current_id: Starting event ID
            should_stop: Optional callback to determine when to stop
            block_ms: Milliseconds to block waiting for new events
            count: Maximum number of events to read per batch

        Yields:
            Deserialized event data dictionaries

        Raises:
            RedisConnectionError: If connection fails
            ResponseError: If stream read operation fails
            OSError: If network error occurs

        """
        client = self._ensure_connected()

        try:
            while True:
                # Read batch of events from stream
                result = await client.xread({stream_id: current_id}, count=count, block=block_ms)

                # If no events returned, continue waiting
                if not result:
                    await asyncio.sleep(0)
                    continue

                # Process batch and check for stop condition
                last_id, events, stop_triggered = self._process_event_batch(stream_id, result, should_stop)

                # Update current_id to continue from last processed event
                if last_id:
                    current_id = last_id

                # Yield all events from batch
                for event in events:
                    yield event

                # Stop after yielding if should_stop was triggered
                if stop_triggered:
                    return

        except ResponseError:
            logger.exception("Cache error reading from stream", stream_id=stream_id)
            raise
        except RedisConnectionError:
            logger.exception("Connection error reading from stream", stream_id=stream_id)
            raise
        except OSError as e:
            logger.exception("Network error reading from stream", stream_id=stream_id)
            msg = f"Network error: {e}"
            raise RedisConnectionError(msg) from e

    async def events(
        self,
        stream_id: str,
        start_id: str | None = None,
        replay: int | None = None,
        should_stop: Callable[[dict[str, Any]], bool] | None = None,
        block_ms: int = 1000,
        count: int = 100,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Read events from a stream as an async generator.

        Yields events one by one starting from the specified position. Automatically
        deserializes JSON data. Supports multiple termination mechanisms:
        - Manual: caller can break from loop at any time
        - Conditional: provide should_stop function for automatic termination
        - External: use asyncio.Event or other signaling mechanisms

        Position can be specified in two mutually exclusive ways:
        - start_id: Explicit stream position (honored first)
        - replay: Read last N events from current head (used if start_id not provided)

        Note: This method does NOT automatically disconnect when done since:
        - Multiple generators might be running concurrently
        - The client may be reused for multiple operations
        Use the context manager pattern or manually call disconnect() when finished.

        Args:
            stream_id: Stream identifier
            start_id: Starting position in stream. If provided, replay is ignored.
            replay: Number of events to replay from current head. Only used if start_id
                   is not provided. Retrieves last N events and starts from there.
            should_stop: Optional callback to determine when to stop reading.
                        Called with each event dict, stops when returns True.
            block_ms: Milliseconds to block waiting for new events (default 1000)
            count: Maximum number of events to read per batch (default 100)

        Yields:
            Dict[str, Any]: Deserialized event data dictionaries

        Raises:
            RedisConnectionError: If connection to cache fails
            json.JSONDecodeError: If event data cannot be deserialized
            ResponseError: If stream read operation fails
            ValueError: If stream_id is empty or both start_id and replay provided

        Example:
            >>> async with StreamClient() as client:
            ...     # Read from beginning
            ...     async for event in client.events("user_actions"):
            ...         print(event)
            ...
            ...     # Replay last 10 events
            ...     async for event in client.events("user_actions", replay=10):
            ...         print(event)
            ...
            ...     # Start from specific ID
            ...     async for event in client.events("user_actions", start_id="1234567890-0"):
            ...         print(event)
            ...
            ...     # Manual termination
            ...     async for event in client.events("user_actions"):
            ...         if event.get("action") == "logout":
            ...             break
            ...
            ...     # Conditional termination
            ...     async for event in client.events(
            ...         "user_actions",
            ...         should_stop=lambda e: e.get("type") == "end"
            ...     ):
            ...         process_event(event)

        """
        # Validate parameters
        self._validate_events_params(stream_id, start_id, replay)

        # Ensure connection
        self._ensure_connected()

        # Determine starting position
        current_id = await self._determine_start_position(stream_id, start_id, replay)

        # Read and yield events from stream
        async for event in self._read_event_stream(stream_id, current_id, should_stop, block_ms, count):
            yield event

    async def info(self, stream_id: str) -> dict[str, Any]:
        """Get metadata information about a stream.

        Retrieves stream statistics including length, first/last event IDs,
        and existence status.

        Args:
            stream_id: The stream identifier to inspect

        Returns:
            Dictionary containing stream metadata:
                - length: Number of events in stream
                - last_event_id: ID of most recent event (or None if empty)
                - first_event_id: ID of first event (or None if empty)
                - exists: Whether the stream exists

        Raises:
            RedisConnectionError: If connection to Redis fails
            ResponseError: If stream info operation fails (other than non-existence)
            ValueError: If stream_id is empty

        Example:
            >>> async with StreamClient() as client:
            ...     info = await client.info("user_actions")
            ...     print(f"Stream has {info['length']} events")
            ...     if info['exists']:
            ...         print(f"First: {info['first_event_id']}, Last: {info['last_event_id']}")

        """
        if not stream_id:
            msg = _STREAM_ID_EMPTY_ERROR
            raise SafeValueError(msg)

        client = self._ensure_connected()

        try:
            stream_info = await client.xinfo_stream(stream_id)
            return {
                "length": stream_info["length"],
                "last_event_id": stream_info["last-generated-id"],
                "first_event_id": stream_info["first-entry"][0] if stream_info["first-entry"] else None,
                "exists": True,
            }
        except ResponseError as e:
            # Stream doesn't exist
            if "no such key" in str(e).lower():
                return {
                    "length": 0,
                    "last_event_id": None,
                    "first_event_id": None,
                    "exists": False,
                }
            # Other error
            logger.exception("Redis error getting info for stream", stream_id=stream_id)
            raise
        except RedisConnectionError:
            logger.exception("Connection error getting info for stream", stream_id=stream_id)
            raise
        except OSError as e:
            logger.exception("Network error getting info for stream", stream_id=stream_id)
            msg = f"Network error: {e}"
            raise RedisConnectionError(msg) from e

    async def delete(self, stream_id: str) -> bool:
        """Delete a stream immediately.

        Removes the stream and all its events from Redis. Useful for cleanup
        in tests or when streams need to be explicitly removed before their TTL expires.

        Args:
            stream_id: The stream identifier to delete

        Returns:
            True if stream was deleted, False if it didn't exist

        Raises:
            RedisConnectionError: If connection to Redis fails
            ValueError: If stream_id is empty

        Example:
            >>> async with StreamClient() as client:
            ...     # Create and publish to stream
            ...     await client.publish("test_stream", {"key": "value"})
            ...     # Delete stream
            ...     deleted = await client.delete("test_stream")
            ...     print(deleted)  # True
            ...     # Try deleting non-existent stream
            ...     deleted = await client.delete("nonexistent")
            ...     print(deleted)  # False

        """
        if not stream_id:
            msg = _STREAM_ID_EMPTY_ERROR
            raise SafeValueError(msg)

        client = self._ensure_connected()

        try:
            deleted_count: int = await client.delete(stream_id)
            logger.debug("Deleted stream", stream_id=stream_id, deleted=deleted_count > 0)
            return deleted_count > 0

        except RedisConnectionError:
            logger.exception("Connection error deleting stream", stream_id=stream_id)
            raise
        except OSError as e:
            logger.exception("Network error deleting stream", stream_id=stream_id)
            msg = f"Network error: {e}"
            raise RedisConnectionError(msg) from e
