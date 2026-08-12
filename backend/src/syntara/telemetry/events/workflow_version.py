"""Workflow version telemetry event models.

Emitted when workflow versions are created, restored, published, unpublished,
or exported, enabling tracking of workflow evolution frequency, publishing
patterns, rollback rates, and export adoption.
"""

from __future__ import annotations

from sqlmodel import Field

from syntara.telemetry.events.base import BaseTelemetryEvent

_WORKFLOW_NAME_DESC = "Human-readable workflow name"
_WORKFLOW_ID_DESC = "Unique workflow identifier (UUID v4)"


class WorkflowVersionCreatedEvent(BaseTelemetryEvent):
    """Telemetry event emitted when a new workflow version is created.

    Attributes:
        workflow_id: Unique workflow identifier (UUID v4 format).
        version: Sequential version number within the workflow.

    """

    workflow_id: str = Field(description=_WORKFLOW_ID_DESC)
    version: int = Field(ge=1, description="Sequential version number")


class WorkflowVersionRestoredEvent(BaseTelemetryEvent):
    """Telemetry event emitted when a workflow version is restored.

    Attributes:
        workflow_id: Unique workflow identifier (UUID v4 format).
        restored_from_version: Version number that was restored from.
        new_version: Version number of the newly created draft.

    """

    workflow_id: str = Field(description=_WORKFLOW_ID_DESC)
    restored_from_version: int = Field(ge=1, description="Source version restored from")
    new_version: int = Field(ge=1, description="New draft version created by restore")


class WorkflowVersionPublishedEvent(BaseTelemetryEvent):
    """Telemetry event emitted when a workflow version is published."""

    workflow_id: str = Field(description=_WORKFLOW_ID_DESC)
    version: int = Field(ge=1, description="Version number published")
    workflow_name: str = Field(description=_WORKFLOW_NAME_DESC)
    project_id: str | None = Field(default=None, description="Project identifier")
    error_type: str | None = Field(default=None, description="Error type if operation failed")


class WorkflowVersionUnpublishedEvent(BaseTelemetryEvent):
    """Telemetry event emitted when a workflow is unpublished."""

    workflow_id: str = Field(description=_WORKFLOW_ID_DESC)
    version: int = Field(ge=1, description="Version number that was unpublished")
    workflow_name: str = Field(description=_WORKFLOW_NAME_DESC)
    project_id: str | None = Field(default=None, description="Project identifier")
    error_type: str | None = Field(default=None, description="Error type if operation failed")


class WorkflowVersionExportedEvent(BaseTelemetryEvent):
    """Telemetry event emitted when a workflow version is exported."""

    workflow_id: str = Field(description=_WORKFLOW_ID_DESC)
    version: int = Field(ge=1, description="Version number exported")
    workflow_name: str = Field(description=_WORKFLOW_NAME_DESC)
