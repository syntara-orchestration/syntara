"""Integration tests for complete approval lifecycle.

T063: Tests workflow creation → execution pause at approval → decision submission
→ workflow resumption on correct path → execution completion (scenarios 1-6 from quickstart).
Includes Temporal signal replay safety test (workflow replay should not create duplicate
approval requests).

Requirements: AAP-79xxx (T063)

Run with:
    pytest backend/tests/integration/approvals/test_approval_flow.py
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.approvals.audit.approval import (
    ApprovalDecidedEvent,
    ApprovalDecidedHandler,
    ApprovalRequestedEvent,
    ApprovalRequestedHandler,
)
from syntara.approvals.exceptions import ApprovalAlreadyRequestedError
from syntara.approvals.models import (
    ActivitySummary,
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    ApprovalDecisionStatus,
    ApprovalRequestStatus,
    PreviousStepContext,
    WorkflowContext,
)
from syntara.approvals.services.approval_service import ApprovalService
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.models import User
from tests.integration.helpers.workflow import ExecutionsFactory

pytestmark = [pytest.mark.integration]

# Test constant for query limits
_QUERY_LIMIT = 999  # Use high limit to effectively get all results


class TestApprovalLifecycleFlow:
    """Test complete approval lifecycle from creation to resumption."""

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
        name: str = "Deployment Approval",
        approved_step_id: str = "deploy_step",
        rejected_step_id: str | None = "rollback_step",
    ) -> ApprovalCreateRequest:
        """Create approval request with approved and rejected paths."""
        workflow_context = WorkflowContext(
            workflow_id=uuid4(),
            workflow_name="Deploy Workflow",
            inputs={"environment": "production"},
        )

        next_step_approved = ActivitySummary(
            id=approved_step_id,
            name="Deploy to Production",
            type="script",
        )

        next_step_rejected = (
            ActivitySummary(
                id=rejected_step_id,
                name="Rollback Changes",
                type="script",
            )
            if rejected_step_id
            else None
        )

        return ApprovalCreateRequest(
            execution_id=execution_id,
            project_id=project_id,
            approval_node_id=approval_node_id,
            name=name,
            timeout_at=None,
            next_step_approved=next_step_approved,
            next_step_rejected=next_step_rejected,
            workflow_context=workflow_context,
        )

    async def test_scenario_1_create_and_approve_simple_flow(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Scenario 1: Create workflow with approval, execute, approve, verify completion.

        Flow:
        1. Create workflow with trigger → approval → downstream script
        2. Start execution (simulated)
        3. Approval is created in PENDING state
        4. User approves the request
        5. Verify approval decision is recorded
        6. Verify workflow can proceed (downstream step info available)
        """
        service = self._create_test_service(test_db_session, test_user)

        # Setup execution context
        executions = await executions_factory.create_executions(count=1)

        execution = executions[0]
        approval_request = self._create_approval_request(
            execution_id=execution.id,
            project_id=execution.project_id,
        )

        # Step 1-2: Create approval (simulates workflow pausing at approval node)
        approval = await service.create(approval_request)
        assert approval.status == ApprovalRequestStatus.PENDING
        assert approval.execution_id == execution.id
        assert approval.approval_node_id == "approval_gate"
        assert approval.next_step_approved.id == "deploy_step"

        # Step 3: Approve the request
        decision_request = ApprovalDecisionRequest(
            status=ApprovalDecisionStatus.APPROVED,
            notes="Deployment looks good, proceeding",
        )
        decided_approval = await service.decide(approval.id, decision_request)

        # Step 4: Verify decision is recorded
        assert decided_approval.status == ApprovalRequestStatus.APPROVED
        assert decided_approval.decided_by is not None
        assert decided_approval.decided_by.id == test_user.id
        assert decided_approval.decided_at is not None
        assert decided_approval.decision_notes == "Deployment looks good, proceeding"

        # Step 5: Verify workflow can proceed on approved path
        assert decided_approval.next_step_approved.id == "deploy_step"
        assert decided_approval.next_step_approved.name == "Deploy to Production"

    async def test_scenario_2_create_and_reject_flow(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Scenario 2: Create workflow, execute, reject, verify rejection path.

        Flow:
        1. Create workflow with approval (approved + rejected paths)
        2. Execution pauses at approval
        3. User rejects the request
        4. Verify rejection decision is recorded
        5. Verify workflow proceeds on rejected path
        """
        service = self._create_test_service(test_db_session, test_user)

        executions = await executions_factory.create_executions(count=1)

        execution = executions[0]
        approval_request = self._create_approval_request(
            execution_id=execution.id,
            project_id=execution.project_id,
        )

        # Create pending approval
        approval = await service.create(approval_request)
        assert approval.status == ApprovalRequestStatus.PENDING

        # Reject the request
        decision_request = ApprovalDecisionRequest(
            status=ApprovalDecisionStatus.REJECTED,
            notes="Failed security checks, rolling back",
        )
        decided_approval = await service.decide(approval.id, decision_request)

        # Verify rejection is recorded
        assert decided_approval.status == ApprovalRequestStatus.REJECTED
        assert decided_approval.decided_by is not None
        assert decided_approval.decided_by.id == test_user.id
        assert decided_approval.decision_notes == "Failed security checks, rolling back"

        # Verify workflow can proceed on rejected path
        assert decided_approval.next_step_rejected is not None
        assert decided_approval.next_step_rejected.id == "rollback_step"
        assert decided_approval.next_step_rejected.name == "Rollback Changes"

    async def test_scenario_3_multiple_approvals_in_sequence(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Scenario 3: Workflow with multiple sequential approvals.

        Flow:
        1. Create workflow: trigger → approval_1 → task → approval_2 → final_task
        2. Execute workflow, pause at approval_1
        3. Approve approval_1
        4. Execution proceeds to approval_2
        5. Approve approval_2
        6. Verify both approvals are approved, workflow completes
        """
        service = self._create_test_service(test_db_session, test_user)

        executions = await executions_factory.create_executions(count=1)

        execution = executions[0]

        # First approval node
        approval_1_request = self._create_approval_request(
            execution_id=execution.id,
            project_id=execution.project_id,
            approval_node_id="approval_1",
            name="First Gate",
            approved_step_id="middle_task",
        )
        approval_1 = await service.create(approval_1_request)

        # Approve first approval
        decision_1 = ApprovalDecisionRequest(status=ApprovalDecisionStatus.APPROVED)
        approved_1 = await service.decide(approval_1.id, decision_1)
        assert approved_1.status == ApprovalRequestStatus.APPROVED

        # Second approval node (created after first approval allows execution to proceed)
        approval_2_request = self._create_approval_request(
            execution_id=execution.id,
            project_id=execution.project_id,
            approval_node_id="approval_2",
            name="Second Gate",
            approved_step_id="final_task",
        )
        approval_2 = await service.create(approval_2_request)

        # Approve second approval
        decision_2 = ApprovalDecisionRequest(status=ApprovalDecisionStatus.APPROVED)
        approved_2 = await service.decide(approval_2.id, decision_2)
        assert approved_2.status == ApprovalRequestStatus.APPROVED

        # Verify both approvals exist for the same execution
        query_params = [("execution_id", str(execution.id))]
        approvals = await service.list(limit=_QUERY_LIMIT, query_params_items=query_params)
        assert len(approvals.resources) == 2
        assert all(a.status in (ApprovalRequestStatus.APPROVED,) for a in approvals.resources)

    async def test_scenario_4_approval_with_previous_step_output(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Scenario 4: Approval node receives output from previous step.

        Flow:
        1. Create workflow: trigger → analysis_task → approval (with previous output)
        2. Execute workflow, analysis outputs data
        3. Approval receives previous_step_output in context
        4. User reviews output and approves
        """
        service = self._create_test_service(test_db_session, test_user)

        executions = await executions_factory.create_executions(count=1)

        execution = executions[0]

        # Create approval with previous step context
        workflow_context = WorkflowContext(
            workflow_id=uuid4(),
            workflow_name="Analysis Workflow",
            inputs={"dataset": "production_logs"},
            previous_step=PreviousStepContext(
                id="analysis_task",
                name="Analyze Data",
                type="script",
                output={"findings": 42, "anomalies": 3, "confidence": 0.95},
            ),
        )

        approval_request = ApprovalCreateRequest(
            execution_id=execution.id,
            project_id=execution.project_id,
            approval_node_id="review_gate",
            name="Review Analysis Results",
            timeout_at=None,
            next_step_approved=ActivitySummary(
                id="publish_results",
                name="Publish Results",
                type="script",
            ),
            next_step_rejected=None,
            workflow_context=workflow_context,
        )

        approval = await service.create(approval_request)

        # Verify previous step output is available
        assert approval.workflow_context.previous_step is not None
        assert approval.workflow_context.previous_step.output is not None
        assert approval.workflow_context.previous_step.output["findings"] == 42
        assert approval.workflow_context.previous_step.output["anomalies"] == 3

        # Approve based on analysis results
        decision = ApprovalDecisionRequest(
            status=ApprovalDecisionStatus.APPROVED,
            notes="Analysis results look good, 95% confidence",
        )
        decided = await service.decide(approval.id, decision)
        assert decided.status == ApprovalRequestStatus.APPROVED

    async def test_scenario_5_approval_timeout_not_expired(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Scenario 5: Approval with timeout that hasn't expired yet.

        Flow:
        1. Create workflow with approval node (timeout in future)
        2. Execute workflow
        3. Approval is created with timeout_at set
        4. User approves before timeout
        5. Verify approval succeeds
        """
        service = self._create_test_service(test_db_session, test_user)

        executions = await executions_factory.create_executions(count=1)

        execution = executions[0]

        # Set timeout 1 hour in future
        timeout_at = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=1)

        approval_request = self._create_approval_request(
            execution_id=execution.id,
            project_id=execution.project_id,
        )
        approval_request.timeout_at = timeout_at

        approval = await service.create(approval_request)
        assert approval.timeout_at == timeout_at

        # Approve before timeout
        decision = ApprovalDecisionRequest(status=ApprovalDecisionStatus.APPROVED)
        decided = await service.decide(approval.id, decision)
        assert decided.status == ApprovalRequestStatus.APPROVED

    async def test_scenario_6_list_approvals_for_execution(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Scenario 6: List all approvals for a specific execution.

        Flow:
        1. Create workflow with multiple approval nodes
        2. Execute workflow
        3. Multiple approvals are created
        4. Query approvals by execution_id
        5. Verify all approvals are returned
        """
        service = self._create_test_service(test_db_session, test_user)

        executions = await executions_factory.create_executions(count=1)

        execution = executions[0]

        # Create 3 approvals for the same execution
        approvals_created = []
        for i in range(3):
            approval_request = self._create_approval_request(
                execution_id=execution.id,
                project_id=execution.project_id,
                approval_node_id=f"approval_{i}",
                name=f"Gate {i}",
            )
            approval = await service.create(approval_request)
            approvals_created.append(approval)

        # List approvals for execution
        query_params = [("execution_id", str(execution.id))]
        result = await service.list(limit=_QUERY_LIMIT, query_params_items=query_params)
        assert len(result.resources) == 3
        assert all(a.execution_id == execution.id for a in result.resources)
        assert {a.approval_node_id for a in result.resources} == {"approval_0", "approval_1", "approval_2"}

    async def test_temporal_replay_safety_no_duplicate_approvals(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Temporal signal replay safety: workflow replay should not create duplicate approval requests.

        Flow:
        1. Create workflow with approval node
        2. Execute workflow, approval is created
        3. Simulate Temporal workflow replay (attempt to create same approval again)
        4. Verify second create call is idempotent (no duplicate created)
        5. Verify only one approval exists for the node
        """
        service = self._create_test_service(test_db_session, test_user)

        executions = await executions_factory.create_executions(count=1)

        execution = executions[0]
        approval_request = self._create_approval_request(
            execution_id=execution.id,
            project_id=execution.project_id,
            approval_node_id="replay_test_gate",
            name="Replay Safety Test",
        )

        # First create (initial workflow execution)
        approval_1 = await service.create(approval_request)
        assert approval_1.status == ApprovalRequestStatus.PENDING

        # Second create (simulates Temporal replay)
        # This should be idempotent and NOT create a duplicate
        with pytest.raises(ApprovalAlreadyRequestedError) as exc_info:
            await service.create(approval_request)

        assert "already exists" in str(exc_info.value).lower()

        # Verify only one approval exists for this node
        query_params = [
            ("execution_id", str(execution.id)),
        ]
        approvals = await service.list(limit=_QUERY_LIMIT, query_params_items=query_params)

        # Filter by approval_node_id in Python (not a filterable field in API)
        replay_test_approvals = [a for a in approvals.resources if a.approval_node_id == "replay_test_gate"]
        assert len(replay_test_approvals) == 1
        assert replay_test_approvals[0].id == approval_1.id
