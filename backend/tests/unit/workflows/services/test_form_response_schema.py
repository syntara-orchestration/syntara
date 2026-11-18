"""Tests for generated form response JSON Schemas."""

from typing import Any
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator, SchemaError
from pydantic import ValidationError

from syntara.workflow_core.validation import validate_json_schema_definition
from syntara.workflows.services.form_response_schema import (
    generate_form_response_schema,
    prepare_workflow_definition_for_persistence,
)


def _form_definition() -> dict[str, Any]:
    return {
        "fields": [
            {"type": "text", "value_name": "title", "label": "Title", "required": True},
            {"type": "email", "value_name": "contact", "label": "Contact"},
            {"type": "number", "value_name": "count", "label": "Count"},
            {"type": "checkbox", "value_name": "accepted", "label": "Accepted", "required": True},
            {"type": "date", "value_name": "scheduled_at", "label": "Scheduled at", "required": True},
            {
                "type": "dropdown",
                "value_name": "severity",
                "label": "Severity",
                "options": {
                    "source": "static",
                    "values": [
                        {"display_label": "Low", "value": "low"},
                        {"display_label": "High", "value": "high"},
                    ],
                },
            },
            {
                "type": "multi_select",
                "value_name": "tags",
                "label": "Tags",
                "options": {
                    "source": "static",
                    "values": [{"display_label": "One", "value": "one"}],
                },
            },
        ]
    }


def _workflow_definition() -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "name": "form-workflow",
        "triggers": [
            {
                "id": "form",
                "type": "form_trigger",
                "parameters": {
                    "form_definition": _form_definition(),
                    "response_schema": {"type": "invalid-client-schema"},
                },
            }
        ],
        "nodes": [],
        "edges": [],
    }


def test_generated_schema_matches_normalized_response_data() -> None:
    schema = generate_form_response_schema(_form_definition())

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "title",
        "contact",
        "count",
        "accepted",
        "scheduled_at",
        "severity",
        "tags",
    ]
    assert schema["properties"]["title"] == {"type": "string", "minLength": 1}
    assert schema["properties"]["contact"] == {"type": "string"}
    assert schema["properties"]["count"] == {"type": ["number", "null"]}
    assert schema["properties"]["accepted"] == {"const": True}
    assert schema["properties"]["scheduled_at"] == {"type": "string", "format": "date"}
    assert schema["properties"]["severity"] == {
        "type": ["string", "null"],
        "enum": ["low", "high", None],
    }
    assert schema["properties"]["tags"] == {
        "type": "array",
        "items": {"type": "string", "enum": ["one"]},
    }
    assert Draft202012Validator(schema).is_valid(
        {
            "title": "Request title",
            "contact": "",
            "count": None,
            "accepted": True,
            "scheduled_at": "",
            "severity": None,
            "tags": [],
        }
    )

    assert not Draft202012Validator(schema).is_valid(
        {
            "title": "",
            "contact": "",
            "count": None,
            "accepted": True,
            "scheduled_at": "",
            "severity": None,
            "tags": [],
        }
    )


def test_required_email_schema_rejects_empty_string() -> None:
    form_definition = _form_definition()
    form_definition["fields"][1]["required"] = True

    schema = generate_form_response_schema(form_definition)

    assert schema["properties"]["contact"] == {"type": "string", "minLength": 1}
    assert not Draft202012Validator(schema).is_valid(
        {
            "title": "Request title",
            "contact": "",
            "count": None,
            "accepted": True,
            "scheduled_at": "",
            "severity": None,
            "tags": [],
        }
    )


def test_generated_schema_passes_security_validation() -> None:
    schema = generate_form_response_schema(_form_definition())

    validate_json_schema_definition(schema)


def test_generated_schema_is_checked_against_draft_2020_12() -> None:
    schema_error = SchemaError("invalid generated schema")
    with patch.object(Draft202012Validator, "check_schema", side_effect=schema_error):
        with pytest.raises(ValueError, match="Invalid JSON Schema: invalid generated schema"):
            generate_form_response_schema(_form_definition())


@pytest.mark.parametrize(
    ("include_date", "include_time", "include_timezone", "expected_schema"),
    [
        (True, False, False, {"type": "string", "format": "date"}),
        (True, True, False, {"type": "string", "format": "date-time"}),
        (True, True, True, {"type": "string", "format": "date-time"}),
        (False, True, False, {"type": "string", "format": "time"}),
        (False, True, True, {"type": "string", "format": "time"}),
        (False, False, True, {"type": "string"}),
    ],
)
def test_date_field_schema_matches_collected_components(
    *,
    include_date: bool,
    include_time: bool,
    include_timezone: bool,
    expected_schema: dict[str, Any],
) -> None:
    definition = {
        "fields": [
            {
                "type": "date",
                "value_name": "when",
                "label": "When",
                "include_date": include_date,
                "include_time": include_time,
                "include_timezone": include_timezone,
            }
        ]
    }

    schema = generate_form_response_schema(definition)

    assert schema["properties"]["when"] == expected_schema


def test_optional_checkbox_accepts_both_boolean_values() -> None:
    definition = {
        "fields": [
            {
                "type": "checkbox",
                "value_name": "confirmed",
                "label": "Confirmed",
                "required": False,
            }
        ]
    }

    schema = generate_form_response_schema(definition)

    assert schema["properties"]["confirmed"] == {"type": "boolean"}
    assert Draft202012Validator(schema).is_valid({"confirmed": False})
    assert Draft202012Validator(schema).is_valid({"confirmed": True})
    assert not Draft202012Validator(schema).is_valid({"confirmed": None})


def test_required_fields_reject_empty_values() -> None:
    definition = {
        "fields": [
            {"type": "number", "value_name": "count", "label": "Count", "required": True},
            {
                "type": "dropdown",
                "value_name": "static_choice",
                "label": "Static choice",
                "required": True,
                "options": {
                    "source": "static",
                    "values": [{"display_label": "Low", "value": "low"}],
                },
            },
            {
                "type": "dropdown",
                "value_name": "dynamic_choice",
                "label": "Dynamic choice",
                "required": True,
                "options": {
                    "source": "dynamic",
                    "expression": "${upstream.items}",
                    "label_key": "label",
                    "value_key": "value",
                },
            },
            {
                "type": "multi_select",
                "value_name": "tags",
                "label": "Tags",
                "required": True,
                "options": {
                    "source": "static",
                    "values": [{"display_label": "One", "value": "one"}],
                },
            },
        ]
    }

    schema = generate_form_response_schema(definition)

    assert schema["properties"]["count"] == {"type": "number"}
    assert schema["properties"]["static_choice"] == {"type": "string", "enum": ["low"]}
    assert schema["properties"]["dynamic_choice"] == {"type": ["string", "number", "boolean"]}
    assert schema["properties"]["tags"] == {
        "type": "array",
        "items": {"type": "string", "enum": ["one"]},
        "minItems": 1,
    }
    valid_response = {
        "count": 1,
        "static_choice": "low",
        "dynamic_choice": "dynamic",
        "tags": ["one"],
    }
    assert Draft202012Validator(schema).is_valid(valid_response)
    for value_name, empty_value in (
        ("count", None),
        ("static_choice", None),
        ("dynamic_choice", None),
        ("tags", []),
    ):
        invalid_response = {**valid_response, value_name: empty_value}
        assert not Draft202012Validator(schema).is_valid(invalid_response)


def test_prepare_handles_malformed_node_type_and_id() -> None:
    malformed_type_definition = {
        "schema_version": "2.0.0",
        "triggers": [],
        "nodes": [
            {
                "id": [],
                "type": {},
                "parameters": {"form_definition": _form_definition()},
            }
        ],
        "edges": [],
    }
    malformed_id_definition = {
        "schema_version": "2.0.0",
        "triggers": [],
        "nodes": [
            {
                "id": [],
                "type": "form_prompt",
                "parameters": {"form_definition": _form_definition()},
            }
        ],
        "edges": [],
    }

    malformed_type_prepared = prepare_workflow_definition_for_persistence(
        malformed_type_definition, malformed_type_definition
    )
    malformed_id_prepared = prepare_workflow_definition_for_persistence(
        malformed_id_definition, malformed_id_definition
    )

    assert "response_schema" not in malformed_type_prepared["nodes"][0]["parameters"]
    assert "response_schema" in malformed_id_prepared["nodes"][0]["parameters"]


def test_dynamic_options_use_conservative_scalar_types() -> None:
    definition = {
        "fields": [
            {
                "type": "dropdown",
                "value_name": "choice",
                "label": "Choice",
                "options": {
                    "source": "dynamic",
                    "expression": "${upstream.items}",
                    "label_key": "label",
                    "value_key": "value",
                },
            },
            {
                "type": "multi_select",
                "value_name": "choices",
                "label": "Choices",
                "options": {
                    "source": "dynamic",
                    "expression": "${upstream.items}",
                    "label_key": "label",
                    "value_key": "value",
                },
            },
        ]
    }

    schema = generate_form_response_schema(definition)

    assert schema["properties"]["choice"] == {"type": ["string", "number", "boolean", "null"]}
    assert schema["properties"]["choices"] == {
        "type": "array",
        "items": {"type": ["string", "number", "boolean"]},
    }


def test_prepare_overwrites_client_schema_and_does_not_mutate_input() -> None:
    definition = _workflow_definition()

    prepared = prepare_workflow_definition_for_persistence(definition)

    assert definition["triggers"][0]["parameters"]["response_schema"] == {"type": "invalid-client-schema"}
    prepared_parameters = prepared["triggers"][0]["parameters"]
    assert prepared_parameters["response_schema"] == generate_form_response_schema(_form_definition())


def test_prepare_preserves_schema_for_unchanged_legacy_form() -> None:
    definition = _workflow_definition()
    previous = _workflow_definition()
    del previous["triggers"][0]["parameters"]["response_schema"]
    persisted_schema = generate_form_response_schema(_form_definition())
    persisted_schema["title"] = "Persisted form response schema"
    previous["triggers"][0]["parameters"]["response_schema"] = persisted_schema

    prepared = prepare_workflow_definition_for_persistence(definition, previous)

    prepared_schema = prepared["triggers"][0]["parameters"]["response_schema"]
    regenerated_schema = generate_form_response_schema(_form_definition())
    client_supplied_schema = definition["triggers"][0]["parameters"]["response_schema"]

    assert prepared_schema == persisted_schema
    assert prepared_schema != regenerated_schema
    assert client_supplied_schema != persisted_schema


def test_prepare_keeps_legacy_form_without_schema_unchanged() -> None:
    definition = _workflow_definition()
    del definition["triggers"][0]["parameters"]["response_schema"]
    previous = _workflow_definition()
    del previous["triggers"][0]["parameters"]["response_schema"]

    prepared = prepare_workflow_definition_for_persistence(definition, previous)

    assert "response_schema" not in prepared["triggers"][0]["parameters"]


@pytest.mark.parametrize(
    "definition",
    [
        {"fields": []},
        {},
        {
            "fields": [
                {"type": "unknown", "value_name": "value", "label": "Value"},
            ]
        },
        {
            "fields": [
                {"type": "text", "value_name": "value", "label": "Value"},
                {"type": "email", "value_name": "value", "label": "Value"},
            ]
        },
        {
            "fields": [
                {
                    "type": "date",
                    "value_name": "when",
                    "label": "When",
                    "include_date": False,
                    "include_time": False,
                    "include_timezone": False,
                }
            ]
        },
        {
            "fields": [
                {
                    "type": "date",
                    "value_name": "when",
                    "label": "When",
                    "include_date": True,
                    "include_time": False,
                    "include_timezone": True,
                }
            ]
        },
    ],
)
def test_invalid_form_definition_is_rejected(definition: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        generate_form_response_schema(definition)
