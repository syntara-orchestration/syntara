"""Generate JSON Schemas for normalized form response data."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, assert_never

from pydantic import ValidationError

from syntara.core.constants import JsonbLimits
from syntara.core.jsonb_limits import validate_jsonb_size
from syntara.forms.models.form_fields import (
    CheckboxField,
    DateField,
    DropdownField,
    EmailField,
    FormDefinition,
    FormField,
    MultiSelectField,
    NumberField,
    StaticOptions,
    TextField,
)
from syntara.workflow_core.validation import validate_json_schema_definition

_FORM_NODE_TYPES = frozenset({"form_prompt", "form_trigger"})
_SCALAR_TYPES = ["string", "number", "boolean"]


def _text_schema(field: TextField | EmailField) -> dict[str, Any]:
    if field.required:
        return {"type": "string", "minLength": 1}
    return {"type": "string"}


def _number_schema(field: NumberField) -> dict[str, Any]:
    if field.required:
        return {"type": "number"}
    return {"type": ["number", "null"]}


def _checkbox_schema(field: CheckboxField) -> dict[str, Any]:
    return {"const": True} if field.required else {"type": "boolean"}


def _date_schema(field: DateField) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if field.include_date and field.include_time:
        schema["format"] = "date-time"
    elif field.include_date:
        schema["format"] = "date"
    elif field.include_time:
        schema["format"] = "time"
    return schema


def _dropdown_schema(field: DropdownField) -> dict[str, Any]:
    options = field.options
    if isinstance(options, StaticOptions):
        if field.required:
            return {
                "type": "string",
                "enum": [option.value for option in options.values],
            }
        return {
            "type": ["string", "null"],
            "enum": [option.value for option in options.values] + [None],
        }
    if field.required:
        return {"type": _SCALAR_TYPES}
    return {"type": [*_SCALAR_TYPES, "null"]}


def _multi_select_schema(field: MultiSelectField) -> dict[str, Any]:
    options = field.options
    if isinstance(options, StaticOptions):
        schema: dict[str, Any] = {
            "type": "array",
            "items": {"type": "string", "enum": [option.value for option in options.values]},
        }
        if field.required:
            schema["minItems"] = 1
        return schema
    dynamic_schema: dict[str, Any] = {"type": "array", "items": {"type": _SCALAR_TYPES}}
    if field.required:
        dynamic_schema["minItems"] = 1
    return dynamic_schema


def prepare_workflow_definition_for_persistence(
    workflow_definition: dict[str, Any],
    previous_definition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a persistence-ready copy with canonical form response schemas.

    Client-supplied ``response_schema`` values are discarded. When a form
    definition is unchanged, the schema from the previous immutable version is
    retained so legacy definitions are not retroactively modified.
    """
    prepared = deepcopy(workflow_definition)
    previous_parameters = _form_parameters_by_node_id(previous_definition)

    items = [*prepared.get("triggers", []), *prepared.get("nodes", [])]
    for item in items:
        if not isinstance(item, dict):
            continue
        node_type = _form_node_type(item)
        if node_type is None:
            continue

        parameters = item.get("parameters")
        if not isinstance(parameters, dict):
            continue

        node_id = item.get("id")
        previous = previous_parameters.get((node_id, node_type)) if isinstance(node_id, str) else None
        form_definition = parameters.get("form_definition")
        if previous is not None and previous.get("form_definition") == form_definition:
            persisted_schema = previous.get("response_schema")
            if persisted_schema is None:
                parameters.pop("response_schema", None)
            else:
                parameters["response_schema"] = deepcopy(persisted_schema)
            continue

        parameters.pop("response_schema", None)
        if isinstance(form_definition, dict):
            try:
                parameters["response_schema"] = generate_form_response_schema(form_definition)
            except ValidationError:
                continue

    validate_jsonb_size(
        prepared,
        field_name="workflow_definition",
        max_bytes=JsonbLimits.MAX_WORKFLOW_DEFINITION_BYTES,
    )
    return prepared


def generate_form_response_schema(form_definition: dict[str, Any]) -> dict[str, Any]:
    """Generate a JSON Schema for a form's normalized ``response_data`` object."""
    form = FormDefinition.model_validate(form_definition)
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": [field.value_name for field in form.fields],
        "properties": {field.value_name: _field_schema(field) for field in form.fields},
    }
    validate_json_schema_definition(schema, draft="draft-2020-12")
    return schema


def _form_parameters_by_node_id(definition: dict[str, Any] | None) -> dict[tuple[str, str], dict[str, Any]]:
    if definition is None:
        return {}

    parameters_by_node: dict[tuple[str, str], dict[str, Any]] = {}
    for item in [*definition.get("triggers", []), *definition.get("nodes", [])]:
        if not isinstance(item, dict):
            continue
        node_type = _form_node_type(item)
        if node_type is None:
            continue
        parameters = item.get("parameters")
        node_id = item.get("id")
        if isinstance(parameters, dict) and isinstance(node_id, str):
            parameters_by_node[(node_id, node_type)] = parameters
    return parameters_by_node


def _form_node_type(item: dict[str, Any]) -> str | None:
    node_type = item.get("type")
    if isinstance(node_type, str) and node_type in _FORM_NODE_TYPES:
        return node_type
    return None


def _field_schema(field: FormField) -> dict[str, Any]:
    match field:
        case TextField() | EmailField():
            return _text_schema(field)
        case NumberField():
            return _number_schema(field)
        case CheckboxField():
            return _checkbox_schema(field)
        case DateField():
            return _date_schema(field)
        case DropdownField():
            return _dropdown_schema(field)
        case MultiSelectField():
            return _multi_select_schema(field)
        case _:
            assert_never(field)
