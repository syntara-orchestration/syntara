"""Form prompt telemetry event models.

Defines Segment events for form prompt submissions.
"""

from sqlmodel import Field

from syntara.telemetry.events.base import BaseTelemetryEvent


class FormPromptSubmittedEvent(BaseTelemetryEvent):
    """Segment event emitted when a form prompt is submitted.

    Event name: ``form_prompt_submitted``
    """

    workflow_execution_id: str = Field(description="Workflow execution identifier (UUID v4)")
    prompt_node_id: str = Field(description="Activity ID of the form prompt node in the workflow")
    wait_time_ms: int = Field(ge=0, description="Milliseconds between prompt creation and submission")
    field_count: int = Field(ge=0, description="Number of fields in the submitted form")
    outcome: str = Field(description="Outcome value sent to workflow (e.g., 'submitted')")
