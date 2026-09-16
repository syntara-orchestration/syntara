"""Form field models — pure pydantic + stdlib for Temporal sandbox compatibility."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, model_validator

from syntara.core.constants import FieldLimits

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


class DateField(FormFieldBase):
    """Date field."""

    type: Literal["date"]
    default: str | None = None


class StaticOption(BaseModel):
    """A single static option for dropdown or multi-select."""

    model_config = ConfigDict(extra="forbid")

    display_label: str = Field(min_length=1, max_length=200)
    value: str | int | float | bool


class StaticOptions(BaseModel):
    """Static option list for dropdown or multi-select."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["static"]
    values: list[StaticOption] = Field(min_length=1, max_length=FieldLimits.FORM_OPTIONS_MAX_LENGTH)


class DynamicOptions(BaseModel):
    """Dynamic option list resolved from upstream node output."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["dynamic"]
    expression: str
    label_key: str | None = None
    value_key: str | None = None


OptionsSource = Annotated[StaticOptions | DynamicOptions, Discriminator("source")]


class DropdownField(FormFieldBase):
    """Dropdown field."""

    type: Literal["dropdown"]
    options: OptionsSource
    default: str | int | float | bool | None = None


class MultiSelectField(FormFieldBase):
    """Multi-select field."""

    type: Literal["multi_select"]
    options: OptionsSource
    default: list[Any] | None = None


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


def _check_multi_select_defaults(value_name: str, defaults: list[Any], valid_values: set[Any]) -> None:
    """Check multi-select defaults are scalars drawn from the option list.

    Raises:
        ValueError: If any default is non-scalar or absent from the options

    """
    # default is list[Any], so entries may be unhashable. Testing membership
    # against the option set would raise a bare TypeError out of the calling
    # validator - a 500 on an API payload - rather than a clean
    # ValidationError, so screen them first.
    non_scalar = [v for v in defaults if not isinstance(v, (str, int, float, bool))]
    if non_scalar:
        types_found = sorted({type(v).__name__ for v in non_scalar})
        msg = (
            f"Field '{value_name}': default values must be scalars "
            f"(str, int, float, or bool), got {', '.join(types_found)}"
        )
        raise ValueError(msg)

    invalid_defaults = [v for v in defaults if v not in valid_values]
    if invalid_defaults:
        msg = f"Field '{value_name}': default values {invalid_defaults} are not in the option list"
        raise ValueError(msg)


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
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _default_in_static_options(self) -> FormDefinition:
        """Ensure static dropdown/multi-select defaults are in the option list."""
        for field in self.fields:
            if not isinstance(field, (DropdownField, MultiSelectField)) or not isinstance(field.options, StaticOptions):
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
                raise ValueError(msg)
        return self
