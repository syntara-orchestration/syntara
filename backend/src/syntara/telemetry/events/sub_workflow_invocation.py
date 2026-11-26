"""Segment telemetry event for a sub-workflow invocation."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import StrEnum
from uuid import UUID  # noqa: TC003

from sqlmodel import Field

from syntara.telemetry.events.base import BaseTelemetryEvent
from syntara.workflows.workflow_engine.models.workflow_definition import WorkflowTerminalStatus  # noqa: TC001


class SubWorkflowInvocationMode(StrEnum):
    """Invocation modes; Embed is reserved, while paste telemetry uses a separate event."""

    REFERENCE = "reference"
    EMBED = "embed"


class SubWorkflowInvocationEvent(BaseTelemetryEvent):
    """One terminal event for a child execution started by a parent Sub-workflow node.

    ``installation_anon_id`` uses the existing anonymized installation-scoped Segment identity.
    ``child_execution_duration_ms`` measures from the Temporal workflow-start event
    to terminal completion. ``invocation_duration_ms`` starts when the setup activity
    begins and includes child setup and execution.
    Percentiles are calculated by the downstream analytics destination from these
    per-invocation samples.
    """

    parent_execution_id: UUID = Field(description="Parent workflow execution identifier")
    parent_workflow_id: UUID = Field(description="Parent workflow identifier")
    parent_workflow_name: str = Field(description="Parent workflow name")
    parent_node_id: str = Field(description="Sub-workflow node identifier in the parent")
    child_execution_id: UUID = Field(description="Child workflow execution identifier")
    child_workflow_id: UUID = Field(description="Child workflow identifier")
    child_workflow_name: str = Field(description="Child workflow name")
    invocation_mode: SubWorkflowInvocationMode = Field(
        description="Invocation mode. Current backend events use reference."
    )
    status: WorkflowTerminalStatus = Field(description="Terminal child workflow status")
    invocation_duration_ms: int | None = Field(
        default=None,
        ge=0,
        description="Sub-workflow setup activity start to child terminal completion duration in milliseconds",
    )
    child_execution_duration_ms: int | None = Field(
        default=None,
        ge=0,
        description="Child Temporal workflow start to terminal completion duration in milliseconds",
    )
    installation_anon_id: str = Field(
        min_length=1,
        description="Anonymized installation identifier used for aggregation",
    )
    occurred_at: datetime = Field(description="Time the child workflow execution reached a terminal state")
