"""Contract tests for form trigger JSON schema."""

import json
from pathlib import Path
from typing import Any, cast

import jsonschema
import pytest

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "src" / "syntara" / "schemas" / "workflows" / "v2"


@pytest.fixture
def form_schema() -> dict[str, Any]:
    """Load the form trigger schema."""
    return cast("dict[str, Any]", json.loads((SCHEMA_DIR / "triggers" / "form.schema.json").read_text()))


def _valid_parameters() -> dict[str, Any]:
    """Return a minimal valid form trigger parameter object."""
    return {
        "form_definition": {
            "fields": [{"type": "text", "value_name": "email", "label": "Email"}],
        }
    }


def _validate_parameters(parameters: dict[str, Any], form_schema: dict[str, Any]) -> None:
    """Validate a detached parameterSchema with its file-level local definitions."""
    parameter_schema = {
        **form_schema["parameterSchema"],
        "$defs": form_schema["$defs"],
    }
    jsonschema.validate(parameters, parameter_schema)


def test_form_schema_has_parameter_and_result_schema(form_schema: dict[str, Any]) -> None:
    """The schema publishes both parameter and pass-through result contracts."""
    assert "parameterSchema" in form_schema
    assert "resultSchema" in form_schema
    assert "form_definition" in form_schema["parameterSchema"]["required"]
    assert form_schema["resultSchema"]["type"] == "object"


def test_valid_minimal_and_full_configs(form_schema: dict[str, Any]) -> None:
    """Minimal and fully populated supported configs validate."""
    _validate_parameters(_valid_parameters(), form_schema)
    full = {
        **_valid_parameters(),
        "message": "Provide account details.",
        "submit_label": "Continue",
        "success_message": "Your response was received.",
        "css_override": ".form { color: blue; }",
    }
    _validate_parameters(full, form_schema)


def test_rejects_additional_properties(form_schema: dict[str, Any]) -> None:
    """Unknown top-level parameters are rejected."""
    invalid = {**_valid_parameters(), "unexpected": True}
    with pytest.raises(jsonschema.ValidationError):
        _validate_parameters(invalid, form_schema)


@pytest.mark.parametrize("parameter", ["response_window", "fallback_decision", "responder_users", "responder_groups"])
def test_rejects_form_prompt_only_parameters(form_schema: dict[str, Any], parameter: str) -> None:
    """Parameters exclusive to the in-execution prompt are rejected."""
    invalid = {**_valid_parameters(), parameter: "not-supported"}
    with pytest.raises(jsonschema.ValidationError):
        _validate_parameters(invalid, form_schema)


def test_rejects_dynamic_options(form_schema: dict[str, Any]) -> None:
    """Form trigger dropdowns only accept authored static options."""
    invalid = {
        "form_definition": {
            "fields": [
                {
                    "type": "dropdown",
                    "value_name": "region",
                    "label": "Region",
                    "options": {
                        "source": "dynamic",
                        "expression": "available_regions",
                        "label_key": "name",
                        "value_key": "id",
                    },
                }
            ]
        }
    }
    with pytest.raises(jsonschema.ValidationError):
        _validate_parameters(invalid, form_schema)


def test_form_trigger_in_workflow_definition_schema() -> None:
    """The form trigger appears only in the trigger union."""
    schema = json.loads((SCHEMA_DIR / "workflow_definition.schema.json").read_text())
    trigger_branches = schema["$defs"]["trigger_node"]["oneOf"]
    node_branches = schema["$defs"]["node"]["oneOf"]

    def _has_type(branches: list[dict[str, Any]], node_type: str) -> list[dict[str, Any]]:
        return [
            branch
            for branch in branches
            if any(
                item.get("properties", {}).get("type", {}).get("const") == node_type for item in branch.get("allOf", [])
            )
        ]

    assert len(_has_type(trigger_branches, "form_trigger")) == 1
    assert _has_type(node_branches, "form_trigger") == []


def test_form_trigger_in_node_type_catalog() -> None:
    """The node catalog has one form trigger entry with the trigger label."""
    catalog = json.loads((SCHEMA_DIR / "catalog" / "node_type_catalog.json").read_text())
    entries = [entry for entry in catalog["node_types"] if entry["type"] == "form_trigger"]

    assert len(entries) == 1
    assert entries[0]["labels"]["category"] == "trigger"
