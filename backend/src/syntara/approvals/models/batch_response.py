"""Models for batch approval response."""

from datetime import datetime
from uuid import UUID

from sqlmodel import Field, SQLModel

from syntara.approvals.models import ApprovalRequestStatus
from syntara.core.models.user_reference import UserReference


class BatchApprovalResult(SQLModel):
    """Confirmation for a single approval within a batch response."""

    approval_id: UUID = Field(description="ID of the approval request")
    success: bool = Field(description="Whether the decision was successfully recorded")
    status: ApprovalRequestStatus | None = Field(
        default=None, description="New status after the decision (if successful)"
    )
    decided_at: datetime | None = Field(default=None, description="When decision was recorded (if successful)")
    decided_by: UserReference | None = Field(default=None, description="User who made the decision (if successful)")
    decision_notes: str | None = Field(
        default=None, description="Notes provided with the decision (echoed back from request)"
    )
    error: str | None = Field(default=None, description="Error message if the decision failed")


class BatchApprovalResponse(SQLModel):
    """Response for batch approval submission."""

    results: list[BatchApprovalResult] = Field(description="Individual results for each decision")
    total_success: int = Field(ge=0, description="Number of successfully processed decisions")
    total_failed: int = Field(ge=0, description="Number of failed decisions")
