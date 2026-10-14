"""Contract tests for subworkflow trigger JSON schema.

Validates that the subworkflow trigger schema file is well-formed and
accepts/rejects the expected configurations, and that the trigger is
registered in the workflow definition schema and the node type catalog.
"""

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "src" / "syntara" / "schemas" / "workflows" / "v2" / "triggers"


@pytest.fixture
def subworkflow_schema() -> dict[str, Any]:
    """Load the subworkflow trigger schema."""
    schema_path = SCHEMA_DIR / "subworkflow.schema.json"
    with schema_path.open() as f:
        result: dict[str, Any] = json.load(f)
        return result


async def test_subworkflow_schema_has_config_schema(subworkflow_schema: dict[str, Any]) -> None:
    """Schema should have a parameterSchema section."""
    assert "parameterSchema" in subworkflow_schema


async def test_subworkflow_schema_has_result_schema(subworkflow_schema: dict[str, Any]) -> None:
    """Schema should have a resultSchema section."""
    assert "resultSchema" in subworkflow_schema


async def test_subworkflow_config_empty_is_valid(subworkflow_schema: dict[str, Any]) -> None:
    """Empty config should be valid since subworkflow trigger has no required fields."""
    config: dict[str, Any] = {}
    jsonschema.validate(instance=config, schema=subworkflow_schema["parameterSchema"])


async def test_subworkflow_config_valid_with_input_schema(subworkflow_schema: dict[str, Any]) -> None:
    """Config with input_schema should be valid."""
    config = {
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        },
    }
    jsonschema.validate(instance=config, schema=subworkflow_schema["parameterSchema"])


async def test_subworkflow_config_rejects_additional_properties(subworkflow_schema: dict[str, Any]) -> None:
    """Config with unknown properties should be rejected."""
    config = {"unknown_field": "value"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=config, schema=subworkflow_schema["parameterSchema"])


async def test_subworkflow_trigger_in_workflow_definition_schema() -> None:
    """Subworkflow trigger should be listed in the workflow definition schema."""
    schema_path = SCHEMA_DIR.parent / "workflow_definition.schema.json"
    with schema_path.open() as f:
        wf_schema = json.load(f)

    trigger_node = wf_schema["$defs"]["trigger_node"]
    one_of = trigger_node["oneOf"]

    subworkflow_entries = [
        entry
        for entry in one_of
        if any(
            allof_item.get("properties", {}).get("type", {}).get("const") == "subworkflow_trigger"
            for allof_item in entry.get("allOf", [])
        )
    ]
    assert len(subworkflow_entries) == 1


async def test_subworkflow_trigger_in_node_type_catalog() -> None:
    """Subworkflow trigger should be listed in the node type catalog."""
    catalog_path = SCHEMA_DIR.parent / "catalog" / "node_type_catalog.json"
    with catalog_path.open() as f:
        catalog = json.load(f)

    subworkflow_types = [nt for nt in catalog["node_types"] if nt["type"] == "subworkflow_trigger"]
    assert len(subworkflow_types) == 1
    assert subworkflow_types[0]["labels"]["category"] == "trigger"
