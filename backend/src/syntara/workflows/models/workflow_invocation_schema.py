"""Response models for sub-workflow invocation schema discovery."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlmodel import Field, SQLModel


class WorkflowInvocationTriggerSchema(SQLModel):
    """One dedicated Subworkflow Trigger available for Reference mode."""

    trigger_node_id: str
    name: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)


class WorkflowInvocationSchemaRead(SQLModel):
    """Published invocation schemas for a child workflow."""

    workflow_id: UUID
    published_version_id: UUID
    published_version: int
    published_version_name: str | None = None
    published_version_created_at: datetime | None = None
    is_eligible: bool
    triggers: list[WorkflowInvocationTriggerSchema]
