"""Integration tests for ``who_can`` on the ``workflow_node`` resource type.

The node-kind permission model carries the kind as the ``kind`` resource
label, so ``who_can`` must evaluate ``workflow_node:write`` / ``execute`` with
``resource_labels={"kind": ...}`` and honour a deny policy scoped to one kind
without affecting the others (ANSTRAT-1750, AD-17).
"""

from collections.abc import Awaitable, Callable, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import insert
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.api.main import app
from syntara.authz.dependencies import get_authz_evaluator
from syntara.authz.evaluator import evaluate_policy_input
from syntara.authz.models import RoleAssignment
from syntara.authz.models.policy import Policy
from syntara.authz.models.role import Role
from syntara.core.models import User
from syntara.core.models.group import Group, user_groups
from tests.integration.api.conftest import make_admin

_DENIED_KIND = "http_request"
_OTHER_KIND = "script"


def _opa_evaluate_cli(opa_input: dict[str, Any]) -> dict[str, Any]:
    """Evaluate authz against the real rego policy through regopy."""
    return evaluate_policy_input(opa_input)


@pytest.fixture(autouse=True)
def _override_opa_dependency() -> Generator[None, None, None]:
    """Resolve the authz evaluator to the real rego policy for these tests."""
    mock_evaluator = AsyncMock()
    mock_evaluator.evaluate = MagicMock(side_effect=_opa_evaluate_cli)
    app.dependency_overrides[get_authz_evaluator] = lambda: mock_evaluator
    yield
    app.dependency_overrides.pop(get_authz_evaluator, None)


async def _deny_node_kind(session: AsyncSession, user: User, kind: str, action: str) -> None:
    """Attach a deny policy for ``workflow_node:<action>`` on *kind* to *user*."""
    policy_name = f"deny-node-{action}-{kind}"
    role_name = f"deny-node-{action}-role-{kind}"
    session.add(
        Policy(
            id=uuid4(),
            name=policy_name,
            description=f"Deny {action} on {kind} nodes",
            statements=[
                {
                    "effect": "deny",
                    "actions": [f"workflow_node:{action}"],
                    "scope": "any",
                    "conditions": {"resource_labels": {"kind": kind}},
                }
            ],
            is_builtin=False,
            labels={},
        )
    )
    session.add(
        Role(
            id=uuid4(),
            name=role_name,
            description=f"Role denying {kind} nodes",
            is_builtin=False,
            policy_names=[policy_name],
            labels={},
        )
    )
    group = Group(name=f"deny-node-grp-{uuid4()}", description="", labels={})
    session.add(group)
    await session.flush()
    session.add(RoleAssignment(group_id=group.id, role_name=role_name))
    await session.exec(insert(user_groups).values(user_id=user.id, group_id=group.id))
    await session.commit()


async def _who_can_usernames(client: AsyncClient, action: str, kind: str) -> list[str]:
    """Return the usernames who_can reports for ``workflow_node:<action>`` on *kind*."""
    usernames: list[str] = []
    cursor: str | None = None
    while True:
        body: dict[str, Any] = {
            "action": action,
            "resource_type": "workflow_node",
            "resource_labels": {"kind": kind},
            "limit": 100,
        }
        if cursor:
            body["cursor"] = cursor
        response = await client.post("/api/v1/authz/who_can", json=body)
        assert response.status_code == 200, response.text
        data = response.json()
        usernames.extend(row["username"] for row in data["resources"])
        cursor = data.get("next")
        if not cursor:
            break
    return usernames


@pytest.mark.integration
@pytest.mark.asyncio
async def test_who_can_lists_authenticated_users_for_node_write(
    admin_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """Every authenticated user holds the builtin workflow_node:write:any allow."""
    member = await user_factory(username="wcnk-member", email="wcnk-member@test.com")

    usernames = await _who_can_usernames(admin_client, "write", _DENIED_KIND)

    assert member.username in usernames


@pytest.mark.integration
@pytest.mark.asyncio
async def test_who_can_excludes_user_denied_for_that_kind(
    admin_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """A deny on one kind removes the user from that kind's who_can result."""
    denied = await user_factory(username="wcnk-denied", email="wcnk-denied@test.com")
    allowed = await user_factory(username="wcnk-allowed", email="wcnk-allowed@test.com")
    await _deny_node_kind(test_db_session, denied, _DENIED_KIND, "write")

    denied_kind_users = await _who_can_usernames(admin_client, "write", _DENIED_KIND)

    assert denied.username not in denied_kind_users
    assert allowed.username in denied_kind_users


@pytest.mark.integration
@pytest.mark.asyncio
async def test_who_can_other_kinds_unaffected(
    admin_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """The deny is label-scoped: other kinds still list the denied user."""
    denied = await user_factory(username="wcnk-scoped", email="wcnk-scoped@test.com")
    await _deny_node_kind(test_db_session, denied, _DENIED_KIND, "write")

    other_kind_users = await _who_can_usernames(admin_client, "write", _OTHER_KIND)

    assert denied.username in other_kind_users


@pytest.mark.integration
@pytest.mark.asyncio
async def test_who_can_execute_deny_is_action_scoped(
    admin_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """A deny on execute does not remove the user from the write result."""
    denied = await user_factory(username="wcnk-exec", email="wcnk-exec@test.com")
    await _deny_node_kind(test_db_session, denied, _DENIED_KIND, "execute")

    execute_users = await _who_can_usernames(admin_client, "execute", _DENIED_KIND)
    write_users = await _who_can_usernames(admin_client, "write", _DENIED_KIND)

    assert denied.username not in execute_users
    assert denied.username in write_users


@pytest.mark.integration
@pytest.mark.asyncio
async def test_who_can_node_kind_requires_admin(
    base_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """workflow_node is not a tier-1 gate pair, so non-admins cannot query it."""
    limited = await user_factory(username="wcnk-limited", email="wcnk-limited@test.com")
    auth_as(limited)

    response = await base_client.post(
        "/api/v1/authz/who_can",
        json={
            "action": "write",
            "resource_type": "workflow_node",
            "resource_labels": {"kind": _DENIED_KIND},
        },
    )

    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_who_can_node_kind_scoped_to_project(
    admin_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
) -> None:
    """A project-scoped node-kind query still resolves through the builtin allow."""
    admin = await user_factory(username="wcnk-projadmin", email="wcnk-projadmin@test.com")
    await make_admin(test_db_session, admin)

    create = await admin_client.post("/api/v1/projects", json={"name": f"wcnk-proj-{uuid4().hex[:8]}"})
    assert create.status_code == 201, create.text
    project_name = create.json()["name"]

    response = await admin_client.post(
        "/api/v1/authz/who_can",
        json={
            "action": "write",
            "resource_type": "workflow_node",
            "resource_labels": {"kind": _DENIED_KIND},
            "resource_project": project_name,
            "limit": 100,
        },
    )

    assert response.status_code == 200, response.text
    assert admin.username in [row["username"] for row in response.json()["resources"]]
