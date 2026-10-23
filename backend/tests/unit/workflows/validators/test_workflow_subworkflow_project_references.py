"""Unit tests for defensive Sub-workflow project-reference validation."""

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from syntara.workflows.models.validation_finding import ValidationCategory, ValidationSeverity
from syntara.workflows.validators import validate_subworkflow_project_references


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
