"""ToolDiscoveryEvent and ToolInvocationEvent for tool management operations."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from syntara.agent_orchestrator.audit import extract_actor_fields
from syntara.audit.emitter import AuditActorContext
from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import AuditEvent, EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData

# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------


class ToolDiscoveryStatus(StrEnum):
    """Status of tool discovery operation."""

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class ToolInvocationStatus(StrEnum):
    """Status of tool invocation."""

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ToolDiscoveryEvent:
    """Track tool discovery and synchronization operations.

    Emitted during tool synchronization to track:
    - Discovery of tool providers from Tool Manager
    - Discovery of tools from Tool Manager
    - Filtering decisions (enabled/disabled/missing)
    - Final set of tools provided to LLM
    """

    status: ToolDiscoveryStatus
    session_id: str
    invocation_id: UUID
    execution_id: UUID | None = None
    request_id: UUID | None = None
    actor_context: AuditActorContext | None = None

    # Discovery metrics
    integrations_discovered: int | None = None
    tools_discovered: int | None = None
    tools_enabled: int | None = None
    tools_disabled: int | None = None
    tools_filtered: int | None = None
    tools_provided_to_llm: int | None = None

    # Tool details (for COMPLETED status)
    tool_names: list[str] | None = None
    error_type: str | None = None
    activity_id: str | None = None
    activity_name: str | None = None


@dataclass
class ToolInvocationEvent:
    """Track individual tool invocations by LLM.

    Emitted when:
    - LLM requests a tool call (STARTED)
    - Tool execution completes successfully (COMPLETED)
    - Tool execution fails (FAILED)
    """

    tool_name: str
    status: ToolInvocationStatus
    session_id: str
    invocation_id: UUID
    execution_id: UUID | None = None
    request_id: UUID | None = None
    actor_context: AuditActorContext | None = None

    # Tool execution details
    tool_input: dict[str, Any] | None = None
    tool_output: str | None = None
    error_type: str | None = None
    activity_id: str | None = None
    activity_name: str | None = None


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


class ToolDiscoveryHandler(AuditEventHandler[ToolDiscoveryEvent]):
    """Map ToolDiscoveryEvent to normalized AuditEvent."""

    def handle(self, event: ToolDiscoveryEvent) -> AuditEvent:
        """Map ToolDiscoveryEvent to AuditEvent.

        Args:
            event: Domain event for tool discovery operation

        Returns:
            Normalized audit event

        """
        # Extract actor identity atomically from AuditActorContext
        actor_id, actor_username, actor_type = extract_actor_fields(event.actor_context)

        # Determine severity and status
        status_value = event.status.value

        if event.status == ToolDiscoveryStatus.FAILED:
            severity = EventSeverity.ERROR
            status = EventStatus.ERROR
            message = "Tool discovery and synchronization failed"
            error_type = event.error_type
            error_message = "Look at the Operational Logs for full diagnosis" if error_type is not None else None
        elif event.status == ToolDiscoveryStatus.STARTED:
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = "Tool discovery and synchronization started"
            error_type = None
            error_message = None
        else:  # COMPLETED
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"Tool discovery completed - {event.tools_provided_to_llm or 0} tools provided to LLM"
            error_type = None
            error_message = None

        # Build structured data
        structured_data = AuditContextData(
            data_type="tool_discovery",
            error_type=error_type,
            error_message=error_message,
            session_id=event.session_id,
            invocation_id=event.invocation_id,
            request_id=event.request_id,
            status=status_value,
            integrations_discovered=event.integrations_discovered,
            tools_discovered=event.tools_discovered,
            tools_enabled=event.tools_enabled,
            tools_disabled=event.tools_disabled,
            tools_filtered=event.tools_filtered,
            tools_provided_to_llm=event.tools_provided_to_llm,
            tool_names=event.tool_names,
        )

        return AuditEvent(
            event_category=EventCategory.AGENT_INTERACTION,
            event_severity=severity,
            event_status=status,
            event_action="tool_discovery",
            event_message=message,
            source_component="syntara.agent_orchestrator.tool_manager",
            structured_data=structured_data,
            actor_id=actor_id,
            actor_username=actor_username,
            actor_type=actor_type,
            execution_id=event.execution_id,
            activity_id=event.activity_id,
            resource_urn=f"urn:syntara:invocation:{event.invocation_id}",
            resource_name=event.activity_name,
        )


class ToolInvocationHandler(AuditEventHandler[ToolInvocationEvent]):
    """Map ToolInvocationEvent to normalized AuditEvent."""

    def handle(self, event: ToolInvocationEvent) -> AuditEvent:
        """Map ToolInvocationEvent to AuditEvent.

        Args:
            event: Domain event for tool invocation

        Returns:
            Normalized audit event

        """
        # Extract actor identity atomically from AuditActorContext
        actor_id, actor_username, actor_type = extract_actor_fields(event.actor_context)

        # Determine severity and status
        status_value = event.status.value

        if event.status == ToolInvocationStatus.FAILED:
            severity = EventSeverity.ERROR
            status = EventStatus.ERROR
            message = f"Tool invocation failed: {event.tool_name}"
            error_type = event.error_type
            error_message = "Look at the Operational Logs for full diagnosis" if error_type is not None else None
        elif event.status == ToolInvocationStatus.STARTED:
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"Tool invocation started: {event.tool_name}"
            error_type = None
            error_message = None
        else:  # COMPLETED
            severity = EventSeverity.INFO
            status = EventStatus.SUCCESS
            message = f"Tool invocation completed: {event.tool_name}"
            error_type = None
            error_message = None

        # Build structured data
        structured_data = AuditContextData(
            data_type="tool_invocation",
            error_type=error_type,
            error_message=error_message,
            session_id=event.session_id,
            invocation_id=event.invocation_id,
            request_id=event.request_id,
            tool_name=event.tool_name,
            status=status_value,
            tool_input=event.tool_input,
            tool_output=event.tool_output,
        )

        return AuditEvent(
            event_category=EventCategory.AGENT_INTERACTION,
            event_severity=severity,
            event_status=status,
            event_action="tool_invocation",
            event_message=message,
            source_component="syntara.agent_orchestrator.tool_manager",
            structured_data=structured_data,
            actor_id=actor_id,
            actor_username=actor_username,
            actor_type=actor_type,
            execution_id=event.execution_id,
            activity_id=event.activity_id,
            resource_urn=f"urn:syntara:invocation:{event.invocation_id}",
            resource_name=event.activity_name,
        )
