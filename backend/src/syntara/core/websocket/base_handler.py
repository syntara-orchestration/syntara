"""Base handler for streaming events from cache to WebSocket clients.

Provides a template method pattern for implementing WebSocket streaming handlers.
"""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.websockets import WebSocket

if TYPE_CHECKING:
    from uuid import UUID

from syntara.core.cache.stream import StreamClient
from syntara.core.constants import FieldLimits
from syntara.core.models.error import ErrorData
from syntara.core.websocket.close_codes import INTERNAL_ERROR, NORMAL_CLOSURE
from syntara.core.websocket.exceptions import StreamingValidationError, WaitForStreamTimeoutError
from syntara.core.websocket.manager import get_connection_lifecycle_manager

logger = structlog.stdlib.get_logger(__name__)


class BaseWebSocketStreamingHandler(ABC):
    """Base handler for streaming events from cache to WebSocket clients.

    This abstract base class implements the Template Method pattern to provide
    a reusable framework for WebSocket streaming. Subclasses must implement
    the template methods to customize behavior for their specific use cases.

    The base class handles:
    - Connection lifecycle management
    - Error handling patterns
    - WebSocket utilities
    - Common streaming logic

    Subclasses must implement:
    - create_session_state: Validate the streaming request and create session state
    - get_stop_condition: Define when to stop streaming
    - get_resource_id: Get resource ID for connection tracking
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        channel_name: str = "default",
    ) -> None:
        """Initialize base WebSocket streaming handler.

        Args:
            session_factory: Async session factory for database access (optional).
            channel_name: Channel name for connection lifecycle manager.

        """
        self._session_factory = session_factory
        self._channel_name = channel_name
        logger.info("Handler initialized with channel", handler=self.__class__.__name__, channel=channel_name)

    # ============ Template Methods (Must Override) ============

    @abstractmethod
    async def create_session_state(self, **params: Any) -> dict[str, Any]:  # noqa: ANN401
        """Validate request and create session state for this streaming session.

        This method should perform all validation checks required before streaming
        can begin. If validation fails, it should raise a StreamingValidationError
        or a subclass thereof.

        The returned session state dict is passed to other template methods and contains
        all the validated data needed for streaming. Each WebSocket connection gets
        its own session state dict to avoid shared state issues.

        Args:
            **params: Parameters passed to stream_events_to_websocket

        Returns:
            Session state dict containing validated data (e.g., resource_id, status, etc.)

        Raises:
            StreamingValidationError: If validation fails

        """

    @abstractmethod
    def get_stop_condition(self, session_state: dict[str, Any]) -> Callable[[dict[str, Any]], bool]:
        """Return function that determines when to stop streaming.

        Args:
            session_state: Session state dict from create_session_state

        Returns:
            Function that takes an event dict and returns True to stop streaming,
            False to continue. Example: lambda e: e.get("event_type") == "completion"

        """

    @abstractmethod
    def get_resource_id(self, session_state: dict[str, Any]) -> str:
        """Get resource ID for connection lifecycle manager.

        Args:
            session_state: Session state dict from create_session_state

        Returns:
            Resource ID string (e.g., invocation_id, task_id, etc.)

        """

    # ============ Optional Hooks (Can Override) ============

    async def wait_for_stream_ready(
        self, stream_id: str, session_state: dict[str, Any]
    ) -> None:  # NOSONAR - async required for subclass overrides
        """Wait for stream to be ready.

        Default implementation raises an error. Override this if your streaming
        use case needs to wait for stream creation (e.g., polling until stream exists).

        Note: This method is async to allow subclass overrides to perform async operations
        (e.g., polling, waiting). The base implementation doesn't await anything, which is
        expected and acceptable.

        Args:
            stream_id: Stream identifier
            session_state: Session state dict from create_session_state

        Raises:
            StreamingValidationError: If stream is not ready

        """
        error_data = ErrorData(
            type="https://api.example.com/errors/cache-stream-not-found",
            title="Cache Stream Not Found",
            detail=f"Cache stream {stream_id} does not exist",
            code="CACHE_STREAM_NOT_FOUND",
            retryable=False,
            instance=f"/{self._channel_name}/{self.get_resource_id(session_state)}",
        )
        raise StreamingValidationError(error_data, INTERNAL_ERROR)

    def get_replay_parameters(
        self,
        replay_count: str,
        last_event_id: str | None,
        session_state: dict[str, Any],  # noqa: ARG002
    ) -> tuple[str | None, int | None]:
        """Determine replay parameters.

        Default implementation provides standard replay logic:
        - last_event_id takes precedence (resume from specific event)
        - "all" -> replay from beginning (start_id="0-0")
        - "0" -> only new events (start_id="$")
        - numeric -> replay last N events (replay=N)

        Override if you need custom replay logic.

        Args:
            replay_count: Number of historical events to replay ("all", "0", or numeric string)
            last_event_id: Specific event ID to resume from (takes precedence)
            session_state: Session state dict from create_session_state

        Returns:
            Tuple of (start_id, replay) where:
                - start_id: Stream position to start from ("0-0", "$", specific ID, or None)
                - replay: Number of events to replay from end (or None if using start_id)

        """
        start_id = None
        replay = None

        if last_event_id:
            # last_event_id takes precedence - explicit resume position
            start_id = "0-0" if last_event_id == "0" else last_event_id
        elif replay_count == "all":
            # Start from beginning
            start_id = "0-0"
        elif replay_count == "0":
            # Only new events - use "$" special marker
            start_id = "$"
        else:
            # Replay last N events
            try:
                replay = int(replay_count)
            except (ValueError, TypeError):
                logger.warning("Invalid replay_count, defaulting to 10", replay_count=replay_count)
                replay = 10

        return start_id, replay

    def get_connection_metadata(self, session_state: dict[str, Any], **params: Any) -> dict[str, Any]:  # noqa: ARG002, ANN401
        """Get metadata for connection lifecycle manager.

        Default implementation returns replay parameters. Override to include
        additional metadata.

        Args:
            session_state: Session state dict from create_session_state
            **params: Parameters passed to stream_events_to_websocket

        Returns:
            Metadata dict for connection lifecycle manager

        """
        return {
            "replay_count": params.get("replay_count", "10"),
            "last_event_id": params.get("last_event_id"),
        }

    # ============ Core Streaming Logic (Don't Override) ============

    async def stream_events_to_websocket(
        self,
        websocket: WebSocket,
        stream_id: str,
        replay_count: str = "10",
        last_event_id: str | None = None,
        connection_id: str | None = None,
        **params: Any,  # noqa: ANN401
    ) -> None:
        """Stream events from cache to WebSocket client.

        This method orchestrates the entire streaming lifecycle:
        1. Create session state (via create_session_state)
        2. Add connection to lifecycle manager
        3. Activate connection
        4. Wait for stream ready if needed (via wait_for_stream_ready)
        5. Determine replay parameters (via get_replay_parameters)
        6. Stream events from cache
        7. Transform and send each event (via transform_event)
        8. Handle errors appropriately
        9. Cleanup connection

        Args:
            websocket: WebSocket connection
            stream_id: Stream identifier
            replay_count: Number of historical events to replay (default: "10")
            last_event_id: Specific event ID to resume from
            connection_id: Connection identifier for logging
            **params: Additional parameters passed to template methods

        """
        # Initialize variables for error handling and cleanup
        session_state: dict[str, Any] | None = None
        lifecycle_conn_id: UUID | None = None
        lifecycle_manager = get_connection_lifecycle_manager()
        conn_id = connection_id or "unknown"

        try:
            # Step 1: Create session state (validates and creates per-connection state)
            session_state = await self.create_session_state(**params)

            # Add connection to lifecycle manager
            client_ip = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"

            resource_id = self.get_resource_id(session_state)
            metadata = self.get_connection_metadata(
                session_state, replay_count=replay_count, last_event_id=last_event_id, **params
            )

            lifecycle_conn_id = lifecycle_manager.add_connection(
                channel=self._channel_name,
                client_ip=client_ip,
                resource_id=resource_id,
                metadata=metadata,
            )

            conn_id = connection_id or resource_id[:8]
            logger.info("Starting event streaming", connection_id=conn_id)

            # Activate connection after successful setup
            lifecycle_manager.activate_connection(lifecycle_conn_id)

            # Step 2: Check if stream exists
            async with StreamClient() as client:
                info = await client.info(stream_id)

                if not info["exists"]:
                    # Stream doesn't exist - wait for it to be ready
                    await self.wait_for_stream_ready(stream_id, session_state)

            # Step 3: Determine streaming replay parameters
            start_id, replay = self.get_replay_parameters(replay_count, last_event_id, session_state)

            # Step 4: Stream events to client
            stop_condition = self.get_stop_condition(session_state)
            async with StreamClient() as client:
                logger.info("Starting event stream", connection_id=conn_id)
                async for event in client.events(
                    stream_id=stream_id,
                    start_id=start_id,
                    replay=replay,
                    should_stop=stop_condition,
                    block_ms=1000,
                    count=10,
                ):
                    # Send event to WebSocket client
                    await websocket.send_json(event)

                    event_type = event.get("event_type")
                    logger.debug("Sent event to connection", event_type=event_type, connection_id=conn_id)

            # Stream completed normally
            await self._close_websocket(websocket, NORMAL_CLOSURE, "Streaming complete")
            logger.info("Event streaming completed", connection_id=conn_id)

        except Exception as e:
            # Handle errors
            await self._handle_error(e, websocket, conn_id, session_state)
            raise

        finally:
            # Always cleanup connection when done (if it was added)
            if lifecycle_conn_id is not None:
                lifecycle_manager.remove_connection(lifecycle_conn_id, reason="normal_close")

    # ============ Protected Utilities ============

    async def _handle_error(
        self, error: Exception, websocket: WebSocket, conn_id: str, session_state: dict[str, Any] | None
    ) -> None:
        """Handle errors during streaming.

        Args:
            error: The exception that occurred
            websocket: WebSocket connection
            conn_id: Connection ID for logging
            session_state: Session state dict from create_session_state
                (None if error occurred during create_session_state)

        """
        if isinstance(error, StreamingValidationError):
            # Handle validation errors by sending error event to client
            logger.warning("Streaming validation error", connection_id=conn_id, error=str(error))
            resource_id = self.get_resource_id(session_state) if session_state else "unknown"
            await self._send_error_event(websocket, error.error_data, resource_id)
            await self._close_websocket(websocket, error.close_code, error.error_data.title)
        else:
            # Handle unexpected errors
            resource_id = self.get_resource_id(session_state) if session_state else "unknown"
            logger.exception(
                "Error streaming events to connection",
                connection_id=conn_id,
                resource_id=resource_id,
                channel=self._channel_name,
                error_type=type(error).__name__,
            )

            # Try to send error to client if possible
            try:
                max_detail = FieldLimits.DESCRIPTION_MAX_LENGTH
                detail_prefix = "An unexpected error occurred during streaming: "
                error_msg = str(error)[: max_detail - len(detail_prefix)]
                error_data = ErrorData(
                    type="https://api.example.com/errors/internal-error",
                    title="Internal Server Error",
                    detail=f"{detail_prefix}{error_msg}",
                    code="INTERNAL_ERROR",
                    retryable=True,
                    instance=f"/{self._channel_name}/{resource_id}",
                )
                await self._send_error_event(websocket, error_data, resource_id)
                await self._close_websocket(websocket, INTERNAL_ERROR, "Internal error")
            except Exception:
                logger.exception(
                    "Failed to send error event to client",
                    connection_id=conn_id,
                    resource_id=resource_id,
                    original_error_type=type(error).__name__,
                    original_error=str(error)[:500],
                )

    async def _send_error_event(self, websocket: WebSocket, error_data: ErrorData, resource_id: str) -> None:
        """Send error event to WebSocket client.

        Args:
            websocket: WebSocket connection
            error_data: RFC 9457 compliant error data
            resource_id: Resource identifier for the error event

        """
        error_event = {
            "type": "error",
            "event_type": "error",
            "resource_id": resource_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "event_id": None,  # Errors don't have stream event_id (not resumable)
            "data": error_data.to_dict(),
        }
        await websocket.send_json(error_event)

    async def _close_websocket(self, websocket: WebSocket, code: int, reason: str) -> None:
        """Close WebSocket connection.

        Args:
            websocket: WebSocket connection
            code: WebSocket close code
            reason: Human-readable close reason

        """
        await websocket.close(code=code, reason=reason)

    async def _wait_for_stream_creation(
        self,
        stream_id: str,
        resource_id: str,
        resource_status: str,
        resource_type: str = "resource",
        max_wait_seconds: int = 30,
    ) -> None:
        """Wait for stream to be created in cache.

        Helper method for subclasses that need to wait for stream creation.

        Args:
            stream_id: Stream identifier
            resource_id: String representation of the resource ID
            resource_status: Current status of the resource
            resource_type: Type of resource (e.g., "invocation", "execution")
            max_wait_seconds: Maximum time to wait for stream creation

        Raises:
            WaitForStreamTimeoutError: If timeout waiting for stream creation

        """
        logger.info(
            "Stream does not exist yet, waiting for creation",
            stream_id=stream_id,
            resource_status=resource_status,
        )

        wait_interval = 0.5
        total_waited = 0.0

        async with StreamClient() as client:
            while total_waited < max_wait_seconds:
                await asyncio.sleep(wait_interval)
                total_waited += wait_interval

                info = await client.info(stream_id)
                if info["exists"]:
                    logger.info("Stream created after wait", stream_id=stream_id, wait_time=total_waited)
                    return

            # Timeout waiting for stream
            logger.error("Timeout waiting for stream to be created", stream_id=stream_id)
            raise WaitForStreamTimeoutError(
                resource_id=resource_id,
                resource_status=resource_status,
                resource_type=resource_type,
            )
