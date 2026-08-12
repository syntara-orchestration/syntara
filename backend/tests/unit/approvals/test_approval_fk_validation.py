"""Unit tests for approval FK validation.

Tests the foreign key validation for approver user/group IDs:
- Invalid user IDs are rejected
- Invalid group IDs are rejected
- Valid IDs are accepted
"""

from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.approvals.models import (
    ActivitySummary,
    ApprovalCreateRequest,
    ApprovalRequestStatus,
    WorkflowContext,
)
from syntara.approvals.services.approval_service import ApprovalService
from syntara.core.models import Group, User
from tests.integration.helpers.workflow import ExecutionsFactory


class TestApprovalFKValidation:
    """Test foreign key validation for approval approvers."""

    @pytest.mark.asyncio
    async def test_create_with_invalid_user_id_fails(
        self, test_db_session: AsyncSession, users: dict[str, User], executions_factory: ExecutionsFactory
    ) -> None:
        """Test that creating approval with non-existent user ID fails."""
        user = users["user_1"]
        executions = await executions_factory.create_executions(count=1)
        execution = executions[0]

        invalid_user_id = uuid4()  # Non-existent user

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

        request = ApprovalCreateRequest(
            execution_id=execution.id,
            approval_node_id="approval_1",
            name="Test Approval",
            timeout_at=None,
            next_step_approved=next_step_approved,
            next_step_rejected=None,
            workflow_context=workflow_context,
            approver_user_ids=[invalid_user_id],
            approver_group_ids=None,
            project_id=execution.project_id,
        )

        service = ApprovalService(test_db_session, user)

        with pytest.raises(ValueError):
            await service.create(request)

    @pytest.mark.asyncio
    async def test_create_with_invalid_group_id_fails(
        self, test_db_session: AsyncSession, users: dict[str, User], executions_factory: ExecutionsFactory
    ) -> None:
        """Test that creating approval with non-existent group ID fails."""
        user = users["user_1"]
        executions = await executions_factory.create_executions(count=1)
        execution = executions[0]

        invalid_group_id = uuid4()  # Non-existent group

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

        request = ApprovalCreateRequest(
            execution_id=execution.id,
            approval_node_id="approval_1",
            name="Test Approval",
            timeout_at=None,
            next_step_approved=next_step_approved,
            next_step_rejected=None,
            workflow_context=workflow_context,
            approver_user_ids=None,
            approver_group_ids=[invalid_group_id],
            project_id=execution.project_id,
        )

        service = ApprovalService(test_db_session, user)

        with pytest.raises(ValueError):
            await service.create(request)

    @pytest.mark.asyncio
    async def test_create_with_valid_ids_succeeds(
        self, test_db_session: AsyncSession, users: dict[str, User], executions_factory: ExecutionsFactory
    ) -> None:
        """Test that creating approval with valid user/group IDs succeeds."""
        user = users["user_1"]
        executions = await executions_factory.create_executions(count=1)
        execution = executions[0]

        # Create a group
        group = Group(name="approvers")
        test_db_session.add(group)
        await test_db_session.commit()
        await test_db_session.refresh(group)

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

        request = ApprovalCreateRequest(
            execution_id=execution.id,
            approval_node_id="approval_1",
            name="Test Approval",
            timeout_at=None,
            next_step_approved=next_step_approved,
            next_step_rejected=None,
            workflow_context=workflow_context,
            approver_user_ids=[user.id],
            approver_group_ids=[group.id],
            project_id=execution.project_id,
        )

        service = ApprovalService(test_db_session, user)
        approval = await service.create(request)

        assert approval.id is not None
        assert approval.status == ApprovalRequestStatus.PENDING
        assert len(approval.approver_users) == 1
        assert approval.approver_users[0].id == user.id
        assert len(approval.approver_groups) == 1
        assert approval.approver_groups[0].id == group.id
