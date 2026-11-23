"""Response models for sub-workflow invocation schema discovery."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlmodel import Field, SQLModel


class WorkflowInvocationTriggerSchema(SQLModel):
    """Invocation contract declared by one Subworkflow Trigger."""

    trigger_node_id: str = Field(description="ID of the Subworkflow Trigger that declares these schemas.")
    name: str | None = Field(default=None, description="Optional display name of the Subworkflow Trigger.")
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema describing the inputs accepted by this trigger.",
    )
    output_schema: dict[str, Any] | None = Field(
        default=None,
        description=(
            "JSON Schema for the public outputs exposed to parent workflows by this trigger. Parent workflows "
            "consume these declared fields; internal child step outputs are not exposed. A null value means this "
            "trigger has no declared output schema."
        ),
    )


class WorkflowInvocationSchemaRead(SQLModel):
    """Invocation schemas from the latest published version of a workflow."""

    workflow_id: UUID = Field(description="ID of the workflow whose invocation contract is returned.")
    published_version_id: UUID = Field(
        description="ID of the latest published workflow version used for this response."
    )
    published_version: int = Field(description="Version number of the latest published workflow version.")
    published_version_name: str | None = Field(default=None, description="Optional name of the published version.")
    published_version_created_at: datetime | None = Field(
        default=None,
        description="Creation time of the published version, in UTC.",
    )
    is_eligible: bool = Field(
        description="Whether the published workflow has at least one Subworkflow Trigger available for invocation."
    )
    triggers: list[WorkflowInvocationTriggerSchema] = Field(
        description="Subworkflow Trigger schemas from the published version; empty when the workflow is not eligible."
    )
