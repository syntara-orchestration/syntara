"""ContextPlanningEvent and CancellationEvent for context manager operations."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from syntara.agent_orchestrator.audit import extract_actor_fields
from syntara.audit.emitter import AuditActorContext
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData

# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------


class ContextPlanningPhase(StrEnum):
    """Phases of context planning workflow."""

    RETRIEVAL = "retrieval"
    ASSEMBLY = "assembly"
    COMPRESSION = "compression"


class ContextPlanningStatus(StrEnum):
    """Status of context planning operation."""

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ContextPlanningEvent:
    """Track context manager planning operations.

    Emitted for each phase of the context planning workflow:
    - Retrieval: Document retrieval from storage backends
    - Assembly: Context package assembly with token management
    - Compression: Document compression during assembly retry loops
    """

    phase: ContextPlanningPhase
    status: ContextPlanningStatus
    session_id: str
    invocation_id: UUID
    execution_id: UUID | None = None
    request_id: UUID | None = None
    actor_context: AuditActorContext | None = None

    # Optional context
    document_count: int | None = None
    error_type: str | None = None
    activity_id: str | None = None
    activity_name: str | None = None


@dataclass
class CancellationEvent:
    """Track detected invocation cancellations during context planning.

    Emitted when context manager detects that an invocation has been cancelled
    during expensive operations (retrieval, assembly).
    """

    phase: ContextPlanningPhase
    session_id: str
    invocation_id: UUID
    execution_id: UUID | None = None
    request_id: UUID | None = None
    actor_context: AuditActorContext | None = None
    activity_id: str | None = None
    activity_name: str | None = None


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


class ContextPlanningHandler(AuditEventHandler[ContextPlanningEvent]):
    """Map ContextPlanningEvent to normalized AuditEvent."""

    def handle(self, event: ContextPlanningEvent) -> AuditEvent:
        """Map ContextPlanningEvent to AuditEvent.

        Args:
            event: Domain event for context planning operation

        Returns:
            Normalized audit event

        """
        # Extract actor identity atomically from AuditActorContext
        actor_id, actor_username, actor_type = extract_actor_fields(event.actor_context)

        # Determine severity and status
        phase = event.phase.value
        status_value = event.status.value

        if event.status == ContextPlanningStatus.FAILED:
            severity = EventSeverity.ERROR
            status = EventStatus.ERROR
            message = f"Context planning {phase} phase failed"
            error_type = event.error_type
            error_message = "Look at the Operational Logs for full diagnosis" if error_type is not None else None
        elif event.status == ContextPlanningStatus.CANCELLED:
            severity = EventSeverity.WARNING
            status = EventStatus.SUCCESS
            message = f"Context planning {phase} phase cancelled"
            error_type = None
            error_message = None
        elif event.status == ContextPlanningStatus.STARTED:
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"Context planning {phase} phase started"
            error_type = None
            error_message = None
        else:  # COMPLETED
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"Context planning {phase} phase completed"
            error_type = None
            error_message = None

        # Build structured data
        structured_data = AuditContextData(
            data_type="context_planning",
            error_type=error_type,
            error_message=error_message,
            session_id=event.session_id,
            invocation_id=event.invocation_id,
            request_id=event.request_id,
            phase=event.phase.value,
            status=status_value,
            document_count=event.document_count,
        )

        return AuditEvent(
            event_category=EventCategory.AGENT_INTERACTION,
            event_severity=severity,
            event_status=status,
            event_action="context_planning",
            event_message=message,
            source_component="syntara.agent_orchestrator.context_manager",
            structured_data=structured_data,
            actor_id=actor_id,
            actor_username=actor_username,
            actor_type=actor_type,
            execution_id=event.execution_id,
            activity_id=event.activity_id,
            resource_urn=f"urn:syntara:invocation:{event.invocation_id}",
            resource_name=event.activity_name,
        )


class CancellationHandler(AuditEventHandler[CancellationEvent]):
    """Map CancellationEvent to normalized AuditEvent."""

    def handle(self, event: CancellationEvent) -> AuditEvent:
        """Map CancellationEvent to AuditEvent.

        Args:
            event: Domain event for detected cancellation

        Returns:
            Normalized audit event

        """
        # Extract actor identity atomically from AuditActorContext
        actor_id, actor_username, actor_type = extract_actor_fields(event.actor_context)

        # Build message
        phase = event.phase.value
        message = f"Invocation cancelled during {phase} phase"

        # Build structured data
        structured_data = AuditContextData(
            data_type="cancellation",
            session_id=event.session_id,
            invocation_id=event.invocation_id,
            request_id=event.request_id,
            phase=event.phase.value,
        )

        return AuditEvent(
            event_category=EventCategory.AGENT_INTERACTION,
            event_severity=EventSeverity.WARNING,
            event_status=EventStatus.SUCCESS,
            event_action="cancellation",
            event_message=message,
            source_component="syntara.agent_orchestrator.context_manager",
            structured_data=structured_data,
            actor_id=actor_id,
            actor_username=actor_username,
            actor_type=actor_type,
            execution_id=event.execution_id,
            activity_id=event.activity_id,
            resource_urn=f"urn:syntara:invocation:{event.invocation_id}",
            resource_name=event.activity_name,
        )
