"""Unit tests for ApprovalRequest model field validation and constraints.

Tests required field validation, length limits, optional fields,
default values, and test helper functionality.
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from syntara.approvals.models import (
    ActivitySummary,
    ApprovalCreateRequest,
    ApprovalRequest,
    ApprovalRequestStatus,
    WorkflowContext,
)
from syntara.core.constants import FieldLimits
from tests.unit.fixtures.approval import (
    create_approved_approval_request,
    create_test_approval_request,
)


class TestApprovalRequestValidation:
    """Test ApprovalRequest field validation and constraints."""

    def test_required_fields(self) -> None:
        """Test that required fields cannot be None or empty."""
        execution_id = uuid4()

        # Test empty name
        with pytest.raises(ValidationError):
            ApprovalRequest(
                execution_id=execution_id,
                approval_node_id="test",
                name="",  # Empty name should fail min_length validation
                next_step_approved={"id": "test"},
                workflow_context={},
            )

        # Test empty approval_node_id
        with pytest.raises(ValidationError):
            ApprovalRequest(
                execution_id=execution_id,
                approval_node_id="",  # Empty approval_node_id should fail
                name="Test",
                next_step_approved={"id": "test"},
                workflow_context={},
            )

    def test_string_field_length_limits(self) -> None:
        """Test string field length constraints."""
        execution_id = uuid4()

        # Test name length limit (max NAME_MAX_LENGTH)
        long_name = "x" * (FieldLimits.NAME_MAX_LENGTH + 1)
        with pytest.raises(ValidationError):
            ApprovalRequest(
                execution_id=execution_id,
                approval_node_id="test",
                name=long_name,
                next_step_approved={"id": "test"},
                workflow_context={},
            )

        # Test approval_node_id length limit (max NAME_MAX_LENGTH)
        long_node_id = "x" * (FieldLimits.NAME_MAX_LENGTH + 1)
        with pytest.raises(ValidationError):
            ApprovalRequest(
                execution_id=execution_id,
                approval_node_id=long_node_id,
                name="Test",
                next_step_approved={"id": "test"},
                workflow_context={},
            )

    def test_optional_fields(self) -> None:
        """Test that optional fields can be None."""
        # Create a non-pending approval so timeout_at can be None
        approval = create_test_approval_request(
            status=ApprovalRequestStatus.APPROVED,  # Non-pending status
            timeout_at=None,
            next_step_rejected=None,
            decided_by=None,
            decided_at=None,
            decision_notes=None,
        )

        assert approval.timeout_at is None
        assert approval.next_step_rejected is None
        assert approval.decided_by is None
        assert approval.decided_at is None
        assert approval.decision_notes is None
        assert approval.prompt is None

    def test_default_values(self) -> None:
        """Test model default values."""
        execution_id = uuid4()
        approval = ApprovalRequest(
            execution_id=execution_id,
            approval_node_id="test",
            name="Test",
            next_step_approved={"id": "test", "name": "Test Step", "type": "task"},
            workflow_context={
                "workflow_id": str(uuid4()),
                "workflow_name": "Test Workflow",
                "inputs": {},
            },
        )

        assert approval.status == ApprovalRequestStatus.PENDING
        assert approval.loop_iteration_path == []

    def test_create_request_rejects_negative_loop_iteration_path(self) -> None:
        """API create payload must not store a negative loop index."""
        with pytest.raises(ValidationError):
            ApprovalCreateRequest(
                execution_id=uuid4(),
                project_id=uuid4(),
                approval_node_id="gate",
                name="Test",
                loop_iteration_path=[-1],
                next_step_approved=ActivitySummary(id="next", name="Next", type="task"),
                workflow_context=WorkflowContext(workflow_name="wf", inputs={}),
            )

    def test_sortable_fields_contains_correct_fields(self) -> None:
        assert ApprovalRequest.__sortable_fields__ == [
            "created_at",
            "updated_at",
            "name",
            "timeout_at",
            "decided_at",
            "status",
        ]


class TestApprovalRequestHelperFactories:
    """Test the helper factory functions work correctly."""

    def test_factory_override_defaults(self) -> None:
        """Test factories accept overrides for default values."""
        custom_execution_id = uuid4()
        approval = create_approved_approval_request(
            execution_id=custom_execution_id,
            name="Custom Approval",
        )

        assert approval.execution_id == custom_execution_id
        assert approval.name == "Custom Approval"
        assert approval.status == ApprovalRequestStatus.APPROVED
