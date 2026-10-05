"""Unit tests for form field models.

Covers shared field constraints, the field-type discriminated union,
option sources, and FormDefinition-level validators (unique names,
static-option defaults).
"""

from typing import Any

import pytest
from pydantic import ValidationError

from syntara.forms.models.form_fields import (
    CheckboxField,
    DateField,
    DropdownField,
    DynamicOptions,
    EmailField,
    FormDefinition,
    MaskedTextField,
    MultiSelectField,
    NumberField,
    ResolvedOptions,
    StaticOptions,
    TextAreaField,
    TextField,
)


def _text(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    """Build a minimal valid text field payload."""
    return {"type": "text", "value_name": "username", "label": "Username", **overrides}


def _form(*fields: dict[str, Any]) -> FormDefinition:
    """Build a FormDefinition from raw field payloads."""
    return FormDefinition.model_validate({"fields": list(fields)})


class TestFormFieldBase:
    """Shared constraints on all field types, exercised through TextField."""

    def test_valid_field(self) -> None:
        """A fully populated field keeps its values."""
        field = TextField.model_validate(
            _text(placeholder="you@example.com", help_text="Your login", required=True, default="bob")
        )

        assert field.value_name == "username"
        assert field.label == "Username"
        assert field.placeholder == "you@example.com"
        assert field.help_text == "Your login"
        assert field.required is True
        assert field.default == "bob"

    def test_optional_fields_default(self) -> None:
        """Optional metadata defaults to None/False."""
        field = TextField.model_validate(_text())

        assert field.placeholder is None
        assert field.help_text is None
        assert field.required is False
        assert field.default is None

    @pytest.mark.parametrize("value_name", ["_private", "snake_case", "camelCase", "a1", "A"])
    def test_valid_value_names(self, value_name: str) -> None:
        """Python-identifier-style names are accepted."""
        assert TextField.model_validate(_text(value_name=value_name)).value_name == value_name

    @pytest.mark.parametrize("value_name", ["1abc", "has-dash", "has space", "", "has.dot", "a" * 65])
    def test_invalid_value_names(self, value_name: str) -> None:
        """Non-identifier and over-long names are rejected."""
        with pytest.raises(ValidationError):
            TextField.model_validate(_text(value_name=value_name))

    def test_extra_keys_forbidden(self) -> None:
        """Unknown keys are rejected (extra='forbid')."""
        with pytest.raises(ValidationError):
            TextField.model_validate(_text(unexpected="nope"))

    def test_empty_label_rejected(self) -> None:
        """Label must be non-empty."""
        with pytest.raises(ValidationError):
            TextField.model_validate(_text(label=""))


class TestFieldDiscriminator:
    """The FormField discriminated union resolves on `type`."""

    @pytest.mark.parametrize(
        ("type_name", "expected_cls", "default"),
        [
            ("text", TextField, "hello"),
            ("textarea", TextAreaField, "hello"),
            ("masked_text", MaskedTextField, "secret"),
            ("email", EmailField, "a@b.com"),
            ("number", NumberField, 4.5),
            ("checkbox", CheckboxField, True),
        ],
    )
    def test_simple_types_resolve(self, type_name: str, expected_cls: type, default: Any) -> None:  # noqa: ANN401
        """Each simple field type parses into its own class."""
        form = _form(_text(type=type_name, default=default))

        field = form.fields[0]
        assert isinstance(field, expected_cls)
        assert field.default == default

    def test_unknown_type_rejected(self) -> None:
        """An unrecognized discriminator value fails validation."""
        with pytest.raises(ValidationError):
            _form(_text(type="rocket"))


class TestOptions:
    """Dropdown/multi-select option sources."""

    def test_static_options(self) -> None:
        """A static option list resolves to StaticOptions."""
        form = _form(
            _text(
                type="dropdown",
                options={"source": "static", "values": [{"display_label": "A", "value": "a"}]},
            )
        )

        field = form.fields[0]
        assert isinstance(field, DropdownField)
        assert isinstance(field.options, StaticOptions)
        assert field.options.values[0].value == "a"

    def test_static_options_require_a_value(self) -> None:
        """An empty static option list is rejected."""
        with pytest.raises(ValidationError):
            _form(_text(type="dropdown", options={"source": "static", "values": []}))

    def test_dynamic_options_require_label_and_value_keys(self) -> None:
        """Dynamic sources need explicit label and value keys at save time."""
        for options in (
            {"source": "dynamic", "expression": "${a.output}"},
            {"source": "dynamic", "expression": "${a.output}", "label_key": "name"},
            {"source": "dynamic", "expression": "${a.output}", "value_key": "id"},
            {"source": "dynamic", "expression": "${a.output}", "label_key": "", "value_key": "id"},
            {"source": "dynamic", "expression": "${a.output}", "label_key": "name", "value_key": ""},
        ):
            with pytest.raises(ValidationError):
                _form(_text(type="multi_select", options=options))

        form = _form(
            _text(
                type="multi_select",
                options={
                    "source": "dynamic",
                    "expression": "${a.output}",
                    "label_key": "name",
                    "value_key": "id",
                },
            )
        )

        field = form.fields[0]
        assert isinstance(field, MultiSelectField)
        assert isinstance(field.options, DynamicOptions)
        assert field.options.expression == "${a.output}"
        assert field.options.label_key == "name"
        assert field.options.value_key == "id"

    def test_unknown_source_rejected(self) -> None:
        """An unrecognized option source fails validation."""
        with pytest.raises(ValidationError):
            _form(_text(type="dropdown", options={"source": "magic", "values": []}))

    def test_resolved_options_parse_with_typed_values(self) -> None:
        """Resolved option values preserve their upstream scalar types."""
        form = _form(
            _text(
                type="dropdown",
                options={"source": "dynamic_resolved", "values": [{"display_label": "1", "value": 1}]},
            )
        )

        field = form.fields[0]
        assert isinstance(field, DropdownField)
        assert isinstance(field.options, ResolvedOptions)
        assert field.options.values[0].value == 1
        assert type(field.options.values[0].value) is int

    def test_resolved_options_require_values(self) -> None:
        """Resolved options always carry a concrete option list."""
        with pytest.raises(ValidationError):
            _form(_text(type="dropdown", options={"source": "dynamic_resolved"}))

    def test_resolved_options_reject_empty_values(self) -> None:
        with pytest.raises(ValidationError):
            _form(_text(type="dropdown", options={"source": "dynamic_resolved", "values": []}))

    def test_resolved_options_reject_extra_keys(self) -> None:
        with pytest.raises(ValidationError):
            _form(
                _text(
                    type="dropdown",
                    options={
                        "source": "dynamic_resolved",
                        "values": [{"display_label": "One", "value": 1, "extra": True}],
                    },
                )
            )

    def test_static_option_value_stays_string_only(self) -> None:
        """Static values are authored strings; typed values belong to resolved options."""
        with pytest.raises(ValidationError):
            _form(
                _text(
                    type="dropdown",
                    options={"source": "static", "values": [{"display_label": "One", "value": 1}]},
                )
            )


class TestFormDefinition:
    """FormDefinition-level constraints and validators."""

    def test_fields_required(self) -> None:
        """A form must define at least one field."""
        with pytest.raises(ValidationError):
            _form()

    def test_duplicate_field_names_rejected(self) -> None:
        """Duplicate value_names are rejected and named in the message."""
        with pytest.raises(ValidationError, match="username"):
            _form(_text(), _text(label="Again"))

    def test_distinct_field_names_allowed(self) -> None:
        """Distinct value_names pass."""
        assert len(_form(_text(), _text(value_name="other")).fields) == 2


class TestStaticOptionDefaults:
    """Defaults on dropdown/multi-select must be in the static option list."""

    @staticmethod
    def _options() -> dict[str, Any]:
        return {
            "source": "static",
            "values": [
                {"display_label": "A", "value": "a"},
                {"display_label": "B", "value": "b"},
            ],
        }

    def test_valid_dropdown_default(self) -> None:
        """A dropdown default present in the option list passes."""
        form = _form(_text(type="dropdown", options=self._options(), default="a"))

        assert form.fields[0].default == "a"

    def test_invalid_dropdown_default_rejected(self) -> None:
        """A dropdown default outside the option list is rejected."""
        with pytest.raises(ValidationError, match="not in the option list"):
            _form(_text(type="dropdown", options=self._options(), default="z"))

    def test_valid_multi_select_default(self) -> None:
        """A multi-select default of known values passes."""
        form = _form(_text(type="multi_select", options=self._options(), default=["a", "b"]))

        assert form.fields[0].default == ["a", "b"]

    @pytest.mark.parametrize("value", ["a", 5, 5.5, True])
    def test_static_multi_select_options_accept_only_string_values(self, value: object) -> None:
        """Static option values are strings, even though dynamic options preserve scalar types."""
        options = {"source": "static", "values": [{"display_label": str(value), "value": value}]}

        if not isinstance(value, str):
            field_payload = _text(type="multi_select", options=options, default=[value])
            with pytest.raises(ValidationError):
                _form(field_payload)
            return

        form = _form(_text(type="multi_select", options=options, default=[value]))
        assert isinstance(form.fields[0], MultiSelectField)
        assert form.fields[0].default == [value]

    @pytest.mark.parametrize("value", ["a", 5, 5.5, True])
    def test_dynamic_multi_select_defaults_accept_scalar_types(self, value: object) -> None:
        """Dynamic multi-select defaults retain each supported scalar type."""
        options = {
            "source": "dynamic",
            "expression": "${upstream.output}",
            "label_key": "display_label",
            "value_key": "value",
        }

        form = _form(_text(type="multi_select", options=options, default=[value]))

        assert isinstance(form.fields[0], MultiSelectField)
        assert form.fields[0].default == [value]

    def test_invalid_multi_select_default_rejected(self) -> None:
        """One unknown entry in a multi-select default is enough to fail."""
        with pytest.raises(ValidationError, match=r"not in the option list"):
            _form(_text(type="multi_select", options=self._options(), default=["a", "z"]))

    def test_dynamic_options_default_not_checked(self) -> None:
        """Defaults are not validated against dynamically resolved options."""
        form = _form(
            _text(
                type="dropdown",
                options={
                    "source": "dynamic",
                    "expression": "${a.output}",
                    "label_key": "display_label",
                    "value_key": "value",
                },
                default="anything",
            )
        )

        assert form.fields[0].default == "anything"


def _date(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    """Build a minimal valid date field payload."""
    return {"type": "date", "value_name": "start", "label": "Start", **overrides}


class TestDateFieldComponents:
    """The include_* toggles decide which components a date field collects."""

    def test_defaults_to_date_only(self) -> None:
        """A bare date field collects a calendar date and nothing else."""
        field = DateField.model_validate(_date())

        assert field.included_components() == ("date",)

    @pytest.mark.parametrize(
        ("toggles", "expected"),
        [
            ({}, ("date",)),
            ({"include_timezone": True}, ("date", "timezone")),
            ({"include_time": True, "include_timezone": True}, ("date", "time", "timezone")),
            ({"include_date": False, "include_time": True, "include_timezone": True}, ("time", "timezone")),
            ({"include_date": False, "include_timezone": True}, ("timezone",)),
        ],
    )
    def test_valid_combinations(self, toggles: dict[str, bool], expected: tuple[str, ...]) -> None:
        """Every combination that pairs a time with a timezone is accepted."""
        field = DateField.model_validate(_date(**toggles))

        assert field.included_components() == expected

    @pytest.mark.parametrize(
        "toggles",
        [
            {"include_time": True},
            {"include_date": False, "include_time": True},
        ],
    )
    def test_time_requires_timezone(self, toggles: dict[str, bool]) -> None:
        """A wall-clock time is ambiguous without the zone it is read in."""
        with pytest.raises(ValidationError, match=r"include_timezone is required when include_time is true"):
            DateField.model_validate(_date(**toggles))

    def test_at_least_one_component_required(self) -> None:
        """A field that collects nothing cannot be answered at all."""
        with pytest.raises(ValidationError, match=r"at least one of include_date"):
            DateField.model_validate(_date(include_date=False))


class TestDateFieldDefault:
    """A date default must match the components the field collects, exactly."""

    def test_date_only_default(self) -> None:
        """A default covering the single included component is accepted."""
        field = DateField.model_validate(_date(default={"date": "2026-01-05"}))

        assert field.default is not None
        assert field.default.date == "2026-01-05"

    def test_full_default(self) -> None:
        """All three components default together when all three are collected."""
        field = DateField.model_validate(
            _date(
                include_time=True,
                include_timezone=True,
                default={"date": "2026-01-05", "time": "14:30", "timezone": "America/New_York"},
            )
        )

        assert field.default is not None
        assert field.default.supplied_components() == ("date", "time", "timezone")

    def test_partial_default_rejected(self) -> None:
        """A default is substituted wholesale, so an incomplete one is useless."""
        with pytest.raises(ValidationError, match=r"default is missing timezone"):
            DateField.model_validate(_date(include_timezone=True, default={"date": "2026-01-05"}))

    def test_default_for_uncollected_component_rejected(self) -> None:
        """Defaulting a component the field never asks for is an authoring mistake."""
        with pytest.raises(ValidationError, match=r"default supplies time, which this field does not collect"):
            DateField.model_validate(_date(default={"date": "2026-01-05", "time": "14:30"}))

    @pytest.mark.parametrize("bad_date", ["tomorrow", "01/05/2026", "2026-13-01", "20260105"])
    def test_non_iso_date_rejected(self, bad_date: str) -> None:
        """Only the ISO 8601 extended YYYY-MM-DD form is accepted."""
        with pytest.raises(ValidationError):
            DateField.model_validate(_date(default={"date": bad_date}))

    def test_impossible_calendar_date_rejected(self) -> None:
        """A well-shaped string still has to name a real day."""
        with pytest.raises(ValidationError, match=r"Invalid date: '2026-02-30'"):
            DateField.model_validate(_date(default={"date": "2026-02-30"}))

    @pytest.mark.parametrize("bad_time", ["25:00", "14:60", "2:30", "14:30:00", "noon"])
    def test_malformed_time_rejected(self, bad_time: str) -> None:
        """Times are 24-hour HH:MM, zero-padded, with no seconds."""
        with pytest.raises(ValidationError):
            DateField.model_validate(
                _date(
                    include_date=False,
                    include_time=True,
                    include_timezone=True,
                    default={"time": bad_time, "timezone": "UTC"},
                )
            )

    def test_unknown_timezone_rejected(self) -> None:
        """Timezones are checked against the IANA database, not just length."""
        with pytest.raises(ValidationError, match=r"Invalid timezone: 'Mars/Olympus'"):
            DateField.model_validate(
                _date(include_date=False, include_timezone=True, default={"timezone": "Mars/Olympus"})
            )

    def test_unknown_component_rejected(self) -> None:
        """A date value carries the three known components and nothing else."""
        with pytest.raises(ValidationError):
            DateField.model_validate(_date(default={"date": "2026-01-05", "offset": "-05:00"}))


class TestResolvedOptionDefaults:
    """Defaults on resolved option lists are checked against typed values."""

    @staticmethod
    def _options() -> dict[str, Any]:
        return {
            "source": "dynamic_resolved",
            "values": [
                {"display_label": "One", "value": 1},
                {"display_label": "Two", "value": 2},
            ],
        }

    def test_default_checked_against_resolved_options(self) -> None:
        with pytest.raises(ValidationError, match="not in the option list"):
            _form(_text(type="dropdown", options=self._options(), default=3))

    def test_typed_default_accepted_against_resolved_options(self) -> None:
        form = _form(_text(type="dropdown", options=self._options(), default=2))

        assert form.fields[0].default == 2

    def test_multi_select_defaults_checked_against_resolved_options(self) -> None:
        with pytest.raises(ValidationError, match="3"):
            _form(_text(type="multi_select", options=self._options(), default=[1, 3]))
