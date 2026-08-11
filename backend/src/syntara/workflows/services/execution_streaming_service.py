"""Streaming service components for WebSocket event streaming.

Provides WebSocket event streaming from Redis streams for workflow executions.
"""

import time
from collections.abc import Callable
from functools import lru_cache
from typing import Any, cast
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.websockets import WebSocket

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.models.error import ErrorData
from syntara.core.models.principal import PrincipalType
from syntara.core.websocket.base_handler import BaseWebSocketStreamingHandler
from syntara.core.websocket.close_codes import POLICY_VIOLATION
from syntara.core.websocket.exceptions import EventsExpiredError, StreamingValidationError
from syntara.workflows.audit.websocket_connection import WebSocketConnectionAction, WebSocketConnectionEvent
from syntara.workflows.models.execution import TERMINAL_EXECUTION_STATUSES, Execution, ExecutionStatus

logger = structlog.stdlib.get_logger(__name__)


# Constants for stream naming
def get_execution_stream_id(execution_id: UUID) -> str:
    """Get Redis stream ID for an execution.

    DRY helper to ensure consistent stream naming across the application.

    Args:
        execution_id: UUID of the execution

    Returns:
        Redis stream ID (e.g., "execution:UUID:events")

    """
    return f"execution:{execution_id}:events"


# Custom exceptions for execution streaming errors
class ExecutionStreamingNotFoundError(StreamingValidationError):
    """Execution does not exist in database (WebSocket streaming context)."""

    def __init__(self, execution_id: UUID) -> None:
        """Initialize execution streaming not found error."""
        error_data = ErrorData(
            type="https://api.example.com/errors/execution-not-found",
            title="Execution Not Found",
            detail=f"Execution {execution_id} not found in database",
            code="EXECUTION_NOT_FOUND",
            retryable=False,
            instance=f"/executions/{execution_id}",
        )
        super().__init__(error_data, POLICY_VIOLATION)


class WebSocketStreamingHandler(BaseWebSocketStreamingHandler):
    """Handler for streaming execution events from Redis to WebSocket clients.

    Extends BaseWebSocketStreamingHandler with execution-specific validation
    and streaming logic.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize WebSocket streaming handler.

        Args:
            session_factory: Async session factory for database access (required).

        """
        super().__init__(session_factory=session_factory, channel_name="executions")
        logger.info("WebSocketStreamingHandler initialized")

    async def create_session_state(self, **params: Any) -> dict[str, Any]:  # noqa: ANN401
        """Validate execution streaming request and create session state.

        Args:
            **params: Must contain 'execution_id' (UUID)

        Returns:
            Session state dict with execution_id and execution_status

        Raises:
            ExecutionStreamingNotFoundError: If execution does not exist
            StreamingValidationError: If execution_id is missing or invalid

        """
        # Extract and validate execution_id
        execution_id = params.get("execution_id")
        if not execution_id:
            error_data = ErrorData(
                type="https://api.example.com/errors/missing-parameter",
                title="Missing Required Parameter",
                detail="execution_id is required for streaming",
                code="MISSING_PARAMETER",
                retryable=False,
                instance="/executions",
            )
            raise StreamingValidationError(error_data, POLICY_VIOLATION)

        if not isinstance(execution_id, UUID):
            error_data = ErrorData(
                type="https://api.example.com/errors/invalid-parameter",
                title="Invalid Parameter Type",
                detail=f"execution_id must be a UUID, got {type(execution_id).__name__}",
                code="INVALID_PARAMETER",
                retryable=False,
                instance="/executions",
            )
            raise StreamingValidationError(error_data, POLICY_VIOLATION)

        execution_status = params.get("execution_status")
        if execution_status is None:
            execution_status = await self._check_execution_exists(execution_id)
        return {
            "execution_id": execution_id,
            "execution_status": execution_status,
        }

    def get_stop_condition(self, session_state: dict[str, Any]) -> Callable[[dict[str, Any]], bool]:  # noqa: ARG002
        """Return stop condition for execution streaming.

        Args:
            session_state: Session state dict with execution data

        Returns:
            Function that stops on final_snapshot message

        """
        return lambda e: e.get("type") == "final_snapshot"

    def get_resource_id(self, session_state: dict[str, Any]) -> str:
        """Get execution ID as resource ID.

        Args:
            session_state: Session state dict with execution_id

        Returns:
            String representation of execution_id

        """
        return str(session_state["execution_id"])

    async def wait_for_stream_ready(self, stream_id: str, session_state: dict[str, Any]) -> None:
        """Wait for execution stream to be created.

        Args:
            stream_id: Redis stream ID
            session_state: Session state dict with execution_id and execution_status

        Raises:
            EventsExpiredError: If execution is terminal but stream doesn't exist
            WaitForStreamTimeoutError: If timeout waiting for stream creation

        """
        execution_id = session_state["execution_id"]
        execution_status = session_state["execution_status"]

        if execution_status in TERMINAL_EXECUTION_STATUSES:
            # Execution finished but stream doesn't exist - events expired
            logger.warning(
                "Execution is in status but the Redis stream has expired",
                execution_id=execution_id,
                execution_status=execution_status.value,
            )
            raise EventsExpiredError(
                resource_id=str(execution_id),
                resource_status=execution_status.value,
                resource_type="execution",
            )

        # Execution still running - wait for stream to be created
        await self._wait_for_stream_creation(
            stream_id=stream_id,
            resource_id=str(execution_id),
            resource_status=execution_status.value,
            resource_type="execution",
        )

    async def _check_execution_exists(self, execution_id: UUID) -> ExecutionStatus:
        """Check if execution exists in database and return its status.

        Args:
            execution_id: UUID of the execution to check

        Returns:
            ExecutionStatus if execution exists

        Raises:
            ExecutionStreamingNotFoundError: If execution does not exist
            Exception: If database query fails

        """
        if self._session_factory is None:
            msg = "Session factory is required but was not provided"
            raise RuntimeError(msg)

        async with self._session_factory() as db_session:
            stmt = select(Execution).where(Execution.id == execution_id)
            result = await db_session.execute(stmt)
            execution = cast("Execution | None", result.scalar_one_or_none())

            if execution is None:
                logger.warning("Execution not found in database", execution_id=execution_id)
                raise ExecutionStreamingNotFoundError(execution_id)

            logger.debug("Execution found with status", execution_id=execution_id, status=execution.status)
            return execution.status


class ExecutionStreamingService:
    """Streaming service for execution WebSocket event delivery.

    Provides WebSocket streaming of execution events from Redis streams.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize streaming service.

        Args:
            session_factory: Async session factory for database access (required).

        """
        self._session_factory = session_factory
        self.websocket_handler = WebSocketStreamingHandler(session_factory=session_factory)
        logger.info("ExecutionStreamingService initialized")

    async def _resolve_workflow_context(self, execution_id: UUID) -> tuple[UUID | None, str, ExecutionStatus | None]:
        """Fetch workflow_id, workflow_name, and status for an execution.

        Returns:
            (workflow_id, workflow_name, status) — or (None, "", None) when
            the execution is not found.  The caller still emits the audit
            event so that the connection attempt is recorded.

        """
        async with self._session_factory() as session:
            result = await session.exec(
                select(Execution).where(Execution.id == execution_id).options(selectinload(Execution.workflow))  # type: ignore[arg-type]
            )
            execution = result.one_or_none()
            if execution is None:
                return None, "", None
            workflow_name = execution.workflow.name if execution.workflow else ""
            return execution.workflow_id, workflow_name, execution.status

    async def stream_events_to_websocket(
        self,
        websocket: WebSocket,
        execution_id: UUID,
        replay: str | None = None,
        connection_id: str | None = None,
        user_id: UUID | None = None,
        username: str | None = None,
        actor_type: PrincipalType | None = None,
    ) -> None:
        """Stream events from Redis to WebSocket client.

        Args:
            websocket: WebSocket connection
            execution_id: UUID of the execution to stream
            replay: Optional replay parameter:
                   - None: Live streaming only (new events after connection)
                   - "0": Replay from beginning (includes initial snapshot)
                   - event_id: Replay from specific Redis stream ID
            connection_id: Connection identifier for logging
            user_id: Authenticated user ID (from WebSocket auth)
            username: Authenticated username (from WebSocket auth)
            actor_type: Principal type of the authenticated actor

        """
        stream_id = get_execution_stream_id(execution_id)

        # Convert single replay parameter to replay_count and last_event_id
        # for BaseWebSocketStreamingHandler compatibility
        if replay is None:
            # Live streaming only
            replay_count = "0"
            last_event_id = None
        else:
            # Replay from beginning or specific event_id
            replay_count = "0"  # Not used when last_event_id is provided
            last_event_id = replay

        client_ip = websocket.client.host if websocket.client else "unknown"
        conn_id = connection_id or str(execution_id)[:8]

        try:
            workflow_id, workflow_name, execution_status = await self._resolve_workflow_context(execution_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to resolve workflow context for audit",
                execution_id=execution_id,
                error_type=type(exc).__name__,
                exc_info=True,
            )
            workflow_id, workflow_name, execution_status = None, "", None

        def _ws_event(
            action: WebSocketConnectionAction,
            duration_ms: int | None = None,
            close_reason: str | None = None,
            error_type: str | None = None,
        ) -> WebSocketConnectionEvent:
            return WebSocketConnectionEvent(
                execution_id=execution_id,
                workflow_id=workflow_id,
                workflow_name=workflow_name,
                action=action,
                client_ip=client_ip,
                connection_id=conn_id,
                duration_ms=duration_ms,
                close_reason=close_reason,
                error_type=error_type,
                replay=replay,
                user_id=user_id,
                username=username,
                actor_type=actor_type,
            )

        start_ns = time.monotonic_ns()

        AuditEventDispatcher.dispatch(_ws_event(action=WebSocketConnectionAction.CONNECTED))

        try:
            await self.websocket_handler.stream_events_to_websocket(
                websocket=websocket,
                stream_id=stream_id,
                replay_count=replay_count,
                last_event_id=last_event_id,
                connection_id=conn_id,
                execution_id=execution_id,
                execution_status=execution_status,
            )
        except Exception as exc:
            duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
            AuditEventDispatcher.dispatch(
                _ws_event(
                    action=WebSocketConnectionAction.ERROR,
                    duration_ms=duration_ms,
                    close_reason=str(exc) or type(exc).__name__,
                    error_type=type(exc).__name__,
                )
            )
            raise

        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        AuditEventDispatcher.dispatch(
            _ws_event(
                action=WebSocketConnectionAction.DISCONNECTED,
                duration_ms=duration_ms,
                close_reason="normal_close",
            )
        )


@lru_cache(maxsize=1)
def get_execution_streaming_service() -> ExecutionStreamingService:
    """Get the ExecutionStreamingService singleton using lru_cache.

    lru_cache provides thread-safe singleton without global mutable state.
    Clear cache in tests: get_execution_streaming_service.cache_clear()

    Returns:
        The shared ExecutionStreamingService instance

    """
    return ExecutionStreamingService(session_factory=AsyncSessionLocal)
