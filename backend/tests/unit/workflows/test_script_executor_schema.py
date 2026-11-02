"""Tests for the Script executor JSON Schema."""

import json
from pathlib import Path


def test_script_schema_uses_execution_profile_union() -> None:
    """The Script schema exposes a discriminated profile instead of a flat target field."""
    schema_path = Path(__file__).resolve().parents[3] / "src" / "syntara" / "schemas" / "workflows" / "v2"
    schema = json.loads((schema_path / "executors" / "script.schema.json").read_text())
    properties = schema["parameterSchema"]["properties"]

    assert "execution_target_id" not in properties
    profile_schema = properties["execution_profile"]
    assert profile_schema["default"] is None
    profile_union = profile_schema["anyOf"][0]
    target_profile = profile_union["oneOf"][0]

    assert profile_union["discriminator"] == {"propertyName": "type"}
    assert target_profile["required"] == ["type", "execution_target_id"]
    assert target_profile["properties"]["type"] == {"const": "execution_target"}
    assert target_profile["properties"]["execution_target_id"] == {"type": "string", "format": "uuid"}
