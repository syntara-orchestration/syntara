"""InvocationLifecycleEvent and InvocationLifecycleHandler for invocation state tracking."""

from dataclasses import dataclass
from uuid import UUID

from syntara.agent_orchestrator.audit import extract_actor_fields
from syntara.agent_orchestrator.models import InvocationStatus
from syntara.audit.emitter import AuditActorContext
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData

# ---------------------------------------------------------------------------
# Domain event
# ---------------------------------------------------------------------------


@dataclass
class InvocationLifecycleEvent:
    """Track high-level invocation state transitions.

    Emitted when invocation status changes (running, completed, failed, cancelled).
    """

    status: InvocationStatus
    session_id: str
    invocation_id: UUID
    execution_id: UUID | None = None
    request_id: UUID | None = None
    actor_context: AuditActorContext | None = None
    error_type: str | None = None

    # Metadata
    model_name: str | None = None
    activity_id: str | None = None
    activity_name: str | None = None


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

_STATUS_MESSAGE: dict[InvocationStatus, str] = {
    InvocationStatus.CREATED: "created",
    InvocationStatus.RUNNING: "running",
    InvocationStatus.PAUSED: "paused",
    InvocationStatus.CANCELLED: "cancelled",
    InvocationStatus.COMPLETED: "completed",
    InvocationStatus.FAILED: "failed",
}


class InvocationLifecycleHandler(AuditEventHandler[InvocationLifecycleEvent]):
    """Map InvocationLifecycleEvent to normalized AuditEvent."""

    def handle(self, event: InvocationLifecycleEvent) -> AuditEvent:
        """Map InvocationLifecycleEvent to AuditEvent.

        Args:
            event: Domain event for invocation lifecycle

        Returns:
            Normalized audit event

        """
        # Extract actor identity atomically from AuditActorContext
        actor_id, actor_username, actor_type = extract_actor_fields(event.actor_context)

        # Determine severity and status based on invocation status
        if event.status == InvocationStatus.FAILED:
            severity = EventSeverity.ERROR
            status = EventStatus.ERROR
            error_type = event.error_type
            error_message = "Look at the Operational Logs for full diagnosis" if error_type is not None else None
        else:
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            error_type = None
            error_message = None

        # Build structured data
        structured_data = AuditContextData(
            data_type="invocation_lifecycle",
            error_type=error_type,
            error_message=error_message,
            session_id=event.session_id,
            invocation_id=event.invocation_id,
            request_id=event.request_id,
            invocation_status=event.status,
            model_name=event.model_name,
        )

        return AuditEvent(
            event_category=EventCategory.AGENT_INTERACTION,
            event_severity=severity,
            event_status=status,
            event_action=f"invocation_{event.status.lower()}",
            event_message=f"Invocation {_STATUS_MESSAGE.get(event.status, 'succeeded')}",
            source_component="syntara.agent_orchestrator.executor",
            structured_data=structured_data,
            actor_id=actor_id,
            actor_username=actor_username,
            actor_type=actor_type,
            execution_id=event.execution_id,
            activity_id=event.activity_id,
            resource_urn=f"urn:syntara:invocation:{event.invocation_id}",
            resource_name=event.activity_name,
        )
