"""API tests for the publish confirmation gate on Subworkflow Trigger removal.

Publishing a version that removes a Subworkflow Trigger still invoked by published parents returns
409 (confirmation required, exposing only the affected count) unless ``confirm=true`` is passed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest

from syntara.workflows.error_handlers import WorkflowPublishTriggerRemovalConfirmationProblem
from syntara.workflows.models import Workflow, WorkflowVersion

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


def _def_with_triggers(trigger_ids: list[str]) -> dict[str, Any]:
    triggers: list[dict[str, Any]] = [{"id": "manual1", "type": "manual_trigger", "parameters": {}}]
    triggers += [{"id": tid, "type": "subworkflow_trigger", "parameters": {}} for tid in trigger_ids]
    return {
        "schema_version": "2.0.0",
        "name": "trigger-removal-test",
        "triggers": triggers,
        "nodes": [{"id": "s", "type": "script", "parameters": {"language": "bash", "code": "echo hi"}}],
        "edges": [{"from": "manual1", "to": "s"}],
    }


def _referencing_def(child_id: UUID, trigger_node_id: str) -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": "manual1", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "sub",
                "type": "sub_workflow",
                "parameters": {"workflow_id": str(child_id), "trigger_node_id": trigger_node_id, "input_mapping": {}},
            }
        ],
        "edges": [],
    }


async def _publish(
    session: AsyncSession, *, created_by: UUID, project_id: UUID, definition: dict[str, Any], name: str
) -> UUID:
    workflow_id = uuid4()
    session.add(Workflow(id=workflow_id, name=name, created_by=created_by, project_id=project_id))
    await session.flush()
    version_id = uuid4()
    session.add(
        WorkflowVersion(
            id=version_id,
            workflow_id=workflow_id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=definition,
            created_by=created_by,
        )
    )
    await session.flush()
    workflow = await session.get(Workflow, workflow_id)
    assert workflow is not None
    workflow.is_enabled = True
    workflow.published_version_id = version_id
    await session.commit()
    return workflow_id


@pytest.mark.asyncio
async def test_publish_removing_referenced_trigger_requires_confirmation(
    admin_client: AsyncClient, test_db_session: AsyncSession, test_user, test_project_id
) -> None:
    """Publishing a version that drops a referenced trigger returns 409 with only the count."""
    project_id = UUID(str(test_project_id))

    # Child: v1 (published) has subworkflow trigger T1; v2 (draft) drops it.
    child_id = uuid4()
    test_db_session.add(
        Workflow(id=child_id, name=f"child-{uuid4().hex[:8]}", created_by=test_user.id, project_id=project_id)
    )
    await test_db_session.flush()
    v1_id = uuid4()
    test_db_session.add(
        WorkflowVersion(
            id=v1_id,
            workflow_id=child_id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=_def_with_triggers(["T1"]),
            created_by=test_user.id,
        )
    )
    test_db_session.add(
        WorkflowVersion(
            id=uuid4(),
            workflow_id=child_id,
            version=2,
            schema_version="2.0.0",
            workflow_definition=_def_with_triggers([]),
            created_by=test_user.id,
        )
    )
    await test_db_session.flush()
    child = await test_db_session.get(Workflow, child_id)
    assert child is not None
    child.is_enabled = True
    child.published_version_id = v1_id
    await test_db_session.commit()

    parent_name = f"parent-{uuid4().hex[:8]}"
    parent = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=project_id,
        definition=_referencing_def(child_id, "T1"),
        name=parent_name,
    )

    resp = await admin_client.post(f"/api/v1/workflows/{child_id}/versions/2/publish", json={})
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "WORKFLOW_PUBLISH_TRIGGER_REMOVAL_CONFIRMATION_REQUIRED"
    assert body["affected_count"] == 1
    assert resp.headers["content-type"].startswith("application/problem+json")
    # Conforms to the specialized schema (detects a missing/renamed count field or wrong code).
    WorkflowPublishTriggerRemovalConfirmationProblem.model_validate(body)
    assert str(parent) not in resp.text
    assert parent_name not in resp.text

    confirmed = await admin_client.post(f"/api/v1/workflows/{child_id}/versions/2/publish?confirm=true", json={})
    assert confirmed.status_code == 200


@pytest.mark.asyncio
async def test_publish_without_trigger_removal_needs_no_confirmation(
    admin_client: AsyncClient, test_db_session: AsyncSession, test_user, test_project_id
) -> None:
    """Publishing a version that removes no referenced trigger proceeds without confirmation."""
    project_id = UUID(str(test_project_id))
    child_id = uuid4()
    test_db_session.add(
        Workflow(id=child_id, name=f"child-{uuid4().hex[:8]}", created_by=test_user.id, project_id=project_id)
    )
    await test_db_session.flush()
    v1_id = uuid4()
    test_db_session.add(
        WorkflowVersion(
            id=v1_id,
            workflow_id=child_id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=_def_with_triggers(["T1"]),
            created_by=test_user.id,
        )
    )
    # v2 keeps T1 (no removal).
    test_db_session.add(
        WorkflowVersion(
            id=uuid4(),
            workflow_id=child_id,
            version=2,
            schema_version="2.0.0",
            workflow_definition=_def_with_triggers(["T1"]),
            created_by=test_user.id,
        )
    )
    await test_db_session.flush()
    child = await test_db_session.get(Workflow, child_id)
    assert child is not None
    child.is_enabled = True
    child.published_version_id = v1_id
    await test_db_session.commit()

    await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=project_id,
        definition=_referencing_def(child_id, "T1"),
        name=f"parent-{uuid4().hex[:8]}",
    )

    resp = await admin_client.post(f"/api/v1/workflows/{child_id}/versions/2/publish", json={})
    assert resp.status_code == 200
