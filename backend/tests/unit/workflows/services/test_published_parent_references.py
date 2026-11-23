"""Unit tests for trigger-scoped published parent workflow references."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.authz.engine import AllowedProjectsResult
from syntara.workflows.models import Workflow, WorkflowVersion
from syntara.workflows.services.workflow_service import WorkflowService


@pytest.mark.asyncio
async def test_published_parent_references_only_include_changed_child_triggers() -> None:
    child_workflow_id = uuid4()
    project_id = uuid4()
    parent_id = uuid4()
    parent_version_id = uuid4()
    actor_id = uuid4()
    parent = Workflow(
        id=parent_id,
        name="parent",
        project_id=project_id,
        created_by=actor_id,
        current_version=1,
        is_enabled=True,
        published_version_id=parent_version_id,
    )
    parent_version = WorkflowVersion(
        id=parent_version_id,
        workflow_id=parent_id,
        version=1,
        schema_version="2.0.0",
        workflow_definition={
            "nodes": [
                {
                    "id": "invoke_a",
                    "name": "Invoke trigger A",
                    "type": "sub_workflow",
                    "parameters": {
                        "workflow_id": str(child_workflow_id),
                        "trigger_node_id": "trigger_a",
                    },
                },
                {
                    "id": "invoke_b",
                    "name": "Invoke trigger B",
                    "type": "sub_workflow",
                    "parameters": {
                        "workflow_id": str(child_workflow_id),
                        "trigger_node_id": "trigger_b",
                    },
                },
            ]
        },
        created_by=actor_id,
    )
    rows = MagicMock()
    rows.all.return_value = [(parent, parent_version)]
    service = WorkflowService.__new__(WorkflowService)
    service.session = AsyncMock()
    service.session.exec.return_value = rows

    references = await service.get_published_parent_references(
        child_workflow_id,
        project_id,
        AllowedProjectsResult(all_projects=True, project_ids=[]),
        {"trigger_a"},
    )

    assert [reference.step_id for reference in references] == ["invoke_a"]


@pytest.mark.asyncio
async def test_published_parent_references_recognizes_an_embedded_origin_reference() -> None:
    """Used-By lists every published parent referencing the child, embedded or hand-authored.

    A copied (embedded) sub-workflow reference is indistinguishable from a hand-authored one in
    the published graph, so Used-By must list every published parent that references the child.
    Scenario (ANSTRAT-2347 embed preserve-references): A references child B; C embeds A and
    preserves the reference to B; both A and C are published. Expected published parents of B
    are {A, C}. get_published_parent_references scans node type + workflow_id, so provenance
    (manual vs embedded) is irrelevant.
    """
    child_b_id = uuid4()
    project_id = uuid4()
    actor_id = uuid4()

    def _parent(name: str) -> tuple[Workflow, WorkflowVersion]:
        wf_id = uuid4()
        ver_id = uuid4()
        workflow = Workflow(
            id=wf_id,
            name=name,
            project_id=project_id,
            created_by=actor_id,
            current_version=1,
            is_enabled=True,
            published_version_id=ver_id,
        )
        version = WorkflowVersion(
            id=ver_id,
            workflow_id=wf_id,
            version=1,
            schema_version="2.0.0",
            workflow_definition={
                "nodes": [
                    {
                        "id": "ref_b",
                        "name": f"{name} invokes B",
                        "type": "sub_workflow",
                        "parameters": {"workflow_id": str(child_b_id), "trigger_node_id": "trigger_main"},
                    }
                ]
            },
            created_by=actor_id,
        )
        return workflow, version

    parent_a = _parent("A")  # hand-authored reference
    parent_c = _parent("C")  # reference arrived via embedding A (identical in the published graph)
    rows = MagicMock()
    rows.all.return_value = [parent_a, parent_c]
    service = WorkflowService.__new__(WorkflowService)
    service.session = AsyncMock()
    service.session.exec.return_value = rows

    references = await service.get_published_parent_references(
        child_b_id,
        project_id,
        AllowedProjectsResult(all_projects=True, project_ids=[]),
        {"trigger_main"},
    )

    assert {reference.workflow_name for reference in references} == {"A", "C"}
    assert [reference.step_id for reference in references] == ["ref_b", "ref_b"]
