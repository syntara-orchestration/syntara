"""WebSocket connection lifecycle — domain event and audit handler.

Fired by ExecutionStreamingService when a WebSocket client connects to or
disconnects from an execution event stream.  Captures connection metadata
(client IP, execution ID, duration, close reason) and actor identity for
audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData

if TYPE_CHECKING:
    from uuid import UUID

    from syntara.core.models.principal import PrincipalType


class WebSocketConnectionAction(StrEnum):
    """Actions in a WebSocket connection lifecycle."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class WebSocketConnectionEvent:
    """Domain event fired on WebSocket connection lifecycle transitions."""

    execution_id: UUID
    workflow_id: UUID | None
    workflow_name: str
    action: WebSocketConnectionAction
    client_ip: str
    connection_id: str
    duration_ms: int | None = field(default=None)
    close_reason: str | None = field(default=None)
    error_type: str | None = field(default=None)
    replay: str | None = field(default=None)
    user_id: UUID | None = field(default=None)
    username: str | None = field(default=None)
    actor_type: PrincipalType | None = field(default=None)


class WebSocketConnectionHandler(AuditEventHandler[WebSocketConnectionEvent]):
    """Maps a WebSocketConnectionEvent to an AuditEvent."""

    def handle(self, event: WebSocketConnectionEvent) -> AuditEvent:
        """Map a WebSocketConnectionEvent to a normalized AuditEvent."""
        is_error = event.action == WebSocketConnectionAction.ERROR

        data = AuditContextData(
            data_type="websocket-connection",
            action=event.action,
            client_ip=event.client_ip,
            connection_id=event.connection_id,
        )
        if event.duration_ms is not None:
            data.duration_ms = event.duration_ms
        if event.close_reason is not None:
            data.close_reason = event.close_reason
        if event.error_type is not None:
            data.error_type = event.error_type
        if event.replay is not None:
            data.replay = event.replay

        resource_urn = f"urn:syntara:workflow:{event.workflow_id}" if event.workflow_id else None
        display_name = event.workflow_name or f"execution:{event.execution_id}"

        return AuditEvent(
            event_category=EventCategory.WORKFLOW_EVENT,
            event_severity=EventSeverity.ERROR if is_error else EventSeverity.INFO,
            event_status=EventStatus.ERROR if is_error else EventStatus.SUCCESS,
            event_action=f"websocket_{event.action}",
            event_message=f"WebSocket {event.action}: {display_name}",
            source_component="syntara.workflows.ws",
            structured_data=data,
            execution_id=event.execution_id,
            workflow_id=event.workflow_id,
            resource_urn=resource_urn,
            resource_name=event.workflow_name,
            actor_id=event.user_id,
            actor_type=event.actor_type or None,
            actor_username=event.username,
        )
