"""Form-trigger telemetry event models."""

from sqlmodel import Field

from syntara.telemetry.events.base import BaseTelemetryEvent


class FormTriggerSubmittedEvent(BaseTelemetryEvent):
    """Segment event emitted when a form-trigger submission starts an execution.

    Event name: ``form_trigger_submitted``
    """

    workflow_execution_id: str = Field(description="Workflow execution identifier (UUID v4)")
    trigger_node_id: str = Field(description="Activity ID of the form trigger node")
    field_count: int = Field(
        ge=0,
        description="Number of form fields",
    )
    field_types: list[str] = Field(description="Sorted unique field types used in the form")
