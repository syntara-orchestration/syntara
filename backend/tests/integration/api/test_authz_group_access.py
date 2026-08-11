"""Integration tests for group-based authorization (Group 3: Group Access).

Validates that group membership correctly grants and revokes access,
that multiple group memberships are additive, and that group-level
project role assignments work.
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
from tests.integration.api.conftest import make_admin


@pytest.mark.asyncio
async def test_group_grants_access(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """Adding user to group grants access that was previously denied."""
    bob = await user_factory(username="bob-gga", email="bob-gga@test.com")

    # Bob has no explicit roles — denied policy:read
    auth_as(bob)
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "read", "resource_type": "policy"},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False

    # Create group with auditor role and add bob
    group = Group(name="dev-team-gga", description="Dev team", labels={})
    test_db_session.add(group)
    await test_db_session.flush()
    test_db_session.add(RoleAssignment(group_id=group.id, role_name="auditor"))
    await test_db_session.exec(insert(user_groups).values(user_id=bob.id, group_id=group.id))
    await test_db_session.commit()

    # Bob now allowed
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "read", "resource_type": "policy"},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True


@pytest.mark.asyncio
async def test_multiple_groups_additive(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """User in multiple groups gets union of permissions."""
    bob = await user_factory(username="bob-mga", email="bob-mga@test.com")

    # Admin group
    admin_group = Group(name="admin-group-mga", description="Admin group", labels={})
    test_db_session.add(admin_group)
    await test_db_session.flush()
    test_db_session.add(RoleAssignment(group_id=admin_group.id, role_name="admin"))
    await test_db_session.exec(insert(user_groups).values(user_id=bob.id, group_id=admin_group.id))

    # Reader group with auditor role
    reader_group = Group(name="reader-group-mga", description="Reader group", labels={})
    test_db_session.add(reader_group)
    await test_db_session.flush()
    test_db_session.add(RoleAssignment(group_id=reader_group.id, role_name="auditor"))
    await test_db_session.exec(insert(user_groups).values(user_id=bob.id, group_id=reader_group.id))
    await test_db_session.commit()

    auth_as(bob)

    # workflow:create from admin role
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "create", "resource_type": "workflow"},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True

    # policy:read from auditor role
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "read", "resource_type": "policy"},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True


@pytest.mark.asyncio
async def test_group_project_role(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """Group assigned project-user grants all members project access."""
    alice = await user_factory(username="alice-gpr", email="alice-gpr@test.com")
    bob = await user_factory(username="bob-gpr", email="bob-gpr@test.com")
    await make_admin(test_db_session, alice)

    auth_as(alice)
    resp = await auth_client.post("/api/v1/projects", json={"name": "gamma-gpr"})
    assert resp.status_code == 201
    gamma_name = resp.json()["name"]

    # Create gamma-team group and add bob
    group = Group(name="gamma-team-gpr", description="Gamma team", labels={})
    test_db_session.add(group)
    await test_db_session.flush()
    await test_db_session.exec(insert(user_groups).values(user_id=bob.id, group_id=group.id))

    # Assign project-user role to group for gamma
    project = (await test_db_session.exec(select(Project).where(Project.name == gamma_name))).first()
    assert project is not None
    test_db_session.add(
        RoleAssignment(
            group_id=group.id,
            project_id=project.id,
            role_name="project-user",
        )
    )
    await test_db_session.commit()

    auth_as(bob)

    # Bob can read in gamma
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "read", "resource_type": "workflow", "resource_project": gamma_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True

    # Bob can create in gamma
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "create", "resource_type": "workflow", "resource_project": gamma_name},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True


@pytest.mark.asyncio
async def test_remove_revokes_access(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """Removing user from group revokes access (sequential, not parametrized)."""
    bob = await user_factory(username="revoke-bob-ga", email="revoke-bob-ga@test.com")

    group = Group(name="revoke-team-ga", description="Revoke team", labels={})
    test_db_session.add(group)
    await test_db_session.flush()
    test_db_session.add(RoleAssignment(group_id=group.id, role_name="auditor"))
    await test_db_session.exec(insert(user_groups).values(user_id=bob.id, group_id=group.id))
    await test_db_session.commit()

    # Bob can read policies while in group
    auth_as(bob)
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "read", "resource_type": "policy"},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True

    # Remove bob from group
    from sqlalchemy import delete

    await test_db_session.exec(
        delete(user_groups).where(
            user_groups.c.user_id == bob.id,
            user_groups.c.group_id == group.id,
        )
    )
    await test_db_session.commit()

    # Bob denied after removal
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "read", "resource_type": "policy"},
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False
