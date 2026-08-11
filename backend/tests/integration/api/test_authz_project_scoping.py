"""Integration tests for project-scoped authorization (Group 2: Project Scoping).

Validates that project-level role assignments are properly isolated:
users with roles in one project cannot access resources in another.
"""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models import Project, RoleAssignment
from syntara.core.models import User
from syntara.core.models.group import Group, user_groups
from tests.integration.api.conftest import make_admin, make_project_admin, make_project_user


@pytest.mark.asyncio
async def test_project_role_isolation(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """Project-user in alpha cannot access beta."""
    alice = await user_factory(username="alice", email="alice@test.com")
    bob = await user_factory(username="bob", email="bob@test.com")
    await make_admin(test_db_session, alice)

    # Alice creates two projects
    auth_as(alice)
    resp = await auth_client.post("/api/v1/projects", json={"name": "alpha"})
    assert resp.status_code == 201
    alpha_name = resp.json()["name"]

    resp = await auth_client.post("/api/v1/projects", json={"name": "beta"})
    assert resp.status_code == 201
    beta_name = resp.json()["name"]

    # Assign bob project-user in alpha
    alpha_project = (await test_db_session.exec(select(Project).where(Project.name == alpha_name))).first()
    assert alpha_project is not None
    await make_project_user(test_db_session, bob, alpha_project)

    # Bob can read/create in alpha
    auth_as(bob)
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "read", "resource_type": "workflow", "resource_project": alpha_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True

    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "create", "resource_type": "workflow", "resource_project": alpha_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True

    # Bob denied in beta
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "read", "resource_type": "workflow", "resource_project": beta_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False

    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "create", "resource_type": "workflow", "resource_project": beta_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False


@pytest.mark.asyncio
async def test_project_admin_boundaries(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """Project-admin in one project cannot manage another."""
    alice = await user_factory(username="alice-pab", email="alice-pab@test.com")
    bob = await user_factory(username="bob-pab", email="bob-pab@test.com")
    carol = await user_factory(username="carol-pab", email="carol-pab@test.com")
    await make_admin(test_db_session, alice)

    auth_as(alice)
    resp = await auth_client.post("/api/v1/projects", json={"name": "alpha-pab"})
    assert resp.status_code == 201
    alpha_name = resp.json()["name"]

    resp = await auth_client.post("/api/v1/projects", json={"name": "beta-pab"})
    assert resp.status_code == 201
    beta_name = resp.json()["name"]

    alpha_project = (await test_db_session.exec(select(Project).where(Project.name == alpha_name))).first()
    beta_project = (await test_db_session.exec(select(Project).where(Project.name == beta_name))).first()
    assert alpha_project is not None
    assert beta_project is not None

    await make_project_admin(test_db_session, bob, alpha_project)
    await make_project_admin(test_db_session, carol, beta_project)

    # Bob can delete in alpha, denied in beta
    auth_as(bob)
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "delete", "resource_type": "workflow", "resource_project": alpha_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True

    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "delete", "resource_type": "workflow", "resource_project": beta_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False

    # Carol can delete in beta, denied in alpha
    auth_as(carol)
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "delete", "resource_type": "workflow", "resource_project": beta_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True

    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "delete", "resource_type": "workflow", "resource_project": alpha_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False


@pytest.mark.asyncio
async def test_cross_project_group_role(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """Group with project-user in alpha grants members alpha access, not beta."""
    alice = await user_factory(username="alice-cpgr", email="alice-cpgr@test.com")
    bob = await user_factory(username="bob-cpgr", email="bob-cpgr@test.com")
    await make_admin(test_db_session, alice)

    auth_as(alice)
    resp = await auth_client.post("/api/v1/projects", json={"name": "alpha-cpgr"})
    assert resp.status_code == 201
    alpha_name = resp.json()["name"]

    resp = await auth_client.post("/api/v1/projects", json={"name": "beta-cpgr"})
    assert resp.status_code == 201
    beta_name = resp.json()["name"]

    # Create group alpha-team with project-user role for alpha
    group = Group(name="alpha-team", description="Alpha team group", labels={})
    test_db_session.add(group)
    await test_db_session.flush()

    await test_db_session.exec(insert(user_groups).values(user_id=bob.id, group_id=group.id))

    project = (await test_db_session.exec(select(Project).where(Project.name == alpha_name))).first()
    assert project is not None
    test_db_session.add(
        RoleAssignment(
            group_id=group.id,
            project_id=project.id,
            role_name="project-user",
        )
    )
    await test_db_session.commit()

    # Bob can read alpha via group
    auth_as(bob)
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "read", "resource_type": "workflow", "resource_project": alpha_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True

    # Bob denied in beta
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "read", "resource_type": "workflow", "resource_project": beta_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False


@pytest.mark.asyncio
async def test_can_i_accepts_project_uuid(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """can-i resolves project UUID to name for project-scoped checks."""
    alice = await user_factory(username="alice-uuid", email="alice-uuid@test.com")
    bob = await user_factory(username="bob-uuid", email="bob-uuid@test.com")
    await make_admin(test_db_session, alice)

    auth_as(alice)
    resp = await auth_client.post("/api/v1/projects", json={"name": "uuid-proj"})
    assert resp.status_code == 201
    project_uuid = resp.json()["id"]
    project_name = resp.json()["name"]

    project = (await test_db_session.exec(select(Project).where(Project.name == project_name))).first()
    assert project is not None
    await make_project_user(test_db_session, bob, project)

    auth_as(bob)

    # UUID should resolve to name and return allowed
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "read", "resource_type": "workflow", "resource_project": project_uuid},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True

    # Name should still work (regression check)
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "read", "resource_type": "workflow", "resource_project": project_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True

    # UUID for a non-existent project should still return denied
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={
            "action": "read",
            "resource_type": "workflow",
            "resource_project": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False
