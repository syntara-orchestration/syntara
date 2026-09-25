"""Unit tests for form prompt node validation rules."""

import pytest

from syntara.workflows.models.validation_finding import ValidationCategory, ValidationSeverity
from syntara.workflows.validators.workflow_definition import WorkflowValidator


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
                    "parameters": {"form_definition": {"type": "object"}},
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
                    "parameters": {"form_definition": {"type": "object"}},
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
                    "parameters": {"form_definition": {"type": "object"}},
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
                    "parameters": {"form_definition": {"type": "object"}},
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
                    "parameters": {"form_definition": {"type": "object"}},
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
                    "parameters": {"form_definition": {"type": "object"}},
                },
                {
                    "id": "form2",
                    "type": "form_prompt",
                    "parameters": {"form_definition": {"type": "object"}},
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
                    "parameters": {"form_definition": {"type": "object"}},
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
                    "parameters": {"form_definition": {"type": "object"}},
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
                    "parameters": {"form_definition": {"type": "object"}},
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
                    "parameters": {"form_definition": {"type": "object"}},
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
                    "parameters": {"form_definition": {"type": "object"}},
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
