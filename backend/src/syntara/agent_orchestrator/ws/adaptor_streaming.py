"""Agent Orchestrator WebSocket handler for streaming LLM responses.

Thin proxy handler that delegates to StreamingService for actual streaming logic.
"""

from uuid import UUID

import structlog
from fastapi import WebSocket
from pydantic import ValidationError

from syntara.agent_orchestrator.models.query_params import StreamingQueryParams
from syntara.agent_orchestrator.services.streaming_service import get_streaming_service
from syntara.core.websocket.close_codes import UNSUPPORTED_DATA

logger = structlog.stdlib.get_logger(__name__)


async def on_connect_invocations(websocket: WebSocket, connection_id: str) -> None:
    """WebSocket connection handler for invocation streaming.

    Thin proxy that delegates to StreamingService for actual streaming logic.

    Args:
        websocket: The WebSocket connection
        connection_id: Unique connection identifier

    """
    # Extract invocation_id from WebSocket path
    # Path format: /ws/agent_orchestrator/v1/invocations/{invocation_id}
    path_parts = websocket.url.path.split("/")
    invocation_id_str = path_parts[-1]

    try:
        invocation_id = UUID(invocation_id_str)
    except ValueError:
        logger.exception("Invalid invocation_id in path", invocation_id_str=invocation_id_str)
        await websocket.close(code=UNSUPPORTED_DATA, reason="Invalid invocation ID")
        return

    # Validate query parameters
    try:
        params = StreamingQueryParams(**dict(websocket.query_params))
        replay_count = params.replay_count
        last_event_id = params.last_event_id
    except ValidationError as e:
        logger.warning("Invalid query parameters", validation_error=str(e))
        # Extract first error message for user-friendly reason
        error_msg = e.errors()[0]["msg"] if e.errors() else "Invalid query parameters"
        await websocket.close(code=UNSUPPORTED_DATA, reason=error_msg)
        return

    # Delegate to streaming service
    # Check app.state first (allows test injection), fallback to singleton
    streaming_service = getattr(websocket.app.state, "streaming_service", None)
    if streaming_service is None:
        streaming_service = get_streaming_service()

    await streaming_service.stream_events_to_websocket(
        websocket=websocket,
        invocation_id=invocation_id,
        replay_count=replay_count,
        last_event_id=last_event_id,
        connection_id=connection_id,
    )
