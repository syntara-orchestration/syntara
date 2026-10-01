"""Activity Execution model for workflow activity runtime instances.

This module provides the ActivityExecution database model.
Activity data is synced from Temporal and persisted to enable querying after
Temporal's retention period expires.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID

from sqlalchemy import CheckConstraint, Column, DateTime, Index, String, Text, UniqueConstraint, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship

from syntara.core.constants import FieldLimits
from syntara.core.models.base import BaseResource
from syntara.core.models.pagination import ResourcesResponse
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType

if TYPE_CHECKING:
    from syntara.workflows.models.execution import Execution


class ActivityStatus(str, Enum):
    """Activity execution status enumeration."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


TERMINAL_ACTIVITY_STATUSES = {
    ActivityStatus.COMPLETED,
    ActivityStatus.FAILED,
    ActivityStatus.SKIPPED,
    ActivityStatus.CANCELLED,
}


class ActivityExecution(BaseResource, table=True):
    """Database model for activity executions.

    Persists activity execution state to enable querying after Temporal's retention
    period expires. Data is synced from Temporal events and cached in database.

    This model serves both as the database table and the API response schema.
    Activities are read-only from the API - they're created/updated by syncing from Temporal.

    Inherits from BaseResource:
        id: UUID primary key
        created_at: Creation timestamp
        updated_at: Last update timestamp
        labels: Optional key-value metadata
    """

    __tablename__ = "activity_execution"

    __filterable_fields__: ClassVar[list[str]] = [
        *BaseResource.__filterable_fields__,
        "execution_id",
        "activity_name",
        "node_type",  # NodeType enum; filtering works via string value (e.g. "approval")
        "status",  # ActivityStatus enum; same filtering pattern as node_type
    ]

    # Constraints for ensuring unique activities per execution
    __table_args__ = (
        UniqueConstraint("execution_id", "temporal_activity_id", name="uix_execution_activity"),
        # Composite indexes for query performance
        Index("ix_activity_execution_execution_activity", "execution_id", "activity_name"),
        Index("ix_activity_execution_execution_iteration", "execution_id", "iteration"),
        # Check constraints for data integrity (T052)
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="ck_activity_execution_completed_after_started",
        ),
        CheckConstraint("retry_count >= 0", name="ck_activity_execution_retry_count_non_negative"),
        CheckConstraint("iteration IS NULL OR iteration >= 0", name="ck_activity_execution_iteration_non_negative"),
    )

    # Execution relationship
    execution_id: UUID = Field(
        foreign_key="executions.id",
        ondelete="CASCADE",
        description="Parent execution ID",
        index=True,
    )
    execution: "Execution" = Relationship(back_populates="activities")

    # Activity identity
    activity_name: str = Field(
        ...,
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Activity ID from workflow definition",
    )
    node_type: NodeType = Field(
        ...,
        description="Node type from workflow definition",
        sa_column=Column(
            SAEnum(
                NodeType,
                name="nodetype",
                create_constraint=True,
                native_enum=True,
                values_callable=lambda x: [e.value for e in x],
            ),
            nullable=False,
            index=True,
        ),
    )

    # Temporal identity
    temporal_activity_id: str = Field(
        ...,
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Temporal activity execution ID",
    )

    # Status and timing
    status: ActivityStatus = Field(
        ...,
        description="Current activity status",
        sa_column=Column(
            SAEnum(
                ActivityStatus,
                name="activitystatus",
                create_constraint=True,
                native_enum=True,
                values_callable=lambda x: [e.value for e in x],
            ),
            nullable=False,
            index=True,
        ),
    )
    started_at: datetime | None = Field(
        None,
        description="When activity started execution",
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )
    completed_at: datetime | None = Field(
        None,
        description="When activity completed/failed",
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )

    # Data
    input_data: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        description="Runtime input parameters",
    )
    output_data: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSONB), description="Activity results (if completed)"
    )
    error_details: str | None = Field(
        None,
        sa_type=Text(),  # type: ignore[call-overload]
        description="Error information if failed",
    )

    # Retry tracking
    retry_count: int = Field(0, sa_column_kwargs={"server_default": text("0")}, description="Number of retry attempts")

    # Loop tracking
    iteration: int | None = Field(None, description="Iteration number if activity is within a loop (0-indexed)")


class ActivityExecutionListResponse(ResourcesResponse[ActivityExecution]):
    """Paginated list response for activity executions."""
