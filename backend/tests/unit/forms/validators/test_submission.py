"""Unit tests for form submission validation and coercion."""

from typing import Any

import pytest

from syntara.forms.exceptions import FormDataValidationError
from syntara.forms.models.form_fields import FormDefinition
from syntara.forms.validators.submission import validate_form_submission

_STATIC_OPTIONS: dict[str, Any] = {
    "source": "static",
    "values": [
        {"display_label": "A", "value": "a"},
        {"display_label": "B", "value": "b"},
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

        cleaned = validate_form_submission(form, {"name": "bob", "age": 30, "subscribe": True, "start": "2026-01-05"})

        assert cleaned == {"name": "bob", "age": 30, "subscribe": True, "start": "2026-01-05"}

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

    def test_required_checkbox_must_be_checked(self) -> None:
        """A required checkbox submitted as False fails (terms-of-service pattern)."""
        errors = _errors(_form(_field("checkbox", "agree", required=True)), {"agree": False})

        assert [(e.field, e.code) for e in errors] == [("agree", "type")]
        assert "must be checked" in errors[0].message

    @pytest.mark.parametrize(("raw", "expected"), [("2026-01-05", "2026-01-05"), ("20260105", "2026-01-05")])
    def test_date_accepted(self, raw: str, expected: str) -> None:
        """ISO dates normalize to YYYY-MM-DD strings."""
        cleaned = validate_form_submission(_form(_field("date", "start")), {"start": raw})

        assert cleaned["start"] == expected

    @pytest.mark.parametrize("raw", ["01/05/2026", "not-a-date", "2026-13-01", "2026-1-5", 20260105])
    def test_date_rejected(self, raw: Any) -> None:  # noqa: ANN401
        """Non-ISO and non-string dates are rejected."""
        errors = _errors(_form(_field("date", "start")), {"start": raw})

        assert [e.code for e in errors] == ["type"]

    @pytest.mark.parametrize("raw", [123, 4.5, True, ["a"], {"a": 1}])
    def test_text_rejects_non_strings(self, raw: Any) -> None:  # noqa: ANN401
        """Text fields do not silently stringify non-string input."""
        errors = _errors(_form(_field("text", "name")), {"name": raw})

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


class TestOptionMembership:
    """Static option membership is enforced on dropdowns and multi-selects."""

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
        """Membership is not enforced against unresolved dynamic options."""
        form = _form(
            _field(
                "dropdown",
                "pick",
                options={"source": "dynamic", "expression": "${a.output}"},
            )
        )

        assert validate_form_submission(form, {"pick": "anything"}) == {"pick": "anything"}
