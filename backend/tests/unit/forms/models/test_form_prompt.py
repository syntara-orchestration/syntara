"""Unit tests for FormPrompt model field validation and constraints.

Tests required field validation, length limits, optional fields,
default values, and test helper functionality.
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from syntara.core.constants import FieldLimits
from syntara.forms.models import FormPrompt, FormPromptStatus
from tests.unit.fixtures.form import create_test_form_prompt


class TestFormPromptValidation:
    """Test FormPrompt field validation and constraints."""

    def test_required_fields(self) -> None:
        """Test that required fields cannot be None or empty."""
        execution_id = uuid4()

        # Test empty name
        with pytest.raises(ValidationError):
            FormPrompt(
                execution_id=execution_id,
                project_id=uuid4(),
                prompt_node_id="test",
                name="",  # Empty name should fail min_length validation
                input_schema={"type": "object"},
            )

        # Test empty prompt_node_id
        with pytest.raises(ValidationError):
            FormPrompt(
                execution_id=execution_id,
                project_id=uuid4(),
                prompt_node_id="",  # Empty prompt_node_id should fail
                name="Test",
                input_schema={"type": "object"},
            )

    def test_string_field_length_limits(self) -> None:
        """Test string field length constraints."""
        execution_id = uuid4()

        # Test name length limit (max NAME_MAX_LENGTH)
        long_name = "x" * (FieldLimits.NAME_MAX_LENGTH + 1)
        with pytest.raises(ValidationError):
            FormPrompt(
                execution_id=execution_id,
                project_id=uuid4(),
                prompt_node_id="test",
                name=long_name,
                input_schema={"type": "object"},
            )

        # Test prompt_node_id length limit (max NAME_MAX_LENGTH)
        long_node_id = "x" * (FieldLimits.NAME_MAX_LENGTH + 1)
        with pytest.raises(ValidationError):
            FormPrompt(
                execution_id=execution_id,
                project_id=uuid4(),
                prompt_node_id=long_node_id,
                name="Test",
                input_schema={"type": "object"},
            )

        # Test message length limit (max DESCRIPTION_MAX_LENGTH)
        long_message = "x" * (FieldLimits.DESCRIPTION_MAX_LENGTH + 1)
        with pytest.raises(ValidationError):
            FormPrompt(
                execution_id=execution_id,
                project_id=uuid4(),
                prompt_node_id="test",
                name="Test",
                message=long_message,
                input_schema={"type": "object"},
            )

    def test_optional_fields(self) -> None:
        """Test that optional fields can be None."""
        prompt = create_test_form_prompt()

        # These fields should be nullable
        prompt.message = None
        prompt.timeout_at = None
        prompt.responded_by = None
        prompt.responded_at = None
        prompt.response_data = None
        prompt.temporal_activity_id = None

        # Should not raise validation errors
        prompt.model_dump()

    def test_default_values(self) -> None:
        """Test that fields have correct defaults."""
        prompt = create_test_form_prompt()

        assert prompt.status == FormPromptStatus.PENDING
        assert prompt.loop_iteration_path == []
        assert prompt.labels == {}

    def test_model_serialization(self) -> None:
        """Test model_dump and model_validate round trip."""
        original = create_test_form_prompt(
            name="Deployment Approval",
            message="Deploy version 1.2.3?",
        )

        # Serialize to dict
        data = original.model_dump()

        # Deserialize back to model
        restored = FormPrompt.model_validate(data)

        assert restored.name == original.name
        assert restored.message == original.message
        assert restored.execution_id == original.execution_id
        assert restored.status == original.status

    def test_form_prompt_status_values(self) -> None:
        """Test that status enum has expected values."""
        assert FormPromptStatus.PENDING.value == "pending"
        assert FormPromptStatus.SUBMITTED.value == "submitted"
        assert FormPromptStatus.EXPIRED.value == "expired"
        assert FormPromptStatus.CANCELLED.value == "cancelled"

    def test_sortable_fields(self) -> None:
        """Test that __sortable_fields__ contains expected fields."""
        expected_sortable = [
            "created_at",
            "updated_at",
            "name",
            "timeout_at",
            "responded_at",
            "status",
        ]

        for field in expected_sortable:
            assert field in FormPrompt.__sortable_fields__

    def test_filterable_fields(self) -> None:
        """Test that __filterable_fields__ contains expected fields."""
        expected_filterable = [
            "id",
            "created_at",
            "updated_at",
            "name",
            "execution_id",
            "project_id",
            "status",
            "timeout_at",
        ]

        for field in expected_filterable:
            assert field in FormPrompt.__filterable_fields__
