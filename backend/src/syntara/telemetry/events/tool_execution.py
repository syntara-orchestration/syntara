"""Tool execution telemetry event model and builder.

Defines the event emitted for each tool execution reaching a terminal state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID  # noqa: TC003

from sqlmodel import Field

from syntara.telemetry.events.base import BaseTelemetryEvent
from syntara.tool_manager.models.tool_execution import ToolExecutionStatus  # noqa: TC001


class ToolExecutionEvent(BaseTelemetryEvent):
    """Telemetry event emitted for each tool execution reaching a terminal state."""

    namespaced_name: str = Field(description="Tool namespaced name (e.g., mcp::get_greeting)")
    status: ToolExecutionStatus = Field(description="Execution status: success, error, timeout")
    duration_ms: int = Field(ge=0, description="Execution duration in milliseconds")
    workflow_execution_id: UUID | None = Field(
        default=None,
        description="Parent workflow execution identifier (UUID v4)",
    )


@dataclass
class ToolExecutedEvent:
    """Domain event fired when a tool execution reaches a terminal state."""

    namespaced_name: str
    status: ToolExecutionStatus
    duration_ms: int
    execution_id: UUID | None = field(default=None)
