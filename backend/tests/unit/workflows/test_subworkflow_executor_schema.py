"""Contract tests for sub-workflow executor JSON schema.

Validates that the sub-workflow executor schema file is well-formed and
accepts/rejects the expected configurations.

These are lightweight schema-only tests that don't require database or Temporal.
"""

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "src" / "syntara" / "schemas" / "workflows" / "v2"
VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"


@pytest.fixture
def subworkflow_schema() -> dict[str, Any]:
    """Load the sub-workflow executor schema."""
    schema_path = SCHEMA_DIR / "executors" / "sub_workflow.schema.json"
    with schema_path.open() as f:
        result: dict[str, Any] = json.load(f)
        return result


def validate_parameter_schema(config: dict[str, Any], schema: dict[str, Any]) -> None:
    jsonschema.validate(
        instance=config,
        schema=schema["parameterSchema"],
        format_checker=jsonschema.FormatChecker(),
    )


def test_subworkflow_schema_has_parameter_schema(subworkflow_schema: dict[str, Any]) -> None:
    """Schema should have a parameterSchema section."""
    assert "parameterSchema" in subworkflow_schema


def test_subworkflow_schema_has_result_schema(subworkflow_schema: dict[str, Any]) -> None:
    """Schema should have a resultSchema section."""
    assert "resultSchema" in subworkflow_schema


def test_subworkflow_schema_has_setting_schema(subworkflow_schema: dict[str, Any]) -> None:
    """Schema should have a settingSchema section."""
    assert "settingSchema" in subworkflow_schema


def test_subworkflow_config_minimal_valid(subworkflow_schema: dict[str, Any]) -> None:
    """Minimal valid config with only required fields should pass."""
    config = {
        "workflow_id": VALID_UUID,
        "trigger_node_id": "subworkflow_trigger",
    }
    validate_parameter_schema(config, subworkflow_schema)


def test_subworkflow_config_with_input_mapping(subworkflow_schema: dict[str, Any]) -> None:
    """Config with input_mapping should be valid."""
    config = {
        "workflow_id": VALID_UUID,
        "trigger_node_id": "trigger_1",
        "input_mapping": {
            "user_name": "admin",
            "count": 42,
            "enabled": True,
            "nested": {"key": "value"},
        },
    }
    validate_parameter_schema(config, subworkflow_schema)


def test_subworkflow_config_rejects_template_expression_for_workflow_id(subworkflow_schema: dict[str, Any]) -> None:
    """V1 workflow IDs are selected UUIDs; template expressions are only for input_mapping values."""
    config = {
        "workflow_id": "${parent_step.workflow_id}",
        "trigger_node_id": "trigger_node",
    }
    with pytest.raises(jsonschema.ValidationError):
        validate_parameter_schema(config, subworkflow_schema)


def test_subworkflow_config_rejects_missing_workflow_id(subworkflow_schema: dict[str, Any]) -> None:
    """Config without workflow_id should be rejected."""
    config = {
        "trigger_node_id": "trigger_1",
    }
    with pytest.raises(jsonschema.ValidationError) as exc_info:
        validate_parameter_schema(config, subworkflow_schema)
    assert "workflow_id" in str(exc_info.value)


def test_subworkflow_config_rejects_missing_trigger_node_id(subworkflow_schema: dict[str, Any]) -> None:
    """Config without trigger_node_id should be rejected."""
    config = {
        "workflow_id": VALID_UUID,
    }
    with pytest.raises(jsonschema.ValidationError) as exc_info:
        validate_parameter_schema(config, subworkflow_schema)
    assert "trigger_node_id" in str(exc_info.value)


def test_subworkflow_config_rejects_workflow_id_exceeding_max_length(subworkflow_schema: dict[str, Any]) -> None:
    """Config with workflow_id exceeding the UUID length should be rejected by JSON Schema."""
    config = {
        "workflow_id": "x" * 37,  # Exceeds maxLength: 36
        "trigger_node_id": "trigger_1",
    }
    with pytest.raises(jsonschema.ValidationError) as exc_info:
        validate_parameter_schema(config, subworkflow_schema)
    assert exc_info.value.validator in {"format", "maxLength"}


def test_subworkflow_config_rejects_invalid_trigger_node_id_pattern(
    subworkflow_schema: dict[str, Any],
) -> None:
    """Config with trigger_node_id that violates pattern should be rejected."""
    config = {
        "workflow_id": VALID_UUID,
        "trigger_node_id": "123-starts-with-digit",
    }
    with pytest.raises(jsonschema.ValidationError):
        validate_parameter_schema(config, subworkflow_schema)


def test_subworkflow_config_rejects_additional_properties(subworkflow_schema: dict[str, Any]) -> None:
    """Config with unknown properties should be rejected."""
    config = {
        "workflow_id": VALID_UUID,
        "trigger_node_id": "trigger_1",
        "unknown_field": "should-fail",
    }
    with pytest.raises(jsonschema.ValidationError):
        validate_parameter_schema(config, subworkflow_schema)


def test_subworkflow_result_schema_has_standard_wrapper_fields(subworkflow_schema: dict[str, Any]) -> None:
    """Result schema should follow StandardOutputWrapper pattern."""
    # The $defs are at root level, not nested in resultSchema
    assert "$defs" in subworkflow_schema
    assert "SubWorkflowOutput" in subworkflow_schema["$defs"]

    output_schema = subworkflow_schema["$defs"]["SubWorkflowOutput"]
    properties = output_schema["properties"]

    # StandardOutputWrapper fields
    assert "Result" in properties
    assert "StatusCode" in properties
    assert "StatusMessage" in properties
    assert "ErrorMessage" in properties


def test_subworkflow_result_has_child_execution_metadata(subworkflow_schema: dict[str, Any]) -> None:
    """Result schema should include child execution metadata fields."""
    # The $defs are at root level
    assert "$defs" in subworkflow_schema
    result_def = subworkflow_schema["$defs"]["SubWorkflowOutputResult"]

    properties = result_def["properties"]
    assert "child_execution_id" in properties
    assert "child_workflow_id" in properties
    assert "child_workflow_name" in properties
    assert "child_workflow_version" in properties
    assert "child_status" in properties
    assert "outputs" in properties


def test_subworkflow_executor_in_node_type_catalog() -> None:
    """Sub-workflow executor should be listed in node type catalog."""
    catalog_path = SCHEMA_DIR / "catalog" / "node_type_catalog.json"
    with catalog_path.open() as f:
        catalog = json.load(f)

    node_types = [entry["type"] for entry in catalog["node_types"]]
    assert "sub_workflow" in node_types

    # Find the sub_workflow entry
    sub_workflow_entry = next(entry for entry in catalog["node_types"] if entry["type"] == "sub_workflow")

    # Verify it has required catalog fields
    assert "name" in sub_workflow_entry
    assert "description" in sub_workflow_entry
    assert "schema_ref" in sub_workflow_entry
    assert sub_workflow_entry["labels"]["category"] == "executor"


def test_subworkflow_settings_reference_no_retry() -> None:
    """Sub-workflow settingSchema should reference nodeSettingsNoRetry."""
    schema_path = SCHEMA_DIR / "executors" / "sub_workflow.schema.json"
    with schema_path.open() as f:
        schema = json.load(f)

    setting_schema = schema["settingSchema"]
    # Should reference common-definitions nodeSettingsNoRetry
    assert "$ref" in setting_schema
    assert "nodeSettingsNoRetry" in setting_schema["$ref"]
