"""Tests for SubWorkflowExecutorParameters model."""

import json
import uuid

import pytest
from pydantic import ValidationError

from syntara.workflows.workflow_engine.models.workflow_definition import SubWorkflowExecutorParameters


@pytest.fixture
def valid_params() -> tuple[str, str]:
    """Generate valid workflow_id (UUID) and trigger_node_id (graph node ID) for tests."""
    return str(uuid.uuid4()), "subworkflow_trigger"


class TestSubWorkflowExecutorParametersValidation:
    """Test validation of SubWorkflowExecutorParameters fields."""

    def test_valid_minimal_parameters(self, valid_params: tuple[str, str]) -> None:
        """Test creation with minimal valid parameters (input_mapping defaults to empty dict)."""
        workflow_id, trigger_node_id = valid_params

        params = SubWorkflowExecutorParameters(
            workflow_id=workflow_id,
            trigger_node_id=trigger_node_id,
        )

        assert params.workflow_id == workflow_id
        assert params.trigger_node_id == trigger_node_id
        assert params.input_mapping == {}

    @pytest.mark.parametrize(
        "template_value",
        [
            "${parent_step.workflow_id}",
            "${step.output.id}",
            "${trigger.data.workflow_id}",
        ],
    )
    def test_workflow_id_accepts_template_expressions(self, template_value: str) -> None:
        """Test that workflow_id accepts template expressions."""
        params = SubWorkflowExecutorParameters(
            workflow_id=template_value,
            trigger_node_id="trigger_node",
        )

        assert params.workflow_id == template_value

    @pytest.mark.parametrize(
        "trigger_node_id",
        [
            "trigger_1",
            "subworkflow_trigger",
            "TRIGGER_NODE",
            "_internal_trigger",
            "trigger123",
        ],
    )
    def test_trigger_node_id_valid_patterns(self, trigger_node_id: str) -> None:
        """Test that trigger_node_id accepts valid graph node ID patterns."""
        params = SubWorkflowExecutorParameters(
            workflow_id=str(uuid.uuid4()),
            trigger_node_id=trigger_node_id,
        )

        assert params.trigger_node_id == trigger_node_id

    @pytest.mark.parametrize(
        "invalid_value",
        [
            "not-a-uuid",
            "12345",
            "invalid-format",
        ],
    )
    def test_workflow_id_invalid_uuid_format(self, invalid_value: str) -> None:
        """Test validation fails for invalid workflow_id UUID format."""
        with pytest.raises(ValidationError) as exc_info:
            SubWorkflowExecutorParameters(
                workflow_id=invalid_value,
                trigger_node_id="trigger_node",
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("workflow_id",) for e in errors)
        assert any("Invalid UUID format" in e["msg"] for e in errors)

    @pytest.mark.parametrize(
        "invalid_node_id",
        [
            "123invalid",  # starts with number
            "trigger-node",  # contains hyphen
            "trigger node",  # contains space
            "trigger.node",  # contains dot
            "",  # empty string
        ],
    )
    def test_trigger_node_id_invalid_patterns(self, invalid_node_id: str) -> None:
        """Test validation fails for invalid trigger_node_id patterns."""
        with pytest.raises(ValidationError) as exc_info:
            SubWorkflowExecutorParameters(
                workflow_id=str(uuid.uuid4()),
                trigger_node_id=invalid_node_id,
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("trigger_node_id",) for e in errors)

    @pytest.mark.parametrize("missing_field", ["workflow_id", "trigger_node_id"])
    def test_missing_required_field(self, missing_field: str) -> None:
        """Test validation fails when required fields are missing."""
        other_field = "trigger_node_id" if missing_field == "workflow_id" else "workflow_id"
        other_value = "trigger_node" if other_field == "trigger_node_id" else str(uuid.uuid4())

        with pytest.raises(ValidationError) as exc_info:
            SubWorkflowExecutorParameters(  # type: ignore[call-arg]
                **{other_field: other_value}
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == (missing_field,) for e in errors)


class TestSubWorkflowExecutorParametersInputMapping:
    """Test input_mapping field behavior."""

    @pytest.mark.parametrize(
        "input_mapping",
        [
            # Static string values
            {"name": "test", "env": "prod"},
            # Static numeric values
            {"count": 42, "ratio": 3.14},
            # Static boolean values
            {"enabled": True, "disabled": False},
            # Static dict values
            {"config": {"host": "localhost", "port": 8080}},
            # Static list values
            {"items": ["a", "b", "c"]},
            # Template expression values
            {"user_id": "${step_1.output.user_id}", "status": "${step_2.result.status}"},
            # Mixed static and template values
            {
                "static": "value",
                "dynamic": "${step.output}",
                "count": 42,
                "enabled": True,
            },
        ],
    )
    def test_input_mapping_value_types(self, valid_params: tuple[str, str], input_mapping: dict) -> None:
        """Test input_mapping supports various value types (stored as-is)."""
        workflow_id, trigger_node_id = valid_params
        params = SubWorkflowExecutorParameters(
            workflow_id=workflow_id,
            trigger_node_id=trigger_node_id,
            input_mapping=input_mapping,
        )

        assert params.input_mapping == input_mapping


class TestSubWorkflowExecutorParametersSerialization:
    """Test serialization and deserialization of SubWorkflowExecutorParameters."""

    def test_model_dump(self, valid_params: tuple[str, str]) -> None:
        """Test serialization via model_dump()."""
        workflow_id, trigger_node_id = valid_params

        params = SubWorkflowExecutorParameters(
            workflow_id=workflow_id,
            trigger_node_id=trigger_node_id,
            input_mapping={"key": "value"},
        )

        dumped = params.model_dump()

        assert dumped == {
            "workflow_id": workflow_id,
            "trigger_node_id": trigger_node_id,
            "input_mapping": {"key": "value"},
        }

    def test_model_dump_json(self, valid_params: tuple[str, str]) -> None:
        """Test JSON serialization via model_dump_json()."""
        workflow_id, trigger_node_id = valid_params

        params = SubWorkflowExecutorParameters(
            workflow_id=workflow_id,
            trigger_node_id=trigger_node_id,
            input_mapping={"count": 42},
        )

        parsed = json.loads(params.model_dump_json())

        assert parsed == {
            "workflow_id": workflow_id,
            "trigger_node_id": trigger_node_id,
            "input_mapping": {"count": 42},
        }

    def test_round_trip_serialization(self, valid_params: tuple[str, str]) -> None:
        """Test round-trip serialization preserves all data types."""
        workflow_id, trigger_node_id = valid_params
        original = SubWorkflowExecutorParameters(
            workflow_id=workflow_id,
            trigger_node_id=trigger_node_id,
            input_mapping={
                "string": "value",
                "number": 42,
                "bool": True,
                "dict": {"nested": "value"},
                "list": [1, 2, 3],
                "template": "${step.output}",
            },
        )

        restored = SubWorkflowExecutorParameters(**original.model_dump())

        assert restored.model_dump() == original.model_dump()
