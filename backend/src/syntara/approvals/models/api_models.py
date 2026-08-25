"""API request/response models for approval endpoints.

This module contains SQLModel classes corresponding to the OpenAPI specification
components for type-safe API operations.
"""

import html
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar
from uuid import UUID

import nh3
from pydantic import AliasChoices, ConfigDict, Field, field_validator
from sqlmodel import SQLModel

from syntara.core.constants import FieldLimits

_SANITIZE_MAX_ROUNDS = 10
_SANITIZE_ERROR = "Decision notes contain deeply nested HTML encoding that cannot be safely sanitized"


def _sanitize_notes(v: str | None) -> str | None:
    if not isinstance(v, str):
        return v
    # Fixed-point loop: keep unescaping entity-encoded HTML and stripping
    # tags until the output stabilises.  Handles arbitrary encoding depth
    # (e.g. &amp;lt;script&amp;gt;).  Bounded to prevent infinite loops.
    result = v
    for _ in range(_SANITIZE_MAX_ROUNDS):
        cleaned = html.unescape(nh3.clean(result, tags=set()))
        if cleaned == result:
            return result
        result = cleaned
    # One extra convergence check: the last peel may have produced a safe
    # result that simply had no iteration left to verify stability.
    final = html.unescape(nh3.clean(result, tags=set()))
    if final == result:
        return result
    raise ValueError(_SANITIZE_ERROR)


class ApproverUserSummary(SQLModel):
    """Summary of a user authorized to approve a request.

    Similar to UserReference but represents an approver rather than a decider.
    Used in API responses to show who can approve a request.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    id: UUID = Field(..., description="User's unique identifier")
    username: str = Field(..., description="User's username")


class ApproverGroupSummary(SQLModel):
    """Summary of a group whose members are authorized to approve a request.

    Represents a group of users who can collectively approve a request.
    Used in API responses to show which groups have approval authority.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    id: UUID = Field(..., description="Group's unique identifier")
    name: str = Field(..., description="Group's name")


class ApprovalRequestStatus(str, Enum):
    """Approval request status enumeration."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalDecisionStatus(str, Enum):
    """Status values for approval decisions.

    This is a subset of ApprovalRequestStatus representing only the
    values that can be submitted in decision requests.
    """

    APPROVED = "approved"
    REJECTED = "rejected"


class BatchApprovalDecisionStatus(str, Enum):
    """Status values that can be submitted in batch approval decisions.

    This is a subset of ApprovalRequestStatus containing only system-actionable values.
    """

    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ActivitySummary(SQLModel):
    """Activity summary for workflow context.

    Passed through from the workflow engine as-is. Contains at minimum
    ``id``, ``name``, ``type``, and usually ``config`` with the full
    activity parameters so approvers can see what the step will do.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True, extra="allow")  # type: ignore[assignment]

    id: str = Field(..., description="Activity ID from workflow definition")
    name: str = Field(..., description="Human-readable activity name")
    type: str = Field(..., description="Activity type (script, approval, agentic, etc.)")


class PreviousStepContext(SQLModel):
    """Previous Step Context for workflow execution.

    The activity that immediately preceded this approval node, including its output.
    Null if the approval node is the first activity in the workflow.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    id: str = Field(..., description="Activity ID from workflow definition")
    name: str = Field(..., description="Human-readable activity name")
    type: str = Field(..., description="Activity type (task, approval, parallel, etc.)")
    output: dict[str, Any] | None = Field(
        None, description="Output from the activity (structure varies per activity type)"
    )


class WorkflowContext(SQLModel):
    """Workflow Context for approvers.

    Essential context for approvers to make a decision.
    Contains workflow identification, inputs, and the output from the immediately
    preceding activity.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    workflow_id: UUID | None = Field(None, description="ID of the workflow")
    workflow_version: int | None = Field(None, description="Integer version number of the workflow version executed")
    workflow_name: str = Field(..., description="Name of the workflow")
    inputs: dict[str, Any] = Field(
        ..., description="Original workflow input parameters (structure varies per workflow)"
    )
    previous_step: PreviousStepContext | None = Field(None, description="Previous step context and output")


class ApprovalCreateRequest(SQLModel):
    """Request payload for creating an approval request.

    This is an internal schema used by the Workflows component.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    execution_id: UUID = Field(..., description="Parent workflow execution ID")
    project_id: UUID = Field(..., description="Project ID (denormalized from execution)")
    approval_node_id: str = Field(..., description="Canvas node ID from the workflow definition")
    name: str = Field(..., min_length=1, max_length=255, description="Display name for the approval request")
    loop_iteration_path: list[int] = Field(
        default_factory=list,
        description="Enclosing-loop indices, outermost first (empty when not inside a loop)",
    )
    temporal_activity_id: str | None = Field(
        default=None,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        description="Temporal activity ID to signal on decide (defaults to approval_node_id)",
    )
    timeout_at: datetime | None = Field(None, description="When this request expires (null = no timeout)")
    next_step_approved: ActivitySummary = Field(..., description="First activity that executes if approved")
    next_step_rejected: ActivitySummary | None = Field(None, description="First activity that executes if rejected")
    workflow_context: WorkflowContext = Field(..., description="Workflow execution context")
    # FK validation: UUIDs must exist in users/groups tables (enforced at service layer)
    approver_user_ids: list[UUID] | None = Field(
        None,
        max_length=FieldLimits.APPROVER_LIST_MAX_LENGTH,
        description="User IDs who can approve (null = any user with approval:decide permission)",
    )
    approver_group_ids: list[UUID] | None = Field(
        None,
        max_length=FieldLimits.APPROVER_LIST_MAX_LENGTH,
        description="Group IDs whose members can approve",
    )

    @field_validator("loop_iteration_path")
    @classmethod
    def _non_negative_loop_iteration_path(cls, value: list[int]) -> list[int]:
        if any(index < 0 for index in value):
            msg = "loop_iteration_path entries must be non-negative integers"
            raise ValueError(msg)
        return value


class ApprovalDecisionRequest(SQLModel):
    """Request payload for submitting an approval decision.

    Status values:
    - approved: Approver grants the request, workflow continues on approval path
    - rejected: Approver denies the request, workflow continues on rejection path
    - cancelled: Internal use only - set by workflow engine when parent workflow is cancelled
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    status: ApprovalDecisionStatus = Field(..., description="Decision status")
    notes: str | None = Field(
        None,
        max_length=FieldLimits.DESCRIPTION_MAX_LENGTH,
        description=(
            "Optional notes explaining the decision. Accepts either `notes` or "
            "`decision_notes` (the key returned in responses) as the request field name."
        ),
        validation_alias=AliasChoices("notes", "decision_notes"),
    )

    @field_validator("notes", mode="before")
    @classmethod
    def strip_html_tags(cls, v: str | None) -> str | None:
        """Strip HTML tags to prevent stored XSS."""
        return _sanitize_notes(v)


class BatchApprovalDecision(SQLModel):
    """Single decision within a batch approval request."""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    approval_id: UUID = Field(..., description="ID of the approval request")
    status: BatchApprovalDecisionStatus = Field(..., description="Decision status")
    notes: str | None = Field(
        None,
        max_length=FieldLimits.DESCRIPTION_MAX_LENGTH,
        description=(
            "Optional notes explaining the decision. Accepts either `notes` or "
            "`decision_notes` (the key returned in responses) as the request field name."
        ),
        validation_alias=AliasChoices("notes", "decision_notes"),
    )

    @field_validator("notes", mode="before")
    @classmethod
    def strip_html_tags(cls, v: str | None) -> str | None:
        """Strip HTML tags to prevent stored XSS."""
        return _sanitize_notes(v)


class BatchApprovalRequest(SQLModel):
    """Request payload for submitting multiple approval decisions at once."""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    decisions: list[BatchApprovalDecision] = Field(
        ..., min_length=1, max_length=100, description="List of approval decisions to submit"
    )
