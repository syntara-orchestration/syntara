"""Integration tests for project-scoped LIST filtering (LP-1 through LP-8).

Validates that GET /projects returns only projects the user has project:read
access to, based on their roles and group memberships.
"""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.api.main import app
from syntara.auth.dependencies import get_current_user
from syntara.authz.models import Project, RoleAssignment
from syntara.core.models import User
from syntara.core.models.group import Group, user_groups


def _auth_as(user: User) -> None:
    """Override the current user dependency to act as a user."""

    async def override() -> User:
        return user

    app.dependency_overrides[get_current_user] = override


@pytest.mark.asyncio
async def test_lp1_fresh_user_sees_only_default_project(
    auth_client: AsyncClient,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """LP-1: A user in the users group sees only the default project."""
    fresh_user = await user_factory(username="lp1-fresh", email="lp1@example.com", group_names=["users"])
    _auth_as(fresh_user)

    response = await auth_client.get("/api/v1/projects")
    assert response.status_code == 200
    names = [p["name"] for p in response.json()["resources"]]
    assert names == ["default"]

    _auth_as(test_user)


@pytest.mark.asyncio
async def test_lp2_project_creator_sees_only_their_project(
    auth_client: AsyncClient,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """LP-2: A user who created one project sees only that project (plus default)."""
    creator = await user_factory(username="lp2-creator", email="lp2@example.com", group_names=["users"])
    _auth_as(creator)

    response = await auth_client.post(
        "/api/v1/projects",
        json={"name": "lp2-my-project"},
    )
    assert response.status_code == 201

    response = await auth_client.get("/api/v1/projects")
    assert response.status_code == 200
    names = sorted(p["name"] for p in response.json()["resources"])
    assert "default" in names
    assert "lp2-my-project" in names

    _auth_as(test_user)


@pytest.mark.asyncio
async def test_lp3_user_with_multiple_project_roles_sees_only_those(
    auth_client: AsyncClient,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """LP-3: A user with roles on two projects sees only those two (plus default)."""
    multi_user = await user_factory(username="lp3-multi", email="lp3@example.com", group_names=["users"])
    _auth_as(multi_user)

    # Create two projects (auto-assigned project-admin on each)
    resp1 = await auth_client.post("/api/v1/projects", json={"name": "lp3-alpha"})
    assert resp1.status_code == 201
    resp2 = await auth_client.post("/api/v1/projects", json={"name": "lp3-beta"})
    assert resp2.status_code == 201

    # Create a third project owned by someone else
    _auth_as(test_user)
    resp3 = await auth_client.post("/api/v1/projects", json={"name": "lp3-other"})
    assert resp3.status_code == 201

    # Switch back — multi_user should see default + their two projects
    _auth_as(multi_user)
    response = await auth_client.get("/api/v1/projects")
    assert response.status_code == 200
    names = sorted(p["name"] for p in response.json()["resources"])
    assert names == ["default", "lp3-alpha", "lp3-beta"]

    _auth_as(test_user)


@pytest.mark.asyncio
async def test_lp4_system_auditor_sees_all_projects(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """LP-4: A system auditor (project:read:any at scope=any) sees all projects."""
    from uuid import uuid4

    # Create some projects first
    resp = await auth_client.post("/api/v1/projects", json={"name": "lp4-proj"})
    assert resp.status_code == 201

    # Create auditor user
    auditor = await user_factory(username="lp4-auditor", email="lp4-aud@example.com")

    # Set up auditor group with auditor role
    auditor_group = Group(
        id=uuid4(), name="lp4-auditor-group", description="Auditor group", is_builtin=False, labels={}
    )
    test_db_session.add(auditor_group)
    await test_db_session.flush()
    test_db_session.add(RoleAssignment(id=uuid4(), group_id=auditor_group.id, role_name="auditor"))
    await test_db_session.exec(insert(user_groups).values(user_id=auditor.id, group_id=auditor_group.id))
    await test_db_session.commit()

    _auth_as(auditor)
    response = await auth_client.get("/api/v1/projects")
    assert response.status_code == 200
    names = [p["name"] for p in response.json()["resources"]]
    # Auditor should see at least the default project and lp4-proj
    assert "default" in names
    assert "lp4-proj" in names

    _auth_as(test_user)


@pytest.mark.asyncio
async def test_lp5_system_admin_sees_all_projects(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """LP-5: A system admin sees all projects."""
    from uuid import uuid4

    resp = await auth_client.post("/api/v1/projects", json={"name": "lp5-proj"})
    assert resp.status_code == 201

    admin = await user_factory(username="lp5-admin", email="lp5-adm@example.com")

    admin_group = Group(id=uuid4(), name="lp5-admin-group", description="Admin group", is_builtin=False, labels={})
    test_db_session.add(admin_group)
    await test_db_session.flush()
    test_db_session.add(RoleAssignment(id=uuid4(), group_id=admin_group.id, role_name="admin"))
    await test_db_session.exec(insert(user_groups).values(user_id=admin.id, group_id=admin_group.id))
    await test_db_session.commit()

    _auth_as(admin)
    response = await auth_client.get("/api/v1/projects")
    assert response.status_code == 200
    names = [p["name"] for p in response.json()["resources"]]
    assert "default" in names
    assert "lp5-proj" in names

    _auth_as(test_user)


@pytest.mark.asyncio
async def test_lp6_project_user_can_see_assigned_project(
    auth_client: AsyncClient,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """LP-6: A user assigned project-user role can see that project."""
    resp = await auth_client.post("/api/v1/projects", json={"name": "lp6-proj"})
    assert resp.status_code == 201
    project_id = resp.json()["id"]

    viewer = await user_factory(username="lp6-viewer", email="lp6-v@example.com", group_names=["users"])
    resp = await auth_client.post(
        f"/api/v1/projects/{project_id}/role_assignments",
        json={"principal_id": str(viewer.id), "role_name": "project-user"},
    )
    assert resp.status_code == 201

    _auth_as(viewer)
    response = await auth_client.get("/api/v1/projects")
    assert response.status_code == 200
    names = sorted(p["name"] for p in response.json()["resources"])
    assert "default" in names
    assert "lp6-proj" in names

    _auth_as(test_user)


@pytest.mark.asyncio
async def test_lp7_granting_role_makes_project_visible(
    auth_client: AsyncClient,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """LP-7: Granting a project role makes the project appear in the list."""
    # Create project owned by test_user
    resp = await auth_client.post("/api/v1/projects", json={"name": "lp7-proj"})
    assert resp.status_code == 201
    project_id = resp.json()["id"]

    # Create a fresh user — should see only default
    new_user = await user_factory(username="lp7-new", email="lp7@example.com", group_names=["users"])
    _auth_as(new_user)
    response = await auth_client.get("/api/v1/projects")
    names = [p["name"] for p in response.json()["resources"]]
    assert names == ["default"]

    # Grant project-auditor role
    _auth_as(test_user)
    resp = await auth_client.post(
        f"/api/v1/projects/{project_id}/role_assignments",
        json={"principal_id": str(new_user.id), "role_name": "project-auditor"},
    )
    assert resp.status_code == 201

    # Now the user should see default + the granted project
    _auth_as(new_user)
    response = await auth_client.get("/api/v1/projects")
    names = sorted(p["name"] for p in response.json()["resources"])
    assert "default" in names
    assert "lp7-proj" in names

    _auth_as(test_user)


@pytest.mark.asyncio
async def test_lp8_revoking_role_removes_project_from_list(
    auth_client: AsyncClient,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """LP-8: Revoking a project role removes the project from the list."""
    # Create project
    resp = await auth_client.post("/api/v1/projects", json={"name": "lp8-proj"})
    assert resp.status_code == 201
    project_id = resp.json()["id"]

    # Create user and assign project-auditor
    target = await user_factory(username="lp8-target", email="lp8@example.com", group_names=["users"])
    resp = await auth_client.post(
        f"/api/v1/projects/{project_id}/role_assignments",
        json={"principal_id": str(target.id), "role_name": "project-auditor"},
    )
    assert resp.status_code == 201
    assignment_id = resp.json()["id"]

    # Verify target can see default + the assigned project
    _auth_as(target)
    response = await auth_client.get("/api/v1/projects")
    names = [p["name"] for p in response.json()["resources"]]
    assert "default" in names
    assert "lp8-proj" in names

    # Revoke the role
    _auth_as(test_user)
    resp = await auth_client.delete(f"/api/v1/projects/{project_id}/role_assignments/{assignment_id}")
    assert resp.status_code == 204

    # Target should still see default but no longer the revoked project
    _auth_as(target)
    response = await auth_client.get("/api/v1/projects")
    names = [p["name"] for p in response.json()["resources"]]
    assert "default" in names
    assert "lp8-proj" not in names

    _auth_as(test_user)


@pytest.mark.asyncio
async def test_authenticated_user_gets_default_project_access(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """A user in the users group gets project-user access to the default project."""
    new_user = await user_factory(
        username="default-access-user", email="default-access@example.com", group_names=["users"]
    )

    _auth_as(new_user)

    response = await auth_client.get("/api/v1/projects")
    assert response.status_code == 200
    names = [p["name"] for p in response.json()["resources"]]
    assert "default" in names

    _auth_as(test_user)


@pytest.mark.asyncio
async def test_soft_deleted_default_project_does_not_break_new_user(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """When the default project is soft-deleted, new users can still be created and list projects."""
    # Soft-delete the default project directly in the DB
    default_project = (await test_db_session.exec(select(Project).where(Project.name == "default"))).one()
    default_project.soft_delete(test_user.id)
    test_db_session.add(default_project)
    await test_db_session.commit()

    # Create a new user — should not error
    new_user = await user_factory(username="post-delete-user", email="post-delete@example.com")
    _auth_as(new_user)

    # GET /projects should succeed and not include the deleted default project
    response = await auth_client.get("/api/v1/projects")
    assert response.status_code == 200
    names = [p["name"] for p in response.json()["resources"]]
    assert "default" not in names

    _auth_as(test_user)
