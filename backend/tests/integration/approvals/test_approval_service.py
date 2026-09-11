"""Unit tests for ApprovalService business logic.

Tests all ApprovalService methods including list, get, create, decide, and batch_decide
following the project's test patterns and using injected factory fixtures.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import ANY, AsyncMock, MagicMock, patch
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
    ApprovalAlreadyRequestedError,
    ApprovalNotAuthorizedError,
    ApprovalNotFoundError,
)
from syntara.approvals.models import (
    ActivitySummary,
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    ApprovalDecisionStatus,
    ApprovalRequestRead,
    ApprovalRequestStatus,
    BatchApprovalDecision,
    BatchApprovalDecisionStatus,
    BatchApprovalRequest,
    WorkflowContext,
)
from syntara.approvals.services.approval_service import ApprovalService
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.models import User
from tests.integration.helpers.approval import ApprovalsFactory
from tests.integration.helpers.workflow import ExecutionsFactory


class TestApprovalServiceBase:
    """Base test class with helper methods for ApprovalService tests."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register(
            {
                ApprovalRequestedEvent: ApprovalRequestedHandler(),
                ApprovalDecidedEvent: ApprovalDecidedHandler(),
            }
        )

    def _create_test_service(self, session: AsyncSession, user: User) -> ApprovalService:
        """Create ApprovalService instance for testing with mocked authz evaluator.

        Integration tests use a mock authz evaluator that allows all approval:decide permissions
        so tests can focus on approver list authorization logic.
        """
        # Create a mock authz evaluator that always returns authorized (allow: true)
        # This allows tests to focus on the approver list logic, not authz evaluator authorization
        mock_evaluator = AsyncMock()
        mock_evaluator.__bool__ = AsyncMock(return_value=True)
        # Mock the evaluate method to return allow: true (authorized)
        # The real authz evaluator unwraps the "result" field, so we return the unwrapped dict
        mock_evaluator.evaluate = MagicMock(return_value={"allow": True})

        return ApprovalService(session=session, user=user, evaluator=mock_evaluator)

    def _create_approval_request(
        self,
        execution_id: UUID,
        project_id: UUID | None = None,
        approval_node_id: str = "approval_1",
        name: str = "Test Approval",
        timeout_at: datetime | None = None,
        loop_iteration_path: list[int] | None = None,
        temporal_activity_id: str | None = None,
    ) -> ApprovalCreateRequest:
        """Create a typed approval request for testing."""
        workflow_context = WorkflowContext(
            workflow_id=uuid4(),
            workflow_name="Test Workflow",
            inputs={"environment": "test"},
        )

        next_step_approved = ActivitySummary(
            id="approved_step",
            name="Approved Step",
            type="task",
        )

        return ApprovalCreateRequest(
            execution_id=execution_id,
            project_id=project_id or uuid4(),
            approval_node_id=approval_node_id,
            name=name,
            timeout_at=timeout_at,
            next_step_approved=next_step_approved,
            next_step_rejected=None,
            workflow_context=workflow_context,
            loop_iteration_path=loop_iteration_path or [],
            temporal_activity_id=temporal_activity_id,
        )

    def _create_decision_request(
        self, status: ApprovalDecisionStatus = ApprovalDecisionStatus.APPROVED, notes: str | None = None
    ) -> ApprovalDecisionRequest:
        """Create a typed decision request for testing."""
        return ApprovalDecisionRequest(
            status=status,
            notes=notes,
        )

    def _create_batch_approval_request(self, decisions: list[BatchApprovalDecision]) -> BatchApprovalRequest:
        """Create a batch approval request for testing."""
        return BatchApprovalRequest(decisions=decisions)

    def _create_batch_decision(
        self,
        approval_id: UUID,
        status: BatchApprovalDecisionStatus = BatchApprovalDecisionStatus.APPROVED,
        notes: str | None = None,
    ) -> BatchApprovalDecision:
        """Create a batch approval decision for testing."""
        return BatchApprovalDecision(
            approval_id=approval_id,
            status=status,
            notes=notes,
        )


class TestApprovalServiceList(TestApprovalServiceBase):
    """Test ApprovalService.list method."""

    @pytest.mark.asyncio
    async def test_list_approvals_uses_base_method(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that list method delegates to base list_resources method."""
        service = self._create_test_service(test_db_session, test_user)

        # Create a test execution first
        executions = await executions_factory.create_executions(count=1)
        execution_id = executions[0].id

        # Create test approval requests with mixed statuses
        await approvals_factory.create_mixed_status_approvals(
            pending_count=2, approved_count=1, rejected_count=1, name_prefix="Service Test", execution_id=execution_id
        )

        result = await service.list(limit=10, include_total=True)

        assert len(result.resources) == 4
        assert result.total == 4

        # Verify the actual approvals are returned
        returned_names = {a.name for a in result.resources}
        expected_names = {"Service Test 1", "Service Test 2", "Service Test 3", "Service Test 4"}
        assert returned_names == expected_names

    @pytest.mark.asyncio
    async def test_list_with_status_filter(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test list with status filter."""
        service = self._create_test_service(test_db_session, test_user)

        # Create a test execution first
        executions = await executions_factory.create_executions(count=1)
        execution_id = executions[0].id

        # Create approvals with different statuses
        await approvals_factory.create_mixed_status_approvals(
            pending_count=2, approved_count=1, rejected_count=1, name_prefix="Filter Test", execution_id=execution_id
        )

        # Filter for pending only - need to build query params manually
        query_params = [("status", "pending")]
        result = await service.list(limit=20, query_params_items=query_params)

        assert len(result.resources) == 2
        assert all(a.status == ApprovalRequestStatus.PENDING for a in result.resources)

    @pytest.mark.asyncio
    async def test_list_with_execution_id_filter(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test list with execution_id filter."""
        service = self._create_test_service(test_db_session, test_user)

        # Create two test executions
        executions = await executions_factory.create_executions(count=2)
        execution_id_1 = executions[0].id
        execution_id_2 = executions[1].id

        # Create approvals for different executions
        await approvals_factory.create_approvals(count=2, execution_id=execution_id_1, name_prefix="Execution 1")
        await approvals_factory.create_approvals(count=2, execution_id=execution_id_2, name_prefix="Execution 2")

        # Filter for execution_id_1 only - need to build query params manually
        query_params = [("execution_id", str(execution_id_1))]
        result = await service.list(limit=20, query_params_items=query_params)

        assert len(result.resources) == 2
        assert all(a.execution_id == execution_id_1 for a in result.resources)
        assert all("Execution 1" in a.name for a in result.resources)

    @pytest.mark.asyncio
    async def test_list_empty_result(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test list with no matching approvals."""
        service = self._create_test_service(test_db_session, test_user)

        query_params = [("status", "pending")]
        result = await service.list(limit=20, query_params_items=query_params, include_total=True)

        assert len(result.resources) == 0
        assert result.total == 0


class TestApprovalServiceGet(TestApprovalServiceBase):
    """Test ApprovalService.get method."""

    @pytest.mark.asyncio
    async def test_get_success(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test successful get operation."""
        service = self._create_test_service(test_db_session, test_user)

        # Create a test execution first
        executions = await executions_factory.create_executions(count=1)
        execution_id = executions[0].id

        approvals = await approvals_factory.create_approvals(count=1, execution_id=execution_id, name_prefix="Get Test")
        approval = approvals[0]

        result = await service.get(approval.id)

        assert result.id == approval.id
        assert result.name == "Get Test 1"

    @pytest.mark.asyncio
    async def test_get_not_found(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test get when approval not found."""
        service = self._create_test_service(test_db_session, test_user)

        non_existent_id = uuid4()

        with pytest.raises(ApprovalNotFoundError) as exc_info:
            await service.get(non_existent_id)

        assert exc_info.value.approval_id == non_existent_id


class TestApprovalServiceCreate(TestApprovalServiceBase):
    """Test ApprovalService.create method."""

    @pytest.mark.asyncio
    async def test_create_success(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test successful create operation."""
        service = self._create_test_service(test_db_session, test_user)

        # Create a test execution first
        executions = await executions_factory.create_executions(count=1)
        execution = executions[0]
        execution_id = execution.id
        timeout_at = datetime.now(UTC) + timedelta(hours=24)

        request = self._create_approval_request(
            execution_id=execution_id,
            project_id=execution.project_id,
            name="Test Create Approval",
            timeout_at=timeout_at,
        )

        result = await service.create(request)

        assert isinstance(result, ApprovalRequestRead)
        assert result.execution_id == execution_id
        assert result.approval_node_id == "approval_1"
        assert result.name == "Test Create Approval"
        assert result.status == ApprovalRequestStatus.PENDING
        assert result.timeout_at == timeout_at
        assert result.decided_by is None
        assert result.decided_at is None

    @pytest.mark.asyncio
    async def test_create_minimal_required_fields(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test create with only required fields."""
        service = self._create_test_service(test_db_session, test_user)

        # Create a test execution first
        executions = await executions_factory.create_executions(count=1)
        execution = executions[0]

        request = self._create_approval_request(
            execution_id=execution.id,
            project_id=execution.project_id,
            approval_node_id="minimal_approval",
            name="Minimal Approval",
            timeout_at=None,
        )

        result = await service.create(request)

        assert result.execution_id == execution.id
        assert result.approval_node_id == "minimal_approval"
        assert result.name == "Minimal Approval"
        assert result.timeout_at is None
        assert result.next_step_rejected is None

    @pytest.mark.asyncio
    async def test_create_duplicate_approval_raises_exception(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that creating a duplicate approval request raises ApprovalAlreadyRequestedError."""
        service = self._create_test_service(test_db_session, test_user)

        # Create a test execution first
        executions = await executions_factory.create_executions(count=1)
        execution = executions[0]

        # Create the first approval request
        request1 = self._create_approval_request(
            execution_id=execution.id,
            project_id=execution.project_id,
            approval_node_id="duplicate_test",
            name="First Approval",
        )

        # Create the first approval successfully
        result1 = await service.create(request1)
        assert result1.execution_id == execution.id
        assert result1.approval_node_id == "duplicate_test"

        # Attempt to create a duplicate approval request with the same execution_id and approval_node_id
        request2 = self._create_approval_request(
            execution_id=execution.id,
            project_id=execution.project_id,
            approval_node_id="duplicate_test",  # Same approval_node_id
            name="Second Approval (should fail)",
        )

        # This should raise ApprovalAlreadyRequestedError
        with pytest.raises(ApprovalAlreadyRequestedError) as exc_info:
            await service.create(request2)

        # Verify the exception contains the correct execution_id and approval_node_id
        assert exc_info.value.execution_id == execution.id
        assert exc_info.value.approval_node_id == "duplicate_test"

    @pytest.mark.asyncio
    async def test_create_same_node_different_loop_path_succeeds(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """The same canvas node can have one approval per loop iteration path."""
        service = self._create_test_service(test_db_session, test_user)
        executions = await executions_factory.create_executions(count=1)
        execution = executions[0]

        first = await service.create(
            self._create_approval_request(
                execution_id=execution.id,
                project_id=execution.project_id,
                approval_node_id="loop_gate",
                name="Iteration 0",
                loop_iteration_path=[0],
                temporal_activity_id="loop_gate_iter_0",
            )
        )
        second = await service.create(
            self._create_approval_request(
                execution_id=execution.id,
                project_id=execution.project_id,
                approval_node_id="loop_gate",
                name="Iteration 1",
                loop_iteration_path=[1],
                temporal_activity_id="loop_gate_iter_1",
            )
        )

        assert first.approval_node_id == "loop_gate"
        assert second.approval_node_id == "loop_gate"
        assert first.loop_iteration_path == [0]
        assert second.loop_iteration_path == [1]
        assert first.id != second.id

        with pytest.raises(ApprovalAlreadyRequestedError):
            await service.create(
                self._create_approval_request(
                    execution_id=execution.id,
                    project_id=execution.project_id,
                    approval_node_id="loop_gate",
                    name="Iteration 1 again",
                    loop_iteration_path=[1],
                )
            )

    @pytest.mark.asyncio
    async def test_create_nonexistent_execution_raises_not_found(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test that creating an approval with a nonexistent execution_id raises ExecutionNotFoundError."""
        from syntara.workflows.exceptions import ExecutionNotFoundError

        service = self._create_test_service(test_db_session, test_user)

        fabricated_execution_id = uuid4()
        request = self._create_approval_request(
            execution_id=fabricated_execution_id,
            project_id=uuid4(),
            name="Orphan Approval",
        )

        with pytest.raises(ExecutionNotFoundError) as exc_info:
            await service.create(request)

        assert exc_info.value.execution_id == fabricated_execution_id

    @pytest.mark.asyncio
    async def test_create_mismatched_project_id_raises_value_error(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that creating an approval with wrong project_id raises ValueError."""
        service = self._create_test_service(test_db_session, test_user)

        executions = await executions_factory.create_executions(count=1)
        execution = executions[0]

        wrong_project_id = uuid4()
        request = self._create_approval_request(
            execution_id=execution.id,
            project_id=wrong_project_id,
            name="Wrong Project Approval",
        )

        with pytest.raises(ValueError, match="does not match"):
            await service.create(request)


class TestApprovalServiceDelete(TestApprovalServiceBase):
    """Test ApprovalService.delete method."""

    @pytest.mark.asyncio
    async def test_delete_pending_approval_success(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that a pending approval can be deleted."""
        service = self._create_test_service(test_db_session, test_user)

        executions = await executions_factory.create_executions(count=1)
        execution_id = executions[0].id

        approvals = await approvals_factory.create_approvals(
            count=1, execution_id=execution_id, name_prefix="Delete Test"
        )
        approval = approvals[0]

        await service.delete(approval.id)

        result = await service.list(limit=10, include_total=True)
        assert all(a.id != approval.id for a in result.resources)

    @pytest.mark.asyncio
    async def test_delete_already_decided_raises_exception(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that deleting an already-decided approval raises ApprovalAlreadyDecidedError."""
        service = self._create_test_service(test_db_session, test_user)

        executions = await executions_factory.create_executions(count=1)
        execution_id = executions[0].id

        approvals = await approvals_factory.create_approvals(
            count=1,
            execution_id=execution_id,
            name_prefix="Already Decided",
            statuses=[ApprovalRequestStatus.APPROVED],
        )
        approval = approvals[0]

        with pytest.raises(ApprovalAlreadyDecidedError) as exc_info:
            await service.delete(approval.id)

        assert exc_info.value.approval_id == approval.id

    @pytest.mark.asyncio
    async def test_delete_nonexistent_approval_raises_not_found(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test that deleting a nonexistent approval raises ApprovalNotFoundError."""
        service = self._create_test_service(test_db_session, test_user)

        non_existent_id = uuid4()
        with pytest.raises(ApprovalNotFoundError):
            await service.delete(non_existent_id)

    @pytest.mark.asyncio
    async def test_delete_unauthorized_raises_not_authorized(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that deleting without authorization raises ApprovalNotAuthorizedError."""
        service = self._create_test_service(test_db_session, test_user)

        executions = await executions_factory.create_executions(count=1)
        execution_id = executions[0].id

        approvals = await approvals_factory.create_approvals(
            count=1, execution_id=execution_id, name_prefix="Unauth Delete"
        )
        approval = approvals[0]

        with patch.object(service, "_is_user_authorized_approver", new_callable=AsyncMock, return_value=False):
            with pytest.raises(ApprovalNotAuthorizedError) as exc_info:
                await service.delete(approval.id)

        assert exc_info.value.approval_id == approval.id
        assert exc_info.value.user_id == test_user.id

    @pytest.mark.asyncio
    async def test_delete_toctou_race_decided_raises_already_decided(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test TOCTOU: approval decided between status check and DELETE raises AlreadyDecided."""
        service = self._create_test_service(test_db_session, test_user)

        fake_id = uuid4()
        pending_approval = MagicMock()
        pending_approval.id = fake_id
        pending_approval.status = ApprovalRequestStatus.PENDING

        decided_approval = MagicMock()
        decided_approval.id = fake_id
        decided_approval.status = ApprovalRequestStatus.APPROVED

        with (
            patch.object(
                service,
                "_get_approval_by_id",
                new_callable=AsyncMock,
                side_effect=[pending_approval, decided_approval],
            ),
            patch.object(service, "_is_user_authorized_approver", new_callable=AsyncMock, return_value=True),
        ):
            with pytest.raises(ApprovalAlreadyDecidedError):
                await service.delete(fake_id)

    @pytest.mark.asyncio
    async def test_delete_toctou_race_vanished_raises_not_found(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test TOCTOU: approval vanishes between status check and DELETE raises NotFound."""
        service = self._create_test_service(test_db_session, test_user)

        fake_id = uuid4()
        pending_approval = MagicMock()
        pending_approval.id = fake_id
        pending_approval.status = ApprovalRequestStatus.PENDING

        with (
            patch.object(
                service,
                "_get_approval_by_id",
                new_callable=AsyncMock,
                side_effect=[pending_approval, None],
            ),
            patch.object(service, "_is_user_authorized_approver", new_callable=AsyncMock, return_value=True),
        ):
            with pytest.raises(ApprovalNotFoundError):
                await service.delete(fake_id)

    @pytest.mark.asyncio
    async def test_delete_concurrent_decide_race_returns_409(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test TOCTOU: if approval is decided between read and delete, returns 409."""
        service = self._create_test_service(test_db_session, test_user)

        executions = await executions_factory.create_executions(count=1)
        execution_id = executions[0].id

        approvals = await approvals_factory.create_approvals(
            count=1, execution_id=execution_id, name_prefix="Race Test"
        )
        approval = approvals[0]

        # Simulate a concurrent decide by updating status directly
        approval.status = ApprovalRequestStatus.APPROVED
        test_db_session.add(approval)
        await test_db_session.commit()

        with pytest.raises(ApprovalAlreadyDecidedError):
            await service.delete(approval.id)


class TestApprovalServiceDecide(TestApprovalServiceBase):
    """Test ApprovalService.decide method."""

    @pytest.mark.asyncio
    async def test_decide_approve_success(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test successful approve decision."""
        service = self._create_test_service(test_db_session, test_user)

        # Create a test execution first
        executions = await executions_factory.create_executions(count=1)
        execution_id = executions[0].id

        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=execution_id)
        approval = approvals[0]

        # Mock workflow client to avoid external dependencies
        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            decision_request = self._create_decision_request(
                status=ApprovalDecisionStatus.APPROVED, notes="Looks good to proceed!"
            )

            result = await service.decide(approval.id, decision_request)

            assert result.status == ApprovalRequestStatus.APPROVED
            assert result.decided_by is not None
            assert result.decided_by.id == test_user.id
            assert result.decided_by.name == test_user.display_name
            assert result.decision_notes == "Looks good to proceed!"
            assert result.decided_at is not None

            # Verify workflow signal was sent
            mock_client.send_approval_signal.assert_called_once_with(
                execution_id=approval.execution_id,
                approval_node_id=approval.approval_node_id,
                decision="approved",
                approval_id=approval.id,
                decided_by=test_user.username,
                decided_at=ANY,
                temporal_activity_id=ANY,
                decision_notes="Looks good to proceed!",
            )

    @pytest.mark.asyncio
    async def test_decide_reject_success(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test successful reject decision."""
        service = self._create_test_service(test_db_session, test_user)

        # Create a test execution first
        executions = await executions_factory.create_executions(count=1)
        execution_id = executions[0].id

        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=execution_id)
        approval = approvals[0]

        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            decision_request = self._create_decision_request(
                status=ApprovalDecisionStatus.REJECTED, notes="Insufficient justification"
            )

            result = await service.decide(approval.id, decision_request)

            assert result.status == ApprovalRequestStatus.REJECTED
            assert result.decided_by is not None
            assert result.decided_by.id == test_user.id
            assert result.decided_by.name == test_user.display_name
            assert result.decision_notes == "Insufficient justification"

            # Verify workflow signal was sent with rejection
            mock_client.send_approval_signal.assert_called_once_with(
                execution_id=approval.execution_id,
                approval_node_id=approval.approval_node_id,
                decision="rejected",
                approval_id=approval.id,
                decided_by=test_user.username,
                decided_at=ANY,
                temporal_activity_id=ANY,
                decision_notes="Insufficient justification",
            )

    @pytest.mark.asyncio
    async def test_decide_not_found(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test decide when approval not found."""
        service = self._create_test_service(test_db_session, test_user)

        non_existent_id = uuid4()

        decision_request = self._create_decision_request(status=ApprovalDecisionStatus.APPROVED)
        with pytest.raises(ApprovalNotFoundError):
            await service.decide(non_existent_id, decision_request)

    @pytest.mark.asyncio
    async def test_decide_already_decided(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test decide when approval already decided."""
        service = self._create_test_service(test_db_session, test_user)

        # Create a test execution first
        executions = await executions_factory.create_executions(count=1)
        execution_id = executions[0].id

        # Create already approved request
        approvals = await approvals_factory.create_approvals(
            count=1, execution_id=execution_id, statuses=[ApprovalRequestStatus.APPROVED]
        )
        approval = approvals[0]

        decision_request = self._create_decision_request(status=ApprovalDecisionStatus.APPROVED)
        with pytest.raises(ApprovalAlreadyDecidedError) as exc_info:
            await service.decide(approval.id, decision_request)

        assert exc_info.value.approval_id == approval.id
        assert exc_info.value.current_status == ApprovalRequestStatus.APPROVED

    @pytest.mark.asyncio
    async def test_decide_workflow_signal_failure(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test decide when workflow signal sending fails."""
        service = self._create_test_service(test_db_session, test_user)

        # Create a test execution first
        executions = await executions_factory.create_executions(count=1)
        execution_id = executions[0].id

        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=execution_id)
        approval = approvals[0]

        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            # Make workflow signal fail
            mock_client.send_approval_signal = AsyncMock(side_effect=Exception("Workflow service unavailable"))

            decision_request = self._create_decision_request(
                status=ApprovalDecisionStatus.APPROVED, notes="Should succeed despite signal failure"
            )

            result = await service.decide(approval.id, decision_request)

            # Decision should still be recorded as successful even if signal fails
            assert result.status == ApprovalRequestStatus.APPROVED
            assert result.decided_by is not None
            assert result.decided_by.id == test_user.id
            assert result.decided_by.name == test_user.display_name
            assert result.decision_notes == "Should succeed despite signal failure"

            # Verify approval was updated in database
            await test_db_session.refresh(approval)
            assert approval.status == ApprovalRequestStatus.APPROVED
            assert approval.decided_by == test_user.id


class TestApprovalServiceBatchDecide(TestApprovalServiceBase):
    """Test ApprovalService.batch_decide method."""

    @pytest.mark.asyncio
    async def test_batch_decide_all_success(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test successful batch decision with all approval status types.

        Verifies signals only for approved/rejected decisions.
        """
        service = self._create_test_service(test_db_session, test_user)

        # Create test execution
        executions = await executions_factory.create_executions(count=1)
        execution_id = executions[0].id

        # Create multiple pending approvals
        approvals = await approvals_factory.create_pending_approvals(
            count=4, execution_id=execution_id, name_prefix="Batch Test"
        )

        # Mock workflow client
        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            # Create batch decisions including all status types
            decisions = [
                self._create_batch_decision(approvals[0].id, BatchApprovalDecisionStatus.APPROVED, "Looks good"),
                self._create_batch_decision(approvals[1].id, BatchApprovalDecisionStatus.REJECTED, "Needs changes"),
                self._create_batch_decision(approvals[2].id, BatchApprovalDecisionStatus.CANCELLED, "No longer needed"),
                self._create_batch_decision(approvals[3].id, BatchApprovalDecisionStatus.EXPIRED, "Timed out"),
            ]
            batch_request = self._create_batch_approval_request(decisions)

            result = await service.batch_decide(batch_request)

            # Verify response structure
            assert len(result.results) == 4
            assert result.total_success == 4
            assert result.total_failed == 0

            # Verify individual results
            assert result.results[0].success is True
            assert result.results[0].status == ApprovalRequestStatus.APPROVED
            assert result.results[0].decision_notes == "Looks good"
            assert result.results[0].decided_by is not None
            assert result.results[0].decided_by.id == test_user.id
            assert result.results[0].decided_by.name == test_user.display_name
            assert result.results[0].decided_at is not None
            assert result.results[0].error is None

            assert result.results[1].success is True
            assert result.results[1].status == ApprovalRequestStatus.REJECTED
            assert result.results[1].decision_notes == "Needs changes"

            assert result.results[2].success is True
            assert result.results[2].status == ApprovalRequestStatus.CANCELLED
            assert result.results[2].decision_notes == "No longer needed"

            assert result.results[3].success is True
            assert result.results[3].status == ApprovalRequestStatus.EXPIRED
            assert result.results[3].decision_notes == "Timed out"

            # Verify workflow signals were sent only for approved/rejected decisions (not cancelled/expired)
            assert mock_client.send_approval_signal.call_count == 2

            # Verify the specific calls were made for approved and rejected only
            calls = mock_client.send_approval_signal.call_args_list
            assert len(calls) == 2

            # First call should be for the approved decision
            assert calls[0][1]["decision"] == BatchApprovalDecisionStatus.APPROVED
            assert calls[0][1]["approval_id"] == approvals[0].id
            assert calls[0][1]["decision_notes"] == "Looks good"

            # Second call should be for the rejected decision
            assert calls[1][1]["decision"] == BatchApprovalDecisionStatus.REJECTED
            assert calls[1][1]["approval_id"] == approvals[1].id
            assert calls[1][1]["decision_notes"] == "Needs changes"

    @pytest.mark.asyncio
    async def test_batch_decide_mixed_success_and_failure(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test batch decision with some successes and some failures."""
        service = self._create_test_service(test_db_session, test_user)

        # Create test execution
        executions = await executions_factory.create_executions(count=1)
        execution_id = executions[0].id

        # Create pending and already decided approvals
        pending_approvals = await approvals_factory.create_pending_approvals(
            count=2, execution_id=execution_id, name_prefix="Pending"
        )
        decided_approvals = await approvals_factory.create_approvals(
            count=1, execution_id=execution_id, statuses=[ApprovalRequestStatus.APPROVED], name_prefix="Already Decided"
        )

        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            # Create batch decisions including some that should fail
            decisions = [
                self._create_batch_decision(
                    pending_approvals[0].id, BatchApprovalDecisionStatus.APPROVED, "Good to go"
                ),
                self._create_batch_decision(
                    decided_approvals[0].id, BatchApprovalDecisionStatus.REJECTED, "Try again"
                ),  # Already decided
                self._create_batch_decision(
                    pending_approvals[1].id, BatchApprovalDecisionStatus.REJECTED, "This should work"
                ),  # Valid decision
                self._create_batch_decision(
                    uuid4(), BatchApprovalDecisionStatus.APPROVED, "Non-existent"
                ),  # Non-existent approval
            ]
            batch_request = self._create_batch_approval_request(decisions)

            result = await service.batch_decide(batch_request)

            # Verify response counts
            assert len(result.results) == 4
            assert result.total_success == 2
            assert result.total_failed == 2

            # Verify successful results
            assert result.results[0].success is True
            assert result.results[0].status == ApprovalRequestStatus.APPROVED
            assert result.results[0].error is None

            assert result.results[2].success is True
            assert result.results[2].status == ApprovalRequestStatus.REJECTED
            assert result.results[2].error is None

            # Verify failure results
            assert result.results[1].success is False
            assert result.results[1].error is not None
            assert "already approved" in result.results[1].error

            assert result.results[3].success is False
            assert result.results[3].error is not None
            assert "Approval not found" in result.results[3].error

            # Two workflow signals should be sent (for the successful decisions)
            assert mock_client.send_approval_signal.call_count == 2

    @pytest.mark.asyncio
    async def test_batch_decide_approval_not_found(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test batch decision with non-existent approval IDs."""
        service = self._create_test_service(test_db_session, test_user)

        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            # Create batch decision with non-existent approval IDs
            decisions = [
                self._create_batch_decision(uuid4(), BatchApprovalDecisionStatus.APPROVED, "Non-existent 1"),
                self._create_batch_decision(uuid4(), BatchApprovalDecisionStatus.REJECTED, "Non-existent 2"),
            ]
            batch_request = self._create_batch_approval_request(decisions)

            result = await service.batch_decide(batch_request)

            # All should fail
            assert len(result.results) == 2
            assert result.total_success == 0
            assert result.total_failed == 2

            # Verify all results are failures with correct error messages
            for result_item in result.results:
                assert result_item.success is False
                assert result_item.error is not None
                assert "Approval not found" in result_item.error
                assert result_item.status is None
                assert result_item.decided_at is None

            # No workflow signals should be sent
            assert mock_client.send_approval_signal.call_count == 0

    @pytest.mark.asyncio
    async def test_batch_decide_already_decided_approvals(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test batch decision with already decided approvals."""
        service = self._create_test_service(test_db_session, test_user)

        # Create test execution
        executions = await executions_factory.create_executions(count=1)
        execution_id = executions[0].id

        # Create approvals with various decided statuses
        approved_approvals = await approvals_factory.create_approvals(
            count=1, execution_id=execution_id, statuses=[ApprovalRequestStatus.APPROVED]
        )
        rejected_approvals = await approvals_factory.create_approvals(
            count=1, execution_id=execution_id, statuses=[ApprovalRequestStatus.REJECTED]
        )
        cancelled_approvals = await approvals_factory.create_approvals(
            count=1, execution_id=execution_id, statuses=[ApprovalRequestStatus.CANCELLED]
        )

        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Try to decide on already decided approvals
            decisions = [
                self._create_batch_decision(
                    approved_approvals[0].id, BatchApprovalDecisionStatus.REJECTED, "Change decision"
                ),
                self._create_batch_decision(
                    rejected_approvals[0].id, BatchApprovalDecisionStatus.APPROVED, "Reconsider"
                ),
                self._create_batch_decision(
                    cancelled_approvals[0].id, BatchApprovalDecisionStatus.APPROVED, "Reactivate"
                ),
            ]
            batch_request = self._create_batch_approval_request(decisions)

            result = await service.batch_decide(batch_request)

            # All should fail
            assert result.total_success == 0
            assert result.total_failed == 3

            # Verify specific error messages contain current status
            assert result.results[0].error is not None
            assert "already approved" in result.results[0].error
            assert result.results[1].error is not None
            assert "already rejected" in result.results[1].error
            assert result.results[2].error is not None
            assert "already cancelled" in result.results[2].error

    @pytest.mark.asyncio
    async def test_batch_decide_with_notes(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test batch decision with various notes values including None."""
        service = self._create_test_service(test_db_session, test_user)

        # Create test execution and approvals
        executions = await executions_factory.create_executions(count=1)
        execution_id = executions[0].id

        approvals = await approvals_factory.create_pending_approvals(count=3, execution_id=execution_id)

        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            # Create decisions with different notes patterns
            decisions = [
                self._create_batch_decision(
                    approvals[0].id, BatchApprovalDecisionStatus.APPROVED, "Detailed notes here"
                ),
                self._create_batch_decision(approvals[1].id, BatchApprovalDecisionStatus.REJECTED, None),  # No notes
                self._create_batch_decision(
                    approvals[2].id, BatchApprovalDecisionStatus.CANCELLED, ""
                ),  # Empty string notes
            ]
            batch_request = self._create_batch_approval_request(decisions)

            result = await service.batch_decide(batch_request)

            # All should succeed
            assert result.total_success == 3
            assert result.total_failed == 0

            # Verify notes are handled correctly
            assert result.results[0].decision_notes == "Detailed notes here"
            assert result.results[1].decision_notes is None
            assert result.results[2].decision_notes == ""

    @pytest.mark.asyncio
    async def test_batch_decide_workflow_signal_failure(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test batch decision when workflow signal sending fails."""
        service = self._create_test_service(test_db_session, test_user)

        # Create test execution and approval
        executions = await executions_factory.create_executions(count=1)
        execution_id = executions[0].id

        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=execution_id)

        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            # Make workflow signal fail
            mock_client.send_approval_signal = AsyncMock(side_effect=Exception("Workflow service unavailable"))

            decisions = [
                self._create_batch_decision(
                    approvals[0].id, BatchApprovalDecisionStatus.APPROVED, "Should succeed despite signal failure"
                ),
            ]
            batch_request = self._create_batch_approval_request(decisions)

            result = await service.batch_decide(batch_request)

            # Decision should still be recorded as successful even if signal fails
            assert result.total_success == 1
            assert result.total_failed == 0
            assert result.results[0].success is True
            assert result.results[0].status == ApprovalRequestStatus.APPROVED

            # Verify approval was updated in database
            await test_db_session.refresh(approvals[0])
            assert approvals[0].status == ApprovalRequestStatus.APPROVED
            assert approvals[0].decided_by == test_user.id
