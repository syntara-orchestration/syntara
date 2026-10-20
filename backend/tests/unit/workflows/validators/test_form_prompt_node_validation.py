"""Unit tests for form prompt node validation rules."""

from typing import Any

import pytest

from syntara.workflows.models.validation_finding import ValidationCategory, ValidationFinding, ValidationSeverity
from syntara.workflows.validators.workflow_definition import (
    WorkflowValidator,
    _merge_form_prompt_field_findings_by_index,
)

_VALID_FORM_DEFINITION: dict[str, Any] = {"fields": [{"type": "text", "value_name": "answer", "label": "Answer"}]}


def _workflow_with_form_prompt(
    fields: list[dict[str, Any]],
    *,
    extra_parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a valid graph around form fields and optional prompt parameters."""
    parameters: dict[str, Any] = {"form_definition": {"fields": fields}}
    if extra_parameters:
        parameters.update(extra_parameters)

    return {
        "schema_version": "2.0.0",
        "name": "form-prompt-paths",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {"id": "form", "type": "form_prompt", "parameters": parameters},
            {"id": "consumer", "type": "script", "parameters": {"language": "bash", "code": "echo done"}},
        ],
        "edges": [
            {"from": "trigger", "to": "form"},
            {"from": "form", "to": "consumer", "from_port": "submitted"},
        ],
    }


class TestFormPromptPlacementMatrix:
    """AC-3 placement matrix: form nodes are allowed mid-workflow."""

    def test_immediately_after_trigger(self) -> None:
        """Form node immediately after the trigger."""
        workflow_def = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "form",
                    "type": "form_prompt",
                    "parameters": {"form_definition": _VALID_FORM_DEFINITION},
                },
                {"id": "done", "type": "script", "parameters": {"language": "bash", "code": "echo done"}},
            ],
            "edges": [
                {"from": "trigger", "to": "form"},
                {"from": "form", "to": "done", "from_port": "submitted"},
            ],
        }
        result = WorkflowValidator().collect_findings(workflow_def)
        assert result.is_valid

    def test_mid_chain_between_script_nodes(self) -> None:
        """Form node between two script nodes."""
        workflow_def = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "script1", "type": "script", "parameters": {"language": "bash", "code": "echo 1"}},
                {
                    "id": "form",
                    "type": "form_prompt",
                    "parameters": {"form_definition": _VALID_FORM_DEFINITION},
                },
                {"id": "script2", "type": "script", "parameters": {"language": "bash", "code": "echo 2"}},
            ],
            "edges": [
                {"from": "trigger", "to": "script1"},
                {"from": "script1", "to": "form"},
                {"from": "form", "to": "script2", "from_port": "submitted"},
            ],
        }
        result = WorkflowValidator().collect_findings(workflow_def)
        assert result.is_valid

    def test_as_last_node(self) -> None:
        """Form node as the last node in a workflow."""
        workflow_def = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "setup", "type": "script", "parameters": {"language": "bash", "code": "echo setup"}},
                {
                    "id": "form",
                    "type": "form_prompt",
                    "parameters": {"form_definition": _VALID_FORM_DEFINITION},
                },
                {"id": "done", "type": "script", "parameters": {"language": "bash", "code": "echo done"}},
            ],
            "edges": [
                {"from": "trigger", "to": "setup"},
                {"from": "setup", "to": "form"},
                {"from": "form", "to": "done", "from_port": "submitted"},
            ],
        }
        result = WorkflowValidator().collect_findings(workflow_def)
        assert result.is_valid

    def test_inside_loop_body(self) -> None:
        """Form node inside a for_each loop body."""
        workflow_def = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "loop", "type": "loop", "parameters": {"type": "for_each", "items": "${trigger.list}"}},
                {
                    "id": "form",
                    "type": "form_prompt",
                    "parameters": {"form_definition": _VALID_FORM_DEFINITION},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "loop"},
                {"from": "loop", "to": "form", "from_port": "iterate"},
                {"from": "form", "to": "loop", "from_port": "submitted", "to_port": "iterate"},
            ],
        }
        result = WorkflowValidator().collect_findings(workflow_def)
        assert result.is_valid

    def test_on_condition_true_branch(self) -> None:
        """Form node on the 'true' branch of a condition."""
        workflow_def = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "cond", "type": "condition", "parameters": {"condition": "1 == 1"}},
                {
                    "id": "form",
                    "type": "form_prompt",
                    "parameters": {"form_definition": _VALID_FORM_DEFINITION},
                },
                {"id": "done", "type": "script", "parameters": {"language": "bash", "code": "echo done"}},
            ],
            "edges": [
                {"from": "trigger", "to": "cond"},
                {"from": "cond", "to": "form", "from_port": "true"},
                {"from": "form", "to": "done", "from_port": "submitted"},
            ],
        }
        result = WorkflowValidator().collect_findings(workflow_def)
        assert result.is_valid

    def test_two_forms_in_sequence(self) -> None:
        """Two form nodes in sequence (multi-step form pattern)."""
        workflow_def = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "form1",
                    "type": "form_prompt",
                    "parameters": {"form_definition": _VALID_FORM_DEFINITION},
                },
                {
                    "id": "form2",
                    "type": "form_prompt",
                    "parameters": {"form_definition": _VALID_FORM_DEFINITION},
                },
                {"id": "done", "type": "script", "parameters": {"language": "bash", "code": "echo done"}},
            ],
            "edges": [
                {"from": "trigger", "to": "form1"},
                {"from": "form1", "to": "form2", "from_port": "submitted"},
                {"from": "form2", "to": "done", "from_port": "submitted"},
            ],
        }
        result = WorkflowValidator().collect_findings(workflow_def)
        assert result.is_valid

    def test_feeding_converge(self) -> None:
        """Form node feeding a converge node."""
        workflow_def = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "form",
                    "type": "form_prompt",
                    "parameters": {"form_definition": _VALID_FORM_DEFINITION},
                },
                {"id": "script", "type": "script", "parameters": {"language": "bash", "code": "echo 1"}},
                {"id": "converge", "type": "converge", "parameters": {}},
            ],
            "edges": [
                {"from": "trigger", "to": "form"},
                {"from": "trigger", "to": "script"},
                {"from": "form", "to": "converge", "from_port": "submitted"},
                {"from": "script", "to": "converge"},
            ],
        }
        result = WorkflowValidator().collect_findings(workflow_def)
        assert result.is_valid


class TestFormPromptPlacementNegative:
    """AC-3 negative: form_prompt in triggers[] is rejected."""

    def test_form_prompt_as_trigger_rejected(self) -> None:
        """form_prompt in triggers[] produces a schema violation."""
        workflow_def = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [
                {
                    "id": "form_trigger",
                    "type": "form_prompt",
                    "parameters": {"form_definition": _VALID_FORM_DEFINITION},
                }
            ],
            "nodes": [],
            "edges": [],
        }
        result = WorkflowValidator().collect_findings(workflow_def)
        assert not result.is_valid
        assert any(f.category == ValidationCategory.schema_violation for f in result.findings)


class TestFormPromptPortRules:
    """Port validation rules for form prompt nodes."""

    def test_missing_submitted_port(self) -> None:
        """Error: no successor on 'submitted' port."""
        workflow_def = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "form",
                    "type": "form_prompt",
                    "parameters": {"form_definition": _VALID_FORM_DEFINITION},
                }
            ],
            "edges": [{"from": "trigger", "to": "form"}],
        }
        result = WorkflowValidator().collect_findings(workflow_def)
        assert not result.is_valid
        errors = [f for f in result.findings if f.severity == ValidationSeverity.error]
        assert len(errors) == 1
        assert errors[0].category == ValidationCategory.form_prompt_configuration
        assert "missing a connection from the 'Submitted' branch" in errors[0].message
        assert errors[0].node_id == "form"

    def test_cof_enabled_without_fallback_port(self) -> None:
        """Allowed: COF enabled without a fallback port (will use submitted port on timeout)."""
        workflow_def = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "ok", "type": "script", "parameters": {"language": "bash", "code": "echo ok"}},
                {
                    "id": "form",
                    "type": "form_prompt",
                    "parameters": {"form_definition": _VALID_FORM_DEFINITION},
                    "settings": {"continue_on_failure": True},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "form"},
                {"from": "form", "to": "ok", "from_port": "submitted"},
            ],
        }
        result = WorkflowValidator().collect_findings(workflow_def)
        # Valid - can route to submitted port on timeout if fallback_decision is "submit"
        assert result.is_valid

    def test_fallback_port_exists_but_cof_disabled(self) -> None:
        """Error: fallback port connected but COF disabled (unreachable branch)."""
        workflow_def = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "ok", "type": "script", "parameters": {"language": "bash", "code": "echo ok"}},
                {"id": "fail_handler", "type": "script", "parameters": {"language": "bash", "code": "echo fail"}},
                {
                    "id": "form",
                    "type": "form_prompt",
                    "parameters": {"form_definition": _VALID_FORM_DEFINITION},
                    "settings": {"continue_on_failure": False},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "form"},
                {"from": "form", "to": "ok", "from_port": "submitted"},
                {"from": "form", "to": "fail_handler", "from_port": "fallback"},
            ],
        }
        result = WorkflowValidator().collect_findings(workflow_def)
        assert not result.is_valid
        errors = [f for f in result.findings if f.severity == ValidationSeverity.error]
        fallback_errors = [
            f for f in errors if f.category == ValidationCategory.form_prompt_configuration and "fallback" in f.message
        ]
        assert len(fallback_errors) == 1
        assert "fallback branch will never execute" in fallback_errors[0].message
        assert fallback_errors[0].node_id == "form"
        assert fallback_errors[0].field_path == "settings.continue_on_failure"


class TestFormPromptNoFalsePositives:
    """No false positives on other node types."""

    def test_approval_only_workflow(self) -> None:
        """Workflow with only approval nodes yields no form_prompt_configuration findings."""
        workflow_def = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "approve", "type": "approval", "parameters": {}},
                {"id": "ok", "type": "script", "parameters": {"language": "bash", "code": "echo ok"}},
            ],
            "edges": [
                {"from": "trigger", "to": "approve"},
                {"from": "approve", "to": "ok", "from_port": "approved"},
            ],
        }
        result = WorkflowValidator().collect_findings(workflow_def)
        form_findings = [f for f in result.findings if f.category == ValidationCategory.form_prompt_configuration]
        assert len(form_findings) == 0


class TestFormPromptValidationErrorPath:
    """validate_workflow_definition() raises on schema-invalid form node."""

    def test_invalid_node_raises(self) -> None:
        """Invalid form node raises SafeValueError."""
        from syntara.core.exceptions import SafeValueError

        workflow_def = {
            "schema_version": "2.0.0",
            "name": "test",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "form",
                    "type": "form_prompt",
                    "parameters": {},  # missing required form_definition
                }
            ],
            "edges": [],
        }
        workflow_validator = WorkflowValidator()
        with pytest.raises(SafeValueError):
            workflow_validator.validate_workflow_definition(workflow_def)


class TestFormPromptFindingPaths:
    """Pydantic findings keep parameter and field locations anchored."""

    def test_non_form_definition_parameter_path_keeps_parameters_prefix(self) -> None:
        workflow_def = _workflow_with_form_prompt(
            _VALID_FORM_DEFINITION["fields"],
            extra_parameters={"css_override": ".form { background: url(https://example.test); }"},
        )

        result = WorkflowValidator().collect_findings(workflow_def)

        finding = next(f for f in result.findings if f.node_id == "form")
        assert finding.category == ValidationCategory.form_prompt_configuration
        assert finding.field_path == "parameters.css_override"

    def test_nested_form_field_path_preserves_form_definition_segment(self) -> None:
        workflow_def = _workflow_with_form_prompt([{"type": "text", "value_name": "bad name", "label": "Answer"}])

        result = WorkflowValidator().collect_findings(workflow_def)

        finding = next(f for f in result.findings if f.node_id == "form")
        assert finding.category == ValidationCategory.schema_violation
        assert finding.field_path == "parameters.form_definition.fields.0.value_name"

    def test_value_name_containing_default_does_not_change_field_path(self) -> None:
        workflow_def = _workflow_with_form_prompt(
            [
                {
                    "type": "date",
                    "value_name": "default_region",
                    "label": "When",
                    "include_date": False,
                    "include_time": False,
                    "include_timezone": False,
                }
            ]
        )

        result = WorkflowValidator().collect_findings(workflow_def)

        finding = next(f for f in result.findings if f.node_id == "form")
        assert finding.category == ValidationCategory.form_prompt_configuration
        assert finding.field_path == "parameters.form_definition.fields.0"

    def test_form_definition_error_points_to_invalid_default(self) -> None:
        workflow_def = _workflow_with_form_prompt(
            [
                {"type": "text", "value_name": "answer", "label": "Answer"},
                {"type": "email", "value_name": "contact", "label": "Contact", "default": "not-an-email"},
            ]
        )

        result = WorkflowValidator().collect_findings(workflow_def)

        finding = next(f for f in result.findings if f.node_id == "form")
        assert finding.category == ValidationCategory.form_prompt_configuration
        assert finding.field_path == "parameters.form_definition.fields.1.default"

    def test_field_findings_are_ordered_without_reordering_non_field_findings(self) -> None:
        def field_finding(index: int) -> ValidationFinding:
            return ValidationFinding(
                severity=ValidationSeverity.error,
                category=ValidationCategory.schema_violation,
                message=f"field-{index}",
                node_id="form",
                field_path=f"parameters.form_definition.fields.{index}.label",
            )

        findings = [
            field_finding(2),
            ValidationFinding(
                severity=ValidationSeverity.warning,
                category=ValidationCategory.form_prompt_configuration,
                message="prompt warning",
                node_id="form",
                field_path="parameters.response_window",
            ),
            field_finding(0),
            ValidationFinding(
                severity=ValidationSeverity.error,
                category=ValidationCategory.schema_violation,
                message="workflow error",
            ),
            field_finding(1),
        ]

        merged = _merge_form_prompt_field_findings_by_index(findings)

        assert [finding.message for finding in merged] == [
            "field-0",
            "prompt warning",
            "field-1",
            "workflow error",
            "field-2",
        ]

    def test_dynamic_resolved_source_schema_and_model_errors_are_deduplicated(self) -> None:
        workflow_def = _workflow_with_form_prompt(
            [
                {
                    "type": "dropdown",
                    "value_name": "choice",
                    "label": "Choice",
                    "options": {
                        "source": "dynamic_resolved",
                        "values": [{"display_label": "Choice", "value": "choice"}],
                    },
                }
            ]
        )

        result = WorkflowValidator().collect_findings(workflow_def)

        form_findings = [finding for finding in result.findings if finding.node_id == "form"]
        assert len(form_findings) == 1
        assert form_findings[0].category == ValidationCategory.form_prompt_configuration
        assert form_findings[0].field_path == "parameters.form_definition.fields.0.options"

    def test_missing_form_definition_schema_and_model_errors_are_deduplicated(self) -> None:
        workflow_def = _workflow_with_form_prompt(_VALID_FORM_DEFINITION["fields"])
        del workflow_def["nodes"][0]["parameters"]["form_definition"]

        result = WorkflowValidator().collect_findings(workflow_def)

        form_findings = [finding for finding in result.findings if finding.node_id == "form"]
        assert len(form_findings) == 1
        assert form_findings[0].category == ValidationCategory.schema_violation
        assert form_findings[0].field_path == "parameters.form_definition"


@pytest.mark.parametrize(
    ("field", "expected_message"),
    [
        pytest.param(
            {"type": "unknown_type", "value_name": "reason", "label": "Reason"},
            "Invalid field type 'unknown_type'",
            id="unknown-type",
        ),
        pytest.param(
            {"value_name": "reason", "label": "Reason"},
            "Required property 'type' missing",
            id="missing-type",
        ),
    ],
)
def test_collect_findings_reports_form_prompt_field_type_errors(
    field: dict[str, str],
    expected_message: str,
) -> None:
    """Unknown or missing field types become safe, node-attributed findings."""
    workflow_def = {
        "schema_version": "2.0.0",
        "name": "invalid-form-field-type",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "form_prompt",
                "type": "form_prompt",
                "parameters": {
                    "form_definition": {"fields": [field]},
                    "response_window": 30,
                },
            },
            {"id": "consumer", "type": "script", "parameters": {"language": "bash", "code": "echo done"}},
        ],
        "edges": [
            {"from": "trigger", "to": "form_prompt"},
            {"from": "form_prompt", "to": "consumer", "from_port": "submitted"},
        ],
    }

    result = WorkflowValidator().collect_findings(workflow_def)

    assert result.is_valid is False
    finding = next(f for f in result.findings if f.node_id == "form_prompt")
    assert finding.severity == ValidationSeverity.error
    assert finding.category == ValidationCategory.form_prompt_configuration
    assert finding.field_path == "parameters.form_definition.fields.0.type"
    assert expected_message in finding.message
