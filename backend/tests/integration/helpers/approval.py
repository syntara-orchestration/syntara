"""Integration-test-only factory for creating batches of approval requests."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.approvals.models import ApprovalRequest, ApprovalRequestStatus
from syntara.core.models import User


class ApprovalsFactory:
    """Factory class for creating test approval requests with configurable properties."""

    def __init__(self, session: AsyncSession, user: User, project_id: UUID) -> None:
        """Initialize with database session, user, and project scope."""
        self.session = session
        self.user = user
        self.project_id = project_id
        self._node_counter = 0

    def _get_decision_fields(
        self, status: ApprovalRequestStatus, name_prefix: str, index: int, timeout_at: datetime
    ) -> tuple[UUID | None, datetime | None, str | None, datetime | None]:
        decided_by = None
        decided_at = None
        decision_notes = None
        timeout = timeout_at if status == ApprovalRequestStatus.PENDING else None

        if status in [ApprovalRequestStatus.APPROVED, ApprovalRequestStatus.REJECTED]:
            decided_by = self.user.id
            decided_at = datetime.now(UTC)
            action = "Approved" if status == ApprovalRequestStatus.APPROVED else "Rejected"
            decision_notes = f"{action}: {name_prefix} {index + 1}"
        elif status == ApprovalRequestStatus.EXPIRED:
            timeout = datetime.now(UTC) - timedelta(hours=1)
            decision_notes = "Request automatically rejected due to timeout"
        elif status == ApprovalRequestStatus.CANCELLED:
            decision_notes = "Workflow execution was cancelled"

        return decided_by, decided_at, decision_notes, timeout

    def _create_single_approval(
        self,
        index: int,
        status: ApprovalRequestStatus,
        execution_id: UUID,
        name_prefix: str,
        timeout_at: datetime,
    ) -> ApprovalRequest:
        decided_by, decided_at, decision_notes, timeout = self._get_decision_fields(
            status, name_prefix, index, timeout_at
        )
        self._node_counter += 1
        node_id = f"approval_node_{self._node_counter}"
        return ApprovalRequest(
            execution_id=execution_id,
            project_id=self.project_id,
            approval_node_id=node_id,
            loop_iteration_path=[],
            temporal_activity_id=node_id,
            name=f"{name_prefix} {index + 1}",
            status=status,
            timeout_at=timeout,
            next_step_approved={
                "id": f"approved_step_{index + 1}",
                "name": f"Approved Step {index + 1}",
                "type": "task",
                "description": f"Next step after approval {index + 1}",
            },
            next_step_rejected={
                "id": f"rejected_step_{index + 1}",
                "name": f"Rejected Step {index + 1}",
                "type": "task",
                "description": f"Next step after rejection {index + 1}",
            }
            if index % 2 == 0
            else None,
            workflow_context={
                "workflow_id": str(uuid4()),
                "workflow_name": f"Test Workflow {index + 1}",
                "inputs": {
                    "environment": "test",
                    "version": f"1.0.{index}",
                    "approval_index": index + 1,
                },
                "previous_step": {
                    "id": f"prev_step_{index + 1}",
                    "name": f"Previous Step {index + 1}",
                    "type": "task",
                    "output": {"step_completed": True, "data_id": index + 1},
                },
            },
            decided_by=decided_by,
            decided_at=decided_at,
            decision_notes=decision_notes,
        )

    async def create_approvals(
        self,
        count: int,
        execution_id: UUID | None = None,
        name_prefix: str = "Test Approval",
        statuses: list[ApprovalRequestStatus] | None = None,
        timeout_hours: int = 24,
        *,
        same_execution: bool = True,
    ) -> list[ApprovalRequest]:
        """Create multiple test approval requests."""
        if statuses is None:
            statuses = [ApprovalRequestStatus.PENDING]

        if same_execution and execution_id is None:
            execution_id = uuid4()

        timeout_at = datetime.now(UTC) + timedelta(hours=timeout_hours)

        approvals = []
        for i in range(count):
            status = statuses[i % len(statuses)]
            current_execution_id = execution_id if same_execution else uuid4()
            assert current_execution_id is not None
            approvals.append(self._create_single_approval(i, status, current_execution_id, name_prefix, timeout_at))

        self.session.add_all(approvals)
        await self.session.commit()
        return approvals

    async def create_pending_approvals(
        self,
        count: int,
        execution_id: UUID | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> list[ApprovalRequest]:
        """Create multiple pending approval requests."""
        return await self.create_approvals(
            count=count,
            execution_id=execution_id,
            statuses=[ApprovalRequestStatus.PENDING],
            **kwargs,
        )

    async def create_mixed_status_approvals(
        self,
        pending_count: int = 2,
        approved_count: int = 1,
        rejected_count: int = 1,
        execution_id: UUID | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> list[ApprovalRequest]:
        """Create approval requests with mixed statuses."""
        total_count = pending_count + approved_count + rejected_count
        statuses = (
            [ApprovalRequestStatus.PENDING] * pending_count
            + [ApprovalRequestStatus.APPROVED] * approved_count
            + [ApprovalRequestStatus.REJECTED] * rejected_count
        )
        return await self.create_approvals(
            count=total_count,
            execution_id=execution_id,
            statuses=statuses,
            **kwargs,
        )
