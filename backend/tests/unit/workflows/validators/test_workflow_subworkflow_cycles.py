"""Unit tests for Sub-workflow dependency cycle detection."""

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from syntara.workflows.models.validation_finding import ValidationCategory, ValidationSeverity
from syntara.workflows.validators.workflow_subworkflow_cycles import (
    _cycle_findings,
    _DependencyEdge,
    validate_subworkflow_dependency_cycles,
)


def _definition_with_self_reference(
    workflow_id: str,
    *,
    reachable: bool = True,
    selected_trigger_id: str = "entry",
) -> dict[str, object]:
    return {
        "triggers": [
            {"id": "entry", "type": "subworkflow_trigger", "parameters": {}},
            {"id": "alternate", "type": "subworkflow_trigger", "parameters": {}},
        ],
        "nodes": [
            {
                "id": "call_self",
                "type": "sub_workflow",
                "parameters": {"workflow_id": workflow_id, "trigger_node_id": selected_trigger_id},
            }
        ],
        "edges": [{"from": "entry", "to": "call_self"}] if reachable else [],
    }


@pytest.mark.asyncio
async def test_detects_direct_self_reference() -> None:
    workflow_id = uuid4()

    findings = await validate_subworkflow_dependency_cycles(
        AsyncMock(),
        _definition_with_self_reference(str(workflow_id)),
        uuid4(),
        workflow_id,
    )

    assert len(findings) == 1
    assert findings[0].severity == ValidationSeverity.error
    assert findings[0].category == ValidationCategory.invalid_reference
    assert findings[0].node_id == "call_self"
    assert findings[0].field_path == "parameters.workflow_id"
    assert "cycle detected" in findings[0].message.lower()
    assert "redirect this Sub-workflow step" in findings[0].message


@pytest.mark.asyncio
async def test_ignores_unreachable_subworkflow_nodes() -> None:
    workflow_id = uuid4()

    findings = await validate_subworkflow_dependency_cycles(
        AsyncMock(),
        _definition_with_self_reference(str(workflow_id), reachable=False),
        uuid4(),
        workflow_id,
    )

    assert findings == []


@pytest.mark.asyncio
async def test_selected_trigger_contexts_are_not_treated_as_the_same_node() -> None:
    workflow_id = uuid4()

    findings = await validate_subworkflow_dependency_cycles(
        AsyncMock(),
        _definition_with_self_reference(str(workflow_id), selected_trigger_id="alternate"),
        uuid4(),
        workflow_id,
    )

    assert findings == []


def test_long_dependency_chain_is_checked_without_python_recursion() -> None:
    contexts: list[tuple[UUID | None, str]] = [(uuid4(), f"trigger-{index}") for index in range(1200)]
    graph = {
        context: [_DependencyEdge(contexts[index + 1], f"call-{index}")] for index, context in enumerate(contexts[:-1])
    }
    graph[contexts[-1]] = []

    assert _cycle_findings(graph, [contexts[0]]) == []
