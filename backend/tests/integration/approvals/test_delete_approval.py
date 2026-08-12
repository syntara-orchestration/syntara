"""Contract tests for DELETE /api/v1/approvals/{id} endpoint.

Tests validation of the delete approval endpoint including:
- Successful deletion of pending approvals
- Error responses for already-decided and nonexistent approvals
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from syntara.approvals.models import ApprovalRequestStatus
from tests.integration.helpers.approval import ApprovalsFactory
from tests.integration.helpers.error_data import assert_error_data
from tests.integration.helpers.workflow import ExecutionsFactory


class TestDeleteApprovalContract:
    """Contract tests for DELETE /api/v1/approvals/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_pending_approval_returns_204(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that deleting a pending approval succeeds with 204."""
        executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=executions[0].id)
        approval_id = str(approvals[0].id)

        response = await auth_client.delete(f"/api/v1/approvals/{approval_id}")

        assert response.status_code == 204

        # Verify the approval is gone
        get_response = await auth_client.get(f"/api/v1/approvals/{approval_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_already_decided_returns_409(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that deleting an already-decided approval returns 409."""
        executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_approvals(
            count=1, execution_id=executions[0].id, name_prefix="Decided", statuses=[ApprovalRequestStatus.APPROVED]
        )
        approval_id = str(approvals[0].id)

        response = await auth_client.delete(f"/api/v1/approvals/{approval_id}")

        assert response.status_code == 409
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/resource-conflict",
            title="Approval Already Decided",
            detail="The approval request has already been decided and cannot be modified",
            code="APPROVAL_ALREADY_DECIDED",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_delete_nonexistent_approval_returns_404(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that deleting a nonexistent approval returns 404."""
        response = await auth_client.delete(f"/api/v1/approvals/{uuid4()}")

        assert response.status_code == 404
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/resource-not-found",
            title="Approval Not Found",
            detail="The requested approval was not found",
            code="APPROVAL_NOT_FOUND",
            retryable=False,
        )
