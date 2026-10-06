"""Workflow stall telemetry event model.

Emitted when a workflow step exceeds its expected duration threshold (SDP R23/AC-13).
"""

from __future__ import annotations

from sqlmodel import Field

from syntara.telemetry.events.base import BaseTelemetryEvent


class WorkflowStallEvent(BaseTelemetryEvent):
    """Telemetry event emitted when a workflow step stalls (exceeds expected duration).

    Anonymized event following SDP R23/AC-13 requirements. Does not include
    workflow/execution/user identifiers or other sensitive data.

    Attributes:
        execution_mode: Execution mode (e.g., 'standard', 'test', 'debug').
        stalled_step_type: Node type of the stalled step (e.g., 'http_request', 'llm').

    """

    execution_mode: str = Field(
        description="Execution mode (e.g., 'standard', 'test', 'debug')",
    )
    stalled_step_type: str = Field(
        description="Node type of the stalled step",
    )
