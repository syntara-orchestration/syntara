"""HitL approval telemetry event models.

Defines Segment events for approval requests and decisions.

Requirements: AAP-72358, AAP-72359
"""

from sqlmodel import Field

from syntara.telemetry.events.base import BaseTelemetryEvent


class ApprovalRequestedEvent(BaseTelemetryEvent):
    """Segment event emitted when a HitL approval request is created.

    Event name: ``approval_requested``
    """

    workflow_execution_id: str = Field(description="Workflow execution identifier (UUID v4)")
    approval_node_id: str = Field(description="Activity ID of the approval node in the workflow")


class ApprovalDecidedEvent(BaseTelemetryEvent):
    """Segment event emitted when a HitL approval is approved or rejected.

    Event name: ``approval_decided``
    """

    workflow_execution_id: str = Field(description="Workflow execution identifier (UUID v4)")
    decision: str = Field(description="Decision made: approved or rejected")
    wait_time_ms: int = Field(ge=0, description="Milliseconds between request creation and decision")
