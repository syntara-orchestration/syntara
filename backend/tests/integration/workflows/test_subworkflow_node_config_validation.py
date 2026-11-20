"""Integration tests for sub-workflow node configuration validation.

Tests validate JSON Schema and Pydantic model alignment for SubWorkflowExecutorParameters,
ensuring contract consistency between schema-level validation (frontend) and model-level
validation (backend).

These are contract-level tests — no database or Temporal required. They test that:
1. JSON Schema correctly validates trigger_node_id and workflow_id patterns
2. Values accepted by JSON Schema are also accepted by Pydantic
3. Required fields are enforced at both schema and model levels

Note: Comprehensive Pydantic-only validation is covered in unit tests.
These integration tests focus on schema-model alignment.
"""

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from pydantic import ValidationError
from referencing import Registry
from referencing.jsonschema import DRAFT202012

from syntara.workflows.models.workflow_definition import SubWorkflowNode, WorkflowDefinition
from syntara.workflows.workflow_engine.models.workflow_definition import (
    SubWorkflowExecutorParameters,
    SubWorkflowOutput,
)

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "src" / "syntara" / "schemas" / "workflows" / "v2"
VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"


@pytest.fixture
def subworkflow_schema() -> dict[str, Any]:
    """Load the sub-workflow node JSON schema with $ref resolution."""
    schema_path = SCHEMA_DIR / "executors" / "sub_workflow.schema.json"
    common_path = SCHEMA_DIR / "common-definitions.schema.json"
    with schema_path.open() as f:
        schema: dict[str, Any] = json.load(f)
    with common_path.open() as f:
        common: dict[str, Any] = json.load(f)
    common_id = common.get("$id", "../common-definitions.schema.json")
    resource = DRAFT202012.create_resource(common)
    registry: Registry[Any] = (
        Registry().with_resource(common_id, resource).with_resource(schema["$id"], DRAFT202012.create_resource(schema))
    )
    schema["_registry"] = registry
    return schema


def _validate_params(config: dict[str, Any], schema: dict[str, Any]) -> None:
    """Validate a config dict against the sub-workflow parameterSchema."""
    registry = schema.pop("_registry", Registry())
    try:
        validator = jsonschema.Draft202012Validator(
            schema["parameterSchema"],
            registry=registry,
            format_checker=jsonschema.FormatChecker(),
        )
        validator.validate(config)
    finally:
        schema["_registry"] = registry


def _validate_result(result: dict[str, Any], schema: dict[str, Any]) -> None:
    """Validate a Sub-workflow result against its node JSON Schema definition."""
    registry = schema.pop("_registry", Registry())
    try:
        validator = jsonschema.Draft202012Validator(
            {"$ref": f"{schema['$id']}#/$defs/SubWorkflowOutput"},
            registry=registry,
        )
        validator.validate(result)
    finally:
        schema["_registry"] = registry


class TestSubWorkflowNodeSchemaValidation:
    """Test JSON Schema validation for sub-workflow node parameters."""

    @pytest.mark.parametrize(
        ("workflow_id", "trigger_node_id"),
        [
            (VALID_UUID, "trigger_1"),
            ("550E8400-E29B-41D4-A716-446655440000", "subworkflow_trigger"),
            (VALID_UUID, "_internal_trigger"),
            (VALID_UUID, "TRIGGER_NODE"),
        ],
    )
    def test_valid_configs_pass_json_schema(
        self,
        workflow_id: str,
        trigger_node_id: str,
        subworkflow_schema: dict[str, Any],
    ) -> None:
        """Valid workflow UUIDs and trigger_node_id values pass JSON Schema validation."""
        config = {
            "workflow_id": workflow_id,
            "trigger_node_id": trigger_node_id,
        }
        # Should not raise
        _validate_params(config, subworkflow_schema)

    @pytest.mark.parametrize(
        ("workflow_id", "trigger_node_id"),
        [
            (VALID_UUID, "trigger_1"),
            ("550E8400-E29B-41D4-A716-446655440000", "subworkflow_trigger"),
        ],
    )
    def test_schema_and_pydantic_alignment_valid_values(
        self,
        workflow_id: str,
        trigger_node_id: str,
        subworkflow_schema: dict[str, Any],
    ) -> None:
        """Values that pass JSON Schema also pass Pydantic model validation."""
        config: dict[str, Any] = {
            "workflow_id": workflow_id,
            "trigger_node_id": trigger_node_id,
        }
        # Both should succeed
        _validate_params(config, subworkflow_schema)
        params = SubWorkflowExecutorParameters(**config)
        assert params.workflow_id == workflow_id
        assert params.trigger_node_id == trigger_node_id

    @pytest.mark.parametrize(
        "static_value",
        [
            "app.example.test",
            8443,
            True,
            ["production", "blue"],
            {"region": "west", "labels": ["stable"]},
        ],
    )
    def test_static_input_mapping_passes_schema_and_model(
        self,
        static_value: object,
        subworkflow_schema: dict[str, Any],
    ) -> None:
        config = {
            "workflow_id": VALID_UUID,
            "trigger_node_id": "child_entry",
            "input_mapping": {"target": static_value},
        }

        _validate_params(config, subworkflow_schema)
        params = SubWorkflowExecutorParameters(**config)

        assert params.input_mapping == config["input_mapping"]

    @pytest.mark.parametrize(
        "expression",
        ["${prepare_request.stdout}", "https://${prepare_request.outputs.host}"],
    )
    def test_template_expression_input_mapping_passes_schema_and_model(
        self,
        expression: str,
        subworkflow_schema: dict[str, Any],
    ) -> None:
        config = {
            "workflow_id": VALID_UUID,
            "trigger_node_id": "child_entry",
            "input_mapping": {"target": expression},
        }

        _validate_params(config, subworkflow_schema)
        params = SubWorkflowExecutorParameters(**config)

        assert params.input_mapping == {"target": expression}

    def test_static_and_template_input_mappings_round_trip_through_workflow_node(self) -> None:
        workflow_definition = {
            "schema_version": "2.0.0",
            "name": "sub-workflow model integration",
            "triggers": [{"id": "start", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "invoke_child",
                    "type": "sub_workflow",
                    "parameters": {
                        "workflow_id": VALID_UUID,
                        "trigger_node_id": "child_entry",
                        "input_mapping": {
                            "target": "${prepare_request.outputs.host}",
                            "port": 8443,
                            "options": {"region": "west", "tags": ["stable", "blue"]},
                        },
                    },
                }
            ],
            "edges": [{"from": "start", "to": "invoke_child"}],
        }
        workflow = WorkflowDefinition.model_validate_json(json.dumps(workflow_definition))

        node = workflow.nodes[0]
        assert isinstance(node, SubWorkflowNode)
        assert node.parameters.input_mapping == {
            "target": "${prepare_request.outputs.host}",
            "port": 8443,
            "options": {"region": "west", "tags": ["stable", "blue"]},
        }

        restored = WorkflowDefinition.model_validate_json(workflow.model_dump_json())
        assert isinstance(restored.nodes[0], SubWorkflowNode)
        assert restored.nodes[0].parameters == node.parameters

    def test_input_mapping_over_limit_is_rejected_by_schema_and_model(self, subworkflow_schema: dict[str, Any]) -> None:
        config = {
            "workflow_id": VALID_UUID,
            "trigger_node_id": "child_entry",
            "input_mapping": {f"field_{index}": index for index in range(101)},
        }

        with pytest.raises(jsonschema.ValidationError):
            _validate_params(config, subworkflow_schema)
        with pytest.raises(ValidationError):
            SubWorkflowExecutorParameters(**config)

    def test_subworkflow_output_matches_result_schema_and_model(self, subworkflow_schema: dict[str, Any]) -> None:
        result = {
            "child_execution_id": "550e8400-e29b-41d4-a716-446655440001",
            "child_workflow_id": VALID_UUID,
            "child_workflow_name": "Release workflow",
            "child_workflow_version": 3,
            "child_status": "completed",
            "outputs": {
                "release_tag": "v3.2.1",
                "published": True,
                "build_number": 42,
                "artifacts": [{"url": "https://example.test/app", "labels": ["stable", "linux"]}],
                "metadata": {"optional": None},
            },
        }

        _validate_result(result, subworkflow_schema)
        output = SubWorkflowOutput.model_validate(result)

        assert output.model_dump(mode="json", exclude_none=True) == result
        assert "Result" not in output.model_dump(mode="json")
        assert "StatusCode" not in output.model_dump(mode="json")

    def test_workflow_node_rejects_invalid_subworkflow_configuration(self) -> None:
        with pytest.raises(ValidationError):
            WorkflowDefinition.model_validate_json(
                json.dumps(
                    {
                        "schema_version": "2.0.0",
                        "name": "invalid sub-workflow model integration",
                        "triggers": [{"id": "start", "type": "manual_trigger", "parameters": {}}],
                        "nodes": [
                            {
                                "id": "invoke_child",
                                "type": "sub_workflow",
                                "parameters": {
                                    "workflow_id": "not-a-uuid",
                                    "trigger_node_id": "child_entry",
                                },
                            },
                        ],
                        "edges": [{"from": "start", "to": "invoke_child"}],
                    }
                )
            )

    def test_workflow_id_exceeding_max_length_rejected_by_schema(
        self,
        subworkflow_schema: dict[str, Any],
    ) -> None:
        """JSON Schema rejects workflow_id exceeding the UUID string length."""
        config = {
            "workflow_id": "x" * 37,  # Exceeds maxLength: 36
            "trigger_node_id": "trigger_node",
        }
        with pytest.raises(jsonschema.ValidationError) as exc_info:
            _validate_params(config, subworkflow_schema)
        assert exc_info.value.validator in {"format", "maxLength"}

    @pytest.mark.parametrize(
        "invalid_workflow_id",
        [
            "not-a-uuid",
            "12345",
            "invalid-format",
            "550e8400e29b41d4a716446655440000",
            "${",  # Incomplete template
            "${}",  # Empty template
        ],
    )
    def test_invalid_workflow_id_rejected_by_pydantic(
        self,
        invalid_workflow_id: str,
        subworkflow_schema: dict[str, Any],
    ) -> None:
        """Both JSON Schema and Pydantic reject non-UUID workflow IDs in V1."""
        from pydantic import ValidationError

        config: dict[str, Any] = {
            "workflow_id": invalid_workflow_id,
            "trigger_node_id": "trigger_node",
        }
        with pytest.raises(jsonschema.ValidationError):
            _validate_params(config, subworkflow_schema)
        with pytest.raises(ValidationError):
            SubWorkflowExecutorParameters(**config)

    @pytest.mark.parametrize(
        "invalid_trigger_node_id",
        [
            "123invalid",  # starts with number
            "trigger-node",  # contains hyphen
            "trigger.node",  # contains dot
            "",  # empty string
        ],
    )
    def test_invalid_trigger_node_id_rejected_by_schema(
        self,
        invalid_trigger_node_id: str,
        subworkflow_schema: dict[str, Any],
    ) -> None:
        """JSON Schema rejects invalid trigger_node_id patterns."""
        config = {
            "workflow_id": VALID_UUID,
            "trigger_node_id": invalid_trigger_node_id,
        }
        with pytest.raises(jsonschema.ValidationError):
            _validate_params(config, subworkflow_schema)
        with pytest.raises(ValidationError):
            SubWorkflowExecutorParameters(**config)

    @pytest.mark.parametrize("missing_field", ["workflow_id", "trigger_node_id"])
    def test_required_fields_enforced_by_schema(
        self,
        missing_field: str,
        subworkflow_schema: dict[str, Any],
    ) -> None:
        """JSON Schema enforces required fields (workflow_id and trigger_node_id)."""
        other_field = "trigger_node_id" if missing_field == "workflow_id" else "workflow_id"
        other_value = "trigger_node" if other_field == "trigger_node_id" else VALID_UUID
        config = {other_field: other_value}
        with pytest.raises(jsonschema.ValidationError) as exc_info:
            _validate_params(config, subworkflow_schema)
        # Verify the error is about the missing field
        assert missing_field in str(exc_info.value)
        with pytest.raises(ValidationError):
            SubWorkflowExecutorParameters(**config)
