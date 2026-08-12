"""Integration tests for user and group role assignment sub-resource endpoints.

Covers:
- POST /api/v1/users/{user_id}/role_assignments
- GET  /api/v1/users/{user_id}/role_assignments
- DELETE /api/v1/users/{user_id}/role_assignments/{assignment_id}
- POST /api/v1/groups/{group_id}/role_assignments
- GET  /api/v1/groups/{group_id}/role_assignments
- DELETE /api/v1/groups/{group_id}/role_assignments/{assignment_id}
"""

from collections.abc import Awaitable, Callable
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.api.main import app
from syntara.auth.dependencies import get_current_user
from syntara.authz.models.assignments import RoleAssignment
from syntara.authz.models.project import Project
from syntara.core.models import User
from syntara.core.models.group import Group

USERS_URL = "/api/v1/users"
GROUPS_URL = "/api/v1/groups"


# ============================================================================
# User role assignment tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_user_role_assignment(
    admin_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """POST /users/{user_id}/role_assignments creates an assignment and returns 201."""
    target_user = await user_factory(username="assign-target", email="assign-target@example.com")

    response = await admin_client.post(
        f"{USERS_URL}/{target_user.id}/role_assignments",
        json={"role_name": "auditor"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["principal_id"] == str(target_user.id)
    assert data["role_name"] == "auditor"
    assert data["principal_name"] == "assign-target"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_list_user_role_assignments(
    admin_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """GET /users/{user_id}/role_assignments lists assignments for a user."""
    target_user = await user_factory(username="list-target", email="list-target@example.com")

    # Create two role assignments for the user
    response = await admin_client.post(
        f"{USERS_URL}/{target_user.id}/role_assignments",
        json={"role_name": "auditor"},
    )
    assert response.status_code == 201

    response = await admin_client.post(
        f"{USERS_URL}/{target_user.id}/role_assignments",
        json={"role_name": "user"},
    )
    assert response.status_code == 201

    # List the assignments
    response = await admin_client.get(f"{USERS_URL}/{target_user.id}/role_assignments")

    assert response.status_code == 200
    data = response.json()
    resources = data["resources"]
    assert len(resources) == 2

    role_names = {r["role_name"] for r in resources}
    assert role_names == {"auditor", "user"}

    # All assignments should be for the target user
    for r in resources:
        assert r["principal_id"] == str(target_user.id)


@pytest.mark.asyncio
async def test_list_user_role_assignments_filter_by_role_name(
    admin_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """GET /users/{user_id}/role_assignments?role_name=... filters correctly."""
    target_user = await user_factory(username="filter-target", email="filter-target@example.com")

    # Create two assignments
    await admin_client.post(
        f"{USERS_URL}/{target_user.id}/role_assignments",
        json={"role_name": "auditor"},
    )
    await admin_client.post(
        f"{USERS_URL}/{target_user.id}/role_assignments",
        json={"role_name": "user"},
    )

    # Filter by role_name
    response = await admin_client.get(
        f"{USERS_URL}/{target_user.id}/role_assignments",
        params={"role_name": "auditor"},
    )

    assert response.status_code == 200
    resources = response.json()["resources"]
    assert len(resources) == 1
    assert resources[0]["role_name"] == "auditor"


@pytest.mark.asyncio
async def test_delete_user_role_assignment(
    admin_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """DELETE /users/{user_id}/role_assignments/{id} revokes and returns 204."""
    target_user = await user_factory(username="delete-target", email="delete-target@example.com")

    # Create an assignment
    response = await admin_client.post(
        f"{USERS_URL}/{target_user.id}/role_assignments",
        json={"role_name": "auditor"},
    )
    assert response.status_code == 201
    assignment_id = response.json()["id"]

    # Delete it
    response = await admin_client.delete(
        f"{USERS_URL}/{target_user.id}/role_assignments/{assignment_id}",
    )
    assert response.status_code == 204

    # Verify it is gone
    response = await admin_client.get(f"{USERS_URL}/{target_user.id}/role_assignments")
    assert response.status_code == 200
    resources = response.json()["resources"]
    assignment_ids = [r["id"] for r in resources]
    assert assignment_id not in assignment_ids


@pytest.mark.asyncio
async def test_delete_user_role_assignment_idor_protection(
    admin_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """DELETE /users/{user_id}/role_assignments/{id} rejects cross-principal deletion.

    An assignment belonging to user_a cannot be deleted via user_b's URL.
    """
    user_a = await user_factory(username="idor-user-a", email="idor-a@example.com")
    user_b = await user_factory(username="idor-user-b", email="idor-b@example.com")

    # Create an assignment for user_a
    response = await admin_client.post(
        f"{USERS_URL}/{user_a.id}/role_assignments",
        json={"role_name": "auditor"},
    )
    assert response.status_code == 201
    assignment_id = response.json()["id"]

    # Try to delete user_a's assignment via user_b's URL
    response = await admin_client.delete(
        f"{USERS_URL}/{user_b.id}/role_assignments/{assignment_id}",
    )
    # The endpoint validates that the assignment belongs to the URL principal
    assert response.status_code == 422

    # Verify user_a's assignment still exists
    response = await admin_client.get(f"{USERS_URL}/{user_a.id}/role_assignments")
    assert response.status_code == 200
    assignment_ids = [r["id"] for r in response.json()["resources"]]
    assert assignment_id in assignment_ids


# ============================================================================
# Group role assignment tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_group_role_assignment(
    admin_client: AsyncClient,
    test_db_session: AsyncSession,
) -> None:
    """POST /groups/{group_id}/role_assignments creates an assignment and returns 201."""
    group = Group(name="role-assign-group", description="Test group for role assignments", labels={})
    test_db_session.add(group)
    await test_db_session.flush()
    await test_db_session.commit()
    await test_db_session.refresh(group)

    response = await admin_client.post(
        f"{GROUPS_URL}/{group.id}/role_assignments",
        json={"role_name": "user"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["group_id"] == str(group.id)
    assert data["role_name"] == "user"
    assert data["principal_name"] == "role-assign-group"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_list_group_role_assignments(
    admin_client: AsyncClient,
    test_db_session: AsyncSession,
) -> None:
    """GET /groups/{group_id}/role_assignments lists assignments for a group."""
    group = Group(name="list-assign-group", description="Test group", labels={})
    test_db_session.add(group)
    await test_db_session.flush()
    await test_db_session.commit()
    await test_db_session.refresh(group)

    # Create two role assignments for the group
    response = await admin_client.post(
        f"{GROUPS_URL}/{group.id}/role_assignments",
        json={"role_name": "user"},
    )
    assert response.status_code == 201

    response = await admin_client.post(
        f"{GROUPS_URL}/{group.id}/role_assignments",
        json={"role_name": "auditor"},
    )
    assert response.status_code == 201

    # List the assignments
    response = await admin_client.get(f"{GROUPS_URL}/{group.id}/role_assignments")

    assert response.status_code == 200
    data = response.json()
    resources = data["resources"]
    assert len(resources) == 2

    role_names = {r["role_name"] for r in resources}
    assert role_names == {"user", "auditor"}

    # All assignments should be for the group
    for r in resources:
        assert r["group_id"] == str(group.id)


@pytest.mark.asyncio
async def test_delete_group_role_assignment(
    admin_client: AsyncClient,
    test_db_session: AsyncSession,
) -> None:
    """DELETE /groups/{group_id}/role_assignments/{id} revokes and returns 204."""
    group = Group(name="delete-assign-group", description="Test group", labels={})
    test_db_session.add(group)
    await test_db_session.flush()
    await test_db_session.commit()
    await test_db_session.refresh(group)

    # Create an assignment
    response = await admin_client.post(
        f"{GROUPS_URL}/{group.id}/role_assignments",
        json={"role_name": "user"},
    )
    assert response.status_code == 201
    assignment_id = response.json()["id"]

    # Delete it
    response = await admin_client.delete(
        f"{GROUPS_URL}/{group.id}/role_assignments/{assignment_id}",
    )
    assert response.status_code == 204

    # Verify it is gone
    response = await admin_client.get(f"{GROUPS_URL}/{group.id}/role_assignments")
    assert response.status_code == 200
    resources = response.json()["resources"]
    assignment_ids = [r["id"] for r in resources]
    assert assignment_id not in assignment_ids


@pytest.mark.asyncio
async def test_delete_group_role_assignment_idor_protection(
    admin_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """DELETE /groups/{group_id}/role_assignments/{id} rejects cross-principal deletion.

    A user-scoped assignment cannot be deleted via a group's URL.
    """
    target_user = await user_factory(username="idor-group-user", email="idor-group@example.com")

    group = Group(name="idor-group", description="Test group", labels={})
    test_db_session.add(group)
    await test_db_session.flush()
    await test_db_session.commit()
    await test_db_session.refresh(group)

    # Create a USER-scoped assignment
    response = await admin_client.post(
        f"{USERS_URL}/{target_user.id}/role_assignments",
        json={"role_name": "auditor"},
    )
    assert response.status_code == 201
    user_assignment_id = response.json()["id"]

    # Try to delete the user assignment via the group's URL
    response = await admin_client.delete(
        f"{GROUPS_URL}/{group.id}/role_assignments/{user_assignment_id}",
    )
    # The endpoint validates the assignment belongs to this group
    assert response.status_code == 422

    # Verify the user assignment still exists
    response = await admin_client.get(f"{USERS_URL}/{target_user.id}/role_assignments")
    assert response.status_code == 200
    assignment_ids = [r["id"] for r in response.json()["resources"]]
    assert user_assignment_id in assignment_ids


# ============================================================================
# XOR invariant tests (global endpoint)
# ============================================================================

ROLE_ASSIGNMENTS_URL = "/api/v1/role_assignments"


@pytest.mark.asyncio
async def test_create_role_assignment_rejects_both_principal_and_group(
    admin_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """POST /role_assignments with both principal_id and group_id returns 422."""
    target_user = await user_factory(username="xor-both-user", email="xor-both@example.com")

    group = Group(name="xor-both-group", description="Test group", labels={})
    test_db_session.add(group)
    await test_db_session.flush()
    await test_db_session.commit()
    await test_db_session.refresh(group)

    response = await admin_client.post(
        ROLE_ASSIGNMENTS_URL,
        json={
            "principal_id": str(target_user.id),
            "group_id": str(group.id),
            "role_name": "user",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_role_assignment_rejects_neither_principal_nor_group(
    admin_client: AsyncClient,
) -> None:
    """POST /role_assignments with neither principal_id nor group_id returns 422."""
    response = await admin_client.post(
        ROLE_ASSIGNMENTS_URL,
        json={"role_name": "user"},
    )
    assert response.status_code == 422


# ============================================================================
# Project name redaction tests
# ============================================================================


@pytest.mark.asyncio
async def test_readable_project_names_shown_in_role_assignments(
    base_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """Project names are shown when the user has project:read via project-user role."""
    user = await user_factory(username="redact-test", email="redact-test@example.com")

    project = Project(id=uuid4(), name="readable-proj", description="", labels={})
    test_db_session.add(project)
    await test_db_session.flush()

    test_db_session.add(
        RoleAssignment(
            principal_id=user.id,
            project_id=project.id,
            role_name="project-user",
        )
    )
    await test_db_session.commit()

    async def override() -> User:
        return user

    app.dependency_overrides[get_current_user] = override

    response = await base_client.get(f"{USERS_URL}/{user.id}/role_assignments")
    assert response.status_code == 200
    resources = response.json()["resources"]

    project_assignments = [r for r in resources if r["project_id"] == str(project.id)]
    assert len(project_assignments) == 1
    assert project_assignments[0]["project_name"] == "readable-proj"


@pytest.mark.asyncio
async def test_admin_sees_all_project_names(
    admin_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """Admin users see project names for all role assignments."""
    user = await user_factory(username="admin-redact", email="admin-redact@example.com")

    project = Project(id=uuid4(), name="admin-visible", description="", labels={})
    test_db_session.add(project)
    await test_db_session.flush()

    test_db_session.add(
        RoleAssignment(
            principal_id=user.id,
            project_id=project.id,
            role_name="project-user",
        )
    )
    await test_db_session.commit()

    response = await admin_client.get(f"{USERS_URL}/{user.id}/role_assignments")
    assert response.status_code == 200
    resources = response.json()["resources"]

    project_assignments = [r for r in resources if r["project_id"] == str(project.id)]
    assert len(project_assignments) == 1
    assert project_assignments[0]["project_name"] == "admin-visible"


@pytest.mark.asyncio
async def test_what_can_i_shows_readable_project_names(
    base_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """what-can-i shows project names for projects the user can read."""
    user = await user_factory(username="whatcan-redact", email="whatcan-redact@example.com")

    project = Project(id=uuid4(), name="whatcan-proj", description="", labels={})
    test_db_session.add(project)
    await test_db_session.flush()

    test_db_session.add(
        RoleAssignment(
            principal_id=user.id,
            project_id=project.id,
            role_name="project-user",
        )
    )
    await test_db_session.commit()

    async def override() -> User:
        return user

    app.dependency_overrides[get_current_user] = override

    # limit=100 to fetch all permissions in one page; pagination is tested separately in WI-5.
    response = await base_client.post("/api/v1/authz/what_can_i", json={"limit": 100})
    assert response.status_code == 200
    permissions = response.json()["resources"]

    project_perms = [p for p in permissions if p["scope"] == "project" and p["project"] == "whatcan-proj"]
    assert len(project_perms) > 0


# ============================================================================
# Builtin assignment protection tests
# ============================================================================


@pytest.mark.asyncio
async def test_revoke_builtin_group_assignment_forbidden(
    admin_client: AsyncClient,
    test_db_session: AsyncSession,
) -> None:
    """DELETE on a seed-level builtin assignment returns 403."""
    result = await test_db_session.exec(
        select(RoleAssignment).where(
            RoleAssignment.is_builtin.is_(True),  # type: ignore[attr-defined]
        )
    )
    builtin_assignment = result.first()
    assert builtin_assignment is not None

    group = await test_db_session.get(Group, builtin_assignment.group_id)
    assert group is not None

    response = await admin_client.delete(
        f"{GROUPS_URL}/{group.id}/role_assignments/{builtin_assignment.id}",
    )
    assert response.status_code == 403
    assert response.json()["code"] == "BUILTIN_PROTECTED"
