"""Integration tests for project lifecycle authorization (Group 8: Project Lifecycle).

Validates create-and-auto-admin, delegation, user/auditor assignment,
and role revocation within project scope.
"""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models import Project
from syntara.authz.models.assignments import RoleAssignment
from syntara.core.models import User
from tests.integration.api.conftest import make_admin, make_project_admin, make_project_user


@pytest.mark.asyncio
async def test_create_and_auto_admin(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """Creating a project auto-assigns project-admin to the creator."""
    alice = await user_factory(username="alice-caa", email="alice-caa@test.com")
    await make_admin(test_db_session, alice)

    auth_as(alice)
    resp = await auth_client.post("/api/v1/projects", json={"name": "pt-alpha"})
    assert resp.status_code == 201
    project_name = resp.json()["name"]

    for action in ("create", "read", "update", "delete"):
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"action": action, "resource_type": "workflow", "resource_project": project_name},
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is True, f"Creator should be allowed {action} in own project"


@pytest.mark.asyncio
async def test_delegate_admin(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """Project-admin can delegate project-admin to another user."""
    alice = await user_factory(username="alice-da", email="alice-da@test.com")
    bob = await user_factory(username="bob-da", email="bob-da@test.com")
    await make_admin(test_db_session, alice)

    auth_as(alice)
    resp = await auth_client.post("/api/v1/projects", json={"name": "pt-beta"})
    assert resp.status_code == 201
    project_name = resp.json()["name"]

    project = (await test_db_session.exec(select(Project).where(Project.name == project_name))).first()
    assert project is not None
    await make_project_admin(test_db_session, bob, project)

    auth_as(bob)
    for action in ("create", "delete"):
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"action": action, "resource_type": "workflow", "resource_project": project_name},
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is True, f"Delegated admin should be allowed {action}"


@pytest.mark.asyncio
async def test_assign_user_and_auditor(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """Project-user can create/read; project-auditor can read but not create/delete."""
    alice = await user_factory(username="alice-aua", email="alice-aua@test.com")
    bob = await user_factory(username="bob-aua", email="bob-aua@test.com")
    carol = await user_factory(username="carol-aua", email="carol-aua@test.com")
    await make_admin(test_db_session, alice)

    auth_as(alice)
    resp = await auth_client.post("/api/v1/projects", json={"name": "pt-gamma"})
    assert resp.status_code == 201
    project_name = resp.json()["name"]

    project = (await test_db_session.exec(select(Project).where(Project.name == project_name))).first()
    assert project is not None

    # Bob as project-user
    await make_project_user(test_db_session, bob, project)

    # Carol as project-auditor (manual assignment)
    test_db_session.add(
        RoleAssignment(
            principal_id=carol.id,
            project_id=project.id,
            role_name="project-auditor",
        )
    )
    await test_db_session.commit()

    # Bob can create and read
    auth_as(bob)
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "create", "resource_type": "workflow", "resource_project": project_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True

    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "read", "resource_type": "workflow", "resource_project": project_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True

    # Carol can read
    auth_as(carol)
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "read", "resource_type": "workflow", "resource_project": project_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True

    # Carol denied create and delete
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "create", "resource_type": "workflow", "resource_project": project_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False

    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "delete", "resource_type": "workflow", "resource_project": project_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False


@pytest.mark.asyncio
async def test_revoke_role(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """Revoking project role removes access (sequential, not parametrized)."""
    alice = await user_factory(username="alice-rr", email="alice-rr@test.com")
    bob = await user_factory(username="bob-rr", email="bob-rr@test.com")
    await make_admin(test_db_session, alice)

    auth_as(alice)
    resp = await auth_client.post("/api/v1/projects", json={"name": "pt-delta"})
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

    # Revoke assignment
    await test_db_session.delete(assignment)
    await test_db_session.commit()

    # Bob denied after revoke
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "create", "resource_type": "workflow", "resource_project": project_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False
