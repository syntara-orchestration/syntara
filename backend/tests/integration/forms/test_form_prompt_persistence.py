"""Integration tests for FormPrompt model persistence.

Tests model instantiation, serialization, and in-memory behavior.
Note: DB-level constraints (FK checks, unique constraints, enum validation)
are tested after migration creation when the full stack runs.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from syntara.forms.models import FormPrompt, FormPromptStatus
from tests.unit.fixtures.form import create_submitted_form_prompt, create_test_form_prompt


class TestFormPromptPersistence:
    """Test FormPrompt model persistence and serialization."""

    def test_create_form_prompt_in_memory(self) -> None:
        """Test creating a FormPrompt instance in memory."""
        execution_id = uuid4()
        project_id = uuid4()

        prompt = FormPrompt(
            execution_id=execution_id,
            project_id=project_id,
            prompt_node_id="deploy_approval",
            name="Deploy to Production",
            message="Deploy version 1.2.3?",
            status=FormPromptStatus.PENDING,
            timeout_at=datetime.now(UTC),
            input_schema={"type": "object", "properties": {"reason": {"type": "string"}}},
        )

        assert prompt.execution_id == execution_id
        assert prompt.project_id == project_id
        assert prompt.name == "Deploy to Production"
        assert prompt.status == FormPromptStatus.PENDING

    def test_jsonb_fields_serialize_deserialize(self) -> None:
        """Test that JSONB fields correctly serialize and deserialize nested structures."""
        complex_schema = {
            "type": "object",
            "properties": {
                "deployment": {
                    "type": "object",
                    "properties": {
                        "version": {"type": "string"},
                        "environment": {"type": "string"},
                    },
                },
            },
        }

        prompt = create_test_form_prompt()
        prompt.input_schema = complex_schema
        prompt.response_data = {"deployment": {"version": "1.2.3", "environment": "prod"}}

        # Serialize to dict
        data = prompt.model_dump()

        # Verify nested structures preserved
        assert data["input_schema"] == complex_schema
        assert data["response_data"]["deployment"]["version"] == "1.2.3"

        # Deserialize back
        restored = FormPrompt.model_validate(data)
        assert restored.input_schema == complex_schema

    def test_default_values_on_instantiation(self) -> None:
        """Test that default values are correctly applied on model instantiation."""
        prompt = FormPrompt(
            execution_id=uuid4(),
            project_id=uuid4(),
            prompt_node_id="test",
            name="Test",
            input_schema={},
        )

        # Defaults from BaseResource
        assert prompt.labels == {}
        assert isinstance(prompt.id, type(uuid4()))
        assert isinstance(prompt.created_at, datetime)
        assert isinstance(prompt.updated_at, datetime)

        # Defaults from BaseFormPrompt
        assert prompt.status == FormPromptStatus.PENDING
        assert prompt.loop_iteration_path == []

    def test_timezone_aware_timestamps(self) -> None:
        """Test that datetime fields preserve timezone information."""
        now = datetime.now(UTC)
        prompt = create_test_form_prompt()
        prompt.timeout_at = now
        prompt.responded_at = now

        # Serialize and deserialize
        data = prompt.model_dump()
        restored = FormPrompt.model_validate(data)

        assert restored.timeout_at == now
        assert restored.responded_at == now
        # Verify timezone is preserved (if implementation supports it)
        assert restored.timeout_at.tzinfo is not None if restored.timeout_at else True

    def test_nullable_fields_accept_none(self) -> None:
        """Test that nullable fields correctly accept None values."""
        prompt = create_test_form_prompt()

        # Set all nullable fields to None
        prompt.message = None
        prompt.timeout_at = None
        prompt.response_data = None
        prompt.responded_by = None
        prompt.responded_at = None
        prompt.temporal_activity_id = None

        # Should serialize without errors
        data = prompt.model_dump()
        assert data["message"] is None
        assert data["timeout_at"] is None
        assert data["response_data"] is None

    def test_enum_fields_serialize_as_strings(self) -> None:
        """Test that enum fields serialize to their string values."""
        prompt = create_test_form_prompt()
        prompt.status = FormPromptStatus.SUBMITTED

        data = prompt.model_dump()

        assert data["status"] == "submitted"

    def test_loop_iteration_path_empty_default(self) -> None:
        """Test that loop_iteration_path defaults to empty list."""
        prompt = create_test_form_prompt()
        assert prompt.loop_iteration_path == []

        # Should serialize as empty list, not None
        data = prompt.model_dump()
        assert data["loop_iteration_path"] == []

    def test_submitted_form_prompt_factory(self) -> None:
        """Test the submitted form prompt factory helper."""
        responded_by = uuid4()
        response_data = {"reason": "Approved for deployment"}

        prompt = create_submitted_form_prompt(
            responded_by=responded_by,
            response_data=response_data,
        )

        assert prompt.status == FormPromptStatus.SUBMITTED
        assert prompt.responded_by == responded_by
        assert prompt.response_data == response_data
        assert prompt.responded_at is not None
        assert prompt.timeout_at is None

    def test_pydantic_validation_rules_enforced(self) -> None:
        """Test that Pydantic validation rules are enforced."""
        # Empty name should fail
        with pytest.raises(ValidationError):
            FormPrompt(
                execution_id=uuid4(),
                project_id=uuid4(),
                prompt_node_id="test",
                name="",  # min_length=1
                input_schema={},
            )
