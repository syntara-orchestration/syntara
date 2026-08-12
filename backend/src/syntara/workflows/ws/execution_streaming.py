"""Workflows WebSocket handler for streaming execution activity updates.

Thin proxy handler that delegates to ExecutionStreamingService for actual streaming logic.
"""

from uuid import UUID

import structlog
from fastapi import WebSocket
from pydantic import ValidationError

from syntara.core.models.principal import PrincipalType
from syntara.core.websocket.close_codes import UNSUPPORTED_DATA
from syntara.workflows.models.query_params import ExecutionStreamingQueryParams
from syntara.workflows.services.execution_streaming_service import get_execution_streaming_service

logger = structlog.stdlib.get_logger(__name__)


async def on_connect_executions(
    websocket: WebSocket,
    connection_id: str,
    user_id: UUID | None = None,
    username: str | None = None,
    actor_type: PrincipalType | None = None,
) -> None:
    """WebSocket connection handler for execution activity streaming.

    Thin proxy that delegates to ExecutionStreamingService for actual streaming logic.

    Args:
        websocket: The WebSocket connection
        connection_id: Unique connection identifier
        user_id: Authenticated user ID (from WebSocket auth)
        username: Authenticated username (from WebSocket auth)
        actor_type: Principal type of the authenticated actor

    """
    # Extract execution_id from WebSocket path
    # Path format: /ws/workflows/v1/executions/{execution_id}
    path_parts = websocket.url.path.split("/")
    execution_id_str = path_parts[-1]

    try:
        execution_id = UUID(execution_id_str)
    except ValueError:
        logger.exception("Invalid execution_id in path", execution_id_str=execution_id_str)
        await websocket.close(code=UNSUPPORTED_DATA, reason="Invalid execution ID")
        return

    # Validate query parameters
    try:
        params = ExecutionStreamingQueryParams(**dict(websocket.query_params))
        replay = params.replay
    except ValidationError as e:
        logger.warning("Invalid query parameters", validation_error=str(e))
        # Extract first error message for user-friendly reason
        error_msg = e.errors()[0]["msg"] if e.errors() else "Invalid query parameters"
        await websocket.close(code=UNSUPPORTED_DATA, reason=error_msg)
        return

    # Delegate to streaming service
    # Check app.state first (allows test injection), fallback to singleton
    streaming_service = getattr(websocket.app.state, "execution_streaming_service", None)
    if streaming_service is None:
        streaming_service = get_execution_streaming_service()

    await streaming_service.stream_events_to_websocket(
        websocket=websocket,
        execution_id=execution_id,
        replay=replay,
        connection_id=connection_id,
        user_id=user_id,
        username=username,
        actor_type=actor_type,
    )
