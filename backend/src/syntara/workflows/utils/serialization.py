"""Serialization utilities for workflow objects."""

from datetime import datetime
from typing import Any
from uuid import UUID

from syntara.workflows.models import WorkflowVersion


class VersionPublishTimestamps:
    """Most recent publish/unpublish timestamps for a version."""

    def __init__(self, published_at: datetime | None = None, unpublished_at: datetime | None = None) -> None:
        """Initialize with optional timestamps."""
        self.published_at = published_at
        self.unpublished_at = unpublished_at


def deserialize_workflow_version(
    version: WorkflowVersion,
    workflow_published_version_id: UUID | None = None,
    ever_published_version_ids: set[UUID] | None = None,
    publish_timestamps: dict[UUID, VersionPublishTimestamps] | None = None,
) -> dict[str, Any]:
    """Convert a WorkflowVersion ORM object to a dict for API responses.

    Status is computed server-side from the events table — not stored on the model:
    - "published": workflow.published_version_id == version.id
    - "previously_published": version has a publish event but is not the current published version
    - "draft": version has never been published

    Args:
        version: WorkflowVersion ORM object from database
        workflow_published_version_id: The parent workflow's published_version_id.
        ever_published_version_ids: Set of version IDs that have at least one
            publish event in workflow_publish_events.
        publish_timestamps: Most recent publish/unpublish timestamps per version ID.

    Returns:
        Dictionary with all version fields including computed status

    """
    if workflow_published_version_id is not None and workflow_published_version_id == version.id:
        status = "published"
    elif ever_published_version_ids and version.id in ever_published_version_ids:
        status = "previously_published"
    else:
        status = "draft"

    ts = publish_timestamps.get(version.id) if publish_timestamps else None

    return {
        "id": version.id,
        "workflow_id": version.workflow_id,
        "version": version.version,
        "schema_version": version.schema_version,
        "workflow_definition": version.workflow_definition,
        "change_description": version.change_description,
        "name": version.name,
        "status": status,
        "last_published_at": ts.published_at if ts else None,
        "last_unpublished_at": ts.unpublished_at
        if ts and ts.unpublished_at and ts.published_at and ts.unpublished_at > ts.published_at
        else None,
        "created_by": version.created_by,
        "created_at": version.created_at,
        "updated_at": version.updated_at,
        "deleted_at": version.deleted_at,
        "deleted_by": version.deleted_by,
    }
