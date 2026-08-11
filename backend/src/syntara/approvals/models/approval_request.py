"""ApprovalRequest SQLModel and ApprovalRequestStatus enum.

This module contains the ApprovalRequest model representing human-in-the-loop
decision points in workflow executions, and the associated status enumeration.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID

from sqlalchemy import Column, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import DateTime, Field, Relationship

from syntara.approvals.models.api_models import (
    ActivitySummary,
    ApprovalRequestStatus,
    ApproverGroupSummary,
    ApproverUserSummary,
    WorkflowContext,
)
from syntara.approvals.models.approval_approvers import ApprovalApproverGroup, ApprovalApproverUser
from syntara.core.constants import FieldLimits
from syntara.core.models.base import BaseResource
from syntara.core.models.pagination import ResourcesResponse
from syntara.core.models.user_reference import UserReference
from syntara.core.utils.sqlmodel import postgres_enum_column

if TYPE_CHECKING:
    from syntara.core.models import Group, User


class BaseApprovalRequest(BaseResource, table=False):
    """Base approval request model with common fields.

    Contains all approval request fields except decided_by, allowing for different
    representations of the deciding user (UUID in database vs UserReference in API).
    """

    # Project scoping (denormalized from execution for efficient filtering)
    project_id: UUID = Field(
        foreign_key="projects.id",
        description="Project this approval belongs to (denormalized from execution)",
        index=True,
    )

    # User-provided identification
    name: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Human-readable name for the approval request",
        index=True,
    )

    # Soft reference to parent execution (no foreign key constraint)
    execution_id: UUID = Field(
        nullable=False,
        description="Parent execution ID",
        index=True,
    )

    # Approval identity
    approval_node_id: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Activity ID from workflow definition",
    )

    # Status
    status: ApprovalRequestStatus = Field(
        default=ApprovalRequestStatus.PENDING,
        description="Current approval status",
        sa_column=postgres_enum_column(
            ApprovalRequestStatus,
            "approvalrequeststatus",
            index=True,
            create_constraint=True,
            server_default=text("'pending'::approvalrequeststatus"),
        ),
    )

    # Timing
    timeout_at: datetime | None = Field(
        default=None,
        nullable=True,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="When this request expires",
        index=True,
    )

    # Context for approvers - ActivitySummary structures
    next_step_approved: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
        description="First activity that executes if approved",
    )

    next_step_rejected: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
        description="First activity that executes if rejected",
    )

    workflow_context: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        description="Workflow inputs and previous step output",
    )

    # Decision fields (without decided_by)
    decided_at: datetime | None = Field(
        default=None,
        nullable=True,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="When decision was made",
    )

    decision_notes: str | None = Field(
        default=None,
        max_length=FieldLimits.DESCRIPTION_MAX_LENGTH,
        sa_type=String(FieldLimits.DESCRIPTION_MAX_LENGTH),  # type: ignore[call-overload]
        description="Notes provided with decision",
    )


class ApprovalRequest(BaseApprovalRequest, table=True):
    """ApprovalRequest database model with UUID foreign key for decided_by.

    Extends BaseApprovalRequest with the database-specific decided_by field
    that stores a UUID foreign key to the users table.
    """

    __tablename__ = "approval_requests"
    __table_args__ = (UniqueConstraint("execution_id", "approval_node_id", name="uix_execution_approval_node"),)

    # Filterable and sortable fields for API endpoints
    __filterable_fields__: ClassVar[list[str]] = [
        *BaseResource.__filterable_fields__,
        "name",
        "execution_id",
        "project_id",
        "status",
        "timeout_at",
    ]

    __sortable_fields__: ClassVar[list[str]] = [
        *BaseResource.__sortable_fields__,
        "name",
        "timeout_at",
        "decided_at",
        "status",
    ]

    # Decision field - database stores UUID foreign key to principals (not users)
    # so that both human users and service principals can be recorded as deciders.
    decided_by: UUID | None = Field(
        default=None,
        foreign_key="principals.id",
        nullable=True,
        ondelete="SET NULL",
        description="Principal who made the decision",
    )

    # Relationships
    decider: "User" = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "ApprovalRequest.decided_by == User.id",
            "foreign_keys": "[ApprovalRequest.decided_by]",
        },
    )

    # Many-to-many relationships through junction tables
    approver_user_records: list["User"] = Relationship(
        link_model=ApprovalApproverUser,
        sa_relationship_kwargs={"viewonly": True},
    )

    approver_group_records: list["Group"] = Relationship(
        link_model=ApprovalApproverGroup,
        sa_relationship_kwargs={"viewonly": True},
    )


class ApprovalRequestRead(BaseApprovalRequest, table=False):
    """ApprovalRequest API response model with typed nested fields.

    Overrides the JSONB dict fields from BaseApprovalRequest with typed models
    so API consumers get proper validation and type safety. Pydantic coerces
    the raw dicts from the database into these typed models during serialization.
    """

    # Override JSONB dict fields with typed models
    next_step_approved: ActivitySummary = Field(  # type: ignore[assignment]
        ..., description="First activity that executes if approved"
    )
    next_step_rejected: ActivitySummary | None = Field(  # type: ignore[assignment]
        default=None, description="First activity that executes if rejected"
    )
    workflow_context: WorkflowContext = Field(  # type: ignore[assignment]
        ..., description="Workflow inputs and previous step output"
    )

    # Approver configuration - API returns summary objects
    approver_users: list[ApproverUserSummary] = Field(
        default_factory=list,
        description="Users who can approve this request (empty = any user with permission)",
    )
    approver_groups: list[ApproverGroupSummary] = Field(
        default_factory=list,
        description="Groups whose members can approve this request",
    )

    # Decision field - API returns UserReference object
    decided_by: UserReference | None = Field(
        default=None,
        description="User who made the decision",
    )

    # Signal delivery status (populated only in the decide response, not persisted)
    signal_delivery_error: str | None = Field(
        default=None,
        description=(
            "Error if the workflow signal failed after a decision."
            " Only present in the decide response; null on subsequent reads."
        ),
    )


# ============================================================================
# List Response
# ============================================================================


class ApprovalListResponse(ResourcesResponse[ApprovalRequestRead]):
    """Paginated list response for approval requests."""
