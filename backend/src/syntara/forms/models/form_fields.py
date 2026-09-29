"""Form field models — pydantic models with no runtime imports beyond core."""

from __future__ import annotations

from datetime import date as calendar_date
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Discriminator, Field, field_validator, model_validator

from syntara.core.constants import FieldLimits
from syntara.core.exceptions import SafeValueError

FIELD_NAME_PATTERN = r"^[a-zA-Z_][a-zA-Z0-9_]*$"


class FormFieldBase(BaseModel):
    """Base class for all form field types."""

    model_config = ConfigDict(extra="forbid")

    value_name: str = Field(pattern=FIELD_NAME_PATTERN, max_length=64)
    label: str = Field(min_length=1, max_length=200)
    placeholder: str | None = None
    help_text: str | None = None
    required: bool = False


class TextField(FormFieldBase):
    """Text field."""

    type: Literal["text"]
    default: str | None = None


class TextAreaField(FormFieldBase):
    """Text area field."""

    type: Literal["textarea"]
    default: str | None = None


class MaskedTextField(FormFieldBase):
    """Masked text field."""

    type: Literal["masked_text"]
    default: str | None = None


class EmailField(FormFieldBase):
    """Email field."""

    type: Literal["email"]
    default: str | None = None


class NumberField(FormFieldBase):
    """Numeric field supporting int or float."""

    type: Literal["number"]
    default: float | int | None = None


class CheckboxField(FormFieldBase):
    """Boolean checkbox field."""

    type: Literal["checkbox"]
    default: bool = False
    required: bool = Field(
        default=False,
        description=(
            "When true the checkbox must be checked to submit, for example "
            "a terms of service or acknowledgment. An unchecked required "
            "checkbox fails with error code 'must_be_checked'."
        ),
    )


# The components a date field can collect, in the order they are reported.
DATE_COMPONENTS = ("date", "time", "timezone")


# Used both for a field's `default` and for the shape a responder submits.
# Which components must be present is decided by the owning DateField, not here:
# every component is independently optional on this model.
class DateValue(BaseModel):
    """The date, time, and timezone components of a date field value."""

    model_config = ConfigDict(extra="forbid")

    date: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="ISO 8601 calendar date in YYYY-MM-DD format.",
    )
    time: str | None = Field(
        default=None,
        pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$",
        description="24-hour time in HH:MM format.",
    )
    timezone: str | None = Field(
        default=None,
        max_length=FieldLimits.FORM_TIMEZONE_MAX_LENGTH,
        description="IANA timezone name, such as America/New_York.",
    )

    @field_validator("date")
    @classmethod
    def _validate_date(cls, value: str | None) -> str | None:
        """Reject well-shaped strings that are not real calendar dates.

        The field pattern only proves YYYY-MM-DD shape, so '2026-02-30' and
        '2026-13-01' reach this validator intact.
        """
        if value is None:
            return None

        try:
            calendar_date.fromisoformat(value)
        except ValueError:
            msg = f"Invalid date: '{value}'. Use a valid ISO 8601 date in YYYY-MM-DD format."
            raise SafeValueError(msg) from None
        return value

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        """Require a recognized IANA timezone name when one is supplied."""
        if value is None:
            return None

        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            msg = f"Invalid timezone: '{value}'. Use a valid IANA timezone name, such as 'America/New_York'."
            raise SafeValueError(msg) from None
        return value

    def supplied_components(self) -> tuple[str, ...]:
        """Return the component names carrying a value, in DATE_COMPONENTS order."""
        return tuple(name for name in DATE_COMPONENTS if getattr(self, name) is not None)


# The three include_* toggles decide which components the form asks for. A
# component that is not included is not collected at all, and every component
# that is included is mandatory once the responder answers the field. Whether
# the field may be skipped entirely is the inherited `required` flag, exactly as
# for every other field type.
class DateField(FormFieldBase):
    """Date field collecting any combination of date, time, and timezone."""

    type: Literal["date"]
    include_date: bool = Field(
        default=True,
        description="Collect a calendar date.",
    )
    include_time: bool = Field(
        default=False,
        description="Collect a 24-hour time. Requires include_timezone.",
    )
    include_timezone: bool = Field(
        default=False,
        description="Collect an IANA timezone name.",
    )
    default: DateValue | None = Field(
        default=None,
        description=(
            "Default value used when the responder submits nothing. Must supply exactly the included components."
        ),
    )

    def included_components(self) -> tuple[str, ...]:
        """Return the component names this field collects, in DATE_COMPONENTS order."""
        return tuple(
            name
            for name, included in (
                ("date", self.include_date),
                ("time", self.include_time),
                ("timezone", self.include_timezone),
            )
            if included
        )

    @model_validator(mode="after")
    def _check_included_components(self) -> DateField:
        """Require at least one component, and a timezone alongside any time."""
        if not self.included_components():
            msg = (
                f"Field '{self.value_name}': at least one of include_date, "
                "include_time, or include_timezone must be true"
            )
            raise SafeValueError(msg)

        # A bare wall-clock time is ambiguous without the zone it is read in.
        if self.include_time and not self.include_timezone:
            msg = f"Field '{self.value_name}': include_timezone is required when include_time is true"
            raise SafeValueError(msg)
        return self

    @model_validator(mode="after")
    def _check_default_covers_components(self) -> DateField:
        """Require a default to supply exactly the components the field collects.

        A default stands in for a whole skipped answer. A partial one would be
        substituted wholesale at submission time and then fail the very coercion
        it was meant to satisfy, so the mismatch is reported here at definition
        time instead.
        """
        if self.default is None:
            return self

        included = set(self.included_components())
        supplied = set(self.default.supplied_components())

        if missing := sorted(included - supplied):
            msg = f"Field '{self.value_name}': default is missing {', '.join(missing)}"
            raise SafeValueError(msg)

        if extra := sorted(supplied - included):
            msg = f"Field '{self.value_name}': default supplies {', '.join(extra)}, which this field does not collect"
            raise SafeValueError(msg)
        return self


class StaticOption(BaseModel):
    """A single static option for dropdown or multi-select."""

    model_config = ConfigDict(extra="forbid")

    display_label: str = Field(min_length=1, max_length=200)
    value: str


class StaticOptions(BaseModel):
    """Static option list for dropdown or multi-select."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["static"]
    values: list[StaticOption] = Field(min_length=1, max_length=FieldLimits.FORM_OPTIONS_MAX_LENGTH)


class DynamicOptions(BaseModel):
    """Dynamic option list resolved from a non-empty array of upstream objects.

    Each object must contain a string label and scalar value at the required
    ``label_key`` and ``value_key``.
    """

    model_config = ConfigDict(extra="forbid")

    source: Literal["dynamic"]
    expression: str = Field(
        description=(
            "Template expression resolving to a non-empty array of objects. Each object must contain a string label "
            "and scalar value at the required 'label_key' and 'value_key'."
        )
    )
    label_key: str = Field(
        min_length=1,
        description="Required object key containing the option label.",
    )
    value_key: str = Field(
        min_length=1,
        description="Required object key containing the typed option value.",
    )


class ResolvedOption(BaseModel):
    """An option materialized from upstream output while preserving its scalar type.

    Python set membership considers ``1``, ``1.0``, and ``True`` equal. That
    behavior is used by the backend's de-duplication and membership checks.
    Static options remain strings because they are authored by a user.
    """

    model_config = ConfigDict(extra="forbid")

    display_label: str = Field(min_length=1, max_length=200)
    value: str | int | float | bool


class ResolvedOptions(BaseModel):
    """Dynamic options materialized into a concrete list at prompt creation.

    Produced only by the workflow engine, never authored. A form prompt is
    persisted with this shape so the responder view and submission membership
    validation operate on the same snapshot.
    """

    model_config = ConfigDict(extra="forbid")

    source: Literal["dynamic_resolved"]
    values: list[ResolvedOption] = Field(min_length=1, max_length=FieldLimits.FORM_OPTIONS_MAX_LENGTH)


OptionsSource = Annotated[StaticOptions | DynamicOptions | ResolvedOptions, Discriminator("source")]


class DropdownField(FormFieldBase):
    """Dropdown field."""

    type: Literal["dropdown"]
    options: OptionsSource
    default: str | int | float | bool | None = None


class MultiSelectField(FormFieldBase):
    """Multi-select field."""

    type: Literal["multi_select"]
    options: OptionsSource
    default: list[str | int | float | bool] | None = None


FormField = Annotated[
    TextField
    | TextAreaField
    | MaskedTextField
    | EmailField
    | NumberField
    | CheckboxField
    | DateField
    | DropdownField
    | MultiSelectField,
    Discriminator("type"),
]


def _check_multi_select_defaults(
    value_name: str,
    defaults: list[str | int | float | bool],
    valid_values: set[str | int | float | bool],
) -> None:
    """Check multi-select defaults are drawn from the option list.

    Raises:
        SafeValueError: If any default is absent from the options

    """
    invalid_defaults = [v for v in defaults if v not in valid_values]
    if invalid_defaults:
        msg = f"Field '{value_name}': default values {invalid_defaults} are not in the option list"
        raise SafeValueError(msg)


class FormDefinition(BaseModel):
    """Complete form definition with fields and metadata."""

    model_config = ConfigDict(extra="forbid")

    fields: list[FormField] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _unique_names(self) -> FormDefinition:
        """Ensure all field names are unique."""
        names = [field.value_name for field in self.fields]
        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            msg = f"Duplicate field names are not allowed: {', '.join(sorted(duplicates))}"
            raise SafeValueError(msg)
        return self

    @model_validator(mode="after")
    def _default_in_option_list(self) -> FormDefinition:
        """Ensure defaults belong to static or runtime-resolved option lists.

        Dynamic options have not been materialized yet, so their defaults are
        checked by the workflow engine after it resolves the upstream value.
        """
        for field in self.fields:
            if not isinstance(field, (DropdownField, MultiSelectField)) or not isinstance(
                field.options, (StaticOptions, ResolvedOptions)
            ):
                continue

            valid_values = {opt.value for opt in field.options.values}

            # Bind to a local after narrowing the field type: the checkers track
            # `defaults is not None` on a local, but disagree about the type of
            # `field.default` across the two branches of the union.
            if isinstance(field, MultiSelectField):
                defaults = field.default
                if defaults is not None:
                    _check_multi_select_defaults(field.value_name, defaults, valid_values)
            elif field.default is not None and field.default not in valid_values:
                msg = f"Field '{field.value_name}': default value '{field.default}' is not in the option list"
                raise SafeValueError(msg)
        return self
