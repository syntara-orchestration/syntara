"""Contract tests for POST /api/v1/approvals/batch endpoint.

Tests validation of OpenAPI schema compliance including:
- BatchApprovalRequest/Response schema validation
- Decisions array validation
- Results with success/error handling
- Counts validation (total_success, total_failed)

Task T030 from AAP-64408 acceptance criteria.
"""

from unittest.mock import ANY, AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from syntara.approvals.models import ApprovalRequestStatus
from syntara.core.models import User
from tests.integration.helpers.approval import ApprovalsFactory
from tests.integration.helpers.error_data import assert_error_data
from tests.integration.helpers.workflow import ExecutionsFactory


class TestBatchApprovalContract:
    """Contract tests for POST /api/v1/approvals/batch endpoint."""

    @pytest.mark.asyncio
    async def test_batch_approval_all_success_response_schema(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
        test_user: User,
    ) -> None:
        """Test batch approval where all decisions succeed.

        Validates:
        - BatchApprovalRequest schema validation
        - BatchApprovalResponse schema validation
        - All decisions succeed scenario
        - Results array structure
        - Success/failure counts are correct
        """
        # Arrange - Create executions first, then multiple pending approvals
        executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_pending_approvals(count=4, execution_id=executions[0].id)
        approval_ids = [str(approval.id) for approval in approvals]

        # Act - Submit batch decisions (all different statuses) with mocked workflow client
        batch_payload = {
            "decisions": [
                {"approval_id": approval_ids[0], "status": "approved", "notes": "First approval looks good"},
                {"approval_id": approval_ids[1], "status": "rejected", "notes": "Second approval needs work"},
                {"approval_id": approval_ids[2], "status": "cancelled", "notes": "Third approval is cancelled"},
                {"approval_id": approval_ids[3], "status": "expired", "notes": "Fourth approval expired"},
            ]
        }

        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            response = await auth_client.post("/api/v1/approvals/batch", json=batch_payload)

        # Assert
        assert response.status_code == 200
        data = response.json()

        # Validate BatchApprovalResponse structure
        required_fields = ["results", "total_success", "total_failed"]
        for field in required_fields:
            assert field in data, f"Required field '{field}' missing from batch response"

        # Validate results array
        results = data["results"]
        assert isinstance(results, list)
        assert len(results) == 4

        # Validate each result matches BatchApprovalResult schema
        for i, result in enumerate(results):
            result_required_fields = ["approval_id", "success"]
            for field in result_required_fields:
                assert field in result, f"Required field '{field}' missing from result {i}"

            assert result["approval_id"] == approval_ids[i]
            assert result["success"] is True, f"Decision {i} failed: {result.get('error')}"

            # For successful results, these fields should be present
            success_fields = ["status", "decided_at", "decided_by", "decision_notes"]
            for field in success_fields:
                assert field in result, f"Success field '{field}' missing from successful result {i}"
                assert result[field] is not None

            # Validate status matches request
            expected_status = batch_payload["decisions"][i]["status"]
            assert result["status"] == expected_status

            # Validate decided_by matches request
            assert result["decided_by"] is not None
            assert result["decided_by"]["id"] == str(test_user.id)
            assert result["decided_by"]["name"] == test_user.display_name

            # Validate notes match request
            expected_notes = batch_payload["decisions"][i]["notes"]
            assert result["decision_notes"] == expected_notes

            # Error field should be null for successful results
            assert result.get("error") is None

        # Validate counts
        assert data["total_success"] == 4
        assert data["total_failed"] == 0

        # Verify workflow signals were sent with correct parameters
        # Workflow signals are not sent for 'cancelled' or 'expired' statuses
        assert mock_client.send_approval_signal.call_count == 2
        expected_calls = [
            mock_client.send_approval_signal.call_args_list[i][1]  # Get kwargs from call
            for i in range(2)
        ]

        # Validate each call had the expected parameters
        for i, call_kwargs in enumerate(expected_calls):
            assert call_kwargs["execution_id"] == approvals[i].execution_id
            assert call_kwargs["approval_node_id"] == approvals[i].approval_node_id
            assert call_kwargs["decision"] == batch_payload["decisions"][i]["status"]
            assert call_kwargs["approval_id"] == approvals[i].id
            assert call_kwargs["decision_notes"] == batch_payload["decisions"][i]["notes"]

    @pytest.mark.asyncio
    async def test_batch_approval_accepts_decision_notes_alias(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Regression for AAP-87655: batch decisions accept the ``decision_notes`` alias.

        A decision that supplies the response-shaped ``decision_notes`` key must have
        its notes stored, echoed in the result, and forwarded on the workflow signal
        rather than silently dropped.
        """
        # Arrange
        executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=executions[0].id)

        batch_payload = {
            "decisions": [
                {"approval_id": str(approvals[0].id), "status": "approved", "decision_notes": "Batch alias note"},
            ]
        }

        # Act
        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            response = await auth_client.post("/api/v1/approvals/batch", json=batch_payload)

        # Assert - value is not silently dropped
        assert response.status_code == 200
        data = response.json()
        assert data["total_success"] == 1
        assert data["total_failed"] == 0
        assert data["results"][0]["decision_notes"] == "Batch alias note"

        mock_client.send_approval_signal.assert_called_once_with(
            execution_id=approvals[0].execution_id,
            approval_node_id=approvals[0].approval_node_id,
            decision="approved",
            approval_id=approvals[0].id,
            decided_by=ANY,
            decided_at=ANY,
            decision_notes="Batch alias note",
        )

    @pytest.mark.asyncio
    async def test_batch_approval_mixed_success_failure_response_schema(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test batch approval with mix of successful and failed decisions.

        Validates:
        - Partial failure handling
        - Error field populated for failures
        - Success field indicates success/failure correctly
        - Counts reflect actual results
        """
        # Arrange - Create executions first, then some pending approvals and some already-decided
        pending_executions = await executions_factory.create_executions(count=2)
        pending_approvals = await approvals_factory.create_pending_approvals(
            count=2, execution_id=pending_executions[0].id
        )
        decided_executions = await executions_factory.create_executions(count=1)
        decided_approvals = await approvals_factory.create_approvals(
            count=1, statuses=[ApprovalRequestStatus.APPROVED], execution_id=decided_executions[0].id
        )

        # Act - Try to decide both pending and already-decided approvals with mocked workflow client
        batch_payload = {
            "decisions": [
                {"approval_id": str(pending_approvals[0].id), "status": "approved", "notes": "This should succeed"},
                {
                    "approval_id": str(decided_approvals[0].id),
                    "status": "rejected",
                    "notes": "This should fail - already decided",
                },
                {
                    "approval_id": str(pending_approvals[1].id),
                    "status": "approved",
                    "notes": "This should also succeed",
                },
                {
                    "approval_id": str(uuid4()),  # Non-existent approval
                    "status": "approved",
                    "notes": "This should fail - not found",
                },
            ]
        }

        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            response = await auth_client.post("/api/v1/approvals/batch", json=batch_payload)

        # Assert
        assert response.status_code == 200
        data = response.json()

        results = data["results"]
        assert len(results) == 4

        # First result should succeed
        assert results[0]["success"] is True
        assert results[0]["error"] is None
        assert results[0]["status"] == "approved"

        # Second result should fail (already decided)
        assert results[1]["success"] is False
        assert results[1]["error"] is not None
        assert isinstance(results[1]["error"], str)
        assert "already" in results[1]["error"].lower()
        # Failed results should not have success fields
        assert results[1].get("status") is None
        assert results[1].get("decided_at") is None

        # Third result should succeed
        assert results[2]["success"] is True
        assert results[2]["error"] is None
        assert results[2]["status"] == "approved"

        # Fourth result should fail (not found)
        assert results[3]["success"] is False
        assert results[3]["error"] is not None
        assert "not found" in results[3]["error"].lower()

        # Validate counts
        assert data["total_success"] == 2
        assert data["total_failed"] == 2

        # Verify workflow signals were sent only for successful decisions (2 calls, not 4)
        assert mock_client.send_approval_signal.call_count == 2
        # Verify the successful calls were for the pending approvals
        successful_calls = mock_client.send_approval_signal.call_args_list
        # First successful call (index 0)
        assert successful_calls[0][1]["execution_id"] == pending_approvals[0].execution_id
        assert successful_calls[0][1]["approval_node_id"] == pending_approvals[0].approval_node_id
        assert successful_calls[0][1]["decision"] == "approved"
        assert successful_calls[0][1]["approval_id"] == pending_approvals[0].id
        assert successful_calls[0][1]["decision_notes"] == "This should succeed"

        # Second successful call (index 2 from batch, index 1 in successful_calls)
        assert successful_calls[1][1]["execution_id"] == pending_approvals[1].execution_id
        assert successful_calls[1][1]["approval_node_id"] == pending_approvals[1].approval_node_id
        assert successful_calls[1][1]["decision"] == "approved"
        assert successful_calls[1][1]["approval_id"] == pending_approvals[1].id
        assert successful_calls[1][1]["decision_notes"] == "This should also succeed"

    @pytest.mark.asyncio
    async def test_batch_approval_decisions_array_validation(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that decisions array validation works correctly.

        Validates:
        - decisions array is required
        - decisions array cannot be empty
        - decisions array has maximum length constraint
        - Each decision has required fields
        """
        # Test missing decisions array
        response = await auth_client.post("/api/v1/approvals/batch", json={})
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail="Validation failed: decisions: Field required",
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

        # Test empty decisions array
        empty_payload: dict[str, list[dict[str, str]]] = {"decisions": []}
        response = await auth_client.post("/api/v1/approvals/batch", json=empty_payload)
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail="Validation failed: decisions: List should have at least 1 item after validation, not 0",
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

        # Test single valid decision (should succeed)
        single_executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=single_executions[0].id)
        single_payload = {
            "decisions": [{"approval_id": str(approvals[0].id), "status": "approved", "notes": "Single decision test"}]
        }
        # Test single valid decision with mocked workflow client
        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            response = await auth_client.post("/api/v1/approvals/batch", json=single_payload)

            # Verify workflow signal was sent with correct parameters
            mock_client.send_approval_signal.assert_called_once_with(
                execution_id=approvals[0].execution_id,
                approval_node_id=approvals[0].approval_node_id,
                decision="approved",
                approval_id=approvals[0].id,
                decided_by=ANY,
                decided_at=ANY,
                decision_notes="Single decision test",
            )

        assert response.status_code == 200

        # Test decisions array at max length (OpenAPI shows max 100)
        # Create enough executions and approvals for max batch
        executions = await executions_factory.create_executions(count=1)
        max_approvals = await approvals_factory.create_pending_approvals(count=100, execution_id=executions[0].id)
        max_payload = {
            "decisions": [
                {
                    "approval_id": str(approval.id),
                    "status": "approved" if i % 2 == 0 else "rejected",
                    "notes": f"Decision {i + 1}",
                }
                for i, approval in enumerate(max_approvals)
            ]
        }
        num_decisions_made = len(max_payload["decisions"])
        assert num_decisions_made == 100

        # Test max batch size with mocked workflow client
        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            response = await auth_client.post("/api/v1/approvals/batch", json=max_payload)
        assert response.status_code == 200

        # Validate all 100 were processed
        data = response.json()
        assert len(data["results"]) == num_decisions_made
        assert data["total_success"] == num_decisions_made  # All should succeed
        assert data["total_failed"] == 0

        # Verify workflow signal was called 100 times
        assert mock_client.send_approval_signal.call_count == num_decisions_made
        for i in range(num_decisions_made):
            call_kwargs = mock_client.send_approval_signal.call_args_list[i][1]
            assert call_kwargs["execution_id"] == max_approvals[i].execution_id
            assert call_kwargs["approval_node_id"] == max_approvals[i].approval_node_id
            assert call_kwargs["decision"] == max_payload["decisions"][i]["status"]
            assert call_kwargs["approval_id"] == max_approvals[i].id
            assert call_kwargs["decision_notes"] == max_payload["decisions"][i]["notes"]

    @pytest.mark.asyncio
    async def test_batch_approval_decision_field_validation(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test individual decision field validation.

        Validates:
        - approval_id field is required and must be valid UUID
        - status field is required and must be valid enum
        - notes field is optional
        """
        # Arrange
        executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=executions[0].id)
        valid_approval_id = str(approvals[0].id)

        # Test missing approval_id
        payload_missing_id = {"decisions": [{"status": "approved", "notes": "Missing approval_id"}]}
        response = await auth_client.post("/api/v1/approvals/batch", json=payload_missing_id)
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail="Validation failed: decisions -> 0 -> approval_id: Field required",
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

        # Test invalid approval_id format
        payload_invalid_id = {"decisions": [{"approval_id": "not-a-uuid", "status": "approved"}]}
        response = await auth_client.post("/api/v1/approvals/batch", json=payload_invalid_id)
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail=(
                "Validation failed: decisions -> 0 -> approval_id: Input should be a valid UUID, "
                "invalid character: found `n` at 1"
            ),
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

        # Test missing status
        payload_missing_status = {"decisions": [{"approval_id": valid_approval_id, "notes": "Missing status"}]}
        response = await auth_client.post("/api/v1/approvals/batch", json=payload_missing_status)
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail="Validation failed: decisions -> 0 -> status: Field required",
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

        # Test invalid status value
        payload_invalid_status = {"decisions": [{"approval_id": valid_approval_id, "status": "invalid_status"}]}
        response = await auth_client.post("/api/v1/approvals/batch", json=payload_invalid_status)
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail=(
                "Validation failed: decisions -> 0 -> status: "
                "Input should be 'approved', 'rejected', 'expired' or 'cancelled'"
            ),
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

        # Test valid decision without notes (should succeed) with mocked workflow client
        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            payload_no_notes = {"decisions": [{"approval_id": valid_approval_id, "status": "approved"}]}
            response = await auth_client.post("/api/v1/approvals/batch", json=payload_no_notes)
        assert response.status_code == 200

        # Validate notes is null when not provided
        data = response.json()
        assert data["results"][0]["decision_notes"] is None

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

    @pytest.mark.asyncio
    async def test_batch_approval_status_enum_validation(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that all valid status enum values work in batch.

        Validates:
        - approved, rejected, cancelled all work
        - Invalid status values are rejected
        - Mixed valid statuses work together
        """
        # Arrange
        executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_pending_approvals(count=3, execution_id=executions[0].id)

        # Test all valid statuses
        valid_payload = {
            "decisions": [
                {"approval_id": str(approvals[0].id), "status": "approved", "notes": "Test approved"},
                {"approval_id": str(approvals[1].id), "status": "rejected", "notes": "Test rejected"},
                {"approval_id": str(approvals[2].id), "status": "cancelled", "notes": "Test cancelled"},
            ]
        }

        # Test all valid statuses with mocked workflow client
        with patch("syntara.approvals.services.approval_service.WorkflowApiClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.send_approval_signal = AsyncMock()

            response = await auth_client.post("/api/v1/approvals/batch", json=valid_payload)
        assert response.status_code == 200

        data = response.json()
        assert data["total_success"] == 3
        assert data["results"][0]["status"] == "approved"
        assert data["results"][1]["status"] == "rejected"
        assert data["results"][2]["status"] == "cancelled"

        # Verify workflow signals were sent for 2 decisions
        # Signals are only sent for approved and rejected. cancelled does not emit a signal
        assert mock_client.send_approval_signal.call_count == 2
        for i, call_kwargs in enumerate([call[1] for call in mock_client.send_approval_signal.call_args_list]):
            assert call_kwargs["execution_id"] == approvals[i].execution_id
            assert call_kwargs["approval_node_id"] == approvals[i].approval_node_id
            assert call_kwargs["decision"] == valid_payload["decisions"][i]["status"]
            assert call_kwargs["approval_id"] == approvals[i].id
            assert call_kwargs["decision_notes"] == valid_payload["decisions"][i]["notes"]

        # Test invalid status in batch
        more_executions = await executions_factory.create_executions(count=1)
        more_approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=more_executions[0].id)
        invalid_payload = {
            "decisions": [
                {
                    "approval_id": str(more_approvals[0].id),
                    "status": "pending",  # Not allowed for decisions
                }
            ]
        }
        response = await auth_client.post("/api/v1/approvals/batch", json=invalid_payload)
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail=(
                "Validation failed: decisions -> 0 -> status: "
                "Input should be 'approved', 'rejected', 'expired' or 'cancelled'"
            ),
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_batch_approval_empty_request_error(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that invalid request formats return proper errors.

        Validates:
        - Empty request body returns 422
        - Invalid JSON returns 400
        - Non-object request returns 422
        """
        # Test completely empty body
        response = await auth_client.post("/api/v1/approvals/batch", content="")
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail="Validation failed: root: Field required",
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

        # Test non-JSON content type
        response = await auth_client.post("/api/v1/approvals/batch", content="not json")
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail=("Validation failed: root: Input should be a valid dictionary or object to extract fields from"),
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )
