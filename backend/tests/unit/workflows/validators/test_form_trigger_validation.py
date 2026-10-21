"""Save-time validation tests for form triggers."""

from typing import Any

import pytest

from syntara.workflows.models.validation_finding import ValidationCategory, ValidationFinding, ValidationSeverity
from syntara.workflows.validators.workflow_definition import WorkflowValidator

_FORM_NODE_ID = "form"


def _text_field(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    """Return a minimal valid text field with optional overrides."""
    return {"type": "text", "value_name": "answer", "label": "Answer", **overrides}


def _parameters(*fields: dict[str, Any], **overrides: Any) -> dict[str, Any]:  # noqa: ANN401
    """Build valid form-trigger parameters."""
    return {"form_definition": {"fields": list(fields)}, **overrides}


def _workflow_with_form_trigger(parameters: dict[str, Any]) -> dict[str, Any]:
    """Build a valid graph so findings come from trigger validation only."""
    return {
        "schema_version": "2.0.0",
        "name": "form-trigger-validation",
        "triggers": [{"id": _FORM_NODE_ID, "type": "form_trigger", "parameters": parameters}],
        "nodes": [{"id": "consume", "type": "script", "parameters": {"language": "bash", "code": "echo done"}}],
        "edges": [{"from": _FORM_NODE_ID, "to": "consume"}],
    }


def _findings(parameters: dict[str, Any]) -> list[ValidationFinding]:
    """Return findings attributed to the form trigger."""
    result = WorkflowValidator().collect_findings(_workflow_with_form_trigger(parameters))
    return [finding for finding in result.findings if finding.node_id == _FORM_NODE_ID]


def _single_finding(parameters: dict[str, Any]) -> ValidationFinding:
    findings = _findings(parameters)
    assert len(findings) == 1, findings
    assert findings[0].severity == ValidationSeverity.error
    return findings[0]


def test_valid_form_trigger_has_no_findings_and_no_form_prompt_port_rules() -> None:
    parameters = _parameters(
        _text_field(),
        {
            "type": "dropdown",
            "value_name": "region",
            "label": "Region",
            "options": {"source": "static", "values": [{"display_label": "East", "value": "east"}]},
        },
    )

    assert _findings(parameters) == []


@pytest.mark.parametrize(
    ("parameters", "expected_path", "expected_message"),
    [
        pytest.param(
            {},
            "parameters.form_definition",
            "Field required",
            id="missing-form-definition",
        ),
        pytest.param(
            {"form_definition": {}},
            "parameters.form_definition.fields",
            "Field required",
            id="missing-fields",
        ),
        pytest.param(
            {"form_definition": {"fields": []}},
            "parameters.form_definition.fields",
            "at least 1 item",
            id="empty-fields",
        ),
    ],
)
def test_missing_or_empty_form_definition_is_located_and_not_duplicated(
    parameters: dict[str, Any],
    expected_path: str,
    expected_message: str,
) -> None:
    finding = _single_finding(parameters)

    assert finding.category == ValidationCategory.schema_violation
    assert finding.field_path == expected_path
    assert expected_message in finding.message


@pytest.mark.parametrize(
    ("field", "expected_path", "expected_message"),
    [
        pytest.param(
            {"type": "text", "label": "Answer"},
            "parameters.form_definition.fields.0.value_name",
            "Field required",
            id="missing-value-name",
        ),
        pytest.param(
            {"type": "text", "value_name": "answer"},
            "parameters.form_definition.fields.0.label",
            "Field required",
            id="missing-label",
        ),
        pytest.param(
            _text_field(value_name="has-dash"),
            "parameters.form_definition.fields.0.value_name",
            "String should match pattern",
            id="invalid-value-name",
        ),
        pytest.param(
            _text_field(unexpected_field=True),
            "parameters.form_definition.fields.0.unexpected_field",
            "Extra inputs are not permitted",
            id="nested-extra-field",
        ),
    ],
)
def test_form_field_structure_errors_have_node_and_field_paths(
    field: dict[str, Any],
    expected_path: str,
    expected_message: str,
) -> None:
    finding = _single_finding(_parameters(field))

    assert finding.category == ValidationCategory.schema_violation
    assert finding.field_path == expected_path
    assert expected_message in finding.message


@pytest.mark.parametrize(
    ("field", "expected_message"),
    [
        pytest.param(
            {"type": "unknown_type", "value_name": "reason", "label": "Reason"},
            "Invalid field type 'unknown_type'",
            id="invalid-discriminator",
        ),
        pytest.param(
            {"value_name": "reason", "label": "Reason"},
            "Required property 'type' missing",
            id="missing-discriminator",
        ),
    ],
)
def test_field_discriminator_errors_are_form_trigger_findings(
    field: dict[str, Any],
    expected_message: str,
) -> None:
    finding = _single_finding(_parameters(field))

    assert finding.category == ValidationCategory.form_trigger_configuration
    assert finding.field_path == "parameters.form_definition.fields.0.type"
    assert expected_message in finding.message


def test_invalid_calendar_date_is_reported_at_default_component() -> None:
    field = {
        "type": "date",
        "value_name": "start_date",
        "label": "Start date",
        "default": {"date": "2025-02-30"},
    }

    finding = _single_finding(_parameters(field))

    assert finding.category == ValidationCategory.form_trigger_configuration
    assert finding.field_path == "parameters.form_definition.fields.0.default.date"
    assert "valid ISO 8601 date" in finding.message


def test_invalid_timezone_is_reported_at_default_component() -> None:
    field = {
        "type": "date",
        "value_name": "start_date",
        "label": "Start date",
        "include_timezone": True,
        "default": {"timezone": "Mars/Olympus"},
    }

    finding = _single_finding(_parameters(field))

    assert finding.category == ValidationCategory.form_trigger_configuration
    assert finding.field_path == "parameters.form_definition.fields.0.default.timezone"
    assert "valid IANA timezone" in finding.message


def test_date_component_rules_are_reported_on_the_field() -> None:
    field = {
        "type": "date",
        "value_name": "start_time",
        "label": "Start time",
        "include_date": False,
        "include_time": True,
        "include_timezone": False,
    }

    finding = _single_finding(_parameters(field))

    assert finding.category == ValidationCategory.form_trigger_configuration
    assert finding.field_path == "parameters.form_definition.fields.0"
    assert "include_timezone is required" in finding.message


def test_default_that_fails_submission_coercion_is_reported_at_default() -> None:
    field = {"type": "email", "value_name": "contact", "label": "Contact", "default": "not-an-email"}

    finding = _single_finding(_parameters(field))

    assert finding.category == ValidationCategory.form_trigger_configuration
    assert finding.field_path == "parameters.form_definition.fields.0.default"
    assert "Default value is not valid" in finding.message


@pytest.mark.parametrize(
    ("options", "source"),
    [
        pytest.param(
            {"source": "dynamic", "expression": "regions", "label_key": "name", "value_key": "id"},
            "dynamic",
            id="dynamic",
        ),
        pytest.param(
            {"source": "dynamic_resolved", "values": [{"display_label": "East", "value": "east"}]},
            "dynamic_resolved",
            id="dynamic-resolved",
        ),
    ],
)
def test_non_static_options_are_reported_once_with_option_path(
    options: dict[str, Any],
    source: str,
) -> None:
    field = {"type": "dropdown", "value_name": "region", "label": "Region", "options": options}

    findings = _findings(_parameters(field))

    assert len(findings) == 1, findings
    assert findings[0].category == ValidationCategory.form_trigger_configuration
    assert findings[0].field_path == "parameters.form_definition.fields.0.options"
    assert f"options source '{source}'" in findings[0].message


def test_unsupported_options_do_not_hide_invalid_default() -> None:
    parameters = _parameters(
        {
            "type": "dropdown",
            "value_name": "region",
            "label": "Region",
            "options": {
                "source": "dynamic",
                "expression": "regions",
                "label_key": "name",
                "value_key": "id",
            },
        },
        {"type": "email", "value_name": "contact", "label": "Contact", "default": "not-an-email"},
    )

    findings = _findings(parameters)

    assert len(findings) == 2, findings
    assert {finding.field_path for finding in findings} == {
        "parameters.form_definition.fields.0.options",
        "parameters.form_definition.fields.1.default",
    }
    assert all(finding.category == ValidationCategory.form_trigger_configuration for finding in findings)
    assert any("options source 'dynamic'" in finding.message for finding in findings)
    assert any("Default value is not valid" in finding.message for finding in findings)


def test_unsafe_css_is_reported_on_css_override() -> None:
    finding = _single_finding(_parameters(_text_field(), css_override=".form { background: url(x); }"))

    assert finding.category == ValidationCategory.form_trigger_configuration
    assert finding.field_path == "parameters.css_override"
    assert "url()" in finding.message


def test_template_expression_is_reported_by_save_time_workflow_validation() -> None:
    finding = _single_finding(_parameters(_text_field(label="${upstream.label}")))

    assert finding.category == ValidationCategory.schema_violation
    assert finding.field_path == "parameters.form_definition.fields[0].label"
    assert "no upstream node" in finding.message


def test_builtin_template_expression_is_rejected_on_form_trigger() -> None:
    finding = _single_finding(_parameters(_text_field(), message="${trigger.data}"))

    assert finding.category == ValidationCategory.schema_violation
    assert finding.field_path == "parameters.message"
    assert "${trigger.data}" in finding.message


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        pytest.param("response_window", 30, id="response-window"),
        pytest.param("fallback_decision", "submit", id="fallback-decision"),
        pytest.param("responder_users", ["alice"], id="responder-users"),
        pytest.param("responder_groups", ["operators"], id="responder-groups"),
    ],
)
def test_schema_and_model_reject_each_prompt_only_parameter_once(parameter: str, value: object) -> None:
    finding = _single_finding(_parameters(_text_field(), **{parameter: value}))

    assert finding.category == ValidationCategory.schema_violation
    assert finding.field_path == f"parameters.{parameter}"
    assert "Extra inputs are not permitted" in finding.message


def test_form_trigger_findings_remain_in_authored_field_order() -> None:
    parameters = _parameters(
        {"type": "unknown_first", "value_name": "first", "label": "First"},
        _text_field(value_name="bad-name", label="Second"),
    )

    findings = _findings(parameters)
    field_indices = [
        int(finding.field_path.split("fields.", maxsplit=1)[1].split(".", maxsplit=1)[0])
        for finding in findings
        if finding.field_path is not None and ".fields." in finding.field_path
    ]

    assert field_indices == sorted(field_indices)
