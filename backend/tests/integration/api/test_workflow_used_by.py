"""API tests for GET /workflows/{workflow_id}/used_by.

Verifies the endpoint is wired and returns the Used-By contract (``referencing_parent_count`` plus the
``resources`` page), and that access to a target that cannot be read is rejected by the standard
``_wf_perm_read`` gate. RBAC filtering of the parent list and non-disclosure of hidden parents are
covered at the service layer in ``tests/integration/workflows/services/test_workflow_used_by.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest

from syntara.workflows.models import Workflow, WorkflowVersion

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User


def _referencing_def(child_id: UUID) -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "sub",
                "type": "sub_workflow",
                "parameters": {
                    "workflow_id": str(child_id),
                    "trigger_node_id": "child_trigger",
                    "input_mapping": {},
                },
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
async def test_used_by_returns_referencing_parent(
    admin_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_project_id: str
) -> None:
    """GET /used_by returns the published parent that references the target, with referencing_parent_count."""
    project_id = UUID(test_project_id)
    child = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=project_id,
        definition=_plain_def(),
        name=f"child-{uuid4().hex[:8]}",
    )
    parent = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=project_id,
        definition=_referencing_def(child),
        name=f"parent-{uuid4().hex[:8]}",
    )

    resp = await admin_client.get(f"/api/v1/workflows/{child}/used_by")

    assert resp.status_code == 200
    body = resp.json()
    assert body["referencing_parent_count"] == 1
    assert str(parent) in [r["id"] for r in body["resources"]]


@pytest.mark.asyncio
async def test_used_by_unknown_target_is_rejected(admin_client: AsyncClient) -> None:
    """A target workflow that cannot be read is rejected by the _wf_perm_read gate."""
    resp = await admin_client.get(f"/api/v1/workflows/{uuid4()}/used_by")

    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_used_by_existing_inaccessible_target_is_rejected(
    admin_client: AsyncClient,
    auth_as: Callable[[User], None],
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: str,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """An existing target in a project the caller cannot read is rejected, not disclosed.

    Distinguishes target-workflow authorization (resource-level ``_wf_perm_read``) from the
    aggregate disclosure of inaccessible *parents*: the ANSTRAT permits the latter but not a
    Used-By response for a target the caller may not read.
    """
    from syntara.authz.models import RoleAssignment
    from syntara.authz.models.project import Project

    here = UUID(test_project_id)
    other = Project(name=f"other-{uuid4().hex[:8]}", created_by=test_user.id)
    test_db_session.add(other)
    await test_db_session.commit()

    # Target exists, but in a project the scoped caller cannot read.
    target = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=other.id,
        definition=_plain_def(),
        name=f"target-{uuid4().hex[:8]}",
    )

    scoped = await user_factory(username=f"scoped-{uuid4().hex[:6]}", email=f"scoped-{uuid4().hex[:6]}@example.com")
    test_db_session.add(RoleAssignment(principal_id=scoped.id, project_id=here, role_name="project-user"))
    await test_db_session.commit()

    auth_as(scoped)
    resp = await admin_client.get(f"/api/v1/workflows/{target}/used_by")

    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_used_by_rbac_counts_all_but_lists_only_visible(
    admin_client: AsyncClient,
    auth_as: Callable[[User], None],
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: str,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """Two parents reference the child; a caller who can see only one gets referencing_parent_count=2 and one item."""
    from syntara.authz.models import RoleAssignment
    from syntara.authz.models.project import Project

    here = UUID(test_project_id)
    other = Project(name=f"other-{uuid4().hex[:8]}", created_by=test_user.id)
    test_db_session.add(other)
    await test_db_session.commit()

    child = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=here,
        definition=_plain_def(),
        name=f"child-{uuid4().hex[:8]}",
    )
    visible = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=here,
        definition=_referencing_def(child),
        name=f"visible-{uuid4().hex[:8]}",
    )
    hidden = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=other.id,
        definition=_referencing_def(child),
        name=f"hidden-{uuid4().hex[:8]}",
    )

    # The caller may read only the child's project, so it can view the target and the visible parent.
    scoped = await user_factory(username=f"scoped-{uuid4().hex[:6]}", email=f"scoped-{uuid4().hex[:6]}@example.com")
    test_db_session.add(RoleAssignment(principal_id=scoped.id, project_id=here, role_name="project-user"))
    await test_db_session.commit()

    auth_as(scoped)
    resp = await admin_client.get(f"/api/v1/workflows/{child}/used_by")

    assert resp.status_code == 200
    body = resp.json()
    assert body["referencing_parent_count"] == 2  # both referencing parents counted
    ids = {r["id"] for r in body["resources"]}
    assert ids == {str(visible)}  # only the parent in a project the caller can view
    assert str(hidden) not in ids


def _referencing_def_trigger(child_id: UUID, trigger_node_id: str) -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "sub",
                "type": "sub_workflow",
                "parameters": {
                    "workflow_id": str(child_id),
                    "trigger_node_id": trigger_node_id,
                    "input_mapping": {},
                },
            }
        ],
        "edges": [],
    }


@pytest.mark.asyncio
async def test_used_by_counts_batch_returns_totals(
    admin_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_project_id: str
) -> None:
    """GET /workflows/used_by_counts returns per-workflow unfiltered totals in one request."""
    project_id = UUID(test_project_id)
    child_a = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=project_id,
        definition=_plain_def(),
        name=f"ca-{uuid4().hex[:8]}",
    )
    child_b = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=project_id,
        definition=_plain_def(),
        name=f"cb-{uuid4().hex[:8]}",
    )
    for _ in range(2):
        await _publish(
            test_db_session,
            created_by=test_user.id,
            project_id=project_id,
            definition=_referencing_def(child_a),
            name=f"pa-{uuid4().hex[:8]}",
        )
    await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=project_id,
        definition=_referencing_def(child_b),
        name=f"pb-{uuid4().hex[:8]}",
    )

    resp = await admin_client.get(f"/api/v1/workflows/used_by_counts?workflow_ids={child_a}&workflow_ids={child_b}")

    assert resp.status_code == 200
    counts = {c["workflow_id"]: c["referencing_parent_count"] for c in resp.json()["counts"]}
    assert counts[str(child_a)] == 2
    assert counts[str(child_b)] == 1


@pytest.mark.asyncio
async def test_used_by_counts_batch_omits_workflows_outside_visibility(
    admin_client: AsyncClient,
    auth_as: Callable[[User], None],
    test_db_session: AsyncSession,
    test_user: User,
    test_project_id: str,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """Batch counts omit a workflow the caller cannot read instead of disclosing its total."""
    from syntara.authz.models import RoleAssignment
    from syntara.authz.models.project import Project

    here = UUID(test_project_id)
    other = Project(name=f"other-{uuid4().hex[:8]}", created_by=test_user.id)
    test_db_session.add(other)
    await test_db_session.commit()

    here_child = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=here,
        definition=_plain_def(),
        name=f"here-{uuid4().hex[:8]}",
    )
    hidden_child = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=other.id,
        definition=_plain_def(),
        name=f"hidden-{uuid4().hex[:8]}",
    )
    await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=here,
        definition=_referencing_def(here_child),
        name=f"ph-{uuid4().hex[:8]}",
    )
    await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=other.id,
        definition=_referencing_def(hidden_child),
        name=f"phid-{uuid4().hex[:8]}",
    )

    scoped = await user_factory(username=f"scoped-{uuid4().hex[:6]}", email=f"scoped-{uuid4().hex[:6]}@example.com")
    test_db_session.add(RoleAssignment(principal_id=scoped.id, project_id=here, role_name="project-user"))
    await test_db_session.commit()

    auth_as(scoped)
    resp = await admin_client.get(
        f"/api/v1/workflows/used_by_counts?workflow_ids={here_child}&workflow_ids={hidden_child}"
    )

    assert resp.status_code == 200
    counts = {c["workflow_id"]: c["referencing_parent_count"] for c in resp.json()["counts"]}
    assert counts.get(str(here_child)) == 1
    assert str(hidden_child) not in counts


@pytest.mark.asyncio
async def test_used_by_trigger_node_id_filter(
    admin_client: AsyncClient, test_db_session: AsyncSession, test_user: User, test_project_id: str
) -> None:
    """GET /used_by?trigger_node_id=... returns only parents invoking that specific child trigger."""
    project_id = UUID(test_project_id)
    child = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=project_id,
        definition=_plain_def(),
        name=f"child-{uuid4().hex[:8]}",
    )
    parent_a = await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=project_id,
        definition=_referencing_def_trigger(child, "trig_a"),
        name=f"pa-{uuid4().hex[:8]}",
    )
    await _publish(
        test_db_session,
        created_by=test_user.id,
        project_id=project_id,
        definition=_referencing_def_trigger(child, "trig_b"),
        name=f"pb-{uuid4().hex[:8]}",
    )

    resp = await admin_client.get(f"/api/v1/workflows/{child}/used_by?trigger_node_ids=trig_a")

    assert resp.status_code == 200
    body = resp.json()
    assert body["referencing_parent_count"] == 1
    assert {r["id"] for r in body["resources"]} == {str(parent_a)}


@pytest.mark.asyncio
async def test_used_by_counts_rejects_more_than_100_ids(admin_client: AsyncClient) -> None:
    """The batch counts endpoint caps workflow_ids at 100 (422 beyond the limit)."""
    query = "&".join(f"workflow_ids={uuid4()}" for _ in range(101))
    resp = await admin_client.get(f"/api/v1/workflows/used_by_counts?{query}")
    assert resp.status_code == 422
