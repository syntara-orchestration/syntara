"""ContextIntegrationEvent and ContextIntegrationHandler for context manager tracking."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from syntara.agent_orchestrator.audit import extract_actor_fields
from syntara.audit.emitter import AuditActorContext
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData

# ---------------------------------------------------------------------------
# Domain event
# ---------------------------------------------------------------------------


class ContextIntegrationStatus(StrEnum):
    """Status of context integration."""

    SUCCESS = "success"
    TIMEOUT = "timeout"
    FALLBACK = "fallback"


@dataclass
class ContextIntegrationEvent:
    """Track context manager integration.

    Emitted when context manager is called to enhance prompts.
    """

    status: ContextIntegrationStatus
    session_id: str
    invocation_id: UUID
    execution_id: UUID | None = None
    request_id: UUID | None = None
    grounding_score: float | None = None
    citations_count: int | None = None
    actor_context: AuditActorContext | None = None
    activity_id: str | None = None
    activity_name: str | None = None


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

_STATUS_MESSAGE: dict[ContextIntegrationStatus, str] = {
    ContextIntegrationStatus.SUCCESS: "succeeded",
    ContextIntegrationStatus.TIMEOUT: "timed-out",
    ContextIntegrationStatus.FALLBACK: "fell back to original prompt",
}


class ContextIntegrationHandler(AuditEventHandler[ContextIntegrationEvent]):
    """Map ContextIntegrationEvent to normalized AuditEvent."""

    def handle(self, event: ContextIntegrationEvent) -> AuditEvent:
        """Map ContextIntegrationEvent to AuditEvent.

        Args:
            event: Domain event for context integration

        Returns:
            Normalized audit event

        """
        # Extract actor identity atomically from AuditActorContext
        actor_id, actor_username, actor_type = extract_actor_fields(event.actor_context)

        # Determine severity and status
        if event.status in (ContextIntegrationStatus.TIMEOUT, ContextIntegrationStatus.FALLBACK):
            severity = EventSeverity.WARNING
            status = EventStatus.SUCCESS
        else:
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS

        # Build structured data
        structured_data = AuditContextData(
            data_type="context_integration",
            error_type=None,
            error_message=None,
            status=event.status.value,
            session_id=event.session_id,
            invocation_id=event.invocation_id,
            request_id=event.request_id,
            grounding_score=event.grounding_score,
            citations_count=event.citations_count,
        )

        return AuditEvent(
            event_category=EventCategory.AGENT_INTERACTION,
            event_severity=severity,
            event_status=status,
            event_action="context_integration",
            event_message=f"Context integration {_STATUS_MESSAGE.get(event.status, 'succeeded')}",
            source_component="syntara.agent_orchestrator.agents.orchestrator",
            structured_data=structured_data,
            actor_id=actor_id,
            actor_username=actor_username,
            actor_type=actor_type,
            execution_id=event.execution_id,
            activity_id=event.activity_id,
            resource_urn=f"urn:syntara:invocation:{event.invocation_id}",
            resource_name=event.activity_name,
        )
