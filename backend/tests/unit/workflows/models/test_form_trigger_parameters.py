"""Tests for form trigger parameter validation."""

import pytest
from pydantic import ValidationError

from syntara.forms.exceptions import FormDefinitionError
from syntara.forms.models.form_fields import FormDefinition
from syntara.workflows.workflow_engine.models.workflow_definition import FormTriggerParameters


def _text_field(**overrides: object) -> dict[str, object]:
    """Build a minimal valid text field, with optional overrides."""
    return {"type": "text", "value_name": "reason", "label": "Reason", **overrides}


def _parameters(*fields: dict[str, object], **overrides: object) -> dict[str, object]:
    """Build valid form trigger parameters from field definitions."""
    return {"form_definition": {"fields": list(fields)}, **overrides}


class TestFormTriggerParameters:
    """Form trigger accepts authored form fields and rejects prompt-only behavior."""

    def test_minimal_and_full_parameters(self) -> None:
        minimal = FormTriggerParameters.model_validate(_parameters(_text_field()))
        assert isinstance(minimal.form_definition, FormDefinition)
        assert minimal.message is None

        full = FormTriggerParameters.model_validate(
            _parameters(
                _text_field(),
                message="Please provide the requested information.",
                submit_label="Send",
                success_message="Thanks for your response.",
                css_override=".form { color: blue; }",
            )
        )
        assert full.message == "Please provide the requested information."
        assert full.submit_label == "Send"
        assert full.success_message == "Thanks for your response."
        assert full.css_override == ".form { color: blue; }"

    def test_all_shared_field_types_are_accepted(self) -> None:
        fields: list[dict[str, object]] = [
            _text_field(),
            {"type": "textarea", "value_name": "notes", "label": "Notes"},
            {"type": "number", "value_name": "count", "label": "Count"},
            {"type": "masked_text", "value_name": "secret", "label": "Secret"},
            {
                "type": "dropdown",
                "value_name": "region",
                "label": "Region",
                "options": {"source": "static", "values": [{"display_label": "East", "value": "east"}]},
            },
            {
                "type": "multi_select",
                "value_name": "regions",
                "label": "Regions",
                "options": {"source": "static", "values": [{"display_label": "East", "value": "east"}]},
            },
            {"type": "checkbox", "value_name": "acknowledged", "label": "Acknowledged"},
            {"type": "date", "value_name": "start_date", "label": "Start date"},
            {"type": "email", "value_name": "email", "label": "Email"},
        ]

        parameters = FormTriggerParameters.model_validate(_parameters(*fields))
        assert [field.type for field in parameters.form_definition.fields] == [
            "text",
            "textarea",
            "number",
            "masked_text",
            "dropdown",
            "multi_select",
            "checkbox",
            "date",
            "email",
        ]

    @pytest.mark.parametrize(
        "parameter",
        ["response_window", "fallback_decision", "responder_users", "responder_groups"],
    )
    def test_prompt_only_parameters_are_named_and_rejected(self, parameter: str) -> None:
        with pytest.raises(ValidationError, match=parameter):
            FormTriggerParameters.model_validate(_parameters(_text_field(), **{parameter: "not-supported"}))

    @pytest.mark.parametrize(
        ("options", "source"),
        [
            (
                {
                    "source": "dynamic",
                    "expression": "source.options",
                    "label_key": "label",
                    "value_key": "value",
                },
                "dynamic",
            ),
            (
                {"source": "dynamic_resolved", "values": [{"display_label": "East", "value": "east"}]},
                "dynamic_resolved",
            ),
        ],
    )
    def test_dynamic_option_sources_are_rejected(self, options: dict[str, object], source: str) -> None:
        fields: list[dict[str, object]] = [
            {
                "type": "dropdown",
                "value_name": "region",
                "label": "Region",
                "options": options,
            }
        ]
        with pytest.raises(ValidationError, match=f"Field 'region'.*{source}"):
            FormTriggerParameters.model_validate(_parameters(*fields))

    @pytest.mark.parametrize(
        ("parameters", "expected_path"),
        [
            (_parameters(_text_field(), message="${upstream.value}"), "message"),
            (_parameters(_text_field(label="${upstream.label}")), "form_definition.fields.0.label"),
            (_parameters(_text_field(default="${upstream.default}")), "form_definition.fields.0.default"),
            (
                _parameters(
                    {
                        "type": "dropdown",
                        "value_name": "region",
                        "label": "Region",
                        "options": {
                            "source": "static",
                            "values": [{"display_label": "${upstream.label}", "value": "east"}],
                        },
                    }
                ),
                "form_definition.fields.0.options.values.0.display_label",
            ),
        ],
    )
    def test_template_expressions_are_rejected_with_paths(
        self, parameters: dict[str, object], expected_path: str
    ) -> None:
        with pytest.raises(ValidationError, match=expected_path.replace(".", r"\.")):
            FormTriggerParameters.model_validate(parameters)

    def test_invalid_default_is_rejected_by_shared_form_definition_validation(self) -> None:
        fields: list[dict[str, object]] = [
            {
                "type": "email",
                "value_name": "contact",
                "label": "Contact",
                "default": "not-an-email",
            }
        ]
        with pytest.raises(FormDefinitionError, match="invalid field definition"):
            FormTriggerParameters.model_validate(_parameters(*fields))

    def test_unsafe_css_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match=r"url\(\)"):
            FormTriggerParameters.model_validate(
                _parameters(_text_field(), css_override=".form { background: url(x); }")
            )

    def test_unknown_parameters_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            FormTriggerParameters.model_validate(_parameters(_text_field(), unexpected="value"))
