"""Contract tests for GET /api/v1/approvals/{id} endpoint.

Tests validation of OpenAPI schema compliance including:
- Response schema validation (all fields present, nullable fields, WorkflowContext structure)
- Proper HTTP status codes
- Field validation and data types

Task T028 from AAP-64408 acceptance criteria.
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from syntara.approvals.models import ApprovalRequestStatus
from syntara.core.models import User
from tests.integration.helpers.approval import ApprovalsFactory
from tests.integration.helpers.error_data import assert_error_data
from tests.integration.helpers.workflow import ExecutionsFactory


class TestGetApprovalContract:
    """Contract tests for GET /api/v1/approvals/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_approval_response_schema_pending_status(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test that response schema matches OpenAPI specification for pending approval.

        Validates:
        - All required fields are present
        - Nullable fields are handled correctly
        - Data types match specification
        - WorkflowContext structure is correct
        - ActivitySummary structures are correct
        """
        # Arrange - Create execution first, then pending approval with full data
        executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=executions[0].id)
        approval_id = str(approvals[0].id)

        # Act
        response = await auth_client.get(f"/api/v1/approvals/{approval_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()

        # Validate all required fields are present
        required_fields = [
            "id",
            "execution_id",
            "approval_node_id",
            "name",
            "status",
            "next_step_approved",
            "workflow_context",
            "created_at",
            "updated_at",
        ]
        for field in required_fields:
            assert field in data, f"Required field '{field}' missing from response"

        # Validate nullable fields are present (but may be null for pending)
        nullable_fields = [
            "timeout_at",
            "next_step_rejected",
            "decided_by",
            "decided_at",
            "decision_notes",
        ]
        for field in nullable_fields:
            assert field in data, f"Nullable field '{field}' missing from response"

        # Validate data types and values for pending approval
        assert isinstance(data["id"], str)
        assert isinstance(data["execution_id"], str)
        assert isinstance(data["approval_node_id"], str)
        assert isinstance(data["name"], str)
        assert data["status"] == ApprovalRequestStatus.PENDING.value
        assert isinstance(data["created_at"], str)
        assert isinstance(data["updated_at"], str)

        # For pending approval, decision fields should be null
        assert data["decided_by"] is None
        assert data["decided_at"] is None
        assert data["decision_notes"] is None

        # Validate WorkflowContext structure
        workflow_context = data["workflow_context"]
        assert isinstance(workflow_context, dict)
        context_required_fields = ["workflow_name", "inputs"]
        for field in context_required_fields:
            assert field in workflow_context, f"Required WorkflowContext field '{field}' missing"

        assert isinstance(workflow_context["workflow_id"], str)
        assert isinstance(workflow_context["workflow_name"], str)
        assert isinstance(workflow_context["inputs"], dict)

        # previous_step is optional
        if "previous_step" in workflow_context and workflow_context["previous_step"] is not None:
            prev_step = workflow_context["previous_step"]
            prev_step_required = ["id", "name", "type"]
            for field in prev_step_required:
                assert field in prev_step, f"Required PreviousStepContext field '{field}' missing"

        # Validate ActivitySummary structures
        next_step_approved = data["next_step_approved"]
        assert isinstance(next_step_approved, dict)
        activity_required_fields = ["id", "name", "type"]
        for field in activity_required_fields:
            assert field in next_step_approved, f"Required ActivitySummary field '{field}' missing"

    @pytest.mark.asyncio
    async def test_get_approval_response_schema_decided_status(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
        test_user: User,
    ) -> None:
        """Test response schema for approved/rejected approval with decision data.

        Validates:
        - Decision fields are populated for decided approvals
        - decided_by, decided_at, decision_notes have correct values
        - All other fields remain consistent
        """
        # Arrange - Create execution first, then approved approval
        executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_approvals(
            count=1, statuses=[ApprovalRequestStatus.APPROVED], execution_id=executions[0].id
        )
        approval_id = str(approvals[0].id)

        # Act
        response = await auth_client.get(f"/api/v1/approvals/{approval_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()

        # Validate basic structure
        assert data["status"] == ApprovalRequestStatus.APPROVED.value

        # For approved approval, decision fields should be populated
        assert data["decided_by"] is not None
        assert isinstance(data["decided_by"], dict)
        assert "id" in data["decided_by"]
        assert "name" in data["decided_by"]
        assert data["decided_by"]["id"] == str(test_user.id)
        assert data["decided_by"]["name"] == test_user.display_name
        assert data["decided_at"] is not None
        assert isinstance(data["decided_at"], str)  # ISO datetime string
        assert data["decision_notes"] is not None
        assert isinstance(data["decision_notes"], str)

        # Validate the decision values match expectations
        assert "Approved:" in data["decision_notes"]

        # Create rejected approval for comparison
        rejected_executions = await executions_factory.create_executions(count=1)
        rejected_approvals = await approvals_factory.create_approvals(
            count=1, statuses=[ApprovalRequestStatus.REJECTED], execution_id=rejected_executions[0].id
        )
        rejected_id = str(rejected_approvals[0].id)

        # Act
        response = await auth_client.get(f"/api/v1/approvals/{rejected_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == ApprovalRequestStatus.REJECTED.value
        assert "Rejected:" in data["decision_notes"]

    @pytest.mark.asyncio
    async def test_get_approval_workflow_context_structure_validation(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test detailed WorkflowContext structure validation.

        Validates:
        - workflow_id is valid UUID string
        - workflow_name is non-empty string
        - inputs is object (can be empty)
        - previous_step structure when present
        - previous_step output structure when present
        """
        # Arrange
        executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=executions[0].id)
        approval_id = str(approvals[0].id)

        # Act
        response = await auth_client.get(f"/api/v1/approvals/{approval_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()

        workflow_context = data["workflow_context"]

        # Validate workflow_id is UUID format
        workflow_id = workflow_context["workflow_id"]
        assert isinstance(workflow_id, str)
        # Validate it's a valid UUID by trying to parse it
        uuid_obj = uuid4()
        try:
            parsed_uuid = type(uuid_obj)(workflow_id)
            assert str(parsed_uuid) == workflow_id
        except ValueError:
            pytest.fail(f"workflow_id '{workflow_id}' is not a valid UUID")

        # Validate workflow_name
        assert isinstance(workflow_context["workflow_name"], str)
        assert len(workflow_context["workflow_name"]) > 0

        # Validate inputs structure
        inputs = workflow_context["inputs"]
        assert isinstance(inputs, dict)
        # inputs can be empty, but if present, values should be serializable

        # Validate previous_step if present
        if workflow_context.get("previous_step"):
            prev_step = workflow_context["previous_step"]
            assert isinstance(prev_step, dict)

            # Required fields
            assert "id" in prev_step
            assert "name" in prev_step
            assert "type" in prev_step
            assert isinstance(prev_step["id"], str)
            assert isinstance(prev_step["name"], str)
            assert isinstance(prev_step["type"], str)

            # Optional output field
            if "output" in prev_step and prev_step["output"] is not None:
                assert isinstance(prev_step["output"], dict)

    @pytest.mark.asyncio
    async def test_get_approval_activity_summary_structure_validation(
        self,
        auth_client: AsyncClient,
        approvals_factory: ApprovalsFactory,
        executions_factory: ExecutionsFactory,
    ) -> None:
        """Test ActivitySummary structure validation in detail.

        Validates:
        - next_step_approved structure (always present)
        - next_step_rejected structure (may be null)
        - Required and optional fields in ActivitySummary
        """
        # Arrange - Create execution first, then approval with both approved and rejected steps
        executions = await executions_factory.create_executions(count=1)
        approvals = await approvals_factory.create_pending_approvals(count=1, execution_id=executions[0].id)
        approval_id = str(approvals[0].id)

        # Act
        response = await auth_client.get(f"/api/v1/approvals/{approval_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()

        # Validate next_step_approved (should always be present)
        next_step_approved = data["next_step_approved"]
        assert isinstance(next_step_approved, dict)

        approved_required_fields = ["id", "name", "type"]
        for field in approved_required_fields:
            assert field in next_step_approved
            assert isinstance(next_step_approved[field], str)
            assert len(next_step_approved[field]) > 0

        # Optional description field
        if "description" in next_step_approved and next_step_approved["description"] is not None:
            assert isinstance(next_step_approved["description"], str)

        # Validate next_step_rejected (may be null)
        next_step_rejected = data["next_step_rejected"]
        if next_step_rejected is not None:
            assert isinstance(next_step_rejected, dict)

            rejected_required_fields = ["id", "name", "type"]
            for field in rejected_required_fields:
                assert field in next_step_rejected
                assert isinstance(next_step_rejected[field], str)
                assert len(next_step_rejected[field]) > 0

    @pytest.mark.asyncio
    async def test_get_approval_not_found_error_response(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that non-existent approval returns proper 404 error.

        Validates:
        - Non-existent UUID returns 404 Not Found
        - Error response format matches RFC 9457
        """
        # Act
        non_existent_id = str(uuid4())
        response = await auth_client.get(f"/api/v1/approvals/{non_existent_id}")

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
    async def test_get_approval_invalid_uuid_format_error(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """Test that invalid UUID format returns validation error.

        Validates:
        - Invalid UUID format returns 422 Unprocessable Entity
        - Path parameter validation works correctly
        """
        # Act
        invalid_uuid = "not-a-valid-uuid"
        response = await auth_client.get(f"/api/v1/approvals/{invalid_uuid}")

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
