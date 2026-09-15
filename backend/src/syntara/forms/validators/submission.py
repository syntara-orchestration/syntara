"""Form submission validation and coercion.

Validates submitted form data against a FormDefinition, applying type coercion
and enforcing required fields and option membership constraints.
"""

from __future__ import annotations

import math
from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

from syntara.forms.exceptions import FormDataValidationError
from syntara.forms.models.form_errors import FormFieldError
from syntara.forms.models.form_fields import (
    CheckboxField,
    DateField,
    DropdownField,
    EmailField,
    FormDefinition,
    FormField,
    MaskedTextField,
    MultiSelectField,
    NumberField,
    StaticOptions,
    TextAreaField,
    TextField,
)

# Sentinel for distinguishing "not provided" from None
_MISSING = object()


def validate_form_submission(  # noqa: C901
    form: FormDefinition,
    submitted: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and coerce submitted form data.

    Args:
        form: The form definition to validate against
        submitted: Raw submitted data (never mutated)

    Returns:
        Cleaned and coerced data ready for the workflow namespace

    Raises:
        FormDataValidationError: If validation fails (carries all field errors)

    """
    errors: list[FormFieldError] = []
    cleaned: dict[str, Any] = {}

    # Process each field in definition order
    for field in form.fields:
        raw = submitted.get(field.value_name, _MISSING)

        # Step 2: Empty normalization (except checkbox - False is real)
        if not isinstance(field, CheckboxField) and _is_empty(raw):
            raw = _MISSING

        # Step 3: Apply default if absent
        if raw is _MISSING and field.default is not None:
            raw = field.default

        # Step 4: Check required
        if raw is _MISSING:
            if field.required:
                errors.append(
                    FormFieldError(
                        field=field.value_name,
                        label=field.label,
                        code="required",
                        message="This field is required",
                    )
                )
            # Optional and absent → omit key entirely (not None)
            continue

        # Step 5: Coerce to correct type
        try:
            coerced = _coerce_field(field, raw)
        except (TypeError, ValueError) as exc:
            errors.append(
                FormFieldError(
                    field=field.value_name,
                    label=field.label,
                    code="type",
                    message=str(exc),
                )
            )
            continue

        # Step 6: Check option membership for dropdowns/multi-selects
        if isinstance(field, (DropdownField, MultiSelectField)) and isinstance(field.options, StaticOptions):
            valid_values = {opt.value for opt in field.options.values}

            if isinstance(field, MultiSelectField):
                if not isinstance(coerced, list):
                    # Should have been caught by coercion, but guard anyway
                    errors.append(
                        FormFieldError(
                            field=field.value_name,
                            label=field.label,
                            code="type",
                            message="Must be a list",
                        )
                    )
                    continue

                invalid = [v for v in coerced if v not in valid_values]
                if invalid:
                    errors.append(
                        FormFieldError(
                            field=field.value_name,
                            label=field.label,
                            code="not_in_options",
                            message=f"Invalid selection(s): {len(invalid)} value(s) not in option list",
                        )
                    )
                    continue
            # Dropdown - single value
            elif coerced not in valid_values:
                errors.append(
                    FormFieldError(
                        field=field.value_name,
                        label=field.label,
                        code="not_in_options",
                        message="Selected value is not in the option list",
                    )
                )
                continue

        cleaned[field.value_name] = coerced

    # Check for unknown fields in submission
    known_names = {f.value_name for f in form.fields}
    errors.extend(
        FormFieldError(
            field=submitted_key,
            label=submitted_key,
            code="unknown_field",
            message="Unknown field - not defined in form",
        )
        for submitted_key in submitted
        if submitted_key not in known_names
    )

    if errors:
        raise FormDataValidationError(errors)

    return cleaned


def _is_empty(value: Any) -> bool:  # noqa: ANN401
    """Check if a value should be treated as absent.

    Empty string, empty list, and None are all treated as absent.
    This matches HTML form behavior where empty text inputs post as "".
    """
    return value in ("", [], None)


def _coerce_field(field: FormField, raw: Any) -> Any:  # noqa: ANN401
    """Coerce raw submitted value to the field's expected type.

    Args:
        field: Field definition
        raw: Raw submitted value

    Returns:
        Coerced value

    Raises:
        ValueError: If coercion fails

    """
    if isinstance(field, (TextField, TextAreaField, MaskedTextField, EmailField)):
        return _coerce_string(raw)

    if isinstance(field, NumberField):
        return _coerce_number(raw)

    if isinstance(field, CheckboxField):
        return _coerce_checkbox(raw, required=field.required)

    if isinstance(field, DateField):
        return _coerce_date(raw)

    if isinstance(field, DropdownField):
        return _coerce_dropdown(raw)

    if isinstance(field, MultiSelectField):
        return _coerce_multi_select(raw)

    # Should never reach here due to discriminated union
    msg = f"Unknown field type: {type(field)}"
    raise ValueError(msg)


def _coerce_string(raw: Any) -> str:  # noqa: ANN401
    """Coerce to string - only str accepted, no silent stringification."""
    if not isinstance(raw, str):
        msg = f"Must be a string, got {type(raw).__name__}"
        raise TypeError(msg)
    return raw


def _coerce_number(raw: Any) -> int | float:  # noqa: ANN401
    """Coerce to number (int or float).

    Accepts: int, float, or numeric string.
    Rejects: bool (even though bool subclasses int), nan, inf.

    Args:
        raw: Raw value

    Returns:
        Coerced number

    Raises:
        ValueError: If coercion fails

    """
    # Reject bool first (bool subclasses int, but we don't want True → 1)
    if isinstance(raw, bool):
        msg = "Boolean values are not accepted as numbers"
        raise TypeError(msg)

    # Accept: int, float
    if isinstance(raw, (int, float)):
        return raw

    # Accept: numeric string
    if isinstance(raw, str):
        try:
            parsed = float(raw)
            # Reject nan and inf
            if not math.isfinite(parsed):
                msg = "Infinite and NaN values are not accepted"
                raise ValueError(msg)  # noqa: TRY301
            return parsed
        except ValueError:
            msg = "Must be a valid number string"
            raise ValueError(msg) from None

    msg = f"Must be a number, got {type(raw).__name__}"
    raise TypeError(msg)


def _coerce_checkbox(raw: Any, *, required: bool) -> bool:  # noqa: ANN401
    """Coerce to boolean.

    Accepts: bool, 0/1 (int), "true"/"false"/"on"/"off"/"yes"/"no"/"1"/"0" (case-insensitive).

    Special handling for required: if required=True and value is False,
    raises ValueError with code "must_be_checked" (terms-of-service pattern).

    Args:
        raw: Raw value
        required: Whether the checkbox is required (must be checked)

    Returns:
        Boolean value

    Raises:
        ValueError: If coercion fails or required checkbox is unchecked

    """
    result: bool

    if isinstance(raw, bool):
        result = raw
    elif isinstance(raw, int) and raw in (0, 1):
        result = bool(raw)
    elif isinstance(raw, str):
        lower = raw.lower()
        if lower in ("true", "on", "yes", "1"):
            result = True
        elif lower in ("false", "off", "no", "0"):
            result = False
        else:
            msg = "Must be a boolean value (true/false, yes/no, on/off, 1/0)"
            raise ValueError(msg)
    else:
        msg = f"Must be a boolean, got {type(raw).__name__}"
        raise ValueError(msg)

    # Special required handling: must be checked
    if required and not result:
        msg = "This checkbox must be checked"
        raise ValueError(msg)

    return result


def _coerce_date(raw: Any) -> str:  # noqa: ANN401
    """Coerce to ISO 8601 date string.

    Accepts: ISO 8601 date string (YYYY-MM-DD).
    Returns: Normalized ISO 8601 string (JSON-serializable for Temporal namespace).

    Args:
        raw: Raw value

    Returns:
        ISO 8601 date string

    Raises:
        ValueError: If coercion fails

    """
    if not isinstance(raw, str):
        msg = f"Must be a date string, got {type(raw).__name__}"
        raise TypeError(msg)

    try:
        # Parse and re-emit to normalize format
        parsed = date.fromisoformat(raw)
        return parsed.isoformat()
    except ValueError:
        msg = "Must be a valid ISO 8601 date (YYYY-MM-DD)"
        raise ValueError(msg) from None


def _coerce_dropdown(raw: Any) -> str | float | bool:  # noqa: ANN401
    """Coerce dropdown value - scalar only, no lists."""
    if isinstance(raw, list):
        msg = "Dropdown expects a single value, not a list"
        raise TypeError(msg)

    if isinstance(raw, dict):
        msg = "Dropdown expects a scalar value, not a dict"
        raise TypeError(msg)

    # Accept str, float, bool (these are the valid StaticOption.value types)
    if not isinstance(raw, (str, float, bool)):
        msg = f"Must be a string, number, or boolean, got {type(raw).__name__}"
        raise TypeError(msg)

    return raw


def _coerce_multi_select(raw: Any) -> list[Any]:  # noqa: ANN401
    """Coerce multi-select value - list or single scalar (wrapped).

    Accepts: list, or a single scalar (wrapped into a one-element list).
    Browsers sometimes submit single-item multi-selects as a bare scalar.

    Args:
        raw: Raw value

    Returns:
        List of values

    Raises:
        ValueError: If coercion fails

    """
    if isinstance(raw, list):
        return raw

    # Wrap single scalar into list (browser behavior)
    if isinstance(raw, (str, float, bool, int)):
        return [raw]

    # Reject dict and other complex types
    if isinstance(raw, dict):
        msg = "Multi-select expects a list or scalar, not a dict"
        raise TypeError(msg)

    msg = f"Must be a list or scalar value, got {type(raw).__name__}"
    raise TypeError(msg)
