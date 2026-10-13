"""Dynamic options resolution for form fields.

Resolves dynamic dropdown/multi-select options from upstream node output and
materializes them as a typed option snapshot for a form prompt.
"""

from __future__ import annotations

import copy
import math
from typing import Any

import structlog
from pydantic import ValidationError

from syntara.core.constants import FieldLimits
from syntara.core.exceptions import SafeValueError
from syntara.forms.models.form_fields import FormDefinition, ResolvedOption, ResolvedOptions

logger = structlog.stdlib.get_logger(__name__)

_OPTION_FIELD_TYPES = frozenset({"dropdown", "multi_select"})
_OPTION_LABEL_MAX_LENGTH = 200
_OptionScalar = str | int | float | bool


def _validate_scalar(value: Any, field_name: str, index: int, *, key: str) -> _OptionScalar:  # noqa: ANN401
    """Validate one option value without including its contents in errors."""
    location = f" at key '{key}'"
    if not isinstance(value, (str, int, float, bool)):
        msg = (
            f"Dynamic options for field '{field_name}' at index {index}{location} "
            f"must be a scalar (str, int, float, or bool), got {type(value).__name__}"
        )
        raise TypeError(msg)

    if isinstance(value, float) and not math.isfinite(value):
        msg = (
            f"Dynamic options for field '{field_name}' at index {index}{location} "
            "contains a non-finite number; NaN and Infinity are not accepted"
        )
        raise ValueError(msg)

    return value


def _record_option(
    record: dict[str, Any],
    field_name: str,
    index: int,
    label_key: str,
    value_key: str,
) -> ResolvedOption:
    """Extract a display label and typed value from one upstream record."""
    if label_key not in record:
        msg = f"Dynamic options for field '{field_name}' at index {index} is missing label key '{label_key}'"
        raise TypeError(msg)
    label = record[label_key]
    if not isinstance(label, str):
        msg = (
            f"Dynamic options for field '{field_name}' at index {index} has a non-string "
            f"label at key '{label_key}' ({type(label).__name__})"
        )
        raise TypeError(msg)
    if not label:
        msg = f"Dynamic options for field '{field_name}' at index {index} has an empty label at key '{label_key}'"
        raise ValueError(msg)
    if len(label) > _OPTION_LABEL_MAX_LENGTH:
        msg = (
            f"Dynamic options for field '{field_name}' at index {index} has a label longer than "
            f"{_OPTION_LABEL_MAX_LENGTH} characters at key '{label_key}'"
        )
        raise ValueError(msg)

    if value_key not in record:
        msg = f"Dynamic options for field '{field_name}' at index {index} is missing value key '{value_key}'"
        raise TypeError(msg)
    value = _validate_scalar(record[value_key], field_name, index, key=value_key)
    return ResolvedOption(display_label=label, value=value)


def resolve_dynamic_option_items(
    items: list[Any],
    field_name: str,
    label_key: str,
    value_key: str,
) -> list[ResolvedOption]:
    """Convert a list of upstream records into typed options."""
    options: list[ResolvedOption] = []
    seen: set[_OptionScalar] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            msg = (
                f"Dynamic options for field '{field_name}' at index {index} must be an object "
                f"with label key '{label_key}' and value key '{value_key}', got {type(item).__name__}"
            )
            raise TypeError(msg)
        option = _record_option(item, field_name, index, label_key, value_key)

        if option.value in seen:
            logger.warning("Duplicate option value in dynamic options", field=field_name, index=index)
            continue
        seen.add(option.value)
        options.append(option)

    return options


def resolve_dynamic_option_values(
    resolved_list: Any,  # noqa: ANN401
    field_name: str,
    *,
    label_key: str,
    value_key: str,
) -> ResolvedOptions:
    """Resolve an upstream list of records into typed options.

    Each record must provide the configured ``label_key`` and ``value_key``.
    """
    if not isinstance(resolved_list, list):
        type_name = type(resolved_list).__name__
        msg = (
            f"Dynamic options for field '{field_name}' expected a list, "
            f"got {type_name}. Do not coerce scalars into single-item lists - "
            "this likely indicates a bug in the upstream node."
        )
        raise TypeError(msg)

    if len(resolved_list) > FieldLimits.FORM_OPTIONS_MAX_LENGTH:
        msg = (
            f"Dynamic options for field '{field_name}' produced {len(resolved_list)} options, "
            f"exceeding the maximum of {FieldLimits.FORM_OPTIONS_MAX_LENGTH}"
        )
        raise ValueError(msg)

    if not resolved_list:
        msg = f"Dynamic options for field '{field_name}' resolved to an empty list"
        raise ValueError(msg)

    options = resolve_dynamic_option_items(resolved_list, field_name, label_key, value_key)
    return ResolvedOptions(source="dynamic_resolved", values=options)


def _validation_summary(error: ValidationError, form_definition: dict[str, Any]) -> str:
    """Build a short validation error without including upstream input values."""
    details = error.errors(include_url=False)
    if not details:
        return "Resolved form definition is invalid"

    detail = details[0]
    message = str(detail.get("msg", "Resolved form definition is invalid"))
    if message.startswith("Value error, "):
        message = message.removeprefix("Value error, ")
    if message.startswith(("Field '", "Duplicate field names")):
        return message

    location = detail.get("loc", ())
    fields = form_definition.get("fields")
    if isinstance(location, tuple) and len(location) > 1 and location[0] == "fields" and isinstance(fields, list):
        index = location[1]
        if isinstance(index, int) and 0 <= index < len(fields) and isinstance(fields[index], dict):
            field_name = fields[index].get("value_name")
            if isinstance(field_name, str):
                return f"Field '{field_name}': {message}"

    return f"Resolved form definition is invalid: {message}"


def resolve_dynamic_options(form_definition: dict[str, Any]) -> dict[str, Any]:
    """Replace dynamic options with a runtime-resolved list, without mutating input.

    This operates after workflow expressions have been interpolated. The final
    model validation ensures that defaults and the materialized options agree
    before the create-prompt activity is scheduled.
    """
    fields = form_definition.get("fields")
    if not isinstance(fields, list):
        return form_definition

    materialized = copy.deepcopy(form_definition)
    materialized_fields = materialized["fields"]
    for index, field in enumerate(materialized_fields):
        if not isinstance(field, dict) or field.get("type") not in _OPTION_FIELD_TYPES:
            continue
        options = field.get("options")
        if not isinstance(options, dict) or options.get("source") != "dynamic":
            continue

        field_name = field.get("value_name")
        if not isinstance(field_name, str):
            field_name = f"<unnamed at index {index}>"
        label_key = options.get("label_key")
        value_key = options.get("value_key")
        if not isinstance(label_key, str) or not label_key:
            message = f"Dynamic options for field '{field_name}' require a non-empty 'label_key'"
            raise SafeValueError(message)
        if not isinstance(value_key, str) or not value_key:
            message = f"Dynamic options for field '{field_name}' require a non-empty 'value_key'"
            raise SafeValueError(message)
        try:
            resolved = resolve_dynamic_option_values(
                options.get("expression"),
                field_name,
                label_key=label_key,
                value_key=value_key,
            )
        except (TypeError, ValueError) as error:
            raise SafeValueError(str(error)) from error

        field["options"] = resolved.model_dump(mode="json")

    try:
        FormDefinition.model_validate(materialized)
    except ValidationError as error:
        raise SafeValueError(_validation_summary(error, materialized)) from error

    return materialized
