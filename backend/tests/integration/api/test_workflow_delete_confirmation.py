"""API tests for delete confirmation when a workflow is referenced by published parents.

DELETE /workflows/{id} re-checks published references server-side: a referenced workflow
returns 409 (confirmation required, exposing only the count -- never the parents' identities)
unless ``confirm=true`` is passed, while an unreferenced workflow deletes as before.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
from sqlmodel import select

from syntara.workflows.models import Workflow, WorkflowVersion

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


def _referencing_def(child_id: UUID) -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "sub",
                "type": "sub_workflow",
                "parameters": {"workflow_id": str(child_id), "trigger_node_id": "child_trigger", "input_mapping": {}},
            }
        ],
        "edges": [],
    }


def _plain_def() -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": [{"id": "s", "type": "script", "parameters": {"language": "bash", "code": "echo hi"}}],
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
async def test_delete_referenced_requires_confirmation(
    auth_client: AsyncClient, test_db_session: AsyncSession, test_project_id, test_user
) -> None:
    """A referenced workflow returns 409 with the count and no parent details unless confirmed."""
    project_id = UUID(str(test_project_id))
    child = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=project_id,
        definition=_plain_def(),
        name=f"child-{uuid4().hex[:8]}",
    )
    parent_name = f"parent-{uuid4().hex[:8]}"
    parent = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=project_id,
        definition=_referencing_def(child),
        name=parent_name,
    )

    resp = await auth_client.delete(f"/api/v1/workflows/{child}")
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "WORKFLOW_REFERENCED_CONFIRMATION_REQUIRED"
    assert body["referencing_count"] == 1
    # The referencing parent's identity must not leak in the confirmation response.
    assert str(parent) not in resp.text
    assert parent_name not in resp.text

    # Re-read the child with populate_existing instead of expire_all(): expiring the whole
    # session also expires the shared test_user, and the next authenticated request would then
    # lazy-load current_user.id on the async session outside a greenlet (MissingGreenlet).
    assert (
        await test_db_session.scalar(
            select(Workflow).where(Workflow.id == child).execution_options(populate_existing=True)
        )
    ) is not None

    confirmed = await auth_client.delete(f"/api/v1/workflows/{child}?confirm=true")
    assert confirmed.status_code == 204
    # Re-read the child with populate_existing instead of expire_all(): expiring the whole
    # session also expires the shared test_user, and the next authenticated request would then
    # lazy-load current_user.id on the async session outside a greenlet (MissingGreenlet).
    assert (
        await test_db_session.scalar(
            select(Workflow).where(Workflow.id == child).execution_options(populate_existing=True)
        )
    ) is None


@pytest.mark.asyncio
async def test_delete_unreferenced_needs_no_confirmation(
    auth_client: AsyncClient, test_db_session: AsyncSession, test_project_id, test_user
) -> None:
    """An unreferenced workflow deletes without confirmation, preserving prior behavior."""
    project_id = UUID(str(test_project_id))
    lone = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=project_id,
        definition=_plain_def(),
        name=f"lone-{uuid4().hex[:8]}",
    )

    resp = await auth_client.delete(f"/api/v1/workflows/{lone}")
    assert resp.status_code == 204
    test_db_session.expire_all()
    assert await test_db_session.get(Workflow, lone) is None
