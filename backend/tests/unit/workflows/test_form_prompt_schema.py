"""Tests for form-prompt executor parameter schema validation."""

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "syntara"
    / "schemas"
    / "workflows"
    / "v2"
    / "executors"
    / "form_prompt.schema.json"
)


@pytest.fixture
def form_prompt_schema() -> dict[str, Any]:
    """Load the executor's parameter schema used during workflow validation."""
    with SCHEMA_PATH.open() as schema_file:
        schema: dict[str, Any] = json.load(schema_file)
    return schema


def _parameter_validator(form_prompt_schema: dict[str, Any]) -> jsonschema.Draft202012Validator:
    """Build a validator with the executor's local definitions in the ref scope."""
    parameter_schema = {
        **form_prompt_schema["parameterSchema"],
        "$defs": form_prompt_schema["$defs"],
    }
    return jsonschema.Draft202012Validator(parameter_schema)


def _parameters(options: dict[str, Any]) -> dict[str, Any]:
    """Wrap a dynamic options config in the relevant form-prompt shape."""
    return {
        "form_definition": {
            "fields": [
                {
                    "type": "dropdown",
                    "options": options,
                }
            ]
        }
    }


@pytest.mark.parametrize(
    "options",
    [
        {"source": "dynamic", "expression": "${trigger.regions}", "value_key": "id"},
        {"source": "dynamic", "expression": "${trigger.regions}", "label_key": "name"},
        {
            "source": "dynamic",
            "expression": "${trigger.regions}",
            "label_key": "",
            "value_key": "id",
        },
        {
            "source": "dynamic",
            "expression": "${trigger.regions}",
            "label_key": "name",
            "value_key": "",
        },
    ],
)
def test_dynamic_options_require_non_empty_keys_at_workflow_validation(
    form_prompt_schema: dict[str, Any],
    options: dict[str, Any],
) -> None:
    """The form-prompt executor schema rejects absent and empty object keys."""
    validator = _parameter_validator(form_prompt_schema)

    with pytest.raises(jsonschema.ValidationError):
        validator.validate(_parameters(options))


def test_dynamic_options_accept_explicit_keys_at_workflow_validation(
    form_prompt_schema: dict[str, Any],
) -> None:
    """A dynamic field with both keys passes executor parameter validation."""
    validator = _parameter_validator(form_prompt_schema)

    validator.validate(
        _parameters(
            {
                "source": "dynamic",
                "expression": "${trigger.regions}",
                "label_key": "name",
                "value_key": "id",
            }
        )
    )
