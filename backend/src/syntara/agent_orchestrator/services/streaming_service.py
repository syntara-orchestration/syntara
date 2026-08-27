"""Streaming service components for WebSocket event streaming.

Provides WebSocket event streaming from Redis streams.
"""

from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Any, cast
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.websockets import WebSocket

from syntara.agent_orchestrator.models.invocation import Invocation, InvocationStatus
from syntara.agent_orchestrator.utils.cancellation import get_invocation_cancel_key
from syntara.core.cache.stream import StreamClient
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.models.error import ErrorData
from syntara.core.websocket.base_handler import BaseWebSocketStreamingHandler
from syntara.core.websocket.close_codes import POLICY_VIOLATION
from syntara.core.websocket.exceptions import (
    EventsExpiredError,
    InvocationCancelledStreamError,
    StreamingValidationError,
)

logger = structlog.stdlib.get_logger(__name__)


# Constants for event types
TERMINAL_EVENT_TYPES = frozenset({"completion", "error", "cancelled"})
"""Event types that indicate the end of a streaming session."""


# Constants for stream naming
def get_invocation_stream_id(invocation_id: UUID) -> str:
    """Get Redis stream ID for an invocation.

    DRY helper to ensure consistent stream naming across the application.

    Args:
        invocation_id: UUID of the invocation

    Returns:
        Redis stream ID (e.g., "invocation:UUID:events")

    """
    return f"invocation:{invocation_id}:events"


# Custom exceptions for invocation streaming errors
class InvocationNotFoundError(StreamingValidationError):
    """Invocation does not exist in database."""

    def __init__(self, invocation_id: UUID) -> None:
        """Initialize invocation not found error."""
        error_data = ErrorData(
            type="https://api.example.com/errors/invocation-not-found",
            title="Invocation Not Found",
            detail=f"Invocation {invocation_id} not found in database",
            code="INVOCATION_NOT_FOUND",
            retryable=False,
            instance=f"/invocations/{invocation_id}",
        )
        super().__init__(error_data, POLICY_VIOLATION)


class WebSocketStreamingHandler(BaseWebSocketStreamingHandler):
    """Handler for streaming invocation events from Redis to WebSocket clients.

    Extends BaseWebSocketStreamingHandler with invocation-specific validation
    and streaming logic.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize WebSocket streaming handler.

        Args:
            session_factory: Async session factory for database access (required).

        """
        super().__init__(session_factory=session_factory, channel_name="invocations")
        logger.info("WebSocketStreamingHandler initialized")

    async def create_session_state(self, **params: Any) -> dict[str, Any]:  # noqa: ANN401
        """Validate invocation streaming request and create session state.

        Args:
            **params: Must contain 'invocation_id' (UUID)

        Returns:
            Session state dict with invocation_id and invocation_status

        Raises:
            InvocationNotFoundError: If invocation does not exist
            StreamingValidationError: If invocation_id is missing or invalid

        """
        # Extract and validate invocation_id
        invocation_id = params.get("invocation_id")
        if not invocation_id:
            error_data = ErrorData(
                type="https://api.example.com/errors/missing-parameter",
                title="Missing Required Parameter",
                detail="invocation_id is required for streaming",
                code="MISSING_PARAMETER",
                retryable=False,
                instance="/invocations",
            )
            raise StreamingValidationError(error_data, POLICY_VIOLATION)

        if not isinstance(invocation_id, UUID):
            error_data = ErrorData(
                type="https://api.example.com/errors/invalid-parameter",
                title="Invalid Parameter Type",
                detail=f"invocation_id must be a UUID, got {type(invocation_id).__name__}",
                code="INVALID_PARAMETER",
                retryable=False,
                instance="/invocations",
            )
            raise StreamingValidationError(error_data, POLICY_VIOLATION)

        invocation_status = await self._check_invocation_exists(invocation_id)
        return {
            "invocation_id": invocation_id,
            "invocation_status": invocation_status,
        }

    def get_stop_condition(self, session_state: dict[str, Any]) -> Callable[[dict[str, Any]], bool]:  # noqa: ARG002
        """Return stop condition for invocation streaming.

        Args:
            session_state: Session state dict with invocation data

        Returns:
            Function that stops on terminal invocation events

        """
        return lambda e: e.get("event_type") in TERMINAL_EVENT_TYPES

    def get_resource_id(self, session_state: dict[str, Any]) -> str:
        """Get invocation ID as resource ID.

        Args:
            session_state: Session state dict with invocation_id

        Returns:
            String representation of invocation_id

        """
        return str(session_state["invocation_id"])

    async def check_before_streaming(self, session_state: dict[str, Any]) -> None:
        """Raise if the invocation is CANCELLED before reading events.

        The connect-time ``invocation_status`` snapshot can be stale after
        ``wait_for_stream_ready``. A live Redis cancel-key check (DB fallback
        only when Redis itself errors) prevents replaying a raced
        ``completion`` event for an invocation that was cancelled while waiting.
        """
        invocation_id = session_state["invocation_id"]

        if session_state.get("invocation_status") == InvocationStatus.CANCELLED:
            logger.info(
                "Invocation already cancelled, aborting before streaming",
                invocation_id=invocation_id,
            )
            raise InvocationCancelledStreamError(
                resource_id=str(invocation_id),
                resource_type="invocation",
            )

        cancel_key = get_invocation_cancel_key(invocation_id)
        cancelled = False
        redis_available = True
        try:
            async with StreamClient() as client:
                cancelled = await client.key_exists(cancel_key) is True
        except Exception:  # noqa: BLE001
            redis_available = False
            logger.debug(
                "Pre-stream cancel key check failed, falling back to DB",
                invocation_id=invocation_id,
            )

        if not redis_available and not cancelled:
            try:
                status = await self._check_invocation_exists(invocation_id)
                cancelled = status == InvocationStatus.CANCELLED
            except StreamingValidationError:
                raise
            except Exception:  # noqa: BLE001
                logger.debug(
                    "DB fallback also failed before streaming",
                    invocation_id=invocation_id,
                )
                return

        if cancelled:
            logger.info(
                "Invocation cancelled before streaming (live check)",
                invocation_id=invocation_id,
            )
            raise InvocationCancelledStreamError(
                resource_id=str(invocation_id),
                resource_type="invocation",
            )

    def get_on_idle(
        self,
        session_state: dict[str, Any],
        client: StreamClient,
    ) -> Callable[[], Awaitable[None]] | None:
        """Return cancel-key checker invoked when XREAD returns no events.

        Redis-first, with a DB fallback only when Redis itself errors.
        Also short-circuits on the ``invocation_status`` snapshot from
        ``create_session_state`` so a late connect after the cancel key
        has expired still raises immediately.

        Raises ``InvocationCancelledStreamError`` if the invocation
        has been cancelled, which aborts the event stream.

        """
        invocation_id: UUID = session_state["invocation_id"]
        invocation_status = session_state.get("invocation_status")
        cancel_key = get_invocation_cancel_key(invocation_id)

        async def _check_cancel_on_idle() -> None:
            if invocation_status == InvocationStatus.CANCELLED:
                raise InvocationCancelledStreamError(
                    resource_id=str(invocation_id),
                    resource_type="invocation",
                )

            cancelled = False
            redis_available = True
            try:
                cancelled = await client.key_exists(cancel_key) is True
            except Exception:  # noqa: BLE001
                redis_available = False
                logger.debug("Idle cancel key check failed, falling back to DB", invocation_id=invocation_id)

            if not redis_available and not cancelled:
                try:
                    status = await self._check_invocation_exists(invocation_id)
                    cancelled = status == InvocationStatus.CANCELLED
                except StreamingValidationError:
                    raise
                except Exception:  # noqa: BLE001
                    logger.debug("DB fallback also failed, will retry next idle", invocation_id=invocation_id)
                    return

            if cancelled:
                logger.info("Invocation cancelled during event streaming (idle check)", invocation_id=invocation_id)
                raise InvocationCancelledStreamError(
                    resource_id=str(invocation_id),
                    resource_type="invocation",
                )

        return _check_cancel_on_idle

    async def wait_for_stream_ready(self, stream_id: str, session_state: dict[str, Any]) -> None:
        """Wait for invocation stream to be created.

        Args:
            stream_id: Redis stream ID
            session_state: Session state dict with invocation_id and invocation_status

        Raises:
            EventsExpiredError: If invocation is terminal but stream doesn't exist
            WaitForStreamTimeoutError: If timeout waiting for stream creation

        """
        invocation_id = session_state["invocation_id"]
        invocation_status = session_state["invocation_status"]

        # Terminal statuses indicate invocation has finished
        terminal_statuses = {InvocationStatus.COMPLETED, InvocationStatus.FAILED}

        if invocation_status == InvocationStatus.CANCELLED:
            logger.warning(
                "Invocation already cancelled, no stream to connect to",
                invocation_id=invocation_id,
            )
            raise InvocationCancelledStreamError(
                resource_id=str(invocation_id),
                resource_type="invocation",
            )

        if invocation_status in terminal_statuses:
            logger.warning(
                "Invocation is terminal but the Redis stream has expired",
                invocation_id=invocation_id,
                invocation_status=invocation_status.value,
            )
            raise EventsExpiredError(
                resource_id=str(invocation_id),
                resource_status=invocation_status.value,
                resource_type="invocation",
            )

        cancel_key = get_invocation_cancel_key(invocation_id)

        async def _check_cancel(client: StreamClient) -> None:
            try:
                cancelled = await client.key_exists(cancel_key)
            except Exception:  # noqa: BLE001
                # Redis failed — fall back to DB, same as _cancellation_watcher
                logger.debug("Cancel key check failed, falling back to DB", invocation_id=invocation_id)
                try:
                    status = await self._check_invocation_exists(invocation_id)
                    cancelled = status == InvocationStatus.CANCELLED
                except StreamingValidationError:
                    raise
                except Exception:  # noqa: BLE001
                    logger.debug("DB fallback also failed, will retry next poll", invocation_id=invocation_id)
                    return
            if cancelled:
                logger.info("Invocation cancelled during stream wait", invocation_id=invocation_id)
                raise InvocationCancelledStreamError(
                    resource_id=str(invocation_id),
                    resource_type="invocation",
                )

        await self._wait_for_stream_creation(
            stream_id=stream_id,
            resource_id=str(invocation_id),
            resource_status=invocation_status.value,
            resource_type="invocation",
            on_poll=_check_cancel,
        )

    async def _check_invocation_exists(self, invocation_id: UUID) -> InvocationStatus:
        """Check if invocation exists in database and return its status.

        Args:
            invocation_id: UUID of the invocation to check

        Returns:
            InvocationStatus if invocation exists

        Raises:
            InvocationNotFoundError: If invocation does not exist
            Exception: If database query fails

        """
        if self._session_factory is None:
            msg = "Session factory is required but was not provided"
            raise RuntimeError(msg)

        async with self._session_factory() as db_session:
            stmt = select(Invocation).where(Invocation.id == invocation_id)
            result = await db_session.execute(stmt)
            invocation = result.scalar_one_or_none()

            if invocation is None:
                logger.warning("Invocation not found in database", invocation_id=invocation_id)
                raise InvocationNotFoundError(invocation_id)

            logger.debug("Invocation found with status", invocation_id=invocation_id, status=invocation.status)
            return cast("InvocationStatus", invocation.status)


class StreamingService:
    """Streaming service for WebSocket event delivery.

    Provides WebSocket streaming of events from Redis streams.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize streaming service.

        Args:
            session_factory: Async session factory for database access (required).

        """
        self.websocket_handler = WebSocketStreamingHandler(session_factory=session_factory)
        logger.info("StreamingService initialized")

    async def stream_events_to_websocket(
        self,
        websocket: WebSocket,
        invocation_id: UUID,
        replay_count: str = "10",
        last_event_id: str | None = None,
        connection_id: str | None = None,
    ) -> None:
        """Stream events from Redis to WebSocket client.

        Args:
            websocket: WebSocket connection
            invocation_id: UUID of the invocation to stream
            replay_count: Number of historical events to replay (default: "10")
            last_event_id: Specific event ID to resume from
            connection_id: Connection identifier for logging

        """
        stream_id = get_invocation_stream_id(invocation_id)
        await self.websocket_handler.stream_events_to_websocket(
            websocket=websocket,
            stream_id=stream_id,
            replay_count=replay_count,
            last_event_id=last_event_id,
            connection_id=connection_id,
            invocation_id=invocation_id,
        )


@lru_cache(maxsize=1)
def get_streaming_service() -> StreamingService:
    """Get the StreamingService singleton using lru_cache.

    lru_cache provides thread-safe singleton without global mutable state.
    Clear cache in tests: get_streaming_service.cache_clear()

    Returns:
        The shared StreamingService instance

    """
    return StreamingService(session_factory=AsyncSessionLocal)
