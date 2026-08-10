"""Integration tests for deny-by-default authorization (Group 9: Deny by Default).

Validates that new users have minimal access and that project isolation
is enforced: users can only access projects they own or were granted.
"""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models import Project
from syntara.core.models import User
from tests.integration.api.conftest import make_admin, make_project_user


@pytest.mark.asyncio
async def test_new_user_project_isolation(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """Fresh user can access own project but is denied in another user's project."""
    alice = await user_factory(username="alice-dd", email="alice-dd@test.com")
    fresh = await user_factory(username="fresh-dd", email="fresh-dd@test.com", group_names=["users"])
    await make_admin(test_db_session, alice)

    # Fresh user creates own project (project:create:any via user role on authenticated group)
    auth_as(fresh)
    resp = await auth_client.post("/api/v1/projects", json={"name": "dd-own"})
    assert resp.status_code == 201
    own_name = resp.json()["name"]

    # Admin creates another project
    auth_as(alice)
    resp = await auth_client.post("/api/v1/projects", json={"name": "dd-other"})
    assert resp.status_code == 201
    other_name = resp.json()["name"]

    # Fresh user can create and read in own project
    auth_as(fresh)
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "create", "resource_type": "workflow", "resource_project": own_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True

    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "read", "resource_type": "workflow", "resource_project": own_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True

    # Fresh user denied in other project
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "read", "resource_type": "workflow", "resource_project": other_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False

    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "create", "resource_type": "workflow", "resource_project": other_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False


@pytest.mark.asyncio
async def test_grant_and_revoke(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """Admin grants access then revokes — access is removed (sequential)."""
    alice = await user_factory(username="alice-gar", email="alice-gar@test.com")
    bob = await user_factory(username="bob-gar", email="bob-gar@test.com")
    await make_admin(test_db_session, alice)

    auth_as(alice)
    resp = await auth_client.post("/api/v1/projects", json={"name": "dd-target"})
    assert resp.status_code == 201
    project_name = resp.json()["name"]

    project = (await test_db_session.exec(select(Project).where(Project.name == project_name))).first()
    assert project is not None
    assignment = await make_project_user(test_db_session, bob, project)

    # Bob has access
    auth_as(bob)
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "create", "resource_type": "workflow", "resource_project": project_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True

    # Revoke
    await test_db_session.delete(assignment)
    await test_db_session.commit()

    # Bob denied
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "create", "resource_type": "workflow", "resource_project": project_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False
