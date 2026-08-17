"""Approval-related data structures for workflow engine."""

from dataclasses import dataclass


@dataclass
class ApprovalResult:
    """Result of an approval decision.

    Attributes:
        status: Approval status ("approved" or "rejected")
        approval_id: ID of the approval request
        notes: Optional notes provided with the decision

    """

    status: str  # "approved" or "rejected"
    approval_id: str
    notes: str | None = None
