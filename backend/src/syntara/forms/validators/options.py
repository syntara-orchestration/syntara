"""Dynamic options resolution for form fields.

Resolves dynamic dropdown/multi-select options from upstream node output and
converts them into a static option list.
"""

from __future__ import annotations

import math
from typing import Any

import structlog

from syntara.core.constants import FieldLimits
from syntara.forms.models.form_fields import StaticOption, StaticOptions

logger = structlog.stdlib.get_logger(__name__)


def resolve_dynamic_options(
    resolved_list: Any,  # noqa: ANN401
    field_name: str,
) -> StaticOptions:
    """Resolve dynamic options into a static option list.

    Args:
        resolved_list: The resolved list from upstream node output
        field_name: Field name for error messages

    Returns:
        StaticOptions with resolved values

    Raises:
        TypeError: If resolved_list is not a list or contains non-scalar types
        ValueError: If the list is empty, exceeds size limits, or contains NaN/Infinity

    """
    # Validate that resolved value is a list
    if not isinstance(resolved_list, list):
        type_name = type(resolved_list).__name__
        msg = (
            f"Dynamic options for field '{field_name}' expected a list, "
            f"got {type_name}. Do not coerce scalars into single-item lists - "
            f"this likely indicates a bug in the upstream node."
        )
        raise TypeError(msg)

    # Check size cap
    if len(resolved_list) > FieldLimits.FORM_OPTIONS_MAX_LENGTH:
        msg = (
            f"Dynamic options for field '{field_name}' produced {len(resolved_list)} options, "
            f"exceeding the maximum of {FieldLimits.FORM_OPTIONS_MAX_LENGTH}"
        )
        raise ValueError(msg)

    # Handle empty list
    if len(resolved_list) == 0:
        msg = f"Dynamic options for field '{field_name}' resolved to an empty list"
        raise ValueError(msg)

    # Only scalars are supported
    if not all(isinstance(item, (str, int, float, bool)) for item in resolved_list):
        types_found = {type(item).__name__ for item in resolved_list}
        msg = (
            f"Dynamic options for field '{field_name}' contains unsupported types: {', '.join(sorted(types_found))}. "
            f"All elements must be scalars (str, int, float, or bool)."
        )
        raise TypeError(msg)

    # NaN/Infinity are not representable in standard JSON (json.dumps emits the
    # non-standard NaN/Infinity tokens, which strict parsers reject), and
    # nan != nan would silently defeat the de-duplication below. Mirrors the
    # finiteness rule applied to submitted numbers in _coerce_number.
    non_finite = [item for item in resolved_list if isinstance(item, float) and not math.isfinite(item)]
    if non_finite:
        msg = (
            f"Dynamic options for field '{field_name}' contains non-finite numbers: "
            f"{', '.join(str(item) for item in non_finite)}. NaN and Infinity are not accepted."
        )
        raise ValueError(msg)

    return _convert_scalars_to_options(resolved_list)


def _convert_scalars_to_options(items: list[str | int | float | bool]) -> StaticOptions:
    """Convert a list of scalars to static options.

    Each scalar becomes both label and value: {label: str(v), value: v}.
    Duplicates are de-duplicated, first occurrence wins.
    """
    seen: set[str | int | float | bool] = set()
    options: list[StaticOption] = []

    for item in items:
        if item in seen:
            logger.warning("Duplicate option value in dynamic options", value=item)
            continue

        seen.add(item)
        options.append(StaticOption(display_label=str(item), value=item))

    return StaticOptions(source="static", values=options)
