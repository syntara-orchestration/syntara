"""Unit tests for Form Trigger submission validation in the execution service."""

from typing import Any

import pytest

from syntara.forms.exceptions import FormDataValidationError
from syntara.workflows.exceptions import TriggerValidationError
from syntara.workflows.services.execution_service import ExecutionService


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


class TestTriggerInputDispatch:
    """Form triggers use form validation; other triggers retain JSON Schema behavior."""

    def test_form_trigger_dispatches_to_form_submission_validator(self) -> None:
        trigger = _form_trigger(_field("number", "count"))
        submitted = {"count": "42"}

        cleaned = ExecutionService._normalize_trigger_input(trigger, submitted)

        assert cleaned == {"count": 42.0}
        assert submitted == {"count": "42"}

    def test_manual_trigger_keeps_json_schema_defaults_in_place(self) -> None:
        trigger = {
            "id": "manual",
            "type": "manual_trigger",
            "parameters": {
                "input_schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string", "default": "default-name"}},
                }
            },
        }
        submitted: dict[str, Any] = {}

        cleaned = ExecutionService._normalize_trigger_input(trigger, submitted)

        assert cleaned is submitted
        assert submitted == {"name": "default-name"}

    @pytest.mark.parametrize("trigger_type", ["manual_trigger", "webhook_trigger", "eda_trigger"])
    def test_non_form_trigger_without_schema_is_unchanged(self, trigger_type: str) -> None:
        submitted = {"untouched": "value"}

        cleaned = ExecutionService._normalize_trigger_input(
            {"id": "trigger", "type": trigger_type, "parameters": {}},
            submitted,
        )

        assert cleaned is submitted
        assert submitted == {"untouched": "value"}

    def test_form_submission_helper_returns_cleaned_data(self) -> None:
        trigger = _form_trigger(_field("text", "name"))

        assert ExecutionService._validate_form_trigger_submission(trigger, {"name": "Ada"}) == {"name": "Ada"}


class TestFormTriggerSubmissionCleaning:
    """Form Trigger values use the same coercion and defaults as form prompts."""

    def test_number_is_coerced_and_email_domain_normalized(self) -> None:
        trigger = _form_trigger(_field("number", "count"), _field("email", "contact"))

        cleaned = ExecutionService._validate_form_trigger_submission(
            trigger,
            {"count": "42", "contact": "Bob@Example.COM"},
        )

        assert cleaned == {"count": 42.0, "contact": "Bob@example.com"}

    def test_optional_absent_field_is_omitted(self) -> None:
        trigger = _form_trigger(_field("text", "required", required=True), _field("text", "optional"))

        cleaned = ExecutionService._validate_form_trigger_submission(trigger, {"required": "value"})

        assert cleaned == {"required": "value"}

    def test_default_is_applied(self) -> None:
        trigger = _form_trigger(_field("text", "name", default="Ada"))

        assert ExecutionService._validate_form_trigger_submission(trigger, {}) == {"name": "Ada"}

    def test_date_is_normalized_to_included_components(self) -> None:
        trigger = _form_trigger(_field("date", "start"))

        cleaned = ExecutionService._validate_form_trigger_submission(trigger, {"start": {"date": "2026-02-14"}})

        assert cleaned == {"start": "2026-02-14"}

    def test_checkbox_on_is_coerced_to_true(self) -> None:
        trigger = _form_trigger(_field("checkbox", "confirmed"))

        assert ExecutionService._validate_form_trigger_submission(trigger, {"confirmed": "on"}) == {"confirmed": True}

    def test_submission_input_is_not_mutated(self) -> None:
        trigger = _form_trigger(_field("text", "name"), _field("text", "defaulted", default="default"))
        submitted = {"name": "Ada"}

        ExecutionService._validate_form_trigger_submission(trigger, submitted)

        assert submitted == {"name": "Ada"}


class TestFormTriggerSubmissionFailures:
    """Form data errors retain field details and identify their trigger."""

    def test_missing_required_field_has_trigger_context(self) -> None:
        trigger = _form_trigger(_field("text", "name", required=True), node_id="request")

        with pytest.raises(FormDataValidationError) as exc_info:
            ExecutionService._validate_form_trigger_submission(trigger, {})

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
            ExecutionService._validate_form_trigger_submission(trigger, submitted)

        assert expected_code in {error.code for error in exc_info.value.errors}

    def test_all_field_errors_are_preserved(self) -> None:
        trigger = _form_trigger(
            _field("text", "required_name", required=True),
            _field("number", "count", required=True),
        )

        with pytest.raises(FormDataValidationError) as exc_info:
            ExecutionService._validate_form_trigger_submission(trigger, {"count": "not-a-number", "unknown": 1})

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
            ExecutionService._validate_form_trigger_submission(trigger, {})

    def test_dynamic_options_are_rejected_for_form_triggers(self) -> None:
        trigger = _form_trigger(
            _field(
                "dropdown",
                "environment",
                options={
                    "source": "dynamic",
                    "expression": "${upstream.options}",
                    "label_key": "label",
                    "value_key": "value",
                },
            )
        )

        with pytest.raises(TriggerValidationError, match="form definition"):
            ExecutionService._validate_form_trigger_submission(trigger, {"environment": "staging"})

    def test_wrong_typed_default_is_a_trigger_validation_error(self) -> None:
        trigger = _form_trigger(_field("number", "count", default="not-a-number"))

        with pytest.raises(TriggerValidationError, match="form definition"):
            ExecutionService._validate_form_trigger_submission(trigger, {})
