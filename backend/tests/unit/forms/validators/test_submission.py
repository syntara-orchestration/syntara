"""Unit tests for form submission validation and coercion."""

from typing import Any, get_args

import pytest

from syntara.forms.exceptions import FormDataValidationError
from syntara.forms.models.form_fields import FormDefinition, FormField
from syntara.forms.validators.submission import validate_form_submission

_STATIC_OPTIONS: dict[str, Any] = {
    "source": "static",
    "values": [
        {"display_label": "A", "value": "a"},
        {"display_label": "B", "value": "b"},
    ],
}

# Every field type that coerce_field routes through _coerce_string.
# "email" is excluded: it adds a format check on top (see TestEmailField).
_STRING_FIELD_TYPES = ["text", "textarea", "masked_text"]

_DYNAMIC_OPTIONS: dict[str, Any] = {
    "source": "dynamic",
    "expression": "${upstream.output}",
    "label_key": "display_label",
    "value_key": "value",
}

_RESOLVED_NUMERIC_OPTIONS: dict[str, Any] = {
    "source": "dynamic_resolved",
    "values": [
        {"display_label": "Five", "value": 5},
        {"display_label": "Six", "value": 6},
    ],
}


def _field(type_name: str, value_name: str, **overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    """Build a field payload."""
    return {"type": type_name, "value_name": value_name, "label": value_name.title(), **overrides}


def _form(*fields: dict[str, Any]) -> FormDefinition:
    """Build a FormDefinition from raw field payloads."""
    return FormDefinition.model_validate({"fields": list(fields)})


def _errors(form: FormDefinition, submitted: dict[str, Any]) -> list[Any]:
    """Run validation expecting failure and return the field errors."""
    with pytest.raises(FormDataValidationError) as exc_info:
        validate_form_submission(form, submitted)
    return exc_info.value.errors


class TestSubmissionFlow:
    """Overall validation flow: defaults, required, unknown keys."""

    def test_valid_submission(self) -> None:
        """A well-formed submission returns cleaned values."""
        form = _form(
            _field("text", "name"),
            _field("number", "age"),
            _field("checkbox", "subscribe"),
            _field("date", "start"),
        )

        cleaned = validate_form_submission(
            form, {"name": "bob", "age": 30, "subscribe": True, "start": {"date": "2026-01-05"}}
        )

        assert cleaned == {"name": "bob", "age": 30, "subscribe": True, "start": {"date": "2026-01-05"}}

    def test_absent_optional_key_omitted(self) -> None:
        """An absent optional field is omitted entirely, not set to None."""
        cleaned = validate_form_submission(_form(_field("text", "name")), {})

        assert cleaned == {}

    @pytest.mark.parametrize("empty", ["", [], None])
    def test_empty_values_treated_as_absent(self, empty: Any) -> None:  # noqa: ANN401
        """Empty string/list/None normalize to absent."""
        cleaned = validate_form_submission(_form(_field("text", "name")), {"name": empty})

        assert cleaned == {}

    def test_default_applied_when_absent(self) -> None:
        """A default fills in for an absent field."""
        cleaned = validate_form_submission(_form(_field("text", "name", default="anon")), {})

        assert cleaned == {"name": "anon"}

    def test_submitted_value_beats_default(self) -> None:
        """A submitted value takes precedence over the default."""
        cleaned = validate_form_submission(_form(_field("text", "name", default="anon")), {"name": "bob"})

        assert cleaned == {"name": "bob"}

    def test_missing_required_field(self) -> None:
        """A required field with no value reports code 'required'."""
        errors = _errors(_form(_field("text", "name", required=True)), {})

        assert [(e.field, e.code) for e in errors] == [("name", "required")]

    def test_unknown_field(self) -> None:
        """Keys not defined in the form are reported."""
        errors = _errors(_form(_field("text", "name")), {"name": "bob", "sneaky": "x"})

        assert [(e.field, e.code) for e in errors] == [("sneaky", "unknown_field")]

    def test_errors_accumulate(self) -> None:
        """Validation collects all errors rather than failing fast."""
        form = _form(_field("text", "name", required=True), _field("number", "age", required=True))

        errors = _errors(form, {"age": "not-a-number", "extra": 1})

        assert {(e.field, e.code) for e in errors} == {
            ("name", "required"),
            ("age", "type"),
            ("extra", "unknown_field"),
        }

    def test_submitted_mapping_not_mutated(self) -> None:
        """The caller's submission dict is left untouched."""
        submitted = {"name": "bob"}

        validate_form_submission(_form(_field("text", "name"), _field("text", "other", default="d")), submitted)

        assert submitted == {"name": "bob"}


class TestCoercion:
    """Per-type coercion rules."""

    @pytest.mark.parametrize(("raw", "expected"), [("3.5", 3.5), (7, 7), (-2, -2), ("10", 10.0)])
    def test_number_accepted(self, raw: Any, expected: float) -> None:  # noqa: ANN401
        """Numbers and numeric strings coerce to int/float."""
        cleaned = validate_form_submission(_form(_field("number", "age")), {"age": raw})

        assert cleaned["age"] == expected

    @pytest.mark.parametrize("raw", ["abc", "nan", "inf", "-inf", True, [1]])
    def test_number_rejected(self, raw: Any) -> None:  # noqa: ANN401
        """Non-numeric strings, bools, nan/inf and lists are rejected."""
        errors = _errors(_form(_field("number", "age")), {"age": raw})

        assert [e.code for e in errors] == ["type"]

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (True, True),
            ("yes", True),
            ("ON", True),
            ("1", True),
            (1, True),
            (False, False),
            ("no", False),
            ("off", False),
            ("False", False),
            (0, False),
        ],
    )
    def test_checkbox_accepted(self, raw: Any, *, expected: bool) -> None:  # noqa: ANN401
        """Common truthy/falsey representations coerce to bool."""
        cleaned = validate_form_submission(_form(_field("checkbox", "agree")), {"agree": raw})

        assert cleaned["agree"] is expected

    @pytest.mark.parametrize("raw", ["maybe", 2, {"a": 1}])
    def test_checkbox_rejected(self, raw: Any) -> None:  # noqa: ANN401
        """Unrecognized checkbox values are rejected."""
        errors = _errors(_form(_field("checkbox", "agree")), {"agree": raw})

        assert [e.code for e in errors] == ["type"]

    @pytest.mark.parametrize(
        "submitted",
        [{"agree": False}, {}],
        ids=["explicit_false", "absent_from_submission"],
    )
    def test_required_checkbox_must_be_checked(self, submitted: dict[str, Any]) -> None:
        """A required checkbox that is not ticked fails (terms-of-service pattern).

        Covers both an explicit False and an omitted key - CheckboxField.default
        is a concrete False, so an absent checkbox is filled in by the default
        rather than reported as "required".
        """
        errors = _errors(_form(_field("checkbox", "agree", required=True)), submitted)

        assert [(e.field, e.code) for e in errors] == [("agree", "must_be_checked")]
        assert "must be checked" in errors[0].message

    def test_required_checkbox_checked_passes(self) -> None:
        """A ticked required checkbox passes."""
        form = _form(_field("checkbox", "agree", required=True))

        assert validate_form_submission(form, {"agree": True}) == {"agree": True}

    def test_unparseable_required_checkbox_is_a_type_error(self) -> None:
        """A coercion failure stays "type", distinct from "must_be_checked"."""
        errors = _errors(_form(_field("checkbox", "agree", required=True)), {"agree": "maybe"})

        assert [e.code for e in errors] == ["type"]

    @pytest.mark.parametrize("raw", ["2026-01-05", "01/05/2026", "not-a-date", 20260105, ["2026-01-05"]])
    def test_date_must_be_an_object(self, raw: Any) -> None:  # noqa: ANN401
        """A date value is always a component object, never a bare scalar.

        Even a date-only field takes {"date": ...}: keeping one shape means
        enabling a timezone later cannot silently break downstream expressions.
        """
        errors = _errors(_form(_field("date", "start")), {"start": raw})

        assert [e.code for e in errors] == ["type"]

    @pytest.mark.parametrize("field_type", _STRING_FIELD_TYPES)
    def test_string_family_accepted(self, field_type: str) -> None:
        """Every field type routed through _coerce_string accepts a string.

        Pins the isinstance dispatch tuple in coerce_field: narrowing it would
        drop a type into the "Unknown field type" branch, which this catches.
        """
        cleaned = validate_form_submission(_form(_field(field_type, "name")), {"name": "bob"})

        assert cleaned == {"name": "bob"}

    @pytest.mark.parametrize("field_type", _STRING_FIELD_TYPES)
    @pytest.mark.parametrize("raw", [123, 4.5, True, ["a"], {"a": 1}])
    def test_string_family_rejects_non_strings(self, field_type: str, raw: Any) -> None:  # noqa: ANN401
        """String fields do not silently stringify non-string input."""
        errors = _errors(_form(_field(field_type, "name")), {"name": raw})

        assert [e.code for e in errors] == ["type"]

    def test_multi_select_wraps_bare_scalar(self) -> None:
        """A bare scalar is wrapped into a one-element list (browser behavior)."""
        form = _form(_field("multi_select", "picks", options=_STATIC_OPTIONS))

        cleaned = validate_form_submission(form, {"picks": "a"})

        assert cleaned["picks"] == ["a"]

    def test_multi_select_passes_list_through(self) -> None:
        """A submitted list is preserved."""
        form = _form(_field("multi_select", "picks", options=_STATIC_OPTIONS))

        cleaned = validate_form_submission(form, {"picks": ["a", "b"]})

        assert cleaned["picks"] == ["a", "b"]

    def test_dropdown_rejects_list(self) -> None:
        """A dropdown expects a single value."""
        form = _form(_field("dropdown", "pick", options=_STATIC_OPTIONS))

        errors = _errors(form, {"pick": ["a"]})

        assert [e.code for e in errors] == ["type"]

    @pytest.mark.parametrize("field_type", ["dropdown", "multi_select"])
    def test_dynamic_int_accepted_and_not_normalized(self, field_type: str) -> None:
        """Both dynamic option field types preserve submitted ints."""
        form = _form(_field(field_type, "pick", options=_DYNAMIC_OPTIONS))

        cleaned = validate_form_submission(form, {"pick": 5})

        value = cleaned["pick"][0] if field_type == "multi_select" else cleaned["pick"]
        assert value == 5
        assert isinstance(value, int)

    @pytest.mark.parametrize("field_type", ["dropdown", "multi_select"])
    def test_dynamic_float_preserves_type(self, field_type: str) -> None:
        """Both dynamic option field types preserve submitted floats."""
        form = _form(_field(field_type, "pick", options=_DYNAMIC_OPTIONS))

        cleaned = validate_form_submission(form, {"pick": 5.0})

        assert cleaned["pick"] == ([5.0] if field_type == "multi_select" else 5.0)

    @pytest.mark.parametrize("bad", [{"a": 1}, [1], None])
    def test_multi_select_rejects_non_scalar_elements(self, bad: Any) -> None:  # noqa: ANN401
        """Unhashable/unsupported list elements are a type error, not a crash.

        Regression: these previously bypassed coercion and reached the option
        membership set test, raising TypeError: unhashable type.
        """
        form = _form(_field("multi_select", "picks", options=_STATIC_OPTIONS))

        errors = _errors(form, {"picks": [bad]})

        assert [e.code for e in errors] == ["type"]


class TestCoercerDispatch:
    """coerce_field handles every field type in the FormField union.

    A missing case is a mypy error via assert_never, but the pre-commit pyrefly
    hook does not flag it, so this is the backstop for anyone who adds a field
    type without running `make typecheck`.
    """

    def test_every_field_type_is_routed(self) -> None:
        union, _discriminator = get_args(FormField)
        members = get_args(union)
        assert members, "FormField union introspection returned nothing - the test needs updating"

        for member in members:
            (type_name,) = get_args(member.model_fields["type"].annotation)
            overrides = {"options": _STATIC_OPTIONS} if "options" in member.model_fields else {}
            form = _form(_field(type_name, "probe", **overrides))

            # No coercer accepts a bare object, so every case must turn this
            # into a field error rather than falling through to assert_never.
            assert _errors(form, {"probe": object()}), f"{type_name} produced no error"


class TestEmailField:
    """Email fields validate format on top of the shared string coercion."""

    @pytest.mark.parametrize("raw", ["bob@example.com", "first.last+tag@sub.example.co.uk"])
    def test_valid_email_accepted(self, raw: str) -> None:
        """Well-formed addresses pass through."""
        cleaned = validate_form_submission(_form(_field("email", "contact")), {"contact": raw})

        assert cleaned == {"contact": raw}

    def test_domain_is_normalized(self) -> None:
        """The domain is lowercased; the local part is left alone.

        Local parts are case-sensitive per RFC 5321, so only the domain is
        folded. This is what reaches the workflow namespace.
        """
        cleaned = validate_form_submission(_form(_field("email", "contact")), {"contact": "Bob@Example.COM"})

        assert cleaned == {"contact": "Bob@example.com"}

    @pytest.mark.parametrize(
        "raw",
        ["bob", "bob@", "@example.com", "bob @example.com", "bob@localhost", "bob@example"],
    )
    def test_malformed_email_is_invalid_format(self, raw: str) -> None:
        """A string that is not an address reports 'invalid_format', not 'type'."""
        errors = _errors(_form(_field("email", "contact")), {"contact": raw})

        assert [(e.field, e.code) for e in errors] == [("contact", "invalid_format")]
        assert errors[0].message

    @pytest.mark.parametrize("raw", [123, 4.5, True, ["a@b.co"], {"a": 1}])
    def test_non_string_is_type_not_format(self, raw: Any) -> None:  # noqa: ANN401
        """Wrong type stays 'type'; only wrong content is 'invalid_format'."""
        errors = _errors(_form(_field("email", "contact")), {"contact": raw})

        assert [e.code for e in errors] == ["type"]

    def test_error_message_excludes_pydantic_prefix(self) -> None:
        """The user-facing message is email_validator's, not pydantic's wrapper."""
        errors = _errors(_form(_field("email", "contact")), {"contact": "bob"})

        assert "value is not a valid email address" not in errors[0].message
        assert "@-sign" in errors[0].message


class TestOptionMembership:
    """Static and resolved option membership is enforced on dropdowns and multi-selects."""

    def test_valid_dropdown_value(self) -> None:
        """A value from the option list passes."""
        form = _form(_field("dropdown", "pick", options=_STATIC_OPTIONS))

        assert validate_form_submission(form, {"pick": "a"}) == {"pick": "a"}

    def test_invalid_dropdown_value(self) -> None:
        """A value outside the option list is rejected."""
        form = _form(_field("dropdown", "pick", options=_STATIC_OPTIONS))

        errors = _errors(form, {"pick": "z"})

        assert [(e.field, e.code) for e in errors] == [("pick", "not_in_options")]

    def test_valid_multi_select_values(self) -> None:
        """All-valid multi-select values pass."""
        form = _form(_field("multi_select", "picks", options=_STATIC_OPTIONS))

        assert validate_form_submission(form, {"picks": ["a", "b"]}) == {"picks": ["a", "b"]}

    def test_invalid_multi_select_value(self) -> None:
        """One unknown entry fails the whole field."""
        form = _form(_field("multi_select", "picks", options=_STATIC_OPTIONS))

        errors = _errors(form, {"picks": ["a", "z"]})

        assert [(e.field, e.code) for e in errors] == [("picks", "not_in_options")]

    def test_dynamic_options_skip_membership_check(self) -> None:
        """Membership is not enforced against an unresolved authoring definition."""
        form = _form(
            _field(
                "dropdown",
                "pick",
                options={
                    "source": "dynamic",
                    "expression": "${a.output}",
                    "label_key": "display_label",
                    "value_key": "value",
                },
            )
        )

        assert validate_form_submission(form, {"pick": "anything"}) == {"pick": "anything"}


class TestDateFieldSubmission:
    """A date submission must carry exactly the components the field collects."""

    @staticmethod
    def _date_form(**toggles: Any) -> FormDefinition:  # noqa: ANN401
        return _form(_field("date", "start", **toggles))

    @pytest.mark.parametrize(
        ("toggles", "submitted"),
        [
            ({}, {"date": "2026-01-05"}),
            ({"include_timezone": True}, {"date": "2026-01-05", "timezone": "America/New_York"}),
            (
                {"include_time": True, "include_timezone": True},
                {"date": "2026-01-05", "time": "14:30", "timezone": "America/New_York"},
            ),
            (
                {"include_date": False, "include_time": True, "include_timezone": True},
                {"time": "14:30", "timezone": "America/New_York"},
            ),
            ({"include_date": False, "include_timezone": True}, {"timezone": "America/New_York"}),
        ],
    )
    def test_complete_submission_round_trips(self, toggles: dict[str, bool], submitted: dict[str, str]) -> None:
        """A submission covering every included component is returned verbatim."""
        cleaned = validate_form_submission(self._date_form(**toggles), {"start": submitted})

        assert cleaned["start"] == submitted

    def test_missing_component_rejected(self) -> None:
        """Every included component is mandatory once the field is answered."""
        form = self._date_form(include_time=True, include_timezone=True)

        errors = _errors(form, {"start": {"date": "2026-01-05", "time": "14:30"}})

        assert [e.code for e in errors] == ["invalid_format"]
        assert "Missing required component: timezone" in errors[0].message

    def test_uncollected_component_rejected(self) -> None:
        """Sending a component the field does not collect is an error, not ignored."""
        errors = _errors(self._date_form(), {"start": {"date": "2026-01-05", "time": "14:30"}})

        assert [e.code for e in errors] == ["invalid_format"]
        assert "This field does not collect: time" in errors[0].message

    def test_unknown_component_rejected(self) -> None:
        """Only the three known component keys are accepted."""
        errors = _errors(self._date_form(), {"start": {"date": "2026-01-05", "offset": "-05:00"}})

        assert [e.code for e in errors] == ["invalid_format"]
        assert "'offset' is not a date component" in errors[0].message

    def test_blank_component_reads_as_absent(self) -> None:
        """An untouched input posting "" is missing, not malformed."""
        errors = _errors(self._date_form(), {"start": {"date": ""}})

        assert "Missing required component: date" in errors[0].message

    @pytest.mark.parametrize(
        ("bad", "expected_message"),
        [
            ({"date": "01/05/2026"}, "date must be a date in YYYY-MM-DD format"),
            ({"date": "2026-02-30"}, "Invalid date: '2026-02-30'"),
        ],
    )
    def test_malformed_date_reports_plain_language(self, bad: dict[str, str], expected_message: str) -> None:
        """Responders see a readable hint, never the raw validation pattern."""
        errors = _errors(self._date_form(), {"start": bad})

        assert [e.code for e in errors] == ["invalid_format"]
        assert expected_message in errors[0].message

    def test_malformed_time_reports_plain_language(self) -> None:
        """A bad time names the expected format rather than the regex."""
        form = self._date_form(include_date=False, include_time=True, include_timezone=True)

        errors = _errors(form, {"start": {"time": "25:00", "timezone": "UTC"}})

        assert "time must be a 24-hour time in HH:MM format" in errors[0].message

    def test_unknown_timezone_rejected(self) -> None:
        """Timezones are checked against the IANA database at submission time."""
        form = self._date_form(include_date=False, include_timezone=True)

        errors = _errors(form, {"start": {"timezone": "Mars/Olympus"}})

        assert "Invalid timezone: 'Mars/Olympus'" in errors[0].message

    def test_absent_optional_date_is_omitted(self) -> None:
        """An unanswered optional date field contributes no key."""
        assert validate_form_submission(self._date_form(), {}) == {}

    def test_absent_required_date_reports_required(self) -> None:
        """The inherited required flag governs skipping the field entirely."""
        errors = _errors(self._date_form(required=True), {})

        assert [e.code for e in errors] == ["required"]

    def test_default_fills_an_absent_field(self) -> None:
        """A complete default stands in for the whole answer."""
        form = self._date_form(
            include_time=True,
            include_timezone=True,
            default={"date": "2026-03-01", "time": "08:00", "timezone": "Europe/Paris"},
        )

        cleaned = validate_form_submission(form, {})

        assert cleaned["start"] == {"date": "2026-03-01", "time": "08:00", "timezone": "Europe/Paris"}

    @pytest.mark.parametrize("field_type", ["dropdown", "multi_select"])
    def test_resolved_options_enforce_typed_membership(self, field_type: str) -> None:
        """Resolved options preserve typed values and reject their string form."""
        form = _form(_field(field_type, "pick", options=_RESOLVED_NUMERIC_OPTIONS))

        accepted = validate_form_submission(form, {"pick": 5})
        assert accepted["pick"] == ([5] if field_type == "multi_select" else 5)
        if field_type == "multi_select":
            assert isinstance(accepted["pick"][0], int)
        else:
            assert isinstance(accepted["pick"], int)

        errors = _errors(form, {"pick": "5"})
        assert [(error.field, error.code) for error in errors] == [("pick", "not_in_options")]
