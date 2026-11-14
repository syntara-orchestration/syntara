"""Unit tests for defensive Sub-workflow project-reference validation."""

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from syntara.workflows.models.validation_finding import ValidationCategory, ValidationSeverity
from syntara.workflows.validators import validate_subworkflow_project_references
from syntara.workflows.validators.workflow_subworkflows import _parent_input_type_findings


@pytest.mark.asyncio
@pytest.mark.parametrize("nodes", [None, "not-a-list", {"id": "call_child"}])
async def test_malformed_nodes_are_left_to_definition_validation(nodes: None | str | dict[str, str]) -> None:
    session = AsyncMock()
    workflow_definition: dict[str, Any] = {"nodes": nodes}

    findings = await validate_subworkflow_project_references(
        session,
        workflow_definition,
        uuid4(),
    )

    assert findings == []
    session.exec.assert_not_awaited()


@pytest.mark.asyncio
async def test_template_workflow_id_is_rejected_in_v1() -> None:
    session = AsyncMock()

    findings = await validate_subworkflow_project_references(
        session,
        {
            "nodes": [
                {
                    "id": "call_child",
                    "type": "sub_workflow",
                    "parameters": {
                        "workflow_id": "${parent.child_workflow_id}",
                        "trigger_node_id": "child_trigger",
                    },
                }
            ]
        },
        uuid4(),
    )

    assert len(findings) == 1
    assert findings[0].severity == ValidationSeverity.error
    assert findings[0].category == ValidationCategory.invalid_reference
    assert findings[0].node_id == "call_child"
    assert findings[0].field_path == "parameters.workflow_id"
    session.exec.assert_not_awaited()


def test_parent_child_input_mapping_rejects_known_incompatible_child_output_type() -> None:
    findings = _parent_input_type_findings(
        node_id="consume_release",
        input_mapping={"build_id": "${invoke_release.Result.outputs.release.id}"},
        input_schema={"type": "object", "properties": {"build_id": {"type": "number"}}},
        nodes_by_id={"invoke_release": {"id": "invoke_release", "type": "sub_workflow"}},
        subworkflow_output_schemas={
            "invoke_release": {
                "type": "object",
                "properties": {"release": {"type": "object", "properties": {"id": {"type": "string"}}}},
            }
        },
    )

    assert len(findings) == 1
    assert findings[0].severity == ValidationSeverity.error
    assert findings[0].category == ValidationCategory.schema_violation
    assert findings[0].node_id == "consume_release"
    assert findings[0].field_path == "parameters.input_mapping.build_id"
    assert "source type 'string'" in findings[0].message
    assert "expects 'number'" in findings[0].message


def test_parent_child_input_mapping_accepts_compatible_types_and_skips_unknown_types() -> None:
    nodes_by_id = {"invoke_release": {"id": "invoke_release", "type": "sub_workflow"}}
    findings = _parent_input_type_findings(
        node_id="consume_release",
        input_mapping={
            "build_id": "${invoke_release.Result.outputs.release.id}",
            "payload": "${invoke_release.Result.outputs.release.payload.id}",
        },
        input_schema={
            "type": "object",
            "properties": {"build_id": {"type": "number"}, "payload": {"type": "object"}},
        },
        nodes_by_id=nodes_by_id,
        subworkflow_output_schemas={
            "invoke_release": {
                "type": "object",
                "properties": {
                    "release": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "payload": {"type": "object", "additionalProperties": True},
                        },
                    }
                },
            }
        },
    )

    assert findings == []
