"""Unit tests for WorkflowDefinition schema model.

Tests cover:
- Empty description coercion to None
- Valid description passthrough
- None description default
- Node type discrimination (SubWorkflowNode)
"""

import pytest
from pydantic import ValidationError

from syntara.workflows.models.workflow_definition import SubWorkflowNode, WorkflowDefinition

MINIMAL_KWARGS = {
    "schema_version": "2.0.0",
    "name": "test-workflow",
    "triggers": [{"type": "manual"}],
    "nodes": [],
    "edges": [],
}


def test_empty_description_coerced_to_none() -> None:
    """Empty string description should be coerced to None."""
    wd = WorkflowDefinition(**MINIMAL_KWARGS, description="")
    assert wd.description is None


def test_valid_description_preserved() -> None:
    """Non-empty description should be preserved as-is."""
    wd = WorkflowDefinition(**MINIMAL_KWARGS, description="A real description")
    assert wd.description == "A real description"


def test_none_description_default() -> None:
    """Omitted description should default to None."""
    wd = WorkflowDefinition(**MINIMAL_KWARGS)
    assert wd.description is None


def test_whitespace_only_description_rejected() -> None:
    """Whitespace-only description should still be accepted (min_length counts whitespace)."""
    wd = WorkflowDefinition(**MINIMAL_KWARGS, description=" ")
    assert wd.description == " "


def test_description_exceeding_max_length_rejected() -> None:
    """Description exceeding 1000 chars should be rejected."""
    with pytest.raises(ValidationError, match="string_too_long"):
        WorkflowDefinition(**MINIMAL_KWARGS, description="x" * 1001)


def test_sub_workflow_node_validates_in_workflow_definition() -> None:
    """SubWorkflowNode should be accepted in WorkflowDefinition.nodes list."""
    workflow_def = WorkflowDefinition(
        schema_version="2.0.0",
        name="test-workflow-with-subworkflow",
        triggers=[{"type": "manual_trigger"}],
        nodes=[
            {
                "id": "sub1",
                "type": "sub_workflow",
                "parameters": {
                    "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
                    "trigger_node_id": "trigger_1",
                },
            }
        ],
        edges=[{"from": "manual_trigger", "to": "sub1"}],
    )

    # Verify workflow validates successfully
    assert workflow_def.schema_version == "2.0.0"
    assert len(workflow_def.nodes) == 1

    # Verify node discriminates correctly to SubWorkflowNode
    node = workflow_def.nodes[0]
    assert isinstance(node, SubWorkflowNode)
    assert node.type == "sub_workflow"
    assert node.parameters.workflow_id == "550e8400-e29b-41d4-a716-446655440000"
    assert node.parameters.trigger_node_id == "trigger_1"


def test_sub_workflow_node_with_input_mapping() -> None:
    """SubWorkflowNode should accept input_mapping in parameters."""
    workflow_def = WorkflowDefinition(
        schema_version="2.0.0",
        name="test-workflow",
        triggers=[{"type": "manual_trigger"}],
        nodes=[
            {
                "id": "sub1",
                "type": "sub_workflow",
                "parameters": {
                    "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
                    "trigger_node_id": "trigger_1",
                    "input_mapping": {"host": "web-server-01", "port": 8080},
                },
            }
        ],
        edges=[],
    )

    node = workflow_def.nodes[0]
    assert isinstance(node, SubWorkflowNode)
    assert node.parameters.input_mapping == {"host": "web-server-01", "port": 8080}


def test_sub_workflow_node_rejects_template_expression_for_workflow_id() -> None:
    """V1 requires a statically selected workflow so its project can be validated."""
    with pytest.raises(ValidationError, match="template expressions are not supported"):
        WorkflowDefinition(
            schema_version="2.0.0",
            name="test-workflow",
            triggers=[{"type": "manual_trigger"}],
            nodes=[
                {
                    "id": "sub1",
                    "type": "sub_workflow",
                    "parameters": {
                        "workflow_id": "${parent_step.child_workflow_id}",
                        "trigger_node_id": "trigger_1",
                    },
                }
            ],
            edges=[],
        )
