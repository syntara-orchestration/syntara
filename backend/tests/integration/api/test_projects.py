"""Integration tests for the projects API and authorization flow.

Covers user stories PT-1 through PT-11 from USER_STORIES.md:
1. Authenticated user creates a project (PT-1)
2. Creator is automatically assigned project-admin with full permissions (PT-2)
3. Project admin grants roles to other users (PT-3, PT-6, PT-7)
4. Non-admin cannot assign roles (PT-5)
5. Role revocation (PT-8)
6. Invalid role name rejected (PT-9)
7. Admin can delete default project (PT-10)
8. Full CRUD lifecycle (PT-11)
"""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import insert
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.api.main import app
from syntara.auth.dependencies import get_current_user
from syntara.authz.resolver import resolve_effective_policies
from syntara.core.models import User
from syntara.core.models.group import Group, user_groups

# ============================================================================
# Helpers
# ============================================================================


def _auth_as(user: User) -> None:
    """Override the current user dependency to act as a user."""

    async def override() -> User:
        return user

    app.dependency_overrides[get_current_user] = override


# ============================================================================
# Tests
# ============================================================================


@pytest.mark.asyncio
async def test_authenticated_user_has_default_policies(
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Every authenticated user gets policies from the 'authenticated' group."""
    policies = await resolve_effective_policies(test_db_session, test_user.id)
    policy_names = {p["name"] for p in policies}

    # The "authenticated" role is assigned to the "authenticated" group,
    # which includes user:read:self, user:update:self, project:create:any
    assert "project:create:any" in policy_names
    assert "user:read:self" in policy_names
    assert "user:update:self" in policy_names


@pytest.mark.asyncio
async def test_create_project_assigns_admin(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Creating a project auto-assigns project-admin to the creator."""
    response = await auth_client.post(
        "/api/v1/projects",
        json={"name": "my-project", "description": "Test project"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "my-project"
    project_id = data["id"]

    # Verify the creator got project-admin
    response = await auth_client.get(f"/api/v1/projects/{project_id}/role_assignments")
    assert response.status_code == 200
    assignments = response.json()["resources"]
    assert len(assignments) == 1
    assert assignments[0]["principal_id"] == str(test_user.id)
    assert assignments[0]["role_name"] == "project-admin"


@pytest.mark.asyncio
async def test_project_admin_grants_roles(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """Project admin can assign project-user and project-auditor roles."""
    # Create a project (test_user becomes project-admin)
    response = await auth_client.post(
        "/api/v1/projects",
        json={"name": "team-project"},
    )
    assert response.status_code == 201
    project_id = response.json()["id"]

    # Create another user
    other_user = await user_factory(username="bob", email="bob@example.com", first_name="Bob")

    # Assign project-user role to bob
    response = await auth_client.post(
        f"/api/v1/projects/{project_id}/role_assignments",
        json={"principal_id": str(other_user.id), "role_name": "project-user"},
    )
    assert response.status_code == 201
    assert response.json()["role_name"] == "project-user"
    assert response.json()["principal_id"] == str(other_user.id)

    # Assign project-auditor role to bob as well
    response = await auth_client.post(
        f"/api/v1/projects/{project_id}/role_assignments",
        json={"principal_id": str(other_user.id), "role_name": "project-auditor"},
    )
    assert response.status_code == 201

    # Verify both assignments exist
    response = await auth_client.get(f"/api/v1/projects/{project_id}/role_assignments")
    assert response.status_code == 200
    assignments = response.json()["resources"]
    # 1 project-admin (creator) + 2 for bob
    assert len(assignments) == 3


@pytest.mark.asyncio
async def test_project_admin_grants_admin_to_another_user(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """Project admin can grant project-admin to another user."""
    response = await auth_client.post(
        "/api/v1/projects",
        json={"name": "shared-project"},
    )
    assert response.status_code == 201
    project_id = response.json()["id"]

    other_user = await user_factory(username="alice", email="alice@example.com", first_name="Alice")

    # Grant project-admin to alice
    response = await auth_client.post(
        f"/api/v1/projects/{project_id}/role_assignments",
        json={"principal_id": str(other_user.id), "role_name": "project-admin"},
    )
    assert response.status_code == 201
    assert response.json()["role_name"] == "project-admin"


@pytest.mark.asyncio
async def test_assigned_user_gets_project_scoped_policies(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """A user assigned a project role gets project-scoped policies in the resolver."""
    response = await auth_client.post(
        "/api/v1/projects",
        json={"name": "scoped-project"},
    )
    assert response.status_code == 201
    project_id = response.json()["id"]
    project_name = response.json()["name"]

    other_user = await user_factory(
        username="carol", email="carol@example.com", first_name="Carol", group_names=["users"]
    )

    # Assign project-user
    response = await auth_client.post(
        f"/api/v1/projects/{project_id}/role_assignments",
        json={"principal_id": str(other_user.id), "role_name": "project-user"},
    )
    assert response.status_code == 201

    # Resolve carol's effective policies
    policies = await resolve_effective_policies(test_db_session, other_user.id)

    # Carol should have global policies from authenticated group
    global_policies = [p for p in policies if p.get("scope") != "project"]
    assert any(p["name"] == "project:create:any" for p in global_policies)

    # Carol should also have project-scoped policies
    project_policies = [p for p in policies if p.get("scope") == "project" and p.get("project") == project_name]
    assert len(project_policies) > 0
    project_policy_names = {p["name"].split("@")[0] for p in project_policies}
    assert "workflow:read:project" in project_policy_names
    assert "workflow:create:project" in project_policy_names
    assert "execution:read:project" in project_policy_names


@pytest.mark.asyncio
async def test_revoke_project_role(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """Project admin can revoke a role assignment."""
    response = await auth_client.post(
        "/api/v1/projects",
        json={"name": "revoke-project"},
    )
    assert response.status_code == 201
    project_id = response.json()["id"]

    other_user = await user_factory(username="dave", email="dave@example.com", first_name="Dave")

    # Assign project-user
    response = await auth_client.post(
        f"/api/v1/projects/{project_id}/role_assignments",
        json={"principal_id": str(other_user.id), "role_name": "project-user"},
    )
    assert response.status_code == 201
    assignment_id = response.json()["id"]

    # Revoke it
    response = await auth_client.delete(f"/api/v1/projects/{project_id}/role_assignments/{assignment_id}")
    assert response.status_code == 204

    # Verify it's gone
    response = await auth_client.get(f"/api/v1/projects/{project_id}/role_assignments")
    assignments = response.json()["resources"]
    user_ids = [a["principal_id"] for a in assignments]
    assert str(other_user.id) not in user_ids


@pytest.mark.asyncio
async def test_invalid_role_name_rejected(
    auth_client: AsyncClient,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """Assigning an invalid role name returns an error."""
    response = await auth_client.post(
        "/api/v1/projects",
        json={"name": "invalid-role-project"},
    )
    assert response.status_code == 201
    project_id = response.json()["id"]

    other_user = await user_factory(username="eve", email="eve@example.com", first_name="Eve")

    response = await auth_client.post(
        f"/api/v1/projects/{project_id}/role_assignments",
        json={"principal_id": str(other_user.id), "role_name": "superadmin"},
    )
    # Should fail — "superadmin" is not an assignable project role
    assert response.status_code >= 400


@pytest.mark.asyncio
async def test_admin_cannot_delete_default_project(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """Default project delete is blocked even for admins (AAP-87623)."""
    from uuid import uuid4

    from sqlmodel import select

    from syntara.authz.models import RoleAssignment
    from syntara.authz.models.project import Project

    # Create an admin user
    admin_user = await user_factory(username="pt10-admin", email="pt10-admin@example.com")

    admin_group = Group(id=uuid4(), name="pt10-admin-group", description="Admin group", is_builtin=False, labels={})
    test_db_session.add(admin_group)
    await test_db_session.flush()
    test_db_session.add(RoleAssignment(id=uuid4(), group_id=admin_group.id, role_name="admin"))
    await test_db_session.exec(insert(user_groups).values(user_id=admin_user.id, group_id=admin_group.id))
    await test_db_session.commit()

    _auth_as(admin_user)

    # Find the default project
    result = await test_db_session.exec(
        select(Project).where(Project.is_default.is_(True))  # type: ignore[attr-defined]
    )
    default_project = result.first()
    assert default_project is not None

    response = await auth_client.delete(f"/api/v1/projects/{default_project.id}")
    assert response.status_code == 403
    body = response.json()
    assert body["detail"] == "Default project cannot be deleted"
    assert body["code"] == "DEFAULT_PROJECT_PROTECTED"
    assert body["title"] == "Default Project Protected"

    await test_db_session.refresh(default_project)
    assert default_project.deleted_at is None
    assert default_project.is_default is True

    _auth_as(test_user)


@pytest.mark.asyncio
async def test_project_crud_lifecycle(
    auth_client: AsyncClient,
    test_user: User,
) -> None:
    """Full CRUD lifecycle: create, read, update, list, delete."""
    # Create
    response = await auth_client.post(
        "/api/v1/projects",
        json={"name": "lifecycle-project", "description": "will be updated"},
    )
    assert response.status_code == 201
    project_id = response.json()["id"]

    # Read
    response = await auth_client.get(f"/api/v1/projects/{project_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "lifecycle-project"

    # Update
    response = await auth_client.patch(
        f"/api/v1/projects/{project_id}",
        json={"description": "updated description"},
    )
    assert response.status_code == 200
    assert response.json()["description"] == "updated description"

    # List (should include this project; test_user has project-admin on it)
    response = await auth_client.get("/api/v1/projects")
    assert response.status_code == 200
    names = [p["name"] for p in response.json()["resources"]]
    assert "lifecycle-project" in names

    # Delete
    response = await auth_client.delete(f"/api/v1/projects/{project_id}")
    assert response.status_code == 204

    # Verify it's gone from the list
    response = await auth_client.get("/api/v1/projects")
    names = [p["name"] for p in response.json()["resources"]]
    assert "lifecycle-project" not in names


@pytest.mark.asyncio
async def test_project_creator_has_full_admin_permissions(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """PT-2: Project creator has full admin permissions for their project."""
    response = await auth_client.post(
        "/api/v1/projects",
        json={"name": "admin-check-project"},
    )
    assert response.status_code == 201
    project_name = response.json()["name"]

    # Resolve effective policies for the creator
    policies = await resolve_effective_policies(test_db_session, test_user.id)

    # Filter to project-scoped policies for this project
    project_policies = [p for p in policies if p.get("scope") == "project" and p.get("project") == project_name]
    assert len(project_policies) > 0

    # Collect all actions from project-scoped policies
    all_actions: set[str] = set()
    for p in project_policies:
        all_actions.update(p["actions"])

    # Creator should have full admin permissions
    expected_actions = {
        "project:read",
        "project:update",
        "project:delete",
        "role-assignment:assign",
        "workflow:read",
        "workflow:create",
        "workflow:update",
        "workflow:delete",
        "execution:read",
        "execution:run",
    }
    for action in expected_actions:
        assert action in all_actions, f"Missing expected admin action: {action}"


@pytest.mark.asyncio
async def test_non_admin_cannot_assign_roles(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """PT-5: Non-admin user cannot assign roles in a project."""
    # Create a project (test_user becomes project-admin)
    response = await auth_client.post(
        "/api/v1/projects",
        json={"name": "restricted-project"},
    )
    assert response.status_code == 201
    project_id = response.json()["id"]

    # Create two other users
    non_admin = await user_factory(username="nonadmin", email="nonadmin@example.com", first_name="Non Admin")
    target_user = await user_factory(username="target", email="target@example.com", first_name="Target")

    # Assign project-user (not admin) to non_admin
    response = await auth_client.post(
        f"/api/v1/projects/{project_id}/role_assignments",
        json={"principal_id": str(non_admin.id), "role_name": "project-user"},
    )
    assert response.status_code == 201

    # Verify non_admin does NOT have role_assignment:assign
    policies = await resolve_effective_policies(test_db_session, non_admin.id)
    project_policies = [p for p in policies if p.get("scope") == "project"]
    all_actions: set[str] = set()
    for p in project_policies:
        all_actions.update(p["actions"])
    assert "role-assignment:assign" not in all_actions

    # Switch auth to non_admin and try to assign a role — should be denied
    _auth_as(non_admin)
    response = await auth_client.post(
        f"/api/v1/projects/{project_id}/role_assignments",
        json={"principal_id": str(target_user.id), "role_name": "project-user"},
    )
    assert response.status_code == 403

    # Restore auth to test_user
    _auth_as(test_user)


@pytest.mark.asyncio
async def test_project_auditor_has_read_only_permissions(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """PT-7: Project auditor has read-only access (no create/update/delete)."""
    response = await auth_client.post(
        "/api/v1/projects",
        json={"name": "auditor-project"},
    )
    assert response.status_code == 201
    project_id = response.json()["id"]
    project_name = response.json()["name"]

    auditor = await user_factory(username="auditor", email="auditor@example.com", first_name="Auditor")

    # Assign project-auditor
    response = await auth_client.post(
        f"/api/v1/projects/{project_id}/role_assignments",
        json={"principal_id": str(auditor.id), "role_name": "project-auditor"},
    )
    assert response.status_code == 201

    # Resolve auditor's effective policies
    policies = await resolve_effective_policies(test_db_session, auditor.id)
    project_policies = [p for p in policies if p.get("scope") == "project" and p.get("project") == project_name]

    all_actions: set[str] = set()
    for p in project_policies:
        all_actions.update(p["actions"])

    # Auditor should have read-only actions
    assert "project:read" in all_actions
    assert "workflow:read" in all_actions
    assert "execution:read" in all_actions

    # Auditor should NOT have write actions
    write_actions = {
        "workflow:create",
        "workflow:update",
        "workflow:delete",
        "execution:run",
        "project:update",
        "project:delete",
        "role-assignment:assign",
    }
    for action in write_actions:
        assert action not in all_actions, f"Auditor should not have: {action}"


@pytest.mark.asyncio
async def test_project_admin_assigns_group_role(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """PT-4: Project admin assigns a role to a group, members inherit access."""
    # Create a project (test_user becomes project-admin)
    response = await auth_client.post(
        "/api/v1/projects",
        json={"name": "group-test-project"},
    )
    assert response.status_code == 201
    project_id = response.json()["id"]
    project_name = response.json()["name"]

    # Create a group "team-leads"
    group = Group(name="team-leads", description="Team leads group", labels={})
    test_db_session.add(group)
    await test_db_session.flush()

    # Create two users and add them to the group
    alice = await user_factory(username="alice", email="alice@example.com", first_name="Alice")
    frank = await user_factory(username="frank", email="frank@example.com", first_name="Frank")

    await test_db_session.exec(insert(user_groups).values(user_id=alice.id, group_id=group.id))
    await test_db_session.exec(insert(user_groups).values(user_id=frank.id, group_id=group.id))
    await test_db_session.commit()

    # Assign project-admin to the group via API
    response = await auth_client.post(
        f"/api/v1/projects/{project_id}/role_assignments",
        json={"group_id": str(group.id), "role_name": "project-admin"},
    )
    assert response.status_code == 201
    assert response.json()["group_id"] == str(group.id)
    assert response.json()["role_name"] == "project-admin"

    # Verify group assignment is listed
    response = await auth_client.get(f"/api/v1/projects/{project_id}/role_assignments?group_id={group.id}")
    assert response.status_code == 200
    assignments = response.json()["resources"]
    assert len(assignments) == 1
    assert assignments[0]["group_id"] == str(group.id)

    # Verify alice inherits project-admin permissions via group membership
    policies = await resolve_effective_policies(test_db_session, alice.id)
    project_policies = [p for p in policies if p.get("scope") == "project" and p.get("project") == project_name]
    all_actions: set[str] = set()
    for p in project_policies:
        all_actions.update(p["actions"])

    expected_admin_actions = {
        "project:read",
        "project:update",
        "project:delete",
        "role-assignment:assign",
        "workflow:read",
        "workflow:create",
        "workflow:update",
        "workflow:delete",
        "execution:read",
        "execution:run",
    }
    for action in expected_admin_actions:
        assert action in all_actions, f"Alice (group member) missing: {action}"

    # Verify frank also inherits the same permissions
    frank_policies = await resolve_effective_policies(test_db_session, frank.id)
    frank_project_policies = [
        p for p in frank_policies if p.get("scope") == "project" and p.get("project") == project_name
    ]
    frank_actions: set[str] = set()
    for p in frank_project_policies:
        frank_actions.update(p["actions"])
    for action in expected_admin_actions:
        assert action in frank_actions, f"Frank (group member) missing: {action}"


@pytest.mark.asyncio
async def test_revoke_group_role_removes_access(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """PT-4 complement: Revoking group role removes project access for members."""
    response = await auth_client.post(
        "/api/v1/projects",
        json={"name": "group-revoke-project"},
    )
    assert response.status_code == 201
    project_id = response.json()["id"]
    project_name = response.json()["name"]

    group = Group(name="temp-team", description="Temporary team", labels={})
    test_db_session.add(group)
    await test_db_session.flush()

    member = await user_factory(username="member", email="member@example.com", first_name="Member")
    await test_db_session.exec(insert(user_groups).values(user_id=member.id, group_id=group.id))
    await test_db_session.commit()

    # Assign and then revoke
    response = await auth_client.post(
        f"/api/v1/projects/{project_id}/role_assignments",
        json={"group_id": str(group.id), "role_name": "project-user"},
    )
    assert response.status_code == 201
    assignment_id = response.json()["id"]

    # Verify member has access
    policies = await resolve_effective_policies(test_db_session, member.id)
    assert any(p.get("scope") == "project" and p.get("project") == project_name for p in policies)

    # Revoke
    response = await auth_client.delete(f"/api/v1/projects/{project_id}/role_assignments/{assignment_id}")
    assert response.status_code == 204

    # Verify member lost project access
    policies = await resolve_effective_policies(test_db_session, member.id)
    assert not any(p.get("scope") == "project" and p.get("project") == project_name for p in policies)
