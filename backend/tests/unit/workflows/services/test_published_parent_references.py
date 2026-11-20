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
