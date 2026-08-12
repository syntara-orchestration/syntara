"""Unit tests for WebSocket connection lifecycle audit events and handlers."""

# mypy: disable-error-code="attr-defined"

from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.core.models.principal import PrincipalType
from syntara.workflows.audit.websocket_connection import (
    WebSocketConnectionAction,
    WebSocketConnectionEvent,
    WebSocketConnectionHandler,
)

EXECUTION_ID = uuid4()
WORKFLOW_ID = uuid4()
USER_ID = uuid4()
WORKFLOW_NAME = "Deploy to Production"


class TestWebSocketConnectionHandler:
    """Tests for WebSocketConnectionHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(WebSocketConnectionHandler, AuditEventHandler)

    def test_connected_event(self) -> None:
        event = WebSocketConnectionEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            workflow_name=WORKFLOW_NAME,
            action=WebSocketConnectionAction.CONNECTED,
            client_ip="192.168.1.1:54321",
            connection_id="conn-abc",
            replay="0",
            user_id=USER_ID,
            username="admin",
            actor_type=PrincipalType.USER,
        )
        result = WebSocketConnectionHandler().handle(event)

        assert result.event_category == EventCategory.WORKFLOW_EVENT
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "websocket_connected"
        assert result.event_message == f"WebSocket connected: {WORKFLOW_NAME}"
        assert result.source_component == "syntara.workflows.ws"
        assert result.execution_id == EXECUTION_ID
        assert result.workflow_id == WORKFLOW_ID
        assert result.resource_urn == f"urn:syntara:workflow:{WORKFLOW_ID}"
        assert result.resource_name == WORKFLOW_NAME
        assert result.actor_id == USER_ID
        assert result.actor_type == PrincipalType.USER
        assert result.actor_username == "admin"
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "websocket-connection"
        assert result.structured_data.action == "connected"
        assert result.structured_data.client_ip == "192.168.1.1:54321"
        assert result.structured_data.connection_id == "conn-abc"
        assert result.structured_data.replay == "0"

    def test_disconnected_event(self) -> None:
        event = WebSocketConnectionEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            workflow_name=WORKFLOW_NAME,
            action=WebSocketConnectionAction.DISCONNECTED,
            client_ip="10.0.0.1:8080",
            connection_id="conn-xyz",
            duration_ms=15_000,
            close_reason="normal_close",
        )
        result = WebSocketConnectionHandler().handle(event)

        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "websocket_disconnected"
        assert result.event_message == f"WebSocket disconnected: {WORKFLOW_NAME}"
        assert result.resource_urn == f"urn:syntara:workflow:{WORKFLOW_ID}"
        assert result.resource_name == WORKFLOW_NAME
        assert result.structured_data.duration_ms == 15_000
        assert result.structured_data.close_reason == "normal_close"

    def test_error_event(self) -> None:
        event = WebSocketConnectionEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            workflow_name=WORKFLOW_NAME,
            action=WebSocketConnectionAction.ERROR,
            client_ip="10.0.0.1:8080",
            connection_id="conn-err",
            duration_ms=500,
            close_reason="ConnectionResetError",
            error_type="ConnectionResetError",
        )
        result = WebSocketConnectionHandler().handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "websocket_error"
        assert result.structured_data.error_type == "ConnectionResetError"
        assert result.structured_data.duration_ms == 500

    def test_connected_without_replay(self) -> None:
        event = WebSocketConnectionEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            workflow_name=WORKFLOW_NAME,
            action=WebSocketConnectionAction.CONNECTED,
            client_ip="192.168.1.1:54321",
            connection_id="conn-live",
        )
        result = WebSocketConnectionHandler().handle(event)

        assert result.event_action == "websocket_connected"
        assert not hasattr(result.structured_data, "replay") or result.structured_data.replay is None
        assert not hasattr(result.structured_data, "duration_ms") or result.structured_data.duration_ms is None

    def test_actor_fields_absent_when_user_not_provided(self) -> None:
        event = WebSocketConnectionEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            workflow_name=WORKFLOW_NAME,
            action=WebSocketConnectionAction.CONNECTED,
            client_ip="192.168.1.1:54321",
            connection_id="conn-anon",
        )
        result = WebSocketConnectionHandler().handle(event)

        assert result.actor_id is None
        assert result.actor_type is None
        assert result.actor_username is None

    def test_event_message_fallback_when_workflow_unknown(self) -> None:
        event = WebSocketConnectionEvent(
            execution_id=EXECUTION_ID,
            workflow_id=None,
            workflow_name="",
            action=WebSocketConnectionAction.CONNECTED,
            client_ip="192.168.1.1:54321",
            connection_id="conn-unknown",
        )
        result = WebSocketConnectionHandler().handle(event)

        assert result.event_message == f"WebSocket connected: execution:{EXECUTION_ID}"
        assert result.resource_urn is None
        assert result.resource_name == ""
