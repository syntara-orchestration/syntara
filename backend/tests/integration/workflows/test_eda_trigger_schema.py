"""Contract tests for EDA trigger JSON schema.

Validates that the EDA trigger schema file is well-formed and accepts/rejects
the expected configurations.
"""

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "src" / "syntara" / "schemas" / "workflows" / "v2" / "triggers"


@pytest.fixture
def eda_schema() -> dict[str, Any]:
    """Load the EDA trigger schema."""
    schema_path = SCHEMA_DIR / "eda.schema.json"
    with schema_path.open() as f:
        result: dict[str, Any] = json.load(f)
        return result


async def test_eda_schema_has_config_schema(eda_schema: dict[str, Any]) -> None:
    """Schema should have a parameterSchema section."""
    assert "parameterSchema" in eda_schema


async def test_eda_schema_has_result_schema(eda_schema: dict[str, Any]) -> None:
    """Schema should have a resultSchema section."""
    assert "resultSchema" in eda_schema


async def test_eda_config_requires_webhook_path(eda_schema: dict[str, Any]) -> None:
    """Config schema should require webhook_path."""
    config_schema = eda_schema["parameterSchema"]
    assert "webhook_path" in config_schema.get("required", [])


async def test_eda_config_valid_minimal(eda_schema: dict[str, Any]) -> None:
    """Minimal config with just webhook_path should be valid."""
    config = {"webhook_path": "my-eda-endpoint"}
    jsonschema.validate(instance=config, schema=eda_schema["parameterSchema"])


async def test_eda_config_valid_with_input_schema(eda_schema: dict[str, Any]) -> None:
    """Config with webhook_path and input_schema should be valid."""
    config = {
        "webhook_path": "validated-eda-endpoint",
        "input_schema": {
            "type": "object",
            "properties": {"event": {"type": "string"}},
        },
    }
    jsonschema.validate(instance=config, schema=eda_schema["parameterSchema"])


async def test_eda_config_rejects_missing_path(eda_schema: dict[str, Any]) -> None:
    """Config without webhook_path should be rejected."""
    config = {"input_schema": {"type": "object"}}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=config, schema=eda_schema["parameterSchema"])


async def test_eda_config_rejects_additional_properties(eda_schema: dict[str, Any]) -> None:
    """Config with unknown properties should be rejected."""
    config = {"webhook_path": "test", "unknown_field": "value"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=config, schema=eda_schema["parameterSchema"])


async def test_eda_trigger_in_workflow_definition_schema() -> None:
    """EDA trigger should be listed in the workflow definition schema."""
    schema_path = SCHEMA_DIR.parent / "workflow_definition.schema.json"
    with schema_path.open() as f:
        wf_schema = json.load(f)

    trigger_node = wf_schema["$defs"]["trigger_node"]
    one_of = trigger_node["oneOf"]

    # Find eda_trigger in oneOf
    eda_entries = [
        entry
        for entry in one_of
        if any(
            allof_item.get("properties", {}).get("type", {}).get("const") == "eda_trigger"
            for allof_item in entry.get("allOf", [])
        )
    ]
    assert len(eda_entries) == 1


async def test_eda_trigger_in_node_type_catalog() -> None:
    """EDA trigger should be listed in the node type catalog."""
    catalog_path = SCHEMA_DIR.parent / "catalog" / "node_type_catalog.json"
    with catalog_path.open() as f:
        catalog = json.load(f)

    eda_types = [nt for nt in catalog["node_types"] if nt["type"] == "eda_trigger"]
    assert len(eda_types) == 1
    assert eda_types[0]["labels"]["category"] == "trigger"
