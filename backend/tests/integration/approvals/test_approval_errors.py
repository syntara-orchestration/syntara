"""Integration tests for approval error scenarios across components.

T064: Tests error propagation through Workflows↔Approvals integration including:
- Non-existent approval (404)
- Already-decided approval (409)
- Invalid status transitions (400)
- Batch partial failures
- Graceful degradation when workflow signal delivery fails

Requirements: AAP-79xxx (T064)

Run with:
    pytest backend/tests/integration/approvals/test_approval_errors.py
"""

from typing import Any
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
from syntara.approvals.exceptions import (
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
)
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
from tests.integration.helpers.workflow import ExecutionsFactory

pytestmark = [pytest.mark.integration]

# Test constant for query limits
_QUERY_LIMIT = 999  # Use high limit to effectively get all results


class TestApprovalErrorScenarios:
    """Test error propagation and graceful degradation across approval components."""

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

    async def test_scenario_7_non_existent_approval_404(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Scenario 7: Attempt to decide a non-existent approval.

        Flow:
        1. Generate random approval UUID (not in database)
        2. Attempt to submit decision
        3. Verify ApprovalNotFoundError is raised
        4. Verify error message contains approval ID
        """
        service = self._create_test_service(test_db_session, test_user)

        non_existent_id = uuid4()
        decision_request = ApprovalDecisionRequest(status=ApprovalDecisionStatus.APPROVED)

        with pytest.raises(ApprovalNotFoundError) as exc_info:
            await service.decide(non_existent_id, decision_request)

        assert str(non_existent_id) in str(exc_info.value)

    async def test_scenario_8_already_decided_approval_409(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Scenario 8: Attempt to re-decide an already-approved approval.

        Flow:
        1. Create approval in PENDING state
        2. Approve the request
        3. Verify status is APPROVED
        4. Attempt to approve again
        5. Verify ApprovalAlreadyDecidedError is raised
        6. Attempt to reject instead
        7. Verify ApprovalAlreadyDecidedError is raised again
        """
        service = self._create_test_service(test_db_session, test_user)

        executions = await executions_factory.create_executions(count=1)

        execution = executions[0]
        approval_request = self._create_approval_request(
            execution_id=execution.id,
            project_id=execution.project_id,
        )

        # Create and approve
        approval = await service.create(approval_request)
        decision_request = ApprovalDecisionRequest(status=ApprovalDecisionStatus.APPROVED)
        decided_approval = await service.decide(approval.id, decision_request)
        assert decided_approval.status == ApprovalRequestStatus.APPROVED

        # Attempt to approve again
        with pytest.raises(ApprovalAlreadyDecidedError) as exc_info:
            await service.decide(approval.id, decision_request)

        assert str(approval.id) in str(exc_info.value)

        # Attempt to reject instead
        reject_request = ApprovalDecisionRequest(status=ApprovalDecisionStatus.REJECTED)
        with pytest.raises(ApprovalAlreadyDecidedError):
            await service.decide(approval.id, reject_request)

    async def test_scenario_9_invalid_status_400(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Scenario 9: Submit approval decision with invalid status value.

        Flow:
        1. Create approval in PENDING state
        2. Attempt to construct decision request with invalid status
        3. Verify Pydantic ValidationError is raised before service layer
        """
        # Pydantic validation happens at model construction time
        # This tests that invalid enum values are rejected before hitting the service
        with pytest.raises((ValueError, TypeError)):
            # Intentionally passing invalid status to test Pydantic validation
            invalid_status: Any = "INVALID_STATUS"
            ApprovalDecisionRequest(status=invalid_status)

    async def test_scenario_10_batch_partial_failures(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Scenario 10: Batch operations with partial failures.

        Flow:
        1. Create 3 approvals for the same execution
        2. Approve approval #1
        3. Attempt to decide all 3 approvals again
        4. Verify #1 raises AlreadyDecidedError
        5. Verify #2 and #3 succeed
        """
        service = self._create_test_service(test_db_session, test_user)

        executions = await executions_factory.create_executions(count=1)

        execution = executions[0]

        # Create 3 approvals
        approvals = []
        for i in range(3):
            approval_request = self._create_approval_request(
                execution_id=execution.id,
                project_id=execution.project_id,
                approval_node_id=f"approval_{i}",
                name=f"Gate {i}",
            )
            approval = await service.create(approval_request)
            approvals.append(approval)

        # Decide approval #0
        decision = ApprovalDecisionRequest(status=ApprovalDecisionStatus.APPROVED)
        await service.decide(approvals[0].id, decision)

        # Attempt to decide all 3 in a batch-like operation
        results: list[tuple[str, object]] = []
        for approval in approvals:
            try:
                decided = await service.decide(approval.id, decision)
                results.append(("success", decided))
            except ApprovalAlreadyDecidedError:
                results.append(("already_decided", None))

        # Verify results
        assert results[0] == ("already_decided", None)  # Already approved
        assert results[1][0] == "success"  # Should succeed
        assert results[2][0] == "success"  # Should succeed

    async def test_scenario_11_graceful_degradation_signal_delivery_failure(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Scenario 11: Approval decision persists even if workflow signal delivery fails.

        Flow:
        1. Create approval in PENDING state
        2. Submit decision (this saves to DB)
        3. Simulate Temporal signal delivery failure (workflow unreachable)
        4. Verify approval decision is still persisted in DB
        5. Verify approval status is APPROVED/REJECTED (not PENDING)
        6. Workflow can recover by polling for decision state

        Note: In the real system, Temporal handles signal delivery retries.
        This test verifies that the decision is durable even if workflow is down.
        """
        service = self._create_test_service(test_db_session, test_user)

        executions = await executions_factory.create_executions(count=1)

        execution = executions[0]
        approval_request = self._create_approval_request(
            execution_id=execution.id,
            project_id=execution.project_id,
        )

        # Create approval
        approval = await service.create(approval_request)
        assert approval.status == ApprovalRequestStatus.PENDING

        # Mock workflow client to simulate signal delivery failure
        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            # Make workflow signal delivery fail
            mock_client.send_approval_signal = AsyncMock(side_effect=Exception("Workflow service unavailable"))

            # Submit decision (approval service writes to DB first, then tries to send signal)
            decision_request = ApprovalDecisionRequest(
                status=ApprovalDecisionStatus.APPROVED,
                notes="Approved for deployment",
            )
            decided_approval = await service.decide(approval.id, decision_request)

        # Verify decision is persisted
        assert decided_approval.status == ApprovalRequestStatus.APPROVED
        assert decided_approval.decided_by is not None
        assert decided_approval.decided_by.id == test_user.id
        assert decided_approval.decision_notes == "Approved for deployment"

        # Retrieve approval from DB to verify persistence (simulates workflow polling)
        retrieved = await service.get(approval.id)
        assert retrieved.status == ApprovalRequestStatus.APPROVED
        assert retrieved.decided_by is not None
        assert retrieved.decided_by.id == test_user.id

        # Even if Temporal signal fails, the decision is durable
        # Workflow can query approval state and proceed accordingly
