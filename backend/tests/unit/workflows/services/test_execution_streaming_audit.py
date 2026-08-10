"""Unit tests for WebSocket audit event dispatch in ExecutionStreamingService."""

# mypy: disable-error-code="attr-defined,method-assign"

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.workflows.audit.websocket_connection import (
    WebSocketConnectionAction,
    WebSocketConnectionEvent,
)
from syntara.workflows.services.execution_streaming_service import ExecutionStreamingService

EXECUTION_ID = uuid4()
WORKFLOW_ID = uuid4()
USER_ID = uuid4()
WORKFLOW_NAME = "Deploy to Production"


def _make_service() -> ExecutionStreamingService:
    """Create an ExecutionStreamingService with mocked internals."""
    service = ExecutionStreamingService(session_factory=MagicMock())
    service.websocket_handler = MagicMock()
    service.websocket_handler.stream_events_to_websocket = AsyncMock()
    service._resolve_workflow_context = AsyncMock(return_value=(WORKFLOW_ID, WORKFLOW_NAME, "running"))
    return service


def _make_websocket() -> MagicMock:
    ws = MagicMock()
    ws.client = MagicMock()
    ws.client.host = "10.0.0.1"
    ws.client.port = 54321
    return ws


class TestExecutionStreamingAudit:
    """Verify audit events are dispatched during WebSocket streaming lifecycle."""

    @pytest.mark.asyncio
    @patch("syntara.workflows.services.execution_streaming_service.AuditEventDispatcher")
    async def test_dispatches_connected_and_disconnected_on_success(self, mock_dispatcher: MagicMock) -> None:
        service = _make_service()
        ws = _make_websocket()

        await service.stream_events_to_websocket(
            websocket=ws,
            execution_id=EXECUTION_ID,
            replay="0",
            connection_id="conn-1",
            user_id=USER_ID,
            username="admin",
        )

        assert mock_dispatcher.dispatch.call_count == 2

        connected_event = mock_dispatcher.dispatch.call_args_list[0][0][0]
        assert isinstance(connected_event, WebSocketConnectionEvent)
        assert connected_event.action == WebSocketConnectionAction.CONNECTED
        assert connected_event.execution_id == EXECUTION_ID
        assert connected_event.workflow_id == WORKFLOW_ID
        assert connected_event.workflow_name == WORKFLOW_NAME
        assert connected_event.client_ip == "10.0.0.1"
        assert connected_event.connection_id == "conn-1"
        assert connected_event.replay == "0"
        assert connected_event.user_id == USER_ID
        assert connected_event.username == "admin"

        disconnected_event = mock_dispatcher.dispatch.call_args_list[1][0][0]
        assert isinstance(disconnected_event, WebSocketConnectionEvent)
        assert disconnected_event.action == WebSocketConnectionAction.DISCONNECTED
        assert disconnected_event.workflow_id == WORKFLOW_ID
        assert disconnected_event.workflow_name == WORKFLOW_NAME
        assert disconnected_event.duration_ms is not None
        assert disconnected_event.duration_ms >= 0
        assert disconnected_event.close_reason == "normal_close"
        assert disconnected_event.error_type is None
        assert disconnected_event.user_id == USER_ID
        assert disconnected_event.username == "admin"

        call_kwargs = service.websocket_handler.stream_events_to_websocket.call_args[1]
        assert call_kwargs["execution_status"] == "running"

    @pytest.mark.asyncio
    @patch("syntara.workflows.services.execution_streaming_service.AuditEventDispatcher")
    async def test_dispatches_connected_and_error_on_exception(self, mock_dispatcher: MagicMock) -> None:
        service = _make_service()
        ws = _make_websocket()
        service.websocket_handler.stream_events_to_websocket.side_effect = ConnectionResetError("peer gone")

        with pytest.raises(ConnectionResetError):
            await service.stream_events_to_websocket(
                websocket=ws,
                execution_id=EXECUTION_ID,
                connection_id="conn-2",
            )

        assert mock_dispatcher.dispatch.call_count == 2

        connected_event = mock_dispatcher.dispatch.call_args_list[0][0][0]
        assert connected_event.action == WebSocketConnectionAction.CONNECTED

        error_event = mock_dispatcher.dispatch.call_args_list[1][0][0]
        assert isinstance(error_event, WebSocketConnectionEvent)
        assert error_event.action == WebSocketConnectionAction.ERROR
        assert error_event.error_type == "ConnectionResetError"
        assert error_event.close_reason == "peer gone"
        assert error_event.duration_ms is not None

    @pytest.mark.asyncio
    @patch("syntara.workflows.services.execution_streaming_service.AuditEventDispatcher")
    async def test_uses_execution_id_prefix_when_no_connection_id(self, mock_dispatcher: MagicMock) -> None:
        service = _make_service()
        ws = _make_websocket()

        await service.stream_events_to_websocket(
            websocket=ws,
            execution_id=EXECUTION_ID,
        )

        connected_event = mock_dispatcher.dispatch.call_args_list[0][0][0]
        assert connected_event.connection_id == str(EXECUTION_ID)[:8]

    @pytest.mark.asyncio
    @patch("syntara.workflows.services.execution_streaming_service.AuditEventDispatcher")
    async def test_handles_missing_websocket_client(self, mock_dispatcher: MagicMock) -> None:
        service = _make_service()
        ws = MagicMock()
        ws.client = None

        await service.stream_events_to_websocket(
            websocket=ws,
            execution_id=EXECUTION_ID,
            connection_id="conn-3",
        )

        connected_event = mock_dispatcher.dispatch.call_args_list[0][0][0]
        assert connected_event.client_ip == "unknown"

    @pytest.mark.asyncio
    @patch("syntara.workflows.services.execution_streaming_service.AuditEventDispatcher")
    async def test_handles_missing_workflow_context(self, mock_dispatcher: MagicMock) -> None:
        service = _make_service()
        service._resolve_workflow_context = AsyncMock(return_value=(None, "", None))
        ws = _make_websocket()

        await service.stream_events_to_websocket(
            websocket=ws,
            execution_id=EXECUTION_ID,
            connection_id="conn-4",
        )

        connected_event = mock_dispatcher.dispatch.call_args_list[0][0][0]
        assert connected_event.workflow_id is None
        assert connected_event.workflow_name == ""

    @pytest.mark.asyncio
    @patch("syntara.workflows.services.execution_streaming_service.AuditEventDispatcher")
    async def test_dispatches_events_when_workflow_context_raises(self, mock_dispatcher: MagicMock) -> None:
        service = _make_service()
        service._resolve_workflow_context = AsyncMock(side_effect=RuntimeError("db down"))
        ws = _make_websocket()

        await service.stream_events_to_websocket(
            websocket=ws,
            execution_id=EXECUTION_ID,
            connection_id="conn-5",
        )

        assert mock_dispatcher.dispatch.call_count == 2

        connected_event = mock_dispatcher.dispatch.call_args_list[0][0][0]
        assert connected_event.action == WebSocketConnectionAction.CONNECTED
        assert connected_event.workflow_id is None
        assert connected_event.workflow_name == ""

        disconnected_event = mock_dispatcher.dispatch.call_args_list[1][0][0]
        assert disconnected_event.action == WebSocketConnectionAction.DISCONNECTED
