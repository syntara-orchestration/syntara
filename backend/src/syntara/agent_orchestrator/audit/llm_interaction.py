"""LLMInteractionEvent and LLMInteractionHandler for LLM call tracking."""

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


class LLMInteractionType(StrEnum):
    """Type of LLM interaction."""

    STANDARD = "standard"
    STRUCTURED_OUTPUT = "structured_output"
    EXTRACTION = "extraction"


class LLMInteractionStatus(StrEnum):
    """Status of LLM interaction."""

    SUCCESS = "success"
    EMPTY_RESPONSE = "empty_response"
    ERROR = "error"


@dataclass
class LLMInteractionEvent:
    """Track LLM calls with business context.

    Emitted for each LLM interaction (standard, structured output, extraction).
    """

    interaction_type: LLMInteractionType
    status: LLMInteractionStatus
    model_name: str
    session_id: str
    invocation_id: UUID
    execution_id: UUID | None = None
    request_id: UUID | None = None
    actor_context: AuditActorContext | None = None
    error_type: str | None = None

    # Optional fields
    tools_available: int | None = None
    tool_calls_made: int | None = None
    response_schema_provided: bool = False
    fallback_strategy_used: str | None = None
    activity_id: str | None = None
    activity_name: str | None = None


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class LLMInteractionHandler(AuditEventHandler[LLMInteractionEvent]):
    """Map LLMInteractionEvent to normalized AuditEvent."""

    def handle(self, event: LLMInteractionEvent) -> AuditEvent:
        """Map LLMInteractionEvent to AuditEvent.

        Args:
            event: Domain event for LLM interaction

        Returns:
            Normalized audit event

        """
        # Extract actor identity atomically from AuditActorContext
        actor_id, actor_username, actor_type = extract_actor_fields(event.actor_context)

        # Determine severity and status
        interaction_type = event.interaction_type.value
        if event.status == LLMInteractionStatus.ERROR:
            severity = EventSeverity.ERROR
            status = EventStatus.ERROR
            message = f"LLM interaction failed ({interaction_type})"
            error_type = event.error_type
            error_message = "Look at the Operational Logs for full diagnosis" if error_type is not None else None
        elif event.status == LLMInteractionStatus.EMPTY_RESPONSE:
            severity = EventSeverity.WARNING
            status = EventStatus.SUCCESS
            message = f"LLM returned empty response ({interaction_type})"
            error_type = None
            error_message = None
        else:
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"LLM interaction completed ({interaction_type})"
            error_type = None
            error_message = None

        # Build structured data
        structured_data = AuditContextData(
            data_type="llm_interaction",
            error_type=error_type,
            error_message=error_message,
            session_id=event.session_id,
            invocation_id=event.invocation_id,
            request_id=event.request_id,
            interaction_type=event.interaction_type,
            model_name=event.model_name,
            status=event.status.value,
            tools_available=event.tools_available,
            tool_calls_made=event.tool_calls_made,
            response_schema_provided=event.response_schema_provided,
            fallback_strategy_used=event.fallback_strategy_used,
        )

        return AuditEvent(
            event_category=EventCategory.LLM_INTERACTION,
            event_severity=severity,
            event_status=status,
            event_action="llm_call",
            event_message=message,
            source_component="syntara.agent_orchestrator.agents.generic",
            structured_data=structured_data,
            actor_id=actor_id,
            actor_username=actor_username,
            actor_type=actor_type,
            execution_id=event.execution_id,
            activity_id=event.activity_id,
            resource_urn=f"urn:syntara:invocation:{event.invocation_id}",
            resource_name=event.activity_name,
        )
