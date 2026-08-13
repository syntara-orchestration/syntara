"""Validation logic for runtime setting values.

Validates values against both the expected :class:`SettingValueType` and
optional constraint schemas (min, max, allowed_values, pattern) before
they are persisted.
"""

from __future__ import annotations

import re
from typing import Any

from syntara.settings.exceptions import SettingValidationError
from syntara.settings.models.runtime_setting import SettingValueType

_TYPE_CHECKS: dict[SettingValueType, type | tuple[type, ...]] = {
    SettingValueType.STRING: str,
    SettingValueType.INTEGER: int,
    SettingValueType.FLOAT: (int, float),
    SettingValueType.BOOLEAN: bool,
}


def validate_setting_value(
    *,
    key: str,
    value: Any,  # noqa: ANN401
    value_type: SettingValueType,
    validation_schema: dict[str, Any] | None,
) -> None:
    """Validate a setting value against its type and constraint schema.

    Args:
        key: Dot-namespaced setting key (for error messages).
        value: The value to validate.
        value_type: Expected type from the setting definition.
        validation_schema: Optional constraint dict with keys like
            ``min``, ``max``, ``allowed_values``, ``pattern``.

    Raises:
        SettingValidationError: If the value fails type or constraint checks.

    """
    if value is None:
        return

    _check_type(key, value, value_type)

    if validation_schema:
        _check_constraints(key, value, validation_schema)


def _check_type(key: str, value: Any, value_type: SettingValueType) -> None:  # noqa: ANN401
    """Validate that the value matches the expected SettingValueType."""
    if value_type == SettingValueType.JSON:
        return

    # Bool must be checked before int because isinstance(True, int) is True
    if value_type != SettingValueType.BOOLEAN and isinstance(value, bool):
        raise SettingValidationError(
            key,
            f"expects type {value_type.value.upper()}, got bool",
        )

    expected = _TYPE_CHECKS.get(value_type)
    if expected is not None and not isinstance(value, expected):
        actual = type(value).__name__
        raise SettingValidationError(
            key,
            f"expects type {value_type.value.upper()}, got {actual}",
        )


_NUMERIC_TYPES = {SettingValueType.INTEGER, SettingValueType.FLOAT}


def check_schema_compatibility(key: str, value_type: SettingValueType, schema: dict[str, Any]) -> None:
    """Validate that the schema constraints make sense for the value_type."""
    if ("min" in schema or "max" in schema) and value_type not in _NUMERIC_TYPES:
        raise SettingValidationError(
            key,
            f"min/max constraints are only valid for INTEGER or FLOAT, got {value_type.value.upper()}",
        )

    if "min" in schema and "max" in schema and schema["min"] > schema["max"]:
        raise SettingValidationError(
            key,
            f"min ({schema['min']}) cannot be greater than max ({schema['max']})",
        )

    if "pattern" in schema and value_type != SettingValueType.STRING:
        raise SettingValidationError(
            key,
            f"pattern constraint is only valid for STRING, got {value_type.value.upper()}",
        )

    if "allowed_values" in schema and value_type != SettingValueType.STRING:
        raise SettingValidationError(
            key,
            f"allowed_values constraint is only valid for STRING, got {value_type.value.upper()}",
        )


def _check_constraints(key: str, value: Any, schema: dict[str, Any]) -> None:  # noqa: ANN401
    """Validate the value against min/max/allowed_values/pattern constraints."""
    if "min" in schema and value < schema["min"]:
        raise SettingValidationError(key, f"must be >= {schema['min']}")

    if "max" in schema and value > schema["max"]:
        raise SettingValidationError(key, f"must be <= {schema['max']}")

    if "allowed_values" in schema and value not in schema["allowed_values"]:
        allowed = ", ".join(str(v) for v in schema["allowed_values"])
        raise SettingValidationError(key, f"must be one of: {allowed}")

    if "pattern" in schema and not re.fullmatch(schema["pattern"], str(value)):
        raise SettingValidationError(key, f"must match pattern: {schema['pattern']}")
