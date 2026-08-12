"""Execution SQLModel for workflow runtime instances.

This module provides the Execution table model and API request/response schemas following
SQLModel Pattern 1 (separate models with table=False for API operations).
"""

from datetime import datetime
from enum import Enum, StrEnum
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID

from pydantic import ConfigDict, field_validator, model_validator
from sqlalchemy import BigInteger, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import CheckConstraint, Column, DateTime, Field, Index, Relationship, SQLModel

from syntara.core.constants import FieldLimits
from syntara.core.models.base import SoftDeletableResource, UserOwnedResource
from syntara.core.models.pagination import ResourcesResponse
from syntara.core.utils.sqlmodel import postgres_enum_column
from syntara.workflows.models.workflow_definition import WorkflowDefinition

if TYPE_CHECKING:
    from syntara.workflows.models.activity_execution import ActivityExecution
    from syntara.workflows.models.workflow import Workflow
    from syntara.workflows.models.workflow_version import WorkflowVersion


class ExecutionInclude(str, Enum):
    """Valid include values for execution endpoints."""

    WORKFLOW_DEFINITION = "workflow_definition"
    ACTIVITIES = "activities"


class ExecutionMode(StrEnum):
    """Execution mode for workflow runs."""

    STANDARD = "standard"
    TEST = "test"
    DEBUG = "debug"


class ExecutionStatus(str, Enum):
    """Current state of a workflow execution lifecycle."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Terminal execution statuses (execution has finished)
TERMINAL_EXECUTION_STATUSES = frozenset(
    {
        ExecutionStatus.COMPLETED,
        ExecutionStatus.COMPLETED_WITH_ERRORS,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
    }
)


class Execution(UserOwnedResource, SoftDeletableResource, table=True):
    """Execution model representing workflow runtime instances.

    Combines UserOwnedResource and SoftDeletableResource (both extend BaseResource)
    with execution-specific fields for tracking workflow execution state and results.

    Attributes:
        id: Primary key UUID (from BaseResource)
        created_at: Timestamp when execution was created/started (from BaseResource)
        updated_at: Timestamp of last update (from BaseResource)
        labels: JSONB key-value labels for categorization (from BaseResource)
        created_by: UUID of user who created/started this execution (from UserOwnedResource)
        updated_by: UUID of user who last updated this execution (from UserOwnedResource)
        deleted_at: Soft delete timestamp (from SoftDeletableResource)
        deleted_by: UUID of user who performed soft delete (from SoftDeletableResource)
        workflow_id: Foreign key to parent Workflow
        workflow_version_id: Foreign key to WorkflowVersion executed
        temporal_workflow_id: Temporal workflow ID for orchestration
        status: Current execution status (ExecutionStatus enum)
        completed_at: Timestamp when execution completed/failed/cancelled
        input_data: Input data passed to workflow execution (JSONB)
        error_details: Error message if execution failed
        last_processed_event_id: Last Temporal event ID processed (internal, for incremental sync)

    Relationships:
        workflow: Parent workflow
        workflow_version: Specific version executed
        creator: User who created (started) the execution (from UserOwnedResource)
        updater: User who last updated the execution (from UserOwnedResource)

    """

    __tablename__ = "executions"

    # Define filterable fields for API endpoints - extend base class fields (deduplicated)
    __filterable_fields__: ClassVar[list[str]] = list(
        dict.fromkeys(
            [
                *UserOwnedResource.__filterable_fields__,
                *SoftDeletableResource.__filterable_fields__,
                "workflow_id",
                "workflow_version_id",
                "project_id",
                "status",
                "mode",
                "completed_at",
                "approval_pending",
            ]
        )
    )

    # Define sortable fields for API endpoints - extend base class fields (deduplicated)
    __sortable_fields__: ClassVar[list[str]] = list(
        dict.fromkeys(
            [
                *UserOwnedResource.__sortable_fields__,
                *SoftDeletableResource.__sortable_fields__,
                "id",
                "workflow_version_id",
                "workflow_id",
                "completed_at",
                "status",
            ]
        )
    )

    # Foreign keys
    workflow_id: UUID = Field(
        foreign_key="workflows.id",
        nullable=False,
        ondelete="RESTRICT",
        description="Workflow ID being executed",
        index=True,
    )

    workflow_version_id: UUID = Field(
        foreign_key="workflow_versions.id",
        nullable=False,
        ondelete="RESTRICT",
        description="Workflow version ID executed",
    )

    project_id: UUID = Field(
        foreign_key="projects.id",
        description="Project this execution belongs to (denormalized from workflow)",
        index=True,
    )

    # Temporal workflow ID
    temporal_workflow_id: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        nullable=False,
        unique=True,
        index=True,
        description="Temporal workflow ID for orchestration",
    )

    # Status
    status: ExecutionStatus = Field(
        default=ExecutionStatus.PENDING,
        description="Current execution status",
        sa_column=postgres_enum_column(
            ExecutionStatus,
            "workflowexecutionstatus",
            index=True,
            create_constraint=True,
            server_default=text("'pending'::workflowexecutionstatus"),
        ),
    )

    # Completion timestamp
    completed_at: datetime | None = Field(
        default=None,
        nullable=True,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="Timestamp when execution completed/failed/cancelled",
    )

    # Trigger node selection
    trigger_node_id: str | None = Field(
        default=None,
        nullable=True,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Trigger node ID used to start this execution (None = first trigger in definition list)",
    )

    # Input data and error details
    input_data: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        description="Input data for workflow execution",
    )

    error_details: str | None = Field(
        default=None,
        nullable=True,
        sa_type=Text(),  # type: ignore[call-overload]
        description="Error message if execution failed",
    )

    # Incremental sync tracking (internal use only, not exposed in API)
    last_processed_event_id: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False, server_default=text("0")),
        description="Last Temporal event ID processed for incremental activity sync (0 = never synced)",
    )

    # Approval pending flag
    approval_pending: bool = Field(
        default=False,
        description="Whether this execution has one or more pending approval requests",
        index=True,
        nullable=False,
        sa_column_kwargs={"server_default": text("false")},
    )

    # Retry lineage
    retried_from_execution_id: UUID | None = Field(
        default=None,
        foreign_key="executions.id",
        nullable=True,
        ondelete="SET NULL",
        index=True,
        description="ID of the execution this was retried from (null if not a retry)",
    )

    # Telemetry: trigger type and interface
    trigger_type: str | None = Field(
        default=None,
        nullable=True,
        max_length=50,
        sa_type=String(50),  # type: ignore[call-overload]
        index=True,
        description="Trigger node type (manual_trigger, scheduled_trigger, webhook_trigger, eda_trigger)",
    )

    interface: str | None = Field(
        default=None,
        nullable=True,
        max_length=10,
        sa_type=String(10),  # type: ignore[call-overload]
        index=True,
        description="Originating interface (ui or api)",
    )

    # Execution mode and metadata
    mode: ExecutionMode = Field(
        default=ExecutionMode.STANDARD,
        description="Execution mode (standard, test, debug)",
        sa_column=postgres_enum_column(
            ExecutionMode,
            "executionmode",
            index=True,
            create_constraint=True,
            server_default=text("'standard'::executionmode"),
        ),
    )

    execution_metadata: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
        description="Additional metadata for test/debug executions",
    )

    # Relationships
    workflow: "Workflow" = Relationship(
        back_populates="executions",
        sa_relationship_kwargs={"foreign_keys": "[Execution.workflow_id]"},
    )

    workflow_version: "WorkflowVersion" = Relationship(
        back_populates="executions",
        sa_relationship_kwargs={"foreign_keys": "[Execution.workflow_version_id]"},
    )

    activities: list["ActivityExecution"] = Relationship(
        back_populates="execution",
        sa_relationship_kwargs={
            "order_by": "[ActivityExecution.created_at, ActivityExecution.activity_name]",
        },
    )

    # Note: creator and updater relationships inherited from UserOwnedResource
    # creator = User who started the execution (created_by)
    # updater = User who last modified the execution (updated_by)

    # Table arguments for indexes and constraints
    __table_args__ = (
        # Check constraint for timestamp validation
        CheckConstraint(
            "completed_at IS NULL OR completed_at > created_at",
            name="check_execution_completed_at_after_created_at",
        ),
        # Composite indexes for query performance
        Index("ix_executions_workflow_id_status", "workflow_id", "status"),
        Index("ix_executions_created_by_created_at", "created_by", "created_at"),
        # GIN index for JSONB labels
        Index(
            "ix_executions_labels",
            "labels",
            postgresql_using="gin",
        ),
    )

    def __repr__(self) -> str:
        """Return string representation of Execution.

        Returns:
            String representation

        """
        return f"<Execution(id={self.id}, workflow_id={self.workflow_id}, status={self.status.value})>"


# ============================================================================
# API Request/Response Schemas (Pattern 1: Separate models with table=False)
# ============================================================================


class ExecutionCreate(SQLModel):
    """Schema for creating a new execution (POST /executions).

    Excludes auto-generated fields: id, created_at, created_by (set by backend).
    """

    workflow_id: UUID = Field(..., description="Workflow ID to execute")
    input_data: dict[str, Any] = Field(default_factory=dict, description="Input data for workflow execution")
    trigger_node_id: str = Field(description="Trigger node ID to start from")
    use_published: bool = Field(
        default=False, description="If true, run the published version instead of the current version"
    )


class PreResolvedNodeOutput(SQLModel):
    """Typed structure for a single pre-resolved node's mock output."""

    output: dict[str, Any] = Field(default_factory=dict, description="Mock output data for the node")
    control: dict[str, Any] | None = Field(
        default=None, description="Control data for condition/loop routing (e.g., next_port)"
    )


class TestExecutionCreate(SQLModel):
    """Request body for POST /workflows/{workflow_id}/test."""

    __test__ = False  # Prevent pytest from collecting this as a test class

    target_node_id: str = Field(description="The node to execute for real")
    pre_resolved_nodes: dict[str, PreResolvedNodeOutput] = Field(
        default_factory=dict,
        description="Mock outputs for predecessor nodes. Keys are node IDs.",
    )
    trigger_inputs: dict[str, Any] = Field(default_factory=dict, description="Input data for the trigger node")
    execute_target: bool = Field(
        default=True,
        description="When False, run predecessors up to (but not including) the target node. "
        "Useful for populating upstream data without executing the target. "
        "When True (default), target_node_id must not appear in pre_resolved_nodes.",
    )
    trigger_node_id: str = Field(description="Trigger node ID to start from")

    @field_validator("target_node_id")
    @classmethod
    def validate_target_node_id_not_empty(cls, v: str) -> str:
        """Reject empty or whitespace-only target node IDs."""
        stripped = v.strip()
        if not stripped:
            msg = "target_node_id must not be empty"
            raise ValueError(msg)
        return stripped

    @field_validator("pre_resolved_nodes")
    @classmethod
    def validate_pre_resolved_nodes_size(cls, v: dict[str, PreResolvedNodeOutput]) -> dict[str, PreResolvedNodeOutput]:
        """Enforce maximum number of pre-resolved nodes."""
        if len(v) > FieldLimits.MAX_PRE_RESOLVED_NODES:
            msg = f"pre_resolved_nodes contains {len(v)} entries, maximum is {FieldLimits.MAX_PRE_RESOLVED_NODES}"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def validate_target_not_in_pre_resolved(self) -> "TestExecutionCreate":
        """Reject target_node_id appearing in pre_resolved_nodes (unless execute_target is False)."""
        if self.execute_target and self.target_node_id in self.pre_resolved_nodes:
            msg = (
                f"target_node_id '{self.target_node_id}' must not appear in "
                "pre_resolved_nodes — it would be skipped instead of executed"
            )
            raise ValueError(msg)
        return self


class CurrentActivity(SQLModel):
    """Currently executing activity information."""

    activity_name: str = Field(..., description="Name of the activity")
    temporal_activity_id: str = Field(..., description="Temporal activity ID")
    iteration: int | None = Field(None, description="Iteration number for loops")


class ActivityData(SQLModel):
    """Activity data for execution response."""

    activity_id: str
    status: str
    error_details: str | None = None
    output_data: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    iteration: int | None = None


class ExecutionRead(SQLModel):
    """Schema for execution response (GET /executions/{id}).

    Includes database table fields plus computed fields (workflow_version,
    workflow_version_name, workflow_version_created_at) populated
    by ExecutionsConvertResourceMixin from the related WorkflowVersion.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    id: UUID
    workflow_id: UUID
    workflow_version_id: UUID
    workflow_version: int | None = Field(
        default=None, description="Version number of the workflow version that was executed"
    )
    workflow_name: str | None = Field(default=None, description="Name of the workflow")
    workflow_version_name: str | None = Field(default=None, description="Name of the executed version, if one was set")
    workflow_version_created_at: datetime | None = Field(
        default=None, description="Timestamp when the executed version was created"
    )
    project_id: UUID
    temporal_workflow_id: str
    status: ExecutionStatus
    created_by: UUID  # User who started the execution
    created_at: datetime  # Timestamp when execution was created/started
    completed_at: datetime | None
    updated_at: datetime
    updated_by: UUID | None  # User who last modified the execution
    input_data: dict[str, Any]
    trigger_node_id: str | None = None
    error_details: str | None
    labels: dict[str, Any] = Field(default_factory=dict)
    approval_pending: bool = False
    current_activities: list[CurrentActivity] = Field(
        default_factory=list, description="Currently executing activities"
    )
    deleted_at: datetime | None = None
    deleted_by: UUID | None = None
    mode: ExecutionMode = ExecutionMode.STANDARD
    execution_metadata: dict[str, Any] | None = None
    retried_from_execution_id: UUID | None = None
    trigger_type: str | None = Field(
        default=None,
        description="Trigger node type (manual_trigger, scheduled_trigger, webhook_trigger, eda_trigger)",
    )
    interface: str | None = Field(
        default=None,
        description="Originating interface (ui or api)",
    )

    # Optional: Only populated when ?include=workflow_definition
    workflow_definition: WorkflowDefinition | None = Field(
        default=None,
        description="Workflow definition from the executed version. "
        "Only included when requested via ?include=workflow_definition query parameter.",
    )

    # Optional: Only populated when ?include=activities
    activities: list[ActivityData] | None = Field(
        default=None,
        description="List of activities with their current status. "
        "Only included when requested via ?include=activities query parameter.",
    )


# ============================================================================
# List Response Schema
# ============================================================================


class ExecutionListResponse(ResourcesResponse[ExecutionRead]):
    """Paginated list response for executions."""
