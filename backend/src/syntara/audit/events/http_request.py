"""HTTPRequestEvent and HTTPRequestHandler for HTTP request audit."""

from dataclasses import dataclass, field
from uuid import UUID

from syntara.audit.emitter import AuditActorContext
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    EventStatus,
)
from syntara.audit.models.structured_data import AuditContextData

# ---------------------------------------------------------------------------
# Domain event
# ---------------------------------------------------------------------------


@dataclass
class HTTPRequestEvent:
    """Domain event representing an HTTP request completion.

    Captures the essential information about an HTTP request/response cycle
    for audit purposes, including method, path, status code, and user context.
    """

    method: str
    path: str
    status_code: int
    actor_context: AuditActorContext
    source_component: str = field(default="syntara.audit.middleware")
    query_params: dict[str, str | list[str]] | None = field(default=None)
    workflow_id: UUID | None = field(default=None)
    execution_id: UUID | None = field(default=None)
    activity_id: str | None = field(default=None)
    response_time_ms: int = field(default=0)
    request_payload_size: int = field(default=0)
    interface: str = field(default="api")
    endpoint_template: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class HTTPRequestHandler(AuditEventHandler[HTTPRequestEvent]):
    """Maps an HTTPRequestEvent to a normalized AuditEvent."""

    def handle(self, event: HTTPRequestEvent) -> AuditEvent:
        """Map an HTTPRequestEvent to a normalized AuditEvent.

        Args:
            event: The HTTP request event to handle.

        Returns:
            A normalized AuditEvent for persistence and querying.

        """
        # Extract actor fields from User object
        actor_id = event.actor_context.actor_id
        actor_type = event.actor_context.actor_type
        actor_username = event.actor_context.actor_username

        # Build structured data with request details
        structured_data = AuditContextData(
            data_type="request_completed",
            method=event.method,
            path=event.path,
            status_code=event.status_code,
            query_params=event.query_params,
            response_time_ms=event.response_time_ms,
            request_payload_size=event.request_payload_size,
        )

        # Derive severity and status from HTTP status code
        if event.status_code >= 500:  # noqa: PLR2004
            event_severity = EventSeverity.ERROR
        elif event.status_code >= 400:  # noqa: PLR2004
            event_severity = EventSeverity.WARNING
        else:
            event_severity = EventSeverity.INFO

        event_status = EventStatus.SUCCESS if event.status_code < 400 else EventStatus.ERROR  # noqa: PLR2004

        return AuditEvent(
            event_category=EventCategory.USER_ACTION,
            event_severity=event_severity,
            event_status=event_status,
            event_action="request_completed",
            event_message=f"Request completed: {event.method} {event.path} {event.status_code}",
            source_component=event.source_component,
            structured_data=structured_data,
            actor_id=actor_id,
            actor_type=actor_type,
            actor_username=actor_username,
            workflow_id=event.workflow_id,
            execution_id=event.execution_id,
            activity_id=event.activity_id,
        )
