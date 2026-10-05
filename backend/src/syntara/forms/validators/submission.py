"""Form submission validation and coercion.

Validates submitted form data against a FormDefinition, applying type coercion
and enforcing required fields and option membership constraints.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, assert_never

if TYPE_CHECKING:
    from syntara.forms.models.form_prompt import FormPrompt

from pydantic import EmailStr, TypeAdapter, ValidationError

from syntara.forms.exceptions import (
    FormDataValidationError,
    FormPromptAlreadyRespondedError,
    FormPromptCancelledError,
    FormPromptExpiredError,
)
from syntara.forms.models.api_models import TERMINAL_PROMPT_STATUSES, FormPromptStatus
from syntara.forms.models.form_errors import FormFieldError
from syntara.forms.models.form_fields import (
    CheckboxField,
    DateField,
    DateValue,
    DropdownField,
    EmailField,
    FormDefinition,
    FormField,
    MaskedTextField,
    MultiSelectField,
    NumberField,
    ResolvedOptions,
    StaticOptions,
    TextAreaField,
    TextField,
)

# Sentinel for distinguishing "not provided" from None
_MISSING = object()

# Built once at import; constructing a TypeAdapter per call is expensive.
# EmailStr validates format only - pydantic passes check_deliverability=False,
# so there is no DNS lookup and no network I/O on the submission path.
_EMAIL_ADAPTER = TypeAdapter(EmailStr)


class _FormatError(ValueError):
    """A value of the right type whose format is wrong.

    Subclasses ValueError so the existing coercion guard still catches it; the
    caller distinguishes it to report code "invalid_format" rather than "type".
    """


def validate_prompt_submission_state(prompt: FormPrompt) -> None:
    """Raise when a prompt is no longer eligible for a response.

    Raises:
        FormPromptExpiredError: If the prompt has expired
        FormPromptCancelledError: If the prompt was cancelled
        FormPromptAlreadyRespondedError: If the prompt was already submitted

    """
    if prompt.status == FormPromptStatus.EXPIRED:
        raise FormPromptExpiredError(prompt.id, prompt.timeout_at)
    if prompt.status == FormPromptStatus.CANCELLED:
        raise FormPromptCancelledError(prompt.id)
    if prompt.status in TERMINAL_PROMPT_STATUSES:
        raise FormPromptAlreadyRespondedError(prompt.id, prompt.status)

    if prompt.timeout_at is not None and prompt.timeout_at <= datetime.now(UTC):
        raise FormPromptExpiredError(prompt.id, prompt.timeout_at)


def validate_form_submission(
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
            coerced = coerce_field(field, raw)
        except (TypeError, ValueError) as exc:
            errors.append(
                FormFieldError(
                    field=field.value_name,
                    label=field.label,
                    code="invalid_format" if isinstance(exc, _FormatError) else "type",
                    message=str(exc),
                )
            )
            continue

        # Step 5b: A required checkbox must be checked (terms-of-service pattern).
        # Distinct from "required": CheckboxField.default is a concrete False, so
        # the default always fills an absent value and the required check above
        # never fires for a checkbox. An unticked box is reported here instead.
        if isinstance(field, CheckboxField) and field.required and not coerced:
            errors.append(
                FormFieldError(
                    field=field.value_name,
                    label=field.label,
                    code="must_be_checked",
                    message="This checkbox must be checked",
                )
            )
            continue

        # Step 6: Check option membership for dropdowns/multi-selects
        option_error = _check_option_membership(field, coerced)
        if option_error is not None:
            errors.append(option_error)
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


def coerce_field(field: FormField, raw: Any) -> Any:  # noqa: ANN401
    """Coerce raw submitted value to the field's expected type.

    FormField is a closed union, so every field type needs a case here. The
    assert_never fallback turns a missing one into a mypy error - note that
    pyrefly does not flag it, so `make typecheck` is what catches this.

    Args:
        field: Field definition
        raw: Raw submitted value

    Returns:
        Coerced value

    Raises:
        ValueError: If coercion fails

    """
    coerced: Any
    match field:
        case TextField() | TextAreaField() | MaskedTextField():
            coerced = _coerce_string(raw)
        case EmailField():
            coerced = _coerce_email(raw)
        case NumberField():
            coerced = _coerce_number(raw)
        case CheckboxField():
            coerced = _coerce_checkbox(raw)
        case DateField():
            # The only coercer that reads its own definition, to learn which
            # date components the field collects.
            coerced = _coerce_date(field, raw)
        case DropdownField():
            coerced = _coerce_dropdown(raw)
        case MultiSelectField():
            coerced = _coerce_multi_select(raw)
        case _:
            assert_never(field)

    return coerced


def _coerce_string(raw: Any) -> str:  # noqa: ANN401
    """Coerce to string - only str accepted, no silent stringification."""
    if not isinstance(raw, str):
        msg = f"Must be a string, got {type(raw).__name__}"
        raise TypeError(msg)
    return raw


_EMAIL_MSG_PREFIX = "value is not a valid email address: "


def _coerce_email(raw: Any) -> str:  # noqa: ANN401
    """Coerce to a validated, normalized email address.

    Applies the same no-silent-stringification rule as _coerce_string, then
    checks format with pydantic's EmailStr.

    The returned address is *normalized*, not echoed back verbatim: the domain
    is lowercased and IDNA-encoded, so "Bob@Example.COM" reaches the workflow
    namespace as "Bob@example.com". The local part is left alone, since it is
    case-sensitive per RFC 5321.

    Args:
        raw: Raw value

    Returns:
        The normalized email address

    Raises:
        TypeError: If the value is not a string
        _FormatError: If the string is not a valid email address

    """
    value = _coerce_string(raw)

    try:
        return str(_EMAIL_ADAPTER.validate_python(value))
    except ValidationError as exc:
        # email_validator's messages are already user-facing ("An email address
        # must have an @-sign."); strip pydantic's wrapper prefix and use them.
        detail = exc.errors()[0]["msg"].removeprefix(_EMAIL_MSG_PREFIX)
        raise _FormatError(detail) from None


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


def _coerce_checkbox(raw: Any) -> bool:  # noqa: ANN401
    """Coerce to boolean.

    Accepts: bool, 0/1 (int), "true"/"false"/"on"/"off"/"yes"/"no"/"1"/"0" (case-insensitive).

    Coercion only. The required-checkbox rule is enforced by the caller, which
    can report it as "must_be_checked" rather than a coercion failure.

    Args:
        raw: Raw value

    Returns:
        Boolean value

    Raises:
        ValueError: If coercion fails

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

    return result


def _coerce_date(field: DateField, raw: Any) -> dict[str, str]:  # noqa: ANN401
    """Coerce to a date value object holding exactly the field's components.

    Accepts: a mapping with any of the "date", "time", and "timezone" keys.
    Returns: a plain dict (JSON-serializable for the Temporal namespace) whose
    keys are exactly the components the field collects.

    The shape is always an object, even for a date-only field. A bare string
    would read more naturally today, but it would mean that enabling a timezone
    toggle later silently changes the namespace shape and breaks every
    downstream expression already reading the field.

    Args:
        field: Date field definition, which decides the required components
        raw: Raw value

    Returns:
        Component dict with exactly the included components

    Raises:
        TypeError: If the value is not a mapping
        ValueError: If a component is malformed, missing, or not collected

    """
    # A field default arrives as an already-validated DateValue, both from the
    # default substitution above and from validate_form_definition.
    if isinstance(raw, DateValue):
        raw = raw.model_dump(exclude_none=True)

    if not isinstance(raw, Mapping):
        expected = ", ".join(field.included_components())
        msg = f"Must be an object with keys: {expected}; got {type(raw).__name__}"
        raise TypeError(msg)

    # Drop blanks so an untouched input posting "" reads as absent, matching
    # _is_empty at the top level.
    present = {key: value for key, value in raw.items() if not _is_empty(value)}

    try:
        value = DateValue.model_validate(present)
    except ValidationError as exc:
        raise _FormatError(_format_date_errors(exc)) from None

    included = set(field.included_components())
    supplied = set(value.supplied_components())

    if missing := sorted(included - supplied):
        msg = f"Missing required {'component' if len(missing) == 1 else 'components'}: {', '.join(missing)}"
        raise _FormatError(msg)

    if extra := sorted(supplied - included):
        msg = f"This field does not collect: {', '.join(extra)}"
        raise _FormatError(msg)

    return {name: getattr(value, name) for name in field.included_components()}


# Pydantic reports a failed `pattern=` as the raw regex, which is noise to a
# responder. Each component gets a plain-language equivalent instead.
_DATE_FORMAT_HINTS = {
    "date": "must be a date in YYYY-MM-DD format",
    "time": "must be a 24-hour time in HH:MM format",
    "timezone": "must be an IANA timezone name, such as America/New_York",
}


def _format_date_errors(exc: ValidationError) -> str:
    """Render pydantic's component errors as one user-safe sentence."""
    parts: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "value"

        if error["type"] == "extra_forbidden":
            parts.append(f"'{location}' is not a date component")
            continue

        hint = _DATE_FORMAT_HINTS.get(location)
        if hint is not None and error["type"] == "string_pattern_mismatch":
            parts.append(f"{location} {hint}")
            continue

        # Custom validators surface through pydantic as "Value error, <msg>".
        parts.append(f"{location}: {error['msg'].removeprefix('Value error, ')}")
    return "; ".join(parts)


def _check_option_membership(field: FormField, coerced: Any) -> FormFieldError | None:  # noqa: ANN401
    """Check a coerced value against a static or resolved option list.

    Args:
        field: Field definition
        coerced: The already-coerced submitted value

    Returns:
        A field error, or None if the field has no concrete option list or the
        value is a member of it. Dynamic options are unresolved only while a
        workflow definition is being authored; persisted prompts use resolved
        options and are checked here.

    """
    if not (
        isinstance(field, (DropdownField, MultiSelectField))
        and isinstance(field.options, (StaticOptions, ResolvedOptions))
    ):
        return None

    valid_values: set[str | int | float | bool] = {opt.value for opt in field.options.values}

    if isinstance(field, MultiSelectField):
        if not isinstance(coerced, list):
            # Should have been caught by coercion, but guard anyway
            return FormFieldError(
                field=field.value_name,
                label=field.label,
                code="type",
                message="Must be a list",
            )

        invalid = [v for v in coerced if v not in valid_values]
        if invalid:
            return FormFieldError(
                field=field.value_name,
                label=field.label,
                code="not_in_options",
                message=f"Invalid selection(s): {len(invalid)} value(s) not in option list",
            )
        return None

    # Dropdown - single value
    if coerced not in valid_values:
        return FormFieldError(
            field=field.value_name,
            label=field.label,
            code="not_in_options",
            message="Selected value is not in the option list",
        )

    return None


def _coerce_option_value(raw: Any) -> str | int | float | bool:  # noqa: ANN401
    """Coerce an option value to the supported scalar types.

    Values are accepted as-is, never converted between numeric types. This
    preserves dynamic option values as they reach the workflow namespace. Static
    option definitions are string-only and are checked for membership separately.

    Args:
        raw: Raw scalar value

    Returns:
        The value, unchanged

    Raises:
        TypeError: If the value is not a supported scalar

    """
    # bool is redundant with int (it subclasses int) but remains explicit for
    # clarity at this JSON-facing boundary.
    if isinstance(raw, (str, int, float, bool)):
        return raw

    msg = f"Must be a string, number, or boolean, got {type(raw).__name__}"
    raise TypeError(msg)


def _coerce_dropdown(raw: Any) -> str | int | float | bool:  # noqa: ANN401
    """Coerce dropdown value - scalar only, no lists."""
    if isinstance(raw, list):
        msg = "Dropdown expects a single value, not a list"
        raise TypeError(msg)

    if isinstance(raw, dict):
        msg = "Dropdown expects a scalar value, not a dict"
        raise TypeError(msg)

    return _coerce_option_value(raw)


def _coerce_multi_select(raw: Any) -> list[str | int | float | bool]:  # noqa: ANN401
    """Coerce multi-select value - list or single scalar (wrapped).

    Accepts: list, or a single scalar (wrapped into a one-element list).
    Browsers sometimes submit single-item multi-selects as a bare scalar.

    Every element goes through the same rules as a dropdown value, so the two
    field types accept identically. Element coercion also keeps unhashable
    values (dict, list) out of the option-membership check, which tests
    against a set.

    Args:
        raw: Raw value

    Returns:
        List of values

    Raises:
        TypeError: If coercion fails

    """
    if isinstance(raw, list):
        return [_coerce_option_value(item) for item in raw]

    # Reject dict before the scalar path to keep the multi-select message
    if isinstance(raw, dict):
        msg = "Multi-select expects a list or scalar, not a dict"
        raise TypeError(msg)

    # Wrap single scalar into list (browser behavior)
    return [_coerce_option_value(raw)]
