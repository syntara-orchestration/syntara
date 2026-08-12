"""Integration tests for the policies CRUD API.

Covers:
- Full CRUD lifecycle (create, read, list, update, delete)
- Builtin protection (cannot update or delete builtins)
- Name conflict handling (409)
- Authorization enforcement (403 for unauthorized users)
"""

from collections.abc import Awaitable, Callable
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import insert
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models import RoleAssignment
from syntara.core.models import User
from syntara.core.models.group import Group, user_groups
from tests.integration.api.conftest import make_user_role


async def _make_admin(session: AsyncSession, user: User) -> None:
    """Assign the admin role to a user via a dedicated group."""
    group = Group(name=f"admin-grp-{uuid4()}", description="", labels={})
    session.add(group)
    await session.flush()
    session.add(RoleAssignment(group_id=group.id, role_name="admin"))
    await session.exec(insert(user_groups).values(user_id=user.id, group_id=group.id))
    await session.commit()


# ============================================================================
# CRUD Lifecycle
# ============================================================================


@pytest.mark.asyncio
async def test_policy_crud_lifecycle(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Full CRUD lifecycle: create, read, list, update, delete."""
    await _make_admin(test_db_session, test_user)

    # Create
    response = await auth_client.post(
        "/api/v1/policies",
        json={
            "name": "custom:test:any",
            "description": "Test policy",
            "statements": [{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
            "labels": {"env": "test"},
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "custom:test:any"
    assert data["description"] == "Test policy"
    assert data["is_builtin"] is False
    assert data["statements"][0]["effect"] == "allow"
    assert data["labels"] == {"env": "test"}
    policy_id = data["id"]

    # Read
    response = await auth_client.get(f"/api/v1/policies/{policy_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "custom:test:any"

    # List (filter to custom only since builtins exceed default page size)
    response = await auth_client.get("/api/v1/policies?is_builtin=false")
    assert response.status_code == 200
    body = response.json()
    names = [p["name"] for p in body["resources"]]
    assert "custom:test:any" in names

    # Update
    response = await auth_client.patch(
        f"/api/v1/policies/{policy_id}",
        json={"description": "Updated description"},
    )
    assert response.status_code == 200
    assert response.json()["description"] == "Updated description"

    # Delete
    response = await auth_client.delete(f"/api/v1/policies/{policy_id}")
    assert response.status_code == 204

    # Verify gone
    response = await auth_client.get(f"/api/v1/policies/{policy_id}")
    assert response.status_code == 404


# ============================================================================
# Builtin Protection
# ============================================================================


@pytest.mark.asyncio
async def test_cannot_update_builtin_policy(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Builtin policies cannot be modified."""
    await _make_admin(test_db_session, test_user)

    # Find a builtin policy
    response = await auth_client.get("/api/v1/policies?is_builtin=true")
    assert response.status_code == 200
    builtins = response.json()["resources"]
    assert len(builtins) > 0
    builtin_id = builtins[0]["id"]

    response = await auth_client.patch(
        f"/api/v1/policies/{builtin_id}",
        json={"description": "hacked"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cannot_delete_builtin_policy(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Builtin policies cannot be deleted."""
    await _make_admin(test_db_session, test_user)

    response = await auth_client.get("/api/v1/policies?is_builtin=true")
    assert response.status_code == 200
    builtin_id = response.json()["resources"][0]["id"]

    response = await auth_client.delete(f"/api/v1/policies/{builtin_id}")
    assert response.status_code == 403


# ============================================================================
# Name Conflict
# ============================================================================


@pytest.mark.asyncio
async def test_duplicate_policy_name_returns_409(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Creating a policy with a duplicate name in the same scope returns 409."""
    await _make_admin(test_db_session, test_user)

    body = {
        "name": "unique-policy",
        "statements": [{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
    }

    response = await auth_client.post("/api/v1/policies", json=body)
    assert response.status_code == 201

    response = await auth_client.post("/api/v1/policies", json=body)
    assert response.status_code == 409


# ============================================================================
# Authorization Enforcement
# ============================================================================


@pytest.mark.asyncio
async def test_regular_user_cannot_create_policy(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """A user with only the 'user' role cannot create policies (403)."""
    limited_user = await user_factory(username="limited-pol-c", email="limited-pol-c@test.com")
    await make_user_role(test_db_session, limited_user)
    auth_as(limited_user)

    response = await auth_client.post(
        "/api/v1/policies",
        json={
            "name": "forbidden-policy",
            "statements": [{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_regular_user_cannot_delete_policy(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """A user with only the 'user' role cannot delete a custom policy (403).

    A limited user (with 'user' role) cannot delete policies even if they exist.
    We insert one directly to have a target for the DELETE attempt.
    """
    from syntara.authz.models.policy import Policy

    limited_user = await user_factory(username="limited-pol-d", email="limited-pol-d@test.com")
    await make_user_role(test_db_session, limited_user)
    auth_as(limited_user)

    policy = Policy(
        name="delete-target",
        statements=[{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
        is_builtin=False,
        labels={},
    )
    test_db_session.add(policy)
    await test_db_session.commit()
    await test_db_session.refresh(policy)

    response = await auth_client.delete(f"/api/v1/policies/{policy.id}")
    assert response.status_code == 403


# ============================================================================
# Filtering
# ============================================================================


@pytest.mark.asyncio
async def test_list_policies_filter_by_builtin(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Can filter policies by is_builtin=true."""
    await _make_admin(test_db_session, test_user)

    # Create a custom policy
    response = await auth_client.post(
        "/api/v1/policies",
        json={
            "name": "filter-test-custom",
            "statements": [{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
        },
    )
    assert response.status_code == 201

    # List only builtins
    response = await auth_client.get("/api/v1/policies?is_builtin=true")
    assert response.status_code == 200
    for p in response.json()["resources"]:
        assert p["is_builtin"] is True

    # List only non-builtins
    response = await auth_client.get("/api/v1/policies?is_builtin=false")
    assert response.status_code == 200
    for p in response.json()["resources"]:
        assert p["is_builtin"] is False


# ============================================================================
# IN Operator on Builtins
# ============================================================================


@pytest.mark.asyncio
async def test_list_builtin_policies_with_name_in_operator(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Builtin policies are returned when filtering with name[in].

    Builtins are filtered in-memory via matches_query_param, not SQL.
    This locks the path so builtins don't silently drop when the [in]
    operator is used.
    """
    await _make_admin(test_db_session, test_user)

    # First, get two known builtin policy names
    response = await auth_client.get("/api/v1/policies?is_builtin=true&limit=100")
    assert response.status_code == 200
    builtins = response.json()["resources"]
    assert len(builtins) >= 2

    target_names = [builtins[0]["name"], builtins[1]["name"]]
    in_value = ",".join(target_names)

    # Filter builtins using name[in]
    response = await auth_client.get(
        "/api/v1/policies",
        params={"is_builtin": "true", "name[in]": in_value},
    )
    assert response.status_code == 200
    data = response.json()

    returned_names = {p["name"] for p in data["resources"]}
    assert returned_names == set(target_names)


@pytest.mark.asyncio
async def test_list_builtin_policies_with_scope_in_operator(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Builtin policies with scope[in] returns policies matching any listed scope.

    Exercises the in-memory matches_query_param path for the scope field,
    which is the filter that originally caused builtins to silently drop.
    """
    await _make_admin(test_db_session, test_user)

    response = await auth_client.get(
        "/api/v1/policies",
        params={"is_builtin": "true", "scope[in]": "any,self", "limit": "100"},
    )
    assert response.status_code == 200
    data = response.json()

    scopes = {p["scope"] for p in data["resources"]}
    assert scopes <= {"any", "self"}
    assert len(data["resources"]) >= 2


# ============================================================================
# Not Found
# ============================================================================


@pytest.mark.asyncio
async def test_get_nonexistent_policy_returns_404(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """Getting a policy that doesn't exist returns 404."""
    await _make_admin(test_db_session, test_user)
    response = await auth_client.get(f"/api/v1/policies/{uuid4()}")
    assert response.status_code == 404
