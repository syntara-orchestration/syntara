"""AgentExecutionEvent and AgentExecutionHandler for agent lifecycle tracking."""

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


class AgentExecutionStatus(StrEnum):
    """Status of agent execution."""

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentExecutionEvent:
    """Track agent lifecycle and routing decisions.

    Emitted when an agent starts/completes/fails execution.
    """

    agent_type: str  # "orchestrator", "generic_agent"
    status: AgentExecutionStatus
    session_id: str
    invocation_id: UUID
    execution_id: UUID | None = None
    request_id: UUID | None = None
    actor_context: AuditActorContext | None = None
    error_type: str | None = None

    # Orchestrator-specific fields
    context_applied: bool | None = None
    grounding_score: float | None = None
    routed_to_agent: str | None = None


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class AgentExecutionHandler(AuditEventHandler[AgentExecutionEvent]):
    """Map AgentExecutionEvent to normalized AuditEvent."""

    def handle(self, event: AgentExecutionEvent) -> AuditEvent:
        """Map AgentExecutionEvent to AuditEvent.

        Args:
            event: Domain event for agent execution

        Returns:
            Normalized audit event

        """
        # Extract actor identity atomically from AuditActorContext
        actor_id, actor_username, actor_type = extract_actor_fields(event.actor_context)

        # Determine severity and status
        if event.status == AgentExecutionStatus.FAILED:
            severity = EventSeverity.ERROR
            status = EventStatus.ERROR
            message = f"Agent {event.agent_type} failed"
            error_type = event.error_type
            error_message = "Look at the Operational Logs for full diagnosis" if error_type is not None else None
        else:
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"Agent {event.agent_type} {event.status.value}"
            error_type = None
            error_message = None

        # Build structured data
        structured_data = AuditContextData(
            data_type="agent_execution",
            error_type=error_type,
            error_message=error_message,
            agent_type=event.agent_type,
            status=event.status.value,
            session_id=event.session_id,
            invocation_id=event.invocation_id,
            request_id=event.request_id,
            context_applied=event.context_applied,
            grounding_score=event.grounding_score,
            routed_to_agent=event.routed_to_agent,
        )

        return AuditEvent(
            event_category=EventCategory.AGENT_INTERACTION,
            event_severity=severity,
            event_status=status,
            event_action=f"agent_{event.status.value}",
            event_message=message,
            source_component=f"syntara.agent_orchestrator.agents.{event.agent_type}",
            structured_data=structured_data,
            actor_id=actor_id,
            actor_username=actor_username,
            actor_type=actor_type,
            execution_id=event.execution_id,
            resource_urn=f"urn:syntara:invocation:{event.invocation_id}",
            resource_name=event.agent_type,
        )
