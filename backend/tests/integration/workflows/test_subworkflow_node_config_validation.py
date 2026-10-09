"""Integration tests for sub-workflow node configuration validation (AAP-94068/AAP-94071).

Tests validate JSON Schema and Pydantic model alignment for SubWorkflowExecutorParameters,
ensuring contract consistency between schema-level validation (frontend) and model-level
validation (backend).

These are contract-level tests — no database or Temporal required. They test that:
1. JSON Schema correctly validates trigger_node_id and workflow_id patterns
2. Values accepted by JSON Schema are also accepted by Pydantic
3. Required fields are enforced at both schema and model levels

Note: Comprehensive Pydantic-only validation is covered in unit tests (PR #816).
These integration tests focus on schema-model alignment.
"""

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from referencing import Registry
from referencing.jsonschema import DRAFT202012

from syntara.workflows.workflow_engine.models.workflow_definition import (
    SubWorkflowExecutorParameters,
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
    registry: Registry[Any] = Registry().with_resource(common_id, resource)
    schema["_registry"] = registry
    return schema


def _validate_params(config: dict[str, Any], schema: dict[str, Any]) -> None:
    """Validate a config dict against the sub-workflow parameterSchema."""
    registry = schema.pop("_registry", Registry())
    try:
        validator = jsonschema.Draft202012Validator(schema["parameterSchema"], registry=registry)
        validator.validate(config)
    finally:
        schema["_registry"] = registry


class TestSubWorkflowNodeSchemaValidation:
    """Test JSON Schema validation for sub-workflow node parameters."""

    @pytest.mark.parametrize(
        ("workflow_id", "trigger_node_id"),
        [
            # UUID and valid node ID
            (VALID_UUID, "trigger_1"),
            # Template expression and valid node ID
            ("${parent.workflow_id}", "subworkflow_trigger"),
            # UUID and underscore-prefixed node ID
            (VALID_UUID, "_internal_trigger"),
            # Template and uppercase node ID
            ("${step.output.id}", "TRIGGER_NODE"),
        ],
    )
    def test_valid_configs_pass_json_schema(
        self,
        workflow_id: str,
        trigger_node_id: str,
        subworkflow_schema: dict[str, Any],
    ) -> None:
        """Valid workflow_id (UUID or template) and trigger_node_id pass JSON Schema validation."""
        config = {
            "workflow_id": workflow_id,
            "trigger_node_id": trigger_node_id,
        }
        # Should not raise
        _validate_params(config, subworkflow_schema)

    @pytest.mark.parametrize(
        ("workflow_id", "trigger_node_id"),
        [
            # UUID and valid node ID
            (VALID_UUID, "trigger_1"),
            # Template expression and valid node ID
            ("${parent.workflow_id}", "subworkflow_trigger"),
        ],
    )
    def test_schema_and_pydantic_alignment_valid_values(
        self,
        workflow_id: str,
        trigger_node_id: str,
        subworkflow_schema: dict[str, Any],
    ) -> None:
        """Values that pass JSON Schema also pass Pydantic model validation."""
        config = {
            "workflow_id": workflow_id,
            "trigger_node_id": trigger_node_id,
        }
        # Both should succeed
        _validate_params(config, subworkflow_schema)
        params = SubWorkflowExecutorParameters(**config)
        assert params.workflow_id == workflow_id
        assert params.trigger_node_id == trigger_node_id

    @pytest.mark.parametrize(
        "invalid_workflow_id",
        [
            "not-a-uuid",
            "12345",
            "invalid-format",
            "${",  # Incomplete template
            "${}",  # Empty template
        ],
    )
    def test_invalid_workflow_id_rejected_by_schema(
        self,
        invalid_workflow_id: str,
        subworkflow_schema: dict[str, Any],
    ) -> None:
        """JSON Schema rejects invalid workflow_id (neither UUID nor valid template)."""
        config = {
            "workflow_id": invalid_workflow_id,
            "trigger_node_id": "trigger_node",
        }
        with pytest.raises(jsonschema.ValidationError):
            _validate_params(config, subworkflow_schema)

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
