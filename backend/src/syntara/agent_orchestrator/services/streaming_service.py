"""Streaming service components for WebSocket event streaming.

Provides WebSocket event streaming from Redis streams.
"""

from collections.abc import Callable
from functools import lru_cache
from typing import Any, cast
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.websockets import WebSocket

from syntara.agent_orchestrator.models.invocation import Invocation, InvocationStatus
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.models.error import ErrorData
from syntara.core.websocket.base_handler import BaseWebSocketStreamingHandler
from syntara.core.websocket.close_codes import POLICY_VIOLATION
from syntara.core.websocket.exceptions import EventsExpiredError, StreamingValidationError

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
        terminal_statuses = {InvocationStatus.COMPLETED, InvocationStatus.FAILED, InvocationStatus.CANCELLED}

        if invocation_status in terminal_statuses:
            # Invocation finished but stream doesn't exist - events expired
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

        # Invocation still running - wait for stream to be created
        await self._wait_for_stream_creation(
            stream_id=stream_id,
            resource_id=str(invocation_id),
            resource_status=invocation_status.value,
            resource_type="invocation",
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
            stmt = select(Invocation).where(Invocation.id == invocation_id)  # type: ignore[arg-type]
            result = await db_session.exec(stmt)  # type: ignore[call-overload]
            invocation = result.one_or_none()

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
