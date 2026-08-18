"""Contract tests for PATCH /api/v1/approvals/{id} endpoint.

Tests validation of OpenAPI schema compliance including:
- Request schema validation (status enum restricted to approved/rejected/cancelled)
- Response schema validation
- Error responses (400, 404, 409)
- State transition validation

Task T029 from AAP-64408 acceptance criteria.
"""

from unittest.mock import ANY, AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from syntara.approvals.models import ApprovalRequestStatus
from tests.integration.helpers.approval import ApprovalsFactory
from tests.integration.helpers.error_data import assert_error_data
from tests.integration.helpers.workflow import ExecutionsFactory


class TestDecideApprovalContract:
    """Contract tests for PATCH /api/v1/approvals/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_decide_approval_approved_request_schema(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test approval decision with 'approved' status.

        Validates:
        - Request schema accepts 'approved' status
        - Optional notes field works correctly
        - Response schema matches specification
        - Status transition from pending to approved
        - Decision metadata is populated correctly
        """
        # Arrange - Create execution first, then pending approval
        executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=executions[0].id)
        approval_id = str(approvals[0].id)

        # Act - Submit approval decision (with mocked workflow client)
        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            decision_payload = {"status": "approved", "notes": "This change looks good to deploy to production."}
            response = await auth_client.patch(f"/api/v1/approvals/{approval_id}", json=decision_payload)

        # Assert
        assert response.status_code == 200
        data = response.json()

        # Validate response structure
        assert "id" in data
        assert "status" in data
        assert "decided_by" in data
        assert "decided_at" in data
        assert "decision_notes" in data

        # Validate decision values
        assert data["id"] == approval_id
        assert data["status"] == "approved"
        assert data["decided_by"] is not None
        assert data["decided_at"] is not None
        assert data["decision_notes"] == "This change looks good to deploy to production."

        # Validate timestamps are ISO format strings
        assert isinstance(data["decided_at"], str)
        # Basic ISO format check (should contain 'T' and timezone)
        assert "T" in data["decided_at"]
        assert data["decided_at"].endswith("+00:00") or data["decided_at"].endswith("Z")

        # Verify workflow signal was sent with correct parameters
        mock_client.send_approval_signal.assert_called_once_with(
            execution_id=approvals[0].execution_id,
            approval_node_id=approvals[0].approval_node_id,
            decision="approved",
            approval_id=approvals[0].id,
            decided_by=ANY,
            decided_at=ANY,
            decision_notes="This change looks good to deploy to production.",
        )

    @pytest.mark.asyncio
    async def test_decide_approval_rejected_request_schema(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test approval decision with 'rejected' status.

        Validates:
        - Request schema accepts 'rejected' status
        - Status transition from pending to rejected
        - Decision metadata populated correctly
        """
        # Arrange - Create execution first, then pending approval
        executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=executions[0].id)
        approval_id = str(approvals[0].id)

        # Act - Submit rejection decision (with mocked workflow client)
        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            decision_payload = {"status": "rejected", "notes": "This change needs more testing before deployment."}
            response = await auth_client.patch(f"/api/v1/approvals/{approval_id}", json=decision_payload)

        # Assert
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "rejected"
        assert data["decision_notes"] == "This change needs more testing before deployment."
        assert data["decided_by"] is not None
        assert data["decided_at"] is not None

        # Verify workflow signal was sent with correct parameters
        mock_client.send_approval_signal.assert_called_once_with(
            execution_id=approvals[0].execution_id,
            approval_node_id=approvals[0].approval_node_id,
            decision="rejected",
            approval_id=approvals[0].id,
            decided_by=ANY,
            decided_at=ANY,
            decision_notes="This change needs more testing before deployment.",
        )

    @pytest.mark.asyncio
    async def test_decide_approval_accepts_decision_notes_alias(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Regression for AAP-87655: request accepts the ``decision_notes`` alias.

        Consumers that model their request on the response schema send
        ``decision_notes``. Previously this key was silently dropped; it must now
        populate the notes field, be stored, echoed in the response, and forwarded
        on the workflow signal.
        """
        # Arrange
        executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=executions[0].id)
        approval_id = str(approvals[0].id)

        # Act - submit using the response-shaped `decision_notes` key
        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            decision_payload = {"status": "approved", "decision_notes": "Approved via alias key"}
            response = await auth_client.patch(f"/api/v1/approvals/{approval_id}", json=decision_payload)

        # Assert - value is not silently dropped
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        assert data["decision_notes"] == "Approved via alias key"

        mock_client.send_approval_signal.assert_called_once_with(
            execution_id=approvals[0].execution_id,
            approval_node_id=approvals[0].approval_node_id,
            decision="approved",
            approval_id=approvals[0].id,
            decided_by=ANY,
            decided_at=ANY,
            decision_notes="Approved via alias key",
        )

    @pytest.mark.asyncio
    async def test_decide_approval_without_notes(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test approval decision without optional notes field.

        Validates:
        - notes field is optional and can be omitted
        - notes field can be explicitly null
        - Decision still succeeds without notes
        """
        # Arrange - Create executions first, then pending approvals
        executions = await executions_factory.create_executions(count=2)
        approvals = await approvals_factory.create_pending_approvals(count=2, execution_id=executions[0].id)

        # Test 1: Omit notes field entirely (with mocked workflow client)
        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            approval_id_1 = str(approvals[0].id)
            decision_payload_1 = {"status": "approved"}
            response = await auth_client.patch(f"/api/v1/approvals/{approval_id_1}", json=decision_payload_1)

            # Verify workflow signal was sent with correct parameters (notes=None)
            mock_client.send_approval_signal.assert_called_once_with(
                execution_id=approvals[0].execution_id,
                approval_node_id=approvals[0].approval_node_id,
                decision="approved",
                approval_id=approvals[0].id,
                decided_by=ANY,
                decided_at=ANY,
                decision_notes=None,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        assert data["decision_notes"] is None

        # Test 2: Explicitly set notes to null (with mocked workflow client)
        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client_2 = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client_2
            mock_client_2.send_approval_signal = AsyncMock()

            approval_id_2 = str(approvals[1].id)
            decision_payload_2: dict[str, str | None] = {"status": "rejected", "notes": None}
            response = await auth_client.patch(f"/api/v1/approvals/{approval_id_2}", json=decision_payload_2)

            # Verify workflow signal was sent with correct parameters (notes=None)
            mock_client_2.send_approval_signal.assert_called_once_with(
                execution_id=approvals[1].execution_id,
                approval_node_id=approvals[1].approval_node_id,
                decision="rejected",
                approval_id=approvals[1].id,
                decided_by=ANY,
                decided_at=ANY,
                decision_notes=None,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"
        assert data["decision_notes"] is None

    @pytest.mark.asyncio
    async def test_decide_approval_invalid_status_values_error(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that invalid status values return validation errors.

        Validates:
        - Invalid status enum values return 422
        - Only approved/rejected/cancelled are accepted
        - Proper error format for bad requests
        """
        # Arrange
        executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=executions[0].id)
        approval_id = str(approvals[0].id)

        # Test invalid status values
        invalid_statuses = ["pending", "expired", "invalid", "approved_typo", ""]

        for invalid_status in invalid_statuses:
            decision_payload = {"status": invalid_status}
            response = await auth_client.patch(f"/api/v1/approvals/{approval_id}", json=decision_payload)

            assert response.status_code == 422, (
                f"Expected 422 for status '{invalid_status}', got {response.status_code}"
            )
            assert_error_data(
                response,
                error_type="https://api.example.com/errors/validation-error",
                title="Request Validation Error",
                detail=("Validation failed: status: Input should be 'approved' or 'rejected'"),
                code="REQUEST_VALIDATION_ERROR",
                retryable=False,
            )

    @pytest.mark.asyncio
    async def test_decide_approval_missing_required_fields_error(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that missing required fields return validation errors.

        Validates:
        - Missing status field returns 422
        - Empty request body returns 422
        """
        # Arrange
        executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=executions[0].id)
        approval_id = str(approvals[0].id)

        # Test missing status field
        decision_payload = {"notes": "Missing status field"}
        response = await auth_client.patch(f"/api/v1/approvals/{approval_id}", json=decision_payload)
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail="Validation failed: status: Field required",
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

        # Test empty request body
        response = await auth_client.patch(f"/api/v1/approvals/{approval_id}", json={})
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail="Validation failed: status: Field required",
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_decide_approval_not_found_error_response(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that non-existent approval returns 404 error.

        Validates:
        - Non-existent approval ID returns 404 Not Found
        - Error response format matches specification
        """
        # Act
        non_existent_id = str(uuid4())
        decision_payload = {"status": "approved"}
        response = await auth_client.patch(f"/api/v1/approvals/{non_existent_id}", json=decision_payload)

        # Assert
        assert response.status_code == 404
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/resource-not-found",
            title="Approval Not Found",
            detail="The requested approval was not found",
            code="APPROVAL_NOT_FOUND",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_decide_approval_already_decided_conflict_error(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that already-decided approval returns 409 conflict error.

        Validates:
        - Attempting to decide already-approved approval returns 409
        - Attempting to decide already-rejected approval returns 409
        - Error response indicates the conflict reason
        """
        # Arrange - Create already-approved approval
        approved_executions = await executions_factory.create_executions(count=1)
        approved_approvals = await approvals_factory.create_approvals(
            count=1, statuses=[ApprovalRequestStatus.APPROVED], execution_id=approved_executions[0].id
        )
        approved_id = str(approved_approvals[0].id)

        # Act - Try to decide already-approved approval
        decision_payload = {"status": "rejected", "notes": "Changing mind"}
        response = await auth_client.patch(f"/api/v1/approvals/{approved_id}", json=decision_payload)

        # Assert
        assert response.status_code == 409
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/resource-conflict",
            title="Approval Already Decided",
            detail="The approval request has already been decided and cannot be modified",
            code="APPROVAL_ALREADY_DECIDED",
            retryable=False,
        )

        # Arrange - Create already-rejected approval
        rejected_executions = await executions_factory.create_executions(count=1)
        rejected_approvals = await approvals_factory.create_approvals(
            count=1, statuses=[ApprovalRequestStatus.REJECTED], execution_id=rejected_executions[0].id
        )
        rejected_id = str(rejected_approvals[0].id)

        # Act - Try to decide already-rejected approval
        decision_payload = {"status": "approved", "notes": "Changing mind again"}
        response = await auth_client.patch(f"/api/v1/approvals/{rejected_id}", json=decision_payload)

        # Assert
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
    async def test_decide_approval_invalid_uuid_format_error(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that invalid UUID format returns validation error.

        Validates:
        - Invalid UUID in path returns 422
        - Path parameter validation works correctly
        """
        # Act
        invalid_uuid = "not-a-valid-uuid"
        decision_payload = {"status": "approved"}
        response = await auth_client.patch(f"/api/v1/approvals/{invalid_uuid}", json=decision_payload)

        # Assert
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail="Validation failed: path -> approval_id: Invalid UUID format: not-a-valid-uuid",
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_decide_approval_notes_length_validation(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that notes field length validation works correctly.

        Validates:
        - Very long notes are handled appropriately
        - Notes field length constraints match OpenAPI spec
        """
        # Arrange
        executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=executions[0].id)
        approval_id = str(approvals[0].id)

        # Test reasonable length notes (should succeed) (with mocked workflow client)
        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            normal_notes = "This is a normal length note for the approval decision."
            decision_payload = {"status": "approved", "notes": normal_notes}
            response = await auth_client.patch(f"/api/v1/approvals/{approval_id}", json=decision_payload)

            # Verify workflow signal was sent with correct parameters
            mock_client.send_approval_signal.assert_called_once_with(
                execution_id=approvals[0].execution_id,
                approval_node_id=approvals[0].approval_node_id,
                decision="approved",
                approval_id=approvals[0].id,
                decided_by=ANY,
                decided_at=ANY,
                decision_notes=normal_notes,
            )

        assert response.status_code == 200

        # Test very long notes (OpenAPI spec shows max 2000 chars)
        # Create another approval for the long notes test
        long_executions = await executions_factory.create_executions(count=1)
        long_approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=long_executions[0].id)
        long_approval_id = str(long_approvals[0].id)

        # 2000 characters should be acceptable (with mocked workflow client)
        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            acceptable_long_notes = "a" * 2000
            decision_payload = {"status": "approved", "notes": acceptable_long_notes}
            response = await auth_client.patch(f"/api/v1/approvals/{long_approval_id}", json=decision_payload)

            # Verify workflow signal was sent with correct parameters
            mock_client.send_approval_signal.assert_called_once_with(
                execution_id=long_approvals[0].execution_id,
                approval_node_id=long_approvals[0].approval_node_id,
                decision="approved",
                approval_id=long_approvals[0].id,
                decided_by=ANY,
                decided_at=ANY,
                decision_notes=acceptable_long_notes,
            )

        assert response.status_code == 200

        # Test extremely long notes (over 2000 chars should fail)
        extreme_executions = await executions_factory.create_executions(count=1)
        extreme_approvals = await approvals_factory.create_pending_approvals(
            count=1, execution_id=extreme_executions[0].id
        )
        extreme_approval_id = str(extreme_approvals[0].id)

        too_long_notes = "a" * 2001  # Over the limit
        decision_payload = {"status": "approved", "notes": too_long_notes}
        response = await auth_client.patch(f"/api/v1/approvals/{extreme_approval_id}", json=decision_payload)
        assert response.status_code == 422  # Should exceed length limit
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail="Validation failed: notes: String should have at most 2000 characters",
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_decide_approval_surfaces_signal_delivery_error(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that signal delivery failure is surfaced in the response.

        Validates:
        - Decision still succeeds with 200 (the decision is durable)
        - signal_delivery_error field contains the error message
        """
        executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=executions[0].id)
        approval_id = str(approvals[0].id)

        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock(side_effect=Exception("Connection refused"))

            response = await auth_client.patch(
                f"/api/v1/approvals/{approval_id}",
                json={"status": "approved"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        assert data["signal_delivery_error"] == "Workflow signal delivery failed"

    @pytest.mark.asyncio
    async def test_decide_approval_signal_success_has_no_error(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that successful signal delivery leaves signal_delivery_error as null."""
        executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=executions[0].id)
        approval_id = str(approvals[0].id)

        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            response = await auth_client.patch(
                f"/api/v1/approvals/{approval_id}",
                json={"status": "approved"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["signal_delivery_error"] is None
