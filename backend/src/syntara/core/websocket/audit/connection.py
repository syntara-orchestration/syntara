"""Audit events for WebSocket connection lifecycle.

Emits audit trail entries for successful connections and authentication
failures on WebSocket endpoints.

Requirement: AAP-79017
"""

from dataclasses import dataclass
from uuid import UUID

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData
from syntara.core.models.principal import PrincipalType


@dataclass
class WebSocketConnectionEvent:
    """Domain event for a successful WebSocket connection."""

    user_id: UUID
    username: str | None
    channel: str
    component: str
    resource_id: str
    client_ip: str
    connection_id: str


@dataclass
class WebSocketAuthFailureEvent:
    """Domain event for a WebSocket authentication or authorization failure."""

    channel: str
    component: str
    client_ip: str
    failure_reason: str
    username: str | None = None
    user_id: UUID | None = None


class WebSocketConnectionHandler(AuditEventHandler[WebSocketConnectionEvent]):
    """Maps a WebSocketConnectionEvent to an AuditEvent."""

    def handle(self, event: WebSocketConnectionEvent) -> AuditEvent:
        """Map a WebSocketConnectionEvent to a normalized AuditEvent."""
        resource_type = event.component
        data = AuditContextData(
            data_type="websocket-connection-context",
            channel=event.channel,
            component=event.component,
            connection_id=event.connection_id,
            client_ip=event.client_ip,
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.INFO,
            event_status=EventStatus.SUCCESS,
            event_action="websocket_connect",
            event_message=f"WebSocket connection established on {event.channel}",
            source_component="syntara.core.websocket",
            structured_data=data,
            actor_id=event.user_id,
            actor_type=PrincipalType.USER,
            actor_username=event.username,
            resource_urn=f"urn:syntara:{resource_type}:{event.resource_id}",
            resource_name=event.channel,
        )


class WebSocketAuthFailureHandler(AuditEventHandler[WebSocketAuthFailureEvent]):
    """Maps a WebSocketAuthFailureEvent to an AuditEvent."""

    def handle(self, event: WebSocketAuthFailureEvent) -> AuditEvent:
        """Map a WebSocketAuthFailureEvent to a normalized AuditEvent."""
        data = AuditContextData(
            data_type="websocket-auth-failure-context",
            channel=event.channel,
            component=event.component,
            client_ip=event.client_ip,
            failure_reason=event.failure_reason,
        )

        return AuditEvent(
            event_category=EventCategory.SECURITY_EVENT,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.ERROR,
            event_action="websocket_auth_failure",
            event_message=f"WebSocket authentication failed on {event.channel}: {event.failure_reason}",
            source_component="syntara.core.websocket",
            structured_data=data,
            actor_id=event.user_id,
            actor_type=PrincipalType.USER if event.user_id else None,
            actor_username=event.username,
        )
