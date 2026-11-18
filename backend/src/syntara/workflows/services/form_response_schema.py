"""Generate JSON Schemas for normalized form response data."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, cast

from pydantic import ValidationError

from syntara.forms.models.form_fields import (
    CheckboxField,
    DateField,
    DropdownField,
    FormDefinition,
    FormField,
    MultiSelectField,
    StaticOptions,
)
from syntara.workflows.json_schema_validation import validate_json_schema_definition

if TYPE_CHECKING:
    from collections.abc import Callable

_FORM_NODE_TYPES = frozenset({"form_prompt", "form_trigger"})
_SCALAR_TYPES = ["string", "number", "boolean"]


def _text_schema(_field: FormField) -> dict[str, Any]:
    return {"type": "string"}


def _number_schema(_field: FormField) -> dict[str, Any]:
    return {"type": ["number", "null"]}


def _checkbox_schema(field: FormField) -> dict[str, Any]:
    return {"const": True} if cast("CheckboxField", field).required else {"type": "boolean"}


def _date_schema(field: FormField) -> dict[str, Any]:
    date_field = cast("DateField", field)
    schema: dict[str, Any] = {"type": "string"}
    if date_field.include_date and date_field.include_time:
        schema["format"] = "date-time"
    elif date_field.include_date:
        schema["format"] = "date"
    elif date_field.include_time:
        schema["format"] = "time"
    return schema


def _dropdown_schema(field: FormField) -> dict[str, Any]:
    options = cast("DropdownField", field).options
    if isinstance(options, StaticOptions):
        return {
            "type": ["string", "null"],
            "enum": [option.value for option in options.values] + [None],
        }
    return {"type": [*_SCALAR_TYPES, "null"]}


def _multi_select_schema(field: FormField) -> dict[str, Any]:
    options = cast("MultiSelectField", field).options
    if isinstance(options, StaticOptions):
        return {
            "type": "array",
            "items": {"type": "string", "enum": [option.value for option in options.values]},
        }
    return {"type": "array", "items": {"type": _SCALAR_TYPES}}


_FIELD_SCHEMA_BUILDERS: dict[str, Callable[[FormField], dict[str, Any]]] = {
    "text": _text_schema,
    "email": _text_schema,
    "number": _number_schema,
    "checkbox": _checkbox_schema,
    "date": _date_schema,
    "dropdown": _dropdown_schema,
    "multi_select": _multi_select_schema,
}


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
        if not isinstance(item, dict) or item.get("type") not in _FORM_NODE_TYPES:
            continue

        parameters = item.get("parameters")
        if not isinstance(parameters, dict):
            continue

        node_id = item.get("id")
        previous = previous_parameters.get((node_id, item.get("type")))
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
    validate_json_schema_definition(schema)
    return schema


def _form_parameters_by_node_id(definition: dict[str, Any] | None) -> dict[tuple[Any, Any], dict[str, Any]]:
    if definition is None:
        return {}

    parameters_by_node: dict[tuple[Any, Any], dict[str, Any]] = {}
    for item in [*definition.get("triggers", []), *definition.get("nodes", [])]:
        if not isinstance(item, dict) or item.get("type") not in _FORM_NODE_TYPES:
            continue
        parameters = item.get("parameters")
        if isinstance(parameters, dict):
            parameters_by_node[(item.get("id"), item.get("type"))] = parameters
    return parameters_by_node


def _field_schema(field: FormField) -> dict[str, Any]:
    builder = _FIELD_SCHEMA_BUILDERS.get(field.type)
    if builder is None:
        msg = f"Unsupported form field type: {field.type}"
        raise ValueError(msg)
    return builder(field)
