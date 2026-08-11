"""WorkflowPublishEvent model for tracking publish/unpublish lifecycle.

Each publish or unpublish action creates an immutable event record,
providing a complete audit trail of the publish lifecycle for any version.
"""

from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from sqlmodel import Field, Index

from syntara.core.models.base import BaseResource
from syntara.core.models.base.base_resource import AuditLevel
from syntara.core.utils.sqlmodel import postgres_enum_column


class PublishAction(StrEnum):
    """Actions in the publish lifecycle."""

    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"


class WorkflowPublishEvent(BaseResource, table=True):
    """Immutable event recording a publish or unpublish action.

    Attributes:
        id: Primary key UUID (from BaseResource)
        created_at: When the action occurred (from BaseResource)
        workflow_id: Parent workflow
        version_id: Which version was published/unpublished
        action: Whether this was a publish or unpublish
        actor_id: Who performed the action

    """

    __tablename__ = "workflow_publish_events"
    __auditable__: ClassVar[AuditLevel] = AuditLevel.NONE

    workflow_id: UUID = Field(
        foreign_key="workflows.id",
        ondelete="CASCADE",
        description="Parent workflow",
    )

    version_id: UUID = Field(
        foreign_key="workflow_versions.id",
        ondelete="CASCADE",
        description="Version that was published or unpublished",
    )

    action: PublishAction = Field(
        sa_column=postgres_enum_column(PublishAction, "publishaction"),
        description="Whether this was a publish or unpublish action",
    )

    actor_id: UUID | None = Field(
        default=None,
        foreign_key="principals.id",
        ondelete="SET NULL",
        nullable=True,
        description="User who performed the action (nullable to preserve events if principal is deleted)",
    )

    __table_args__ = (
        Index("ix_wf_publish_events_workflow_id", "workflow_id"),
        Index("ix_wf_publish_events_version_id", "version_id"),
        Index("ix_wf_publish_events_actor_id", "actor_id"),
    )
