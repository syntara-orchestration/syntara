"""Unit tests for direct self-reference validation on sub-workflow steps.

A ``sub_workflow`` step whose ``workflow_id`` is the workflow's own id would make the workflow
invoke itself. Publishing that configuration is rejected and the offending step is named.
"""

from __future__ import annotations

from uuid import uuid4

from syntara.workflows.models.validation_finding import ValidationCategory, ValidationSeverity
from syntara.workflows.validators import validate_self_referencing_subworkflows


def test_self_referencing_step_is_rejected_and_named() -> None:
    wf_id = uuid4()
    definition = {
        "nodes": [
            {"id": "n1", "type": "script", "parameters": {}},
            {
                "id": "call_self",
                "name": "Call myself",
                "type": "sub_workflow",
                "parameters": {"workflow_id": str(wf_id), "trigger_node_id": "t"},
            },
        ]
    }
    findings = validate_self_referencing_subworkflows(definition, wf_id)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == ValidationSeverity.error
    assert finding.category == ValidationCategory.cycle_detected
    assert finding.node_id == "call_self"
    assert "Call myself" in finding.message


def test_step_referencing_a_different_workflow_is_allowed() -> None:
    wf_id = uuid4()
    definition = {
        "nodes": [
            {
                "id": "call_child",
                "type": "sub_workflow",
                "parameters": {"workflow_id": str(uuid4()), "trigger_node_id": "t"},
            }
        ]
    }
    assert validate_self_referencing_subworkflows(definition, wf_id) == []


def test_non_subworkflow_nodes_are_ignored() -> None:
    wf_id = uuid4()
    definition = {"nodes": [{"id": "s", "type": "script", "parameters": {"workflow_id": str(wf_id)}}]}
    assert validate_self_referencing_subworkflows(definition, wf_id) == []


def test_falls_back_to_node_id_when_step_has_no_name() -> None:
    wf_id = uuid4()
    definition = {"nodes": [{"id": "node_42", "type": "sub_workflow", "parameters": {"workflow_id": str(wf_id)}}]}
    findings = validate_self_referencing_subworkflows(definition, wf_id)
    assert len(findings) == 1
    assert "node_42" in findings[0].message
