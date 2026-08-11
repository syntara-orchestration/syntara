"""Integration tests for admin tooling authorization (Group 10: Admin Tooling).

Validates authz response fields (matched_policy, denied_by, denial_reason)
and the who-can endpoint for authorized-user enumeration.
"""

from collections.abc import Awaitable, Callable
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import insert
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models import RoleAssignment
from syntara.authz.models.policy import Policy
from syntara.authz.models.role import Role
from syntara.core.models import User
from syntara.core.models.group import Group, user_groups
from tests.integration.api.conftest import make_admin, make_auditor, make_user_role


@pytest.mark.asyncio
async def test_matched_policy_field(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """User with user role doing project:create shows matched_policy containing 'project'."""
    bob = await user_factory(username="bob-mpf", email="bob-mpf@test.com")
    await make_user_role(test_db_session, bob)

    auth_as(bob)
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "create", "resource_type": "project"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["allowed"] is True
    assert "project" in data["matched_policy"]


@pytest.mark.asyncio
async def test_implicit_deny_no_policy_match(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """Auditor doing workflow:create is implicitly denied with empty matched_policy."""
    carol = await user_factory(username="carol-idnp", email="carol-idnp@test.com")
    await make_auditor(test_db_session, carol)

    auth_as(carol)
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "create", "resource_type": "workflow"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["allowed"] is False
    assert data["matched_policy"] == ""


@pytest.mark.asyncio
async def test_explicit_deny_fields(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """Explicit deny policy shows denied=True, denied_by, and denial_reason."""
    bob = await user_factory(username="bob-edf", email="bob-edf@test.com")
    await make_user_role(test_db_session, bob)

    # Create deny policy for workflow:delete
    deny_policy = Policy(
        id=uuid4(),
        name="deny-wf-delete-at",
        description="Deny workflow deletion",
        statements=[{"effect": "deny", "actions": ["workflow:delete"], "scope": "any"}],
        is_builtin=False,
        labels={},
    )
    test_db_session.add(deny_policy)

    deny_role = Role(
        id=uuid4(),
        name="deny-delete-role-at",
        description="Role with deny policy",
        is_builtin=False,
        policy_names=["deny-wf-delete-at"],
        labels={},
    )
    test_db_session.add(deny_role)
    await test_db_session.flush()

    group = Group(name=f"deny-at-grp-{uuid4()}", description="", labels={})
    test_db_session.add(group)
    await test_db_session.flush()
    test_db_session.add(RoleAssignment(group_id=group.id, role_name="deny-delete-role-at"))
    await test_db_session.exec(insert(user_groups).values(user_id=bob.id, group_id=group.id))
    await test_db_session.commit()

    auth_as(bob)
    resp = await auth_client.post(
        "/api/v1/authz/can_i",
        json={"action": "delete", "resource_type": "workflow"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["allowed"] is False
    assert data["denied"] is True
    assert data["denied_by"] == "deny-wf-delete-at"
    assert data["denial_reason"] == "policy_deny"


@pytest.mark.asyncio
async def test_who_can_lists_authorized(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """who-can assign role-assignment includes admin, excludes user and auditor.

    All authenticated users get project:create via the authenticated group,
    so we test role-assignment:assign which is admin-only.
    """
    alice = await user_factory(username="alice-wcla", email="alice-wcla@test.com")
    bob = await user_factory(username="bob-wcla", email="bob-wcla@test.com")
    carol = await user_factory(username="carol-wcla", email="carol-wcla@test.com")

    await make_admin(test_db_session, alice)
    await make_user_role(test_db_session, bob)
    await make_auditor(test_db_session, carol)

    auth_as(alice)
    resp = await auth_client.post(
        "/api/v1/authz/who_can",
        json={"action": "assign", "resource_type": "role-assignment"},
    )
    assert resp.status_code == 200
    usernames = {u["username"] for u in resp.json()["resources"]}
    assert "alice-wcla" in usernames
    assert "bob-wcla" not in usernames
    assert "carol-wcla" not in usernames
