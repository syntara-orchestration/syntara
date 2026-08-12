"""Integration tests for approval edge cases involving multiple components.

T065: Tests edge cases with concurrent operations and parallel workflow branches:
- Concurrent approval decision attempts (race condition handling)
- Parallel branch failure cancelling pending approval
- Execution status transitions during parallel approval waits

Requirements: AAP-79xxx (T065)

Run with:
    pytest backend/tests/integration/approvals/test_approval_edge_cases.py
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.approvals.audit.approval import (
    ApprovalDecidedEvent,
    ApprovalDecidedHandler,
    ApprovalRequestedEvent,
    ApprovalRequestedHandler,
)
from syntara.approvals.exceptions import ApprovalAlreadyDecidedError
from syntara.approvals.models import (
    ActivitySummary,
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    ApprovalDecisionStatus,
    ApprovalRequestStatus,
    WorkflowContext,
)
from syntara.approvals.services.approval_service import ApprovalService
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.models import User
from syntara.workflows.models.execution import ExecutionStatus
from tests.integration.helpers.workflow import ExecutionsFactory

pytestmark = [pytest.mark.integration]

# Test constant for query limits
_QUERY_LIMIT = 999  # Use high limit to effectively get all results


class TestApprovalEdgeCases:
    """Test edge cases involving concurrent operations and parallel workflow branches."""

    def setup_method(self) -> None:
        """Register audit event handlers for each test."""
        AuditEventDispatcher.register(
            {
                ApprovalRequestedEvent: ApprovalRequestedHandler(),
                ApprovalDecidedEvent: ApprovalDecidedHandler(),
            }
        )

    def _create_test_service(self, session: AsyncSession, user: User) -> ApprovalService:
        """Create ApprovalService with mocked OPA client for integration testing."""
        mock_evaluator = AsyncMock()
        mock_evaluator.__bool__ = AsyncMock(return_value=True)
        mock_evaluator.evaluate = MagicMock(return_value={"allow": True})
        return ApprovalService(session=session, user=user, evaluator=mock_evaluator)

    def _create_approval_request(
        self,
        execution_id: UUID,
        project_id: UUID,
        approval_node_id: str = "approval_gate",
        name: str = "Test Approval",
    ) -> ApprovalCreateRequest:
        """Create a minimal approval request for testing."""
        workflow_context = WorkflowContext(
            workflow_id=uuid4(),
            workflow_name="Test Workflow",
            inputs={},
        )

        return ApprovalCreateRequest(
            execution_id=execution_id,
            project_id=project_id,
            approval_node_id=approval_node_id,
            name=name,
            timeout_at=None,
            next_step_approved=ActivitySummary(
                id="next_step",
                name="Next Step",
                type="script",
            ),
            next_step_rejected=None,
            workflow_context=workflow_context,
        )

    async def test_scenario_12_concurrent_approval_attempts_race_condition(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Scenario 12: Concurrent approval decision attempts (race condition handling).

        Each concurrent actor uses its own DB session so optimistic locking
        (UPDATE … WHERE status=PENDING) is actually contended across transactions.

        Flow:
        1. Create approval in PENDING state
        2. Spawn 3 concurrent tasks attempting to approve the same approval
        3. Verify exactly 1 succeeds
        4. Verify other 2 raise ApprovalAlreadyDecidedError
        5. Verify approval state is consistent (only 1 decision recorded)
        """
        session_factory = test_db_session_factory
        service = self._create_test_service(test_db_session, test_user)

        executions = await executions_factory.create_executions(count=1)

        execution = executions[0]
        approval_request = self._create_approval_request(
            execution_id=execution.id,
            project_id=execution.project_id,
        )

        # Create approval (committed so other sessions can see it)
        approval = await service.create(approval_request)
        await test_db_session.commit()
        approval_id = approval.id
        user_id = test_user.id

        decision_request = ApprovalDecisionRequest(status=ApprovalDecisionStatus.APPROVED)

        async def _attempt_decision() -> tuple[str, object]:
            """Attempt to decide the approval on a dedicated session."""
            async with session_factory() as session:
                user = await session.get(User, user_id)
                assert user is not None
                actor_service = self._create_test_service(session, user)
                try:
                    result = await actor_service.decide(approval_id, decision_request)
                    return ("success", result)
                except ApprovalAlreadyDecidedError:
                    return ("already_decided", None)

        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.send_approval_signal = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            results = await asyncio.gather(
                _attempt_decision(),
                _attempt_decision(),
                _attempt_decision(),
            )

        successes = [r for r in results if r[0] == "success"]
        failures = [r for r in results if r[0] == "already_decided"]

        assert len(successes) == 1, f"Exactly one concurrent attempt should succeed; got {results!r}"
        assert len(failures) == 2, f"Two concurrent attempts should fail with AlreadyDecided; got {results!r}"

        retrieved = await service.get(approval_id)
        assert retrieved.status == ApprovalRequestStatus.APPROVED
        assert retrieved.decided_by is not None
        assert retrieved.decided_by.id == user_id

    async def test_scenario_13_parallel_branch_failure_cancels_approval(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Scenario 13: Parallel branch failure cancelling pending approval.

        Flow:
        1. Create workflow with parallel branches:
           - Branch A: task → approval (waits)
           - Branch B: task → fails
        2. Start execution
        3. Branch A creates pending approval
        4. Branch B fails
        5. Execution status transitions to "failed"
        6. Verify pending approval still exists (not auto-cancelled)
        7. User can still view/decide the approval
        8. Decision is recorded even though execution already failed

        Note: Current behavior - approvals are NOT auto-cancelled when execution fails.
        TODO: Future enhancement - add auto-cancellation logic when execution fails.
        This test documents current behavior for regression detection when that's implemented.
        """
        service = self._create_test_service(test_db_session, test_user)

        # Create execution that will represent parallel branches
        executions = await executions_factory.create_executions(count=1)

        execution = executions[0]

        # Branch A: Create pending approval
        approval_request = self._create_approval_request(
            execution_id=execution.id,
            project_id=execution.project_id,
            approval_node_id="branch_a_approval",
            name="Parallel Branch A Approval",
        )
        approval = await service.create(approval_request)
        assert approval.status == ApprovalRequestStatus.PENDING

        # Simulate: Branch B fails → execution status changes to "failed"
        # Update execution status to simulate parallel branch failure
        execution.status = ExecutionStatus.FAILED
        test_db_session.add(execution)
        await test_db_session.commit()
        await test_db_session.refresh(execution)

        # Verify execution is now in FAILED state
        assert execution.status == ExecutionStatus.FAILED

        # Verify approval is still retrievable despite execution failure
        retrieved = await service.get(approval.id)
        assert retrieved.status == ApprovalRequestStatus.PENDING

        # User can still decide the approval even though execution failed
        decision_request = ApprovalDecisionRequest(
            status=ApprovalDecisionStatus.APPROVED,
            notes="Approving for post-mortem analysis",
        )
        decided_approval = await service.decide(approval.id, decision_request)

        # Verify decision is recorded
        assert decided_approval.status == ApprovalRequestStatus.APPROVED
        assert decided_approval.decision_notes == "Approving for post-mortem analysis"

        # This behavior allows:
        # - Post-mortem analysis of what would have happened
        # - Manual intervention workflows
        # - Audit trail of approval decisions regardless of execution outcome

    async def test_multiple_approvals_mixed_states_same_execution(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test multiple approvals in different states for the same execution.

        This tests the realistic scenario where a workflow has multiple sequential
        approval nodes, some of which have been decided while others remain pending.
        Validates that:
        - Multiple approvals can exist for same execution
        - Each approval maintains independent state
        - Status filtering works correctly (important for UI pending approvals list)

        Flow:
        1. Create execution with 4 approvals
        2. Approve approval #0
        3. Reject approval #1
        4. Leave approval #2 pending
        5. Leave approval #3 pending
        6. List all approvals for execution
        7. Verify mixed states are correctly reported
        8. Filter for pending approvals only
        9. Verify only #2 and #3 are returned
        """
        service = self._create_test_service(test_db_session, test_user)

        executions = await executions_factory.create_executions(count=1)

        execution = executions[0]

        # Create 4 approvals
        approvals = []
        for i in range(4):
            approval_request = self._create_approval_request(
                execution_id=execution.id,
                project_id=execution.project_id,
                approval_node_id=f"approval_{i}",
                name=f"Gate {i}",
            )
            approval = await service.create(approval_request)
            approvals.append(approval)

        # Approve #0
        await service.decide(
            approvals[0].id,
            ApprovalDecisionRequest(status=ApprovalDecisionStatus.APPROVED),
        )

        # Reject #1
        await service.decide(
            approvals[1].id,
            ApprovalDecisionRequest(status=ApprovalDecisionStatus.REJECTED),
        )

        # Leave #2 and #3 pending

        # List all approvals
        query_params = [("execution_id", str(execution.id))]
        all_approvals = await service.list(limit=_QUERY_LIMIT, query_params_items=query_params)
        assert len(all_approvals.resources) == 4

        # Verify states
        approval_states = {a.approval_node_id: a.status for a in all_approvals.resources}
        assert approval_states["approval_0"] == ApprovalRequestStatus.APPROVED
        assert approval_states["approval_1"] == ApprovalRequestStatus.REJECTED
        assert approval_states["approval_2"] == ApprovalRequestStatus.PENDING
        assert approval_states["approval_3"] == ApprovalRequestStatus.PENDING

        # Filter for pending only
        query_params_pending = [
            ("execution_id", str(execution.id)),
            ("status", "pending"),
        ]
        pending_approvals = await service.list(limit=_QUERY_LIMIT, query_params_items=query_params_pending)
        assert len(pending_approvals.resources) == 2
        pending_node_ids = {a.approval_node_id for a in pending_approvals.resources}
        assert pending_node_ids == {"approval_2", "approval_3"}
