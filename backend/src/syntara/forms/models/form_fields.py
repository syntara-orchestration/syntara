"""Form field models — pydantic models with no runtime imports beyond core."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, model_validator

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


class DateField(FormFieldBase):
    """Date field."""

    type: Literal["date"]
    default: str | None = None


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

    Each object must contain a string label and scalar value using the configured
    keys (defaulting to display_label and value).
    """

    model_config = ConfigDict(extra="forbid")

    source: Literal["dynamic"]
    expression: str = Field(
        description=(
            "Template expression resolving to a non-empty array of objects. Each object must contain a string label "
            "and scalar value using the configured keys (defaulting to 'display_label' and 'value')."
        )
    )
    label_key: str | None = Field(
        default=None,
        description="Object key containing the option label. Defaults to 'display_label'.",
    )
    value_key: str | None = Field(
        default=None,
        description="Object key containing the typed option value. Defaults to 'value'.",
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
