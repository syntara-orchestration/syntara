"""Integration tests for project-scoped workflow LIST filtering (LW-1 through LW-5).

Validates that GET /workflows returns only workflows belonging to projects
the user has workflow:read access to.
"""

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import insert
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.api.main import app
from syntara.auth.dependencies import get_current_user
from syntara.authz.models import RoleAssignment
from syntara.core.models import User
from syntara.core.models.group import Group, user_groups


def _auth_as(user: User) -> None:
    """Override the current user dependency to act as a user."""

    async def override() -> User:
        return user

    app.dependency_overrides[get_current_user] = override


WORKFLOW_DEFINITION: dict[str, Any] = {
    "name": "test",
    "schema_version": "2.0.0",
    "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
    "nodes": [
        {
            "id": "a1",
            "name": "a1",
            "type": "script",
            "parameters": {"language": "python", "code": "print('hi')"},
        }
    ],
    "edges": [{"from": "trigger_manual", "to": "a1"}],
}


async def _create_workflow_in_project(
    client: AsyncClient,
    name: str,
    project_id: str,
) -> str:
    """Create a workflow via API assigned to a project.

    The caller must be authenticated as a user with global workflow:create
    permission (e.g., a user with the 'user' role).

    Returns the workflow ID.
    """
    resp = await client.post(
        "/api/v1/workflows",
        json={"name": name, "project_id": project_id, "workflow_definition": WORKFLOW_DEFINITION},
    )
    assert resp.status_code == 201
    wf_id: str = resp.json()["id"]

    return wf_id


@pytest.mark.asyncio
async def test_lw1_user_sees_only_workflows_in_their_project(
    auth_client: AsyncClient,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """LW-1: User sees only workflows in projects they have access to."""
    # Create two projects as test_user (has global user role)
    resp1 = await auth_client.post("/api/v1/projects", json={"name": "lw1-proj-a"})
    assert resp1.status_code == 201
    proj_a_id = resp1.json()["id"]

    resp2 = await auth_client.post("/api/v1/projects", json={"name": "lw1-proj-b"})
    assert resp2.status_code == 201
    proj_b_id = resp2.json()["id"]

    # Create workflows in each project (as test_user who has global workflow:create)
    await _create_workflow_in_project(auth_client, "lw1-wf-a", proj_a_id)
    await _create_workflow_in_project(auth_client, "lw1-wf-b", proj_b_id)

    # Create scoped_user with access only to proj_a
    scoped_user = await user_factory(username="lw1-scoped", email="lw1@example.com")
    resp = await auth_client.post(
        f"/api/v1/projects/{proj_a_id}/role_assignments",
        json={"principal_id": str(scoped_user.id), "role_name": "project-user"},
    )
    assert resp.status_code == 201

    # scoped_user should see only lw1-wf-a
    _auth_as(scoped_user)
    response = await auth_client.get("/api/v1/workflows")
    assert response.status_code == 200
    wf_names = [w["name"] for w in response.json()["resources"]]
    assert "lw1-wf-a" in wf_names
    assert "lw1-wf-b" not in wf_names

    _auth_as(test_user)


@pytest.mark.asyncio
async def test_lw2_user_with_multiple_projects_sees_workflows_from_all(
    auth_client: AsyncClient,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """LW-2: User with roles on multiple projects sees workflows from all."""
    # Create two projects
    resp1 = await auth_client.post("/api/v1/projects", json={"name": "lw2-alpha"})
    assert resp1.status_code == 201
    proj1_id = resp1.json()["id"]

    resp2 = await auth_client.post("/api/v1/projects", json={"name": "lw2-beta"})
    assert resp2.status_code == 201
    proj2_id = resp2.json()["id"]

    # Create workflows in each
    await _create_workflow_in_project(auth_client, "lw2-wf-alpha", proj1_id)
    await _create_workflow_in_project(auth_client, "lw2-wf-beta", proj2_id)

    # Create a user with access to both projects
    multi_user = await user_factory(username="lw2-multi", email="lw2@example.com")
    for pid in [proj1_id, proj2_id]:
        resp = await auth_client.post(
            f"/api/v1/projects/{pid}/role_assignments",
            json={"principal_id": str(multi_user.id), "role_name": "project-user"},
        )
        assert resp.status_code == 201

    _auth_as(multi_user)
    response = await auth_client.get("/api/v1/workflows")
    assert response.status_code == 200
    wf_names = [w["name"] for w in response.json()["resources"]]
    assert "lw2-wf-alpha" in wf_names
    assert "lw2-wf-beta" in wf_names

    _auth_as(test_user)


@pytest.mark.asyncio
async def test_lw3_global_admin_sees_all_workflows(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """LW-3: Global admin sees all workflows across all projects."""
    # Create two projects with workflows
    resp = await auth_client.post("/api/v1/projects", json={"name": "lw3-proj-a"})
    assert resp.status_code == 201
    proj_a_id = resp.json()["id"]
    await _create_workflow_in_project(auth_client, "lw3-wf-a", proj_a_id)

    resp = await auth_client.post("/api/v1/projects", json={"name": "lw3-proj-b"})
    assert resp.status_code == 201
    proj_b_id = resp.json()["id"]
    await _create_workflow_in_project(auth_client, "lw3-wf-b", proj_b_id)

    # Create an admin user
    admin = await user_factory(username="lw3-admin", email="lw3-adm@example.com")

    admin_group = Group(id=uuid4(), name="lw3-admin-group", description="Admin group", is_builtin=False, labels={})
    test_db_session.add(admin_group)
    await test_db_session.flush()
    test_db_session.add(RoleAssignment(id=uuid4(), group_id=admin_group.id, role_name="admin"))
    await test_db_session.exec(insert(user_groups).values(user_id=admin.id, group_id=admin_group.id))
    await test_db_session.commit()

    _auth_as(admin)
    response = await auth_client.get("/api/v1/workflows")
    assert response.status_code == 200
    wf_names = [w["name"] for w in response.json()["resources"]]
    assert "lw3-wf-a" in wf_names
    assert "lw3-wf-b" in wf_names

    _auth_as(test_user)


@pytest.mark.asyncio
async def test_lw4_user_with_no_workflow_projects_sees_empty(
    auth_client: AsyncClient,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """LW-4: User with project-user role on a project with no workflows sees empty list."""
    # Create a project with no workflows
    resp = await auth_client.post("/api/v1/projects", json={"name": "lw4-empty-proj"})
    assert resp.status_code == 201
    proj_id = resp.json()["id"]

    # Create a user with access to that project
    scoped_user = await user_factory(username="lw4-empty", email="lw4@example.com")
    resp = await auth_client.post(
        f"/api/v1/projects/{proj_id}/role_assignments",
        json={"principal_id": str(scoped_user.id), "role_name": "project-user"},
    )
    assert resp.status_code == 201

    _auth_as(scoped_user)
    response = await auth_client.get("/api/v1/workflows")
    assert response.status_code == 200
    assert response.json()["resources"] == []

    _auth_as(test_user)


@pytest.mark.asyncio
async def test_lw5_workflows_in_other_projects_hidden_from_project_scoped_users(
    auth_client: AsyncClient,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """LW-5: Workflows in other projects are not visible to project-scoped users."""
    # Create two projects with workflows
    resp = await auth_client.post("/api/v1/projects", json={"name": "lw5-proj-a"})
    assert resp.status_code == 201
    proj_a_id = resp.json()["id"]
    await _create_workflow_in_project(auth_client, "lw5-visible", proj_a_id)

    resp = await auth_client.post("/api/v1/projects", json={"name": "lw5-proj-b"})
    assert resp.status_code == 201
    proj_b_id = resp.json()["id"]
    await _create_workflow_in_project(auth_client, "lw5-hidden", proj_b_id)

    # Create a project-only user with access to proj_a only
    proj_user = await user_factory(username="lw5-proj-user", email="lw5@example.com")
    resp = await auth_client.post(
        f"/api/v1/projects/{proj_a_id}/role_assignments",
        json={"principal_id": str(proj_user.id), "role_name": "project-user"},
    )
    assert resp.status_code == 201

    # proj_user should see lw5-visible but NOT lw5-hidden
    _auth_as(proj_user)
    response = await auth_client.get("/api/v1/workflows")
    assert response.status_code == 200
    wf_names = [w["name"] for w in response.json()["resources"]]
    assert "lw5-visible" in wf_names
    assert "lw5-hidden" not in wf_names

    _auth_as(test_user)
