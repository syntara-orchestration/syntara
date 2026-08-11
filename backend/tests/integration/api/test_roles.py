"""Integration tests for the roles CRUD API.

Covers:
- Full CRUD lifecycle (create, read, list, update, delete)
- Policy name validation on create/update
- Builtin protection (cannot update or delete builtins)
- Name conflict handling (409)
- Authorization enforcement (403 for unauthorized users)
"""

from collections.abc import Awaitable, Callable
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models.role import Role
from syntara.core.models import User
from tests.integration.api.conftest import make_admin, make_user_role

# ============================================================================
# CRUD Lifecycle
# ============================================================================


@pytest.mark.asyncio
async def test_role_crud_lifecycle(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Full CRUD lifecycle: create, read, list, update, delete."""
    await make_admin(test_db_session, test_user)

    # Create
    response = await auth_client.post(
        "/api/v1/roles",
        json={
            "name": "custom-reviewer",
            "description": "Code reviewer role",
            "policies": ["workflow:read:any", "execution:read:any"],
            "labels": {"team": "platform"},
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "custom-reviewer"
    assert data["description"] == "Code reviewer role"
    assert data["is_builtin"] is False
    assert "workflow:read:any" in data["policies"]
    assert data["labels"] == {"team": "platform"}
    role_id = data["id"]

    # Read
    response = await auth_client.get(f"/api/v1/roles/{role_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "custom-reviewer"

    # List
    response = await auth_client.get("/api/v1/roles")
    assert response.status_code == 200
    body = response.json()
    names = [r["name"] for r in body["resources"]]
    assert "custom-reviewer" in names

    # Update
    response = await auth_client.patch(
        f"/api/v1/roles/{role_id}",
        json={"description": "Updated reviewer role"},
    )
    assert response.status_code == 200
    assert response.json()["description"] == "Updated reviewer role"

    # Delete
    response = await auth_client.delete(f"/api/v1/roles/{role_id}")
    assert response.status_code == 204

    # Verify gone
    response = await auth_client.get(f"/api/v1/roles/{role_id}")
    assert response.status_code == 404


# ============================================================================
# Policy Validation
# ============================================================================


@pytest.mark.asyncio
async def test_create_role_with_unknown_policy_fails(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Creating a role that references non-existent policies returns an error."""
    await make_admin(test_db_session, test_user)

    response = await auth_client.post(
        "/api/v1/roles",
        json={
            "name": "bad-role",
            "policies": ["workflow:read:any", "nonexistent:policy"],
        },
    )
    assert response.status_code == 422
    assert "nonexistent:policy" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_role_with_unknown_policy_fails(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Updating a role with a non-existent policy returns an error."""
    await make_admin(test_db_session, test_user)

    response = await auth_client.post(
        "/api/v1/roles",
        json={
            "name": "updatable-role",
            "policies": ["workflow:read:any"],
        },
    )
    assert response.status_code == 201
    role_id = response.json()["id"]

    response = await auth_client.patch(
        f"/api/v1/roles/{role_id}",
        json={"policies": ["nonexistent:policy"]},
    )
    assert response.status_code == 422


# ============================================================================
# Builtin Protection
# ============================================================================


@pytest.mark.asyncio
async def test_cannot_update_builtin_role(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Builtin roles cannot be modified."""
    await make_admin(test_db_session, test_user)

    response = await auth_client.get("/api/v1/roles?is_builtin=true")
    assert response.status_code == 200
    builtins = response.json()["resources"]
    assert len(builtins) > 0
    builtin_id = builtins[0]["id"]

    response = await auth_client.patch(
        f"/api/v1/roles/{builtin_id}",
        json={"description": "hacked"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cannot_delete_builtin_role(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Builtin roles cannot be deleted."""
    await make_admin(test_db_session, test_user)

    response = await auth_client.get("/api/v1/roles?is_builtin=true")
    assert response.status_code == 200
    builtin_id = response.json()["resources"][0]["id"]

    response = await auth_client.delete(f"/api/v1/roles/{builtin_id}")
    assert response.status_code == 403


# ============================================================================
# Name Conflict
# ============================================================================


@pytest.mark.asyncio
async def test_duplicate_role_name_returns_409(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Creating a role with a duplicate name in the same scope returns 409."""
    await make_admin(test_db_session, test_user)

    body = {
        "name": "unique-role",
        "policies": ["workflow:read:any"],
    }

    response = await auth_client.post("/api/v1/roles", json=body)
    assert response.status_code == 201

    response = await auth_client.post("/api/v1/roles", json=body)
    assert response.status_code == 409


# ============================================================================
# Authorization Enforcement
# ============================================================================


@pytest.mark.asyncio
async def test_regular_user_cannot_create_role(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """A user with only the 'user' role cannot create roles (403)."""
    limited_user = await user_factory(username="limited-role-c", email="limited-role-c@test.com")
    await make_user_role(test_db_session, limited_user)
    auth_as(limited_user)

    response = await auth_client.post(
        "/api/v1/roles",
        json={
            "name": "forbidden-role",
            "policies": ["workflow:read:any"],
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_regular_user_cannot_delete_role(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """A user with only the 'user' role cannot delete roles (403).

    Insert a custom role directly to have a target for the DELETE attempt.
    """
    limited_user = await user_factory(username="limited-role-d", email="limited-role-d@test.com")
    await make_user_role(test_db_session, limited_user)
    auth_as(limited_user)

    role = Role(
        name="delete-target-role",
        policies=["workflow:read:any"],
        is_builtin=False,
        labels={},
    )
    test_db_session.add(role)
    await test_db_session.commit()
    await test_db_session.refresh(role)

    response = await auth_client.delete(f"/api/v1/roles/{role.id}")
    assert response.status_code == 403


# ============================================================================
# Policy Name Filter
# ============================================================================


@pytest.mark.asyncio
async def test_list_roles_filter_by_policy_name(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Filter roles by policy_name returns only roles containing that policy."""
    await make_admin(test_db_session, test_user)

    # Create a role with specific policies
    response = await auth_client.post(
        "/api/v1/roles",
        json={
            "name": "filter-test-role",
            "description": "Role for policy_name filter test",
            "policies": ["workflow:read:any", "execution:read:any"],
        },
    )
    assert response.status_code == 201

    # Filter by exact policy name — should include the new role
    response = await auth_client.get("/api/v1/roles", params={"policy_name": "workflow:read:any"})
    assert response.status_code == 200
    names = [r["name"] for r in response.json()["resources"]]
    assert "filter-test-role" in names

    # Filter by a policy not in the role — should exclude it
    response = await auth_client.get("/api/v1/roles", params={"policy_name": "nonexistent-policy"})
    assert response.status_code == 200
    names = [r["name"] for r in response.json()["resources"]]
    assert "filter-test-role" not in names


@pytest.mark.asyncio
async def test_list_roles_filter_by_policy_name_contains(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Filter roles by policy_name[contains] returns roles with matching policies."""
    await make_admin(test_db_session, test_user)

    response = await auth_client.post(
        "/api/v1/roles",
        json={
            "name": "contains-filter-role",
            "description": "Role for contains filter test",
            "policies": ["workflow:read:any", "execution:read:any"],
        },
    )
    assert response.status_code == 201

    # Contains filter should match substring
    response = await auth_client.get("/api/v1/roles", params={"policy_name[contains]": "workflow"})
    assert response.status_code == 200
    names = [r["name"] for r in response.json()["resources"]]
    assert "contains-filter-role" in names


# ============================================================================
# IN Operator on Builtins
# ============================================================================


@pytest.mark.asyncio
async def test_list_builtin_roles_with_in_operator(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Builtin roles are returned when filtering with name[in].

    Builtins are filtered in-memory via matches_query_param, not SQL.
    This locks the path so builtins don't silently drop when the [in]
    operator is used.
    """
    await make_admin(test_db_session, test_user)

    # Get known builtin role names
    response = await auth_client.get("/api/v1/roles?is_builtin=true")
    assert response.status_code == 200
    builtins = response.json()["resources"]
    assert len(builtins) >= 2

    target_names = [builtins[0]["name"], builtins[1]["name"]]
    in_value = ",".join(target_names)

    # Filter builtins using name[in]
    response = await auth_client.get(
        "/api/v1/roles",
        params={"is_builtin": "true", "name[in]": in_value},
    )
    assert response.status_code == 200
    data = response.json()

    returned_names = {r["name"] for r in data["resources"]}
    assert returned_names == set(target_names)


# ============================================================================
# Not Found
# ============================================================================


@pytest.mark.asyncio
async def test_get_nonexistent_role_returns_404(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Getting a role that doesn't exist returns 404."""
    await make_admin(test_db_session, test_user)
    response = await auth_client.get(f"/api/v1/roles/{uuid4()}")
    assert response.status_code == 404
