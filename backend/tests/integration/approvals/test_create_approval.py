"""Contract tests for POST /api/v1/approvals endpoint.

Tests validation of OpenAPI schema compliance including:
- Request schema validation (required fields, UUID formats, ActivitySummary structure)
- Response schema validation
- Proper HTTP status codes
- Field validation and constraints

Task T027 from AAP-64408 acceptance criteria.
"""

from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from syntara.approvals.models import ApprovalRequestStatus
from syntara.workflows.models import Workflow
from tests.integration.helpers.error_data import assert_error_data
from tests.integration.helpers.workflow import ExecutionsFactory


class TestCreateApprovalContract:
    """Contract tests for POST /api/v1/approvals endpoint."""

    @pytest.mark.asyncio
    async def test_create_approval_valid_request_schema(
        self,
        auth_client: AsyncClient,
        executions_factory: ExecutionsFactory,
        test_workflow: Workflow,
    ) -> None:
        """Test that valid request creates approval and returns correct response schema.

        Validates:
        - All required fields are accepted
        - UUID formats are validated correctly
        - ActivitySummary structure is correct
        - WorkflowContext structure is correct
        - Response matches OpenAPI specification
        """
        # Arrange
        # Create execution first to get valid execution_id
        executions = await executions_factory.create_executions(count=1)
        execution_id = str(executions[0].id)
        workflow_id = str(uuid4())

        request_payload = {
            "execution_id": execution_id,
            "project_id": str(test_workflow.project_id),
            "approval_node_id": "test_approval_node",
            "name": "Test Approval Request",
            "description": "This is a test approval request for contract testing",
            "timeout_at": "2024-12-31T23:59:59Z",
            "next_step_approved": {
                "id": "approved_step",
                "name": "Approved Step",
                "type": "task",
                "description": "Step to execute when approved",
            },
            "next_step_rejected": {
                "id": "rejected_step",
                "name": "Rejected Step",
                "type": "task",
                "description": "Step to execute when rejected",
            },
            "workflow_context": {
                "workflow_id": workflow_id,
                "workflow_name": "Test Workflow",
                "inputs": {"environment": "test", "version": "1.0.0"},
                "previous_step": {
                    "id": "prep_step",
                    "name": "Preparation Step",
                    "type": "task",
                    "output": {"data_prepared": True, "rows_processed": 100},
                },
            },
        }

        # Act
        response = await auth_client.post("/api/v1/approvals", json=request_payload)

        # Assert
        assert response.status_code == 201
        data = response.json()

        # Validate response structure matches OpenAPI spec
        required_response_fields = [
            "id",
            "execution_id",
            "approval_node_id",
            "loop_iteration_path",
            "name",
            "status",
            "next_step_approved",
            "workflow_context",
            "created_at",
            "updated_at",
        ]
        for field in required_response_fields:
            assert field in data, f"Required field '{field}' missing from response"

        # Validate specific field values
        assert data["execution_id"] == execution_id
        assert data["approval_node_id"] == "test_approval_node"
        assert data["loop_iteration_path"] == []
        assert data["name"] == "Test Approval Request"
        assert data["status"] == ApprovalRequestStatus.PENDING.value
        assert data["timeout_at"] == "2024-12-31T23:59:59Z"  # Should be normalized

        # Validate ActivitySummary structures
        assert data["next_step_approved"]["id"] == "approved_step"
        assert data["next_step_approved"]["name"] == "Approved Step"
        assert data["next_step_approved"]["type"] == "task"

        assert data["next_step_rejected"]["id"] == "rejected_step"
        assert data["next_step_rejected"]["name"] == "Rejected Step"

        # Validate WorkflowContext structure
        assert data["workflow_context"]["workflow_id"] == workflow_id
        assert data["workflow_context"]["workflow_name"] == "Test Workflow"
        assert data["workflow_context"]["inputs"]["environment"] == "test"
        assert data["workflow_context"]["previous_step"]["id"] == "prep_step"

    @pytest.mark.asyncio
    async def test_create_approval_minimal_required_fields(
        self,
        auth_client: AsyncClient,
        executions_factory: ExecutionsFactory,
        test_workflow: Workflow,
    ) -> None:
        """Test creation with only required fields (optional fields as null).

        Validates:
        - Minimal valid request succeeds
        - Optional fields can be omitted or null
        - Default values are applied correctly
        """
        # Arrange - Only required fields
        # Create execution first to get valid execution_id
        executions = await executions_factory.create_executions(count=1)
        execution_id = str(executions[0].id)
        workflow_id = str(uuid4())

        request_payload = {
            "execution_id": execution_id,
            "project_id": str(test_workflow.project_id),
            "approval_node_id": "minimal_approval",
            "name": "Minimal Approval",
            "next_step_approved": {
                "id": "next_step",
                "name": "Next Step",
                "type": "task",
            },
            "workflow_context": {
                "workflow_id": workflow_id,
                "workflow_name": "Minimal Workflow",
                "inputs": {},
            },
        }

        # Act
        response = await auth_client.post("/api/v1/approvals", json=request_payload)

        # Assert
        assert response.status_code == 201
        data = response.json()

        # Validate required fields are present
        assert data["execution_id"] == execution_id
        assert data["approval_node_id"] == "minimal_approval"
        assert data["name"] == "Minimal Approval"
        assert data["status"] == ApprovalRequestStatus.PENDING.value

        # Validate optional fields are handled properly
        assert data["timeout_at"] is None
        assert data["next_step_rejected"] is None
        assert data["prompt"] is None

        # next_step_approved is required
        assert data["next_step_approved"]["id"] == "next_step"

    @pytest.mark.asyncio
    async def test_create_approval_persists_prompt(
        self,
        auth_client: AsyncClient,
        executions_factory: ExecutionsFactory,
        test_workflow: Workflow,
    ) -> None:
        """Resolved prompt is stored on the approval and returned in the response."""
        executions = await executions_factory.create_executions(count=1)
        execution_id = str(executions[0].id)
        prompt = "Please review this $15,000 infrastructure budget request for Q3 cloud upgrade."

        request_payload = {
            "execution_id": execution_id,
            "project_id": str(test_workflow.project_id),
            "approval_node_id": "prompt_approval",
            "name": "Budget Review",
            "prompt": f"  {prompt}  ",
            "next_step_approved": {
                "id": "next_step",
                "name": "Next Step",
                "type": "task",
            },
            "workflow_context": {
                "workflow_id": str(uuid4()),
                "workflow_name": "Budget Workflow",
                "inputs": {},
            },
        }

        create_response = await auth_client.post("/api/v1/approvals", json=request_payload)
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["prompt"] == prompt

        get_response = await auth_client.get(f"/api/v1/approvals/{created['id']}")
        assert get_response.status_code == 200
        assert get_response.json()["prompt"] == prompt

    @pytest.mark.asyncio
    async def test_create_approval_uuid_format_validation(
        self,
        auth_client: AsyncClient,
        executions_factory: ExecutionsFactory,
        test_workflow: Workflow,
    ) -> None:
        """Test that UUID format validation works correctly.

        Validates:
        - Valid UUIDs are accepted
        - Invalid UUID formats return 422 validation error
        """
        # Arrange - Valid request with proper UUIDs
        # Create execution first to get valid execution_id
        executions = await executions_factory.create_executions(count=1)
        valid_payload = {
            "execution_id": str(executions[0].id),
            "project_id": str(test_workflow.project_id),
            "approval_node_id": "uuid_test",
            "name": "UUID Test",
            "next_step_approved": {
                "id": "next_step",
                "name": "Next Step",
                "type": "task",
            },
            "workflow_context": {
                "workflow_id": str(uuid4()),
                "workflow_name": "UUID Test Workflow",
                "inputs": {},
            },
        }

        # Act - Valid UUIDs should succeed
        response = await auth_client.post("/api/v1/approvals", json=valid_payload)
        assert response.status_code == 201

        # Act & Assert - Invalid execution_id format
        invalid_payload = dict(valid_payload)
        invalid_payload["execution_id"] = "not-a-valid-uuid"

        response = await auth_client.post("/api/v1/approvals", json=invalid_payload)
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail=("Validation failed: execution_id: Input should be a valid UUID, invalid character: found `n` at 1"),
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

        # Act & Assert - Invalid workflow_id format
        invalid_payload = dict(valid_payload)
        invalid_payload["workflow_context"] = {
            "workflow_id": "not-a-uuid",
            "workflow_name": "Test",
            "inputs": {},
        }

        response = await auth_client.post("/api/v1/approvals", json=invalid_payload)
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail=(
                "Validation failed: workflow_context -> workflow_id: Input should be a valid UUID, "
                "invalid character: found `n` at 1"
            ),
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_create_approval_required_field_validation(
        self,
        auth_client: AsyncClient,
        executions_factory: ExecutionsFactory,
        test_workflow: Workflow,
    ) -> None:
        """Test that missing required fields return validation errors.

        Validates:
        - Missing execution_id returns 422
        - Missing project_id returns 422
        - Missing approval_node_id returns 422
        - Missing name returns 422
        - Missing workflow_context returns 422
        """
        # Base valid payload
        # Create execution first to get valid execution_id
        executions = await executions_factory.create_executions(count=1)
        base_payload = {
            "execution_id": str(executions[0].id),
            "project_id": str(test_workflow.project_id),
            "approval_node_id": "test_node",
            "name": "Test Name",
            "next_step_approved": {"id": "next_step", "name": "Next Step", "type": "task"},
            "workflow_context": {"workflow_id": str(uuid4()), "workflow_name": "Test Workflow", "inputs": {}},
        }

        # Test missing execution_id
        payload = dict(base_payload)
        del payload["execution_id"]
        response = await auth_client.post("/api/v1/approvals", json=payload)
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail="Validation failed: execution_id: Field required",
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

        # Test missing project_id
        payload = dict(base_payload)
        del payload["project_id"]
        response = await auth_client.post("/api/v1/approvals", json=payload)
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail="Validation failed: project_id: Field required",
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

        # Test missing approval_node_id
        payload = dict(base_payload)
        del payload["approval_node_id"]
        response = await auth_client.post("/api/v1/approvals", json=payload)
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail="Validation failed: approval_node_id: Field required",
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

        # Test missing name
        payload = dict(base_payload)
        del payload["name"]
        response = await auth_client.post("/api/v1/approvals", json=payload)
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail="Validation failed: name: Field required",
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

        # Test missing workflow_context
        payload = dict(base_payload)
        del payload["workflow_context"]
        response = await auth_client.post("/api/v1/approvals", json=payload)
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail="Validation failed: workflow_context: Field required",
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_create_approval_activity_summary_structure_validation(
        self,
        auth_client: AsyncClient,
        executions_factory: ExecutionsFactory,
        test_workflow: Workflow,
    ) -> None:
        """Test that ActivitySummary structures are validated correctly.

        Validates:
        - Required ActivitySummary fields (id, name, type)
        - Optional description field
        - Invalid ActivitySummary structure returns 422
        """
        # Base payload
        # Create execution first to get valid execution_id
        executions = await executions_factory.create_executions(count=1)
        base_payload = {
            "execution_id": str(executions[0].id),
            "project_id": str(test_workflow.project_id),
            "name": "Activity Test",
            "workflow_context": {"workflow_id": str(uuid4()), "workflow_name": "Test Workflow", "inputs": {}},
        }

        # Test valid ActivitySummary with all fields
        payload = dict(base_payload)
        payload["approval_node_id"] = "activity_test_1"
        payload["next_step_approved"] = {
            "id": "step_1",
            "name": "Step One",
            "type": "task",
            "description": "Optional description",
        }
        response = await auth_client.post("/api/v1/approvals", json=payload)
        assert response.status_code == 201

        # Test valid ActivitySummary with only required fields
        payload = dict(base_payload)
        payload["approval_node_id"] = "activity_test_2"
        payload["next_step_approved"] = {"id": "step_2", "name": "Step Two", "type": "parallel"}
        response = await auth_client.post("/api/v1/approvals", json=payload)
        assert response.status_code == 201

        # Test invalid ActivitySummary - missing required field
        payload = dict(base_payload)
        payload["approval_node_id"] = "activity_test_3"
        payload["next_step_approved"] = {
            "id": "step_3",
            "name": "Step Three",
            # Missing 'type' field
        }
        response = await auth_client.post("/api/v1/approvals", json=payload)
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail="Validation failed: next_step_approved -> type: Field required",
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_create_approval_workflow_context_structure_validation(
        self,
        auth_client: AsyncClient,
        executions_factory: ExecutionsFactory,
        test_workflow: Workflow,
    ) -> None:
        """Test that WorkflowContext structure is validated correctly.

        Validates:
        - Required WorkflowContext fields
        - Optional previous_step field
        - PreviousStepContext structure validation
        """
        # Base payload
        # Create execution first to get valid execution_id
        executions = await executions_factory.create_executions(count=1)
        base_payload = {
            "execution_id": str(executions[0].id),
            "project_id": str(test_workflow.project_id),
            "name": "Context Test",
            "next_step_approved": {"id": "next_step", "name": "Next Step", "type": "task"},
        }

        # Test valid WorkflowContext with previous_step
        payload_1: dict[str, Any] = dict(base_payload)
        payload_1["approval_node_id"] = "context_test_1"
        payload_1["workflow_context"] = {
            "workflow_id": str(uuid4()),
            "workflow_name": "Test Workflow",
            "inputs": {"key": "value"},
            "previous_step": {
                "id": "prev_step",
                "name": "Previous Step",
                "type": "task",
                "output": {"result": "success"},
            },
        }
        response = await auth_client.post("/api/v1/approvals", json=payload_1)
        assert response.status_code == 201

        # Test valid WorkflowContext without previous_step (omitted)
        payload_2: dict[str, Any] = dict(base_payload)
        payload_2["approval_node_id"] = "context_test_2"
        payload_2["workflow_context"] = {
            "workflow_id": str(uuid4()),
            "workflow_name": "Test Workflow",
            "inputs": {},
        }
        response = await auth_client.post("/api/v1/approvals", json=payload_2)
        assert response.status_code == 201

        # Test valid WorkflowContext with explicit previous_step: None
        payload_2b: dict[str, Any] = dict(base_payload)
        payload_2b["approval_node_id"] = "context_test_2b"
        payload_2b["workflow_context"] = {
            "workflow_id": str(uuid4()),
            "workflow_name": "Test Workflow",
            "inputs": {},
            "previous_step": None,
        }
        response = await auth_client.post("/api/v1/approvals", json=payload_2b)
        assert response.status_code == 201
        assert response.json()["workflow_context"]["previous_step"] is None

        # Test invalid WorkflowContext - missing required field
        payload_3: dict[str, Any] = dict(base_payload)
        payload_3["approval_node_id"] = "context_test_3"
        payload_3["workflow_context"] = {
            "workflow_id": str(uuid4()),
            "inputs": {},
            # Missing workflow_name
        }
        response = await auth_client.post("/api/v1/approvals", json=payload_3)
        assert response.status_code == 422
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/validation-error",
            title="Request Validation Error",
            detail="Validation failed: workflow_context -> workflow_name: Field required",
            code="REQUEST_VALIDATION_ERROR",
            retryable=False,
        )

    @pytest.mark.asyncio
    async def test_create_approval_nonexistent_execution_returns_404(
        self,
        auth_client: AsyncClient,
        test_workflow: Workflow,
    ) -> None:
        """Test that creating an approval with a nonexistent execution_id returns 404.

        Validates:
        - Fabricated execution_id (valid UUID but no corresponding execution) returns 404
        - Error response follows RFC 9457 format
        - Orphan approval records are not created
        """
        fabricated_execution_id = str(uuid4())

        request_payload = {
            "execution_id": fabricated_execution_id,
            "project_id": str(test_workflow.project_id),
            "approval_node_id": "orphan_test_node",
            "name": "Orphan Approval Request",
            "next_step_approved": {"id": "next_step", "name": "Next Step", "type": "task"},
            "workflow_context": {
                "workflow_id": str(uuid4()),
                "workflow_name": "Orphan Test Workflow",
                "inputs": {},
            },
        }

        response = await auth_client.post("/api/v1/approvals", json=request_payload)

        assert response.status_code == 404
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/resource-not-found",
            title="Execution Not Found",
            detail="The requested execution was not found",
            code="EXECUTION_NOT_FOUND",
            retryable=False,
        )

        # Verify no orphan approval was created
        list_response = await auth_client.get(
            "/api/v1/approvals",
            params={"execution_id": fabricated_execution_id},
        )
        assert list_response.status_code == 200
        data = list_response.json()
        assert len(data["resources"]) == 0

    @pytest.mark.asyncio
    async def test_create_approval_duplicate_request_returns_409(
        self,
        auth_client: AsyncClient,
        executions_factory: ExecutionsFactory,
        test_workflow: Workflow,
    ) -> None:
        """Test that duplicate approval requests return 409 Conflict error.

        Validates:
        - First approval request succeeds with 201
        - Duplicate approval request (same execution_id and approval_node_id) returns 409
        - Error response follows RFC 9457 format
        - Error contains appropriate message about existing approval
        """
        # Arrange - Create execution first to get valid execution_id
        executions = await executions_factory.create_executions(count=1)
        execution_id = str(executions[0].id)
        workflow_id = str(uuid4())

        base_payload = {
            "execution_id": execution_id,
            "project_id": str(test_workflow.project_id),
            "approval_node_id": "duplicate_test_node",
            "name": "First Approval Request",
            "next_step_approved": {"id": "next_step", "name": "Next Step", "type": "task"},
            "workflow_context": {
                "workflow_id": workflow_id,
                "workflow_name": "Duplicate Test Workflow",
                "inputs": {"test": "data"},
            },
        }

        # Act - Create the first approval request (should succeed)
        response = await auth_client.post("/api/v1/approvals", json=base_payload)

        # Assert - First request succeeds
        assert response.status_code == 201
        data = response.json()
        assert data["execution_id"] == execution_id
        assert data["approval_node_id"] == "duplicate_test_node"
        assert data["name"] == "First Approval Request"
        assert data["status"] == ApprovalRequestStatus.PENDING.value

        # Act - Attempt to create a duplicate approval request
        # (same execution_id and approval_node_id, but different name)
        duplicate_payload = dict(base_payload)
        duplicate_payload["name"] = "Second Approval Request (should fail)"

        response = await auth_client.post("/api/v1/approvals", json=duplicate_payload)

        # Assert - Duplicate request returns 409 Conflict
        assert response.status_code == 409
        assert_error_data(
            response,
            error_type="https://api.example.com/errors/resource-conflict",
            title="Approval Already Requested",
            detail=(
                "An approval request already exists for this execution and approval node "
                "'duplicate_test_node' with loop_iteration_path []"
            ),
            code="APPROVAL_ALREADY_REQUESTED",
            retryable=False,
        )
