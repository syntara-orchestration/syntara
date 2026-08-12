"""Unit-test-only helper functions for creating in-memory approval request instances."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from syntara.approvals.models import ApprovalRequest, ApprovalRequestStatus

# Sentinel value to detect when a parameter was explicitly passed as None
_NOT_PROVIDED = object()


def create_test_approval_request(
    execution_id: UUID | None = None,
    approval_node_id: str = "test_approval",
    name: str = "Test Approval",
    status: ApprovalRequestStatus = ApprovalRequestStatus.PENDING,
    timeout_at: datetime | None = None,
    next_step_approved: dict[str, Any] | None | object = _NOT_PROVIDED,
    next_step_rejected: dict[str, Any] | None | object = _NOT_PROVIDED,
    workflow_context: dict[str, Any] | None = None,
    decided_by: UUID | None = None,
    decided_at: datetime | None = None,
    decision_notes: str | None = None,
) -> ApprovalRequest:
    """Create an ApprovalRequest in memory with sensible defaults for unit tests."""
    if execution_id is None:
        execution_id = uuid4()

    if timeout_at is None and status == ApprovalRequestStatus.PENDING:
        timeout_at = datetime.now(UTC) + timedelta(days=1)

    if next_step_approved is _NOT_PROVIDED:
        next_step_approved = {
            "id": "apply_changes",
            "name": "Apply Changes",
            "type": "task",
            "description": "Apply the approved changes",
        }

    if next_step_rejected is _NOT_PROVIDED:
        next_step_rejected = {
            "id": "log_rejection",
            "name": "Log Rejection",
            "type": "task",
            "description": "Log the rejection reason",
        }

    if workflow_context is None:
        workflow_context = {
            "workflow_id": str(uuid4()),
            "workflow_name": "Test Workflow",
            "inputs": {"environment": "production", "version": "1.0.0"},
            "previous_step": {
                "id": "prepare_data",
                "name": "Prepare Data",
                "type": "task",
                "output": {"data_prepared": True, "row_count": 1000},
            },
        }

    return ApprovalRequest(
        execution_id=execution_id,
        project_id=uuid4(),
        approval_node_id=approval_node_id,
        name=name,
        status=status,
        timeout_at=timeout_at,
        next_step_approved=next_step_approved,
        next_step_rejected=next_step_rejected,
        workflow_context=workflow_context,
        decided_by=decided_by,
        decided_at=decided_at,
        decision_notes=decision_notes,
    )


def create_approved_approval_request(
    decided_by: UUID | None = None,
    decision_notes: str = "Approved after review",
    **kwargs: Any,  # noqa: ANN401
) -> ApprovalRequest:
    """Create an ApprovalRequest in approved state for unit tests."""
    if decided_by is None:
        decided_by = uuid4()

    return create_test_approval_request(
        status=ApprovalRequestStatus.APPROVED,
        decided_by=decided_by,
        decided_at=datetime.now(UTC),
        decision_notes=decision_notes,
        **kwargs,
    )
