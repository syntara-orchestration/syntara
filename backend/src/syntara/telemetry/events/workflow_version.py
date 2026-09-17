"""Workflow version telemetry event models.

Emitted when workflow versions are created, restored, published, unpublished,
or exported, enabling tracking of workflow evolution frequency, publishing
patterns, rollback rates, and export adoption.
"""

from __future__ import annotations

from uuid import UUID  # noqa: TC003

from sqlmodel import Field

from syntara.telemetry.events.base import BaseTelemetryEvent

_WORKFLOW_NAME_DESC = "Human-readable workflow name"
_WORKFLOW_ID_DESC = "Unique workflow identifier (UUID v4)"
_USER_ID_HASH_DESC = "HMAC-SHA256 digest of the acting user's UUID (per-installation salt)"


class WorkflowVersionCreatedEvent(BaseTelemetryEvent):
    """Telemetry event emitted when a new workflow version is created.

    Attributes:
        workflow_id: Unique workflow identifier (UUID v4 format).
        version: Sequential version number within the workflow.
        user_id_hash: Anonymized identifier of the user who saved the version.

    """

    workflow_id: UUID = Field(description=_WORKFLOW_ID_DESC)
    version: int = Field(ge=1, description="Sequential version number")
    user_id_hash: str | None = Field(default=None, description=_USER_ID_HASH_DESC)


class WorkflowVersionRestoredEvent(BaseTelemetryEvent):
    """Telemetry event emitted when a workflow version is restored.

    Attributes:
        workflow_id: Unique workflow identifier (UUID v4 format).
        restored_from_version: Version number that was restored from.
        new_version: Version number of the newly created draft.

    """

    workflow_id: UUID = Field(description=_WORKFLOW_ID_DESC)
    restored_from_version: int = Field(ge=1, description="Source version restored from")
    new_version: int = Field(ge=1, description="New draft version created by restore")


class WorkflowVersionPublishedEvent(BaseTelemetryEvent):
    """Telemetry event emitted when a workflow version is published."""

    workflow_id: UUID = Field(description=_WORKFLOW_ID_DESC)
    version: int = Field(ge=1, description="Version number published")
    workflow_name: str = Field(description=_WORKFLOW_NAME_DESC)
    published_version_id: UUID | None = Field(
        default=None, description="Published workflow version identifier (UUID v4)"
    )
    project_id: UUID | None = Field(default=None, description="Project identifier")
    user_id_hash: str | None = Field(default=None, description=_USER_ID_HASH_DESC)
    error_type: str | None = Field(default=None, description="Error type if operation failed")


class WorkflowVersionUnpublishedEvent(BaseTelemetryEvent):
    """Telemetry event emitted when a workflow is unpublished."""

    workflow_id: UUID = Field(description=_WORKFLOW_ID_DESC)
    version: int = Field(ge=1, description="Version number that was unpublished")
    workflow_name: str = Field(description=_WORKFLOW_NAME_DESC)
    project_id: UUID | None = Field(default=None, description="Project identifier")
    error_type: str | None = Field(default=None, description="Error type if operation failed")


class WorkflowVersionExportedEvent(BaseTelemetryEvent):
    """Telemetry event emitted when a workflow version is exported."""

    workflow_id: UUID = Field(description=_WORKFLOW_ID_DESC)
    version: int = Field(ge=1, description="Version number exported")
    workflow_name: str = Field(description=_WORKFLOW_NAME_DESC)
