"""Unit tests for author-time form definition validation."""

from typing import Any

import pytest

from syntara.forms.exceptions import FormDefinitionError
from syntara.forms.models.form_fields import FormDefinition
from syntara.forms.validators.form_definition import validate_form_definition

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


def _errors(form: FormDefinition) -> list[Any]:
    """Run definition validation expecting failure and return the field errors."""
    with pytest.raises(FormDefinitionError) as exc_info:
        validate_form_definition(form)
    return exc_info.value.errors


class TestValidDefinitions:
    """Definitions that should pass."""

    def test_no_defaults_passes(self) -> None:
        """A form whose fields have no defaults is trivially valid."""
        validate_form_definition(_form(_field("text", "name"), _field("email", "contact")))

    @pytest.mark.parametrize(
        ("field_type", "default"),
        [
            ("text", "anon"),
            ("textarea", "notes"),
            ("masked_text", "secret"),
            ("email", "bob@example.com"),
            ("number", 42),
            ("number", 3.5),
            ("checkbox", True),
            ("date", "2026-01-05"),
        ],
    )
    def test_valid_defaults_pass(self, field_type: str, default: Any) -> None:  # noqa: ANN401
        """A default the submission coercer accepts is a valid default."""
        validate_form_definition(_form(_field(field_type, "x", default=default)))

    def test_valid_option_defaults_pass(self) -> None:
        """Dropdown and multi-select defaults drawn from the option list pass."""
        form = _form(
            _field("dropdown", "pick", options=_STATIC_OPTIONS, default="a"),
            _field("multi_select", "picks", options=_STATIC_OPTIONS, default=["a", "b"]),
        )

        validate_form_definition(form)


class TestInvalidDefaults:
    """Defaults the responder-time coercer would reject are caught at author time."""

    def test_malformed_email_default(self) -> None:
        """Regression: this previously saved fine and failed for every responder."""
        errors = _errors(_form(_field("email", "contact", default="not-an-email")))

        assert [(e.field, e.code) for e in errors] == [("contact", "invalid_default")]
        assert "@-sign" in errors[0].message

    @pytest.mark.parametrize("default", ["tomorrow", "01/05/2026", "2026-13-01"])
    def test_non_iso_date_default(self, default: str) -> None:
        """A date default that is not ISO 8601 is rejected up front."""
        errors = _errors(_form(_field("date", "start", default=default)))

        assert [(e.field, e.code) for e in errors] == [("start", "invalid_default")]

    def test_message_names_the_field_type(self) -> None:
        """The author-facing message says which field type rejected the value."""
        errors = _errors(_form(_field("date", "start", default="tomorrow")))

        assert "'date' field" in errors[0].message

    def test_errors_accumulate_across_fields(self) -> None:
        """Every bad default is reported, not just the first."""
        form = _form(
            _field("email", "contact", default="nope"),
            _field("text", "name", default="fine"),
            _field("date", "start", default="tomorrow"),
        )

        errors = _errors(form)

        assert [(e.field, e.code) for e in errors] == [
            ("contact", "invalid_default"),
            ("start", "invalid_default"),
        ]

    def test_form_id_is_carried(self) -> None:
        """The optional form_id reaches the exception for error context."""
        form = _form(_field("email", "contact", default="nope"))

        with pytest.raises(FormDefinitionError) as exc_info:
            validate_form_definition(form, form_id="node-7")

        assert exc_info.value.form_id == "node-7"
        assert "node-7" in str(exc_info.value)


class TestAuthorTimeMatchesSubmissionTime:
    """The two paths must not drift apart."""

    def test_definition_check_uses_the_submission_coercer(self) -> None:
        """A default accepted here must not be rejected at submission.

        Both paths call coerce_field, so this holds by construction; the test
        pins it against someone reimplementing one side.
        """
        from syntara.forms.validators.submission import validate_form_submission

        form = _form(_field("email", "contact", default="Bob@Example.COM"))

        validate_form_definition(form)

        assert validate_form_submission(form, {}) == {"contact": "Bob@example.com"}


class TestMultiSelectScalarDefaults:
    """Non-scalar multi-select defaults are rejected by the model itself."""

    @pytest.mark.parametrize("bad", [{"a": 1}, ["nested"]])
    def test_unhashable_default_is_a_clean_validation_error(self, bad: Any) -> None:  # noqa: ANN401
        """Regression: these raised a bare TypeError out of the model validator.

        MultiSelectField.default is list[Any], so an unhashable entry reached the
        option-membership set test and escaped as TypeError: unhashable type -
        a 500 rather than a 422, reachable straight from an API payload.
        """
        with pytest.raises(ValueError, match="must be scalars") as exc_info:
            _form(_field("multi_select", "picks", options=_STATIC_OPTIONS, default=[bad]))

        assert not isinstance(exc_info.value, TypeError)
