"""Unit tests for Form Trigger submission validation and normalization."""

from typing import Any

import pytest

from syntara.forms.exceptions import FormDataValidationError
from syntara.workflows.exceptions import TriggerValidationError
from syntara.workflows.form_trigger import validate_form_trigger_submission


def _field(field_type: str, value_name: str, **overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    """Build one raw form-field definition."""
    return {"type": field_type, "value_name": value_name, "label": value_name.replace("_", " ").title(), **overrides}


def _form_trigger(*fields: dict[str, Any], node_id: str = "form") -> dict[str, Any]:
    """Build a raw Form Trigger node."""
    return {
        "id": node_id,
        "type": "form_trigger",
        "parameters": {"form_definition": {"fields": list(fields)}},
    }


class TestFormTriggerSubmissionCleaning:
    """Form Trigger values use the same coercion and defaults as form prompts."""

    def test_form_submission_helper_returns_cleaned_data(self) -> None:
        trigger = _form_trigger(_field("text", "name"))

        cleaned_input, form_definition_metadata = validate_form_trigger_submission(trigger, {"name": "Ada"})

        assert cleaned_input == {"name": "Ada"}
        assert form_definition_metadata.field_types == ["text"]
        assert form_definition_metadata.field_count == 1

    def test_number_is_coerced_and_email_domain_normalized(self) -> None:
        trigger = _form_trigger(_field("number", "count"), _field("email", "contact"))

        cleaned_input, form_definition_metadata = validate_form_trigger_submission(
            trigger,
            {"count": "42", "contact": "Bob@Example.COM"},
        )

        assert cleaned_input == {"count": 42.0, "contact": "Bob@example.com"}
        assert form_definition_metadata.field_types == ["email", "number"]

    def test_optional_absent_field_has_typed_empty_output(self) -> None:
        trigger = _form_trigger(_field("text", "required", required=True), _field("text", "optional"))

        cleaned_input, form_definition_metadata = validate_form_trigger_submission(trigger, {"required": "value"})

        assert cleaned_input == {"required": "value", "optional": ""}
        assert form_definition_metadata.field_types == ["text"]
        assert form_definition_metadata.field_count == 2

    def test_field_count_uses_all_configured_fields_when_values_are_omitted(self) -> None:
        fields = (
            _field("text", "required", required=True),
            *(_field("text", f"optional_{index}") for index in range(9)),
        )
        trigger = _form_trigger(*fields)

        cleaned_input, form_definition_metadata = validate_form_trigger_submission(trigger, {"required": "value"})

        assert cleaned_input == {
            "required": "value",
            **{f"optional_{index}": "" for index in range(9)},
        }
        assert form_definition_metadata.field_count == 10
        assert form_definition_metadata.field_types == ["text"]

    def test_default_is_applied(self) -> None:
        trigger = _form_trigger(_field("text", "name", default="Ada"))

        cleaned_input, form_definition_metadata = validate_form_trigger_submission(trigger, {})

        assert cleaned_input == {"name": "Ada"}
        assert form_definition_metadata.field_types == ["text"]
        assert form_definition_metadata.field_count == 1

    def test_date_is_normalized_to_iso_string(self) -> None:
        trigger = _form_trigger(_field("date", "start"))

        cleaned_input, form_definition_metadata = validate_form_trigger_submission(
            trigger, {"start": {"date": "2026-02-14"}}
        )

        assert cleaned_input == {"start": "2026-02-14"}
        assert form_definition_metadata.field_types == ["date"]
        assert form_definition_metadata.field_count == 1

    def test_checkbox_on_is_coerced_to_true(self) -> None:
        trigger = _form_trigger(_field("checkbox", "confirmed"))

        cleaned_input, form_definition_metadata = validate_form_trigger_submission(trigger, {"confirmed": "on"})

        assert cleaned_input == {"confirmed": True}
        assert form_definition_metadata.field_types == ["checkbox"]

    def test_submission_input_is_not_mutated(self) -> None:
        trigger = _form_trigger(_field("text", "name"), _field("text", "defaulted", default="default"))
        submitted = {"name": "Ada"}

        validate_form_trigger_submission(trigger, submitted)

        assert submitted == {"name": "Ada"}


class TestFormTriggerSubmissionFailures:
    """Form data errors retain field details and identify their trigger."""

    def test_missing_required_field_has_trigger_context(self) -> None:
        trigger = _form_trigger(_field("text", "name", required=True), node_id="request")

        with pytest.raises(FormDataValidationError) as exc_info:
            validate_form_trigger_submission(trigger, {})

        assert [(error.field, error.code) for error in exc_info.value.errors] == [("name", "required")]
        assert exc_info.value.form_id == "request"

    @pytest.mark.parametrize(
        ("fields", "submitted", "expected_code"),
        [
            ((_field("text", "name"),), {"name": "Ada", "unknown": "value"}, "unknown_field"),
            (
                (
                    _field(
                        "dropdown",
                        "environment",
                        options={
                            "source": "static",
                            "values": [{"display_label": "Staging", "value": "staging"}],
                        },
                    ),
                ),
                {"environment": "production"},
                "not_in_options",
            ),
            ((_field("number", "count"),), {"count": {"bad": "value"}}, "type"),
            ((_field("email", "contact"),), {"contact": "not-an-email"}, "invalid_format"),
        ],
        ids=["unknown-key", "invalid-option", "wrong-type", "invalid-email"],
    )
    def test_invalid_field_data_is_rejected(
        self,
        fields: tuple[dict[str, Any], ...],
        submitted: dict[str, Any],
        expected_code: str,
    ) -> None:
        trigger = _form_trigger(*fields)

        with pytest.raises(FormDataValidationError) as exc_info:
            validate_form_trigger_submission(trigger, submitted)

        assert expected_code in {error.code for error in exc_info.value.errors}

    def test_all_field_errors_are_preserved(self) -> None:
        trigger = _form_trigger(
            _field("text", "required_name", required=True),
            _field("number", "count", required=True),
        )

        with pytest.raises(FormDataValidationError) as exc_info:
            validate_form_trigger_submission(trigger, {"count": "not-a-number", "unknown": 1})

        assert {(error.field, error.code) for error in exc_info.value.errors} == {
            ("required_name", "required"),
            ("count", "type"),
            ("unknown", "unknown_field"),
        }

    @pytest.mark.parametrize(
        "trigger",
        [
            {"id": "form", "type": "form_trigger"},
            {"id": "form", "type": "form_trigger", "parameters": {}},
            {"id": "form", "type": "form_trigger", "parameters": {"form_definition": {"fields": []}}},
            {
                "id": "form",
                "type": "form_trigger",
                "parameters": {"form_definition": {"fields": [{"type": "unknown", "value_name": "x"}]}},
            },
        ],
        ids=["missing-parameters", "missing-definition", "empty-fields", "invalid-field-type"],
    )
    def test_invalid_stored_definition_is_a_trigger_validation_error(self, trigger: dict[str, Any]) -> None:
        with pytest.raises(TriggerValidationError, match="form definition"):
            validate_form_trigger_submission(trigger, {})

    @pytest.mark.parametrize("field_type", ["dropdown", "multi_select"])
    @pytest.mark.parametrize(
        "options",
        [
            pytest.param(
                {
                    "source": "dynamic",
                    "expression": "${upstream.options}",
                    "label_key": "label",
                    "value_key": "value",
                },
                id="dynamic",
            ),
            pytest.param(
                {"source": "dynamic_resolved", "values": [{"display_label": "East", "value": "east"}]},
                id="dynamic-resolved",
            ),
        ],
    )
    def test_non_static_options_are_rejected_for_form_triggers(
        self,
        field_type: str,
        options: dict[str, Any],
    ) -> None:
        trigger = _form_trigger(_field(field_type, "environment", options=options))

        with pytest.raises(TriggerValidationError, match=r"^Form trigger has an invalid form definition$"):
            validate_form_trigger_submission(trigger, {"environment": "staging"})

    def test_wrong_typed_default_is_a_trigger_validation_error(self) -> None:
        trigger = _form_trigger(_field("number", "count", default="not-a-number"))

        with pytest.raises(TriggerValidationError, match="form definition"):
            validate_form_trigger_submission(trigger, {})
