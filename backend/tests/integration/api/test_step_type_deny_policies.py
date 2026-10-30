"""Integration tests: step-type deny policies through the policies and authz APIs.

Covers the AAP-99937 acceptance criteria at the HTTP layer: deny statements
accepted on ``step_type:write`` (and rejected elsewhere), can_i reporting
denied plus denied_by, what_can_i reporting the originating policy name,
and who_can excluding denied users.
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


@pytest.fixture(autouse=True)
def _override_opa_dependency() -> Generator[None, None, None]:
    """Evaluate authz queries through the real regopy policy in these tests."""
    mock_evaluator = AsyncMock()
    mock_evaluator.evaluate = MagicMock(side_effect=evaluate_policy_input)
    app.dependency_overrides[get_authz_evaluator] = lambda: mock_evaluator
    yield
    app.dependency_overrides.pop(get_authz_evaluator, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _attach_deny_policy(
    session: AsyncSession,
    user: User,
    name: str,
    kind: str,
    *,
    statements: list[dict[str, Any]] | None = None,
) -> None:
    """Persist a deny policy on step_type:write and attach it to *user*."""
    policy = Policy(
        id=uuid4(),
        name=name,
        description="",
        statements=statements
        or [
            {
                "effect": "deny",
                "actions": ["step_type:write"],
                "scope": "any",
                "conditions": {"resource_labels": {"kind": kind}},
            }
        ],
        is_builtin=False,
        labels={},
    )
    session.add(policy)
    role = Role(
        id=uuid4(),
        name=f"role-{name}-{uuid4().hex[:8]}",
        description="",
        is_builtin=False,
        policy_names=[name],
        labels={},
    )
    session.add(role)
    group = Group(name=f"grp-{name}-{uuid4().hex[:8]}", description="", labels={})
    session.add(group)
    await session.flush()
    session.add(RoleAssignment(group_id=group.id, role_name=role.name))
    await session.exec(insert(user_groups).values(user_id=user.id, group_id=group.id))
    await session.commit()


async def _fetch_all_what_can_i(client: AsyncClient) -> list[dict[str, Any]]:
    """Follow cursors to collect all what_can_i permissions across pages."""
    all_permissions: list[dict[str, Any]] = []
    cursor = None
    while True:
        body: dict[str, Any] = {"limit": 100}
        if cursor:
            body["cursor"] = cursor
        resp = await client.post("/api/v1/authz/what_can_i", json=body)
        assert resp.status_code == 200
        data = resp.json()
        all_permissions.extend(data["resources"])
        cursor = data.get("next")
        if not cursor:
            break
    return all_permissions


# ---------------------------------------------------------------------------
# POST/PATCH /api/v1/policies
# ============================================================================


@pytest.mark.asyncio
async def test_deny_step_type_policy_accepted_and_updated(
    admin_client: AsyncClient,
) -> None:
    """Deny on step_type:write can be created and updated (AAP-99937)."""
    statement = {
        "effect": "deny",
        "actions": ["step_type:write"],
        "scope": "any",
        "conditions": {"resource_labels": {"kind": "script"}},
    }
    response = await admin_client.post(
        "/api/v1/policies",
        json={"name": "deny-script-steps", "statements": [statement]},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["statements"][0]["effect"] == "deny"

    policy_id = body["id"]
    updated = {
        "effect": "deny",
        "actions": ["step_type:write"],
        "scope": "any",
        "conditions": {"resource_labels": {"kind": "http_request"}},
    }
    response = await admin_client.patch(
        f"/api/v1/policies/{policy_id}",
        json={"statements": [updated]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["statements"][0]["conditions"]["resource_labels"]["kind"] == "http_request"


@pytest.mark.asyncio
async def test_deny_on_other_resource_rejected(admin_client: AsyncClient) -> None:
    """A deny outside step_type:write is rejected with a clear error (lockout guard)."""
    response = await admin_client.post(
        "/api/v1/policies",
        json={
            "name": "deny-workflow-read",
            "statements": [{"effect": "deny", "actions": ["workflow:read"], "scope": "any"}],
        },
    )
    assert response.status_code == 422
    assert "Deny effect is only allowed on 'step_type:write'" in response.text


@pytest.mark.asyncio
async def test_deny_with_unknown_kind_rejected(admin_client: AsyncClient) -> None:
    """A deny with an unknown step type is rejected with a 422 that names it."""
    response = await admin_client.post(
        "/api/v1/policies",
        json={
            "name": "deny-unknown-kind",
            "statements": [
                {
                    "effect": "deny",
                    "actions": ["step_type:write"],
                    "scope": "any",
                    "conditions": {"resource_labels": {"kind": "scritp"}},
                }
            ],
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "INVALID_STEP_TYPE"
    assert "Unknown step type 'scritp'" in body["detail"]


# ============================================================================
# POST /authz/can_i
# ============================================================================


@pytest.mark.asyncio
async def test_can_i_reports_step_type_deny(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """can_i with a kind label and a project returns denied plus denied_by."""
    await make_admin(test_db_session, test_user)
    await _attach_deny_policy(test_db_session, test_user, "no-scripts", "script")

    response = await auth_client.post(
        "/api/v1/authz/can_i",
        json={
            "action": "write",
            "resource_type": "step_type",
            "resource_labels": {"kind": "script"},
            "resource_project": "payments",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["allowed"] is False
    assert data["denied"] is True
    assert data["denied_by"] == "no-scripts"
    assert data["denial_reason"] == "policy_deny"

    # Kinds outside the deny are still allowed by the admin allow-all.
    response = await auth_client.post(
        "/api/v1/authz/can_i",
        json={
            "action": "write",
            "resource_type": "step_type",
            "resource_labels": {"kind": "approval"},
            "resource_project": "payments",
        },
    )
    assert response.status_code == 200
    assert response.json()["allowed"] is True


# ============================================================================
# POST /authz/what_can_i
# ============================================================================


@pytest.mark.asyncio
async def test_what_can_i_reports_deny_with_original_policy_name(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    """A multi-statement policy reports its original name, never "name/1"."""
    await make_admin(test_db_session, test_user)
    await _attach_deny_policy(
        test_db_session,
        test_user,
        "mixed-step-policy",
        "script",
        statements=[
            {
                "effect": "deny",
                "actions": ["step_type:write"],
                "scope": "any",
                "conditions": {"resource_labels": {"kind": "http_request"}},
            },
            {
                "effect": "allow",
                "actions": ["step_type:write"],
                "scope": "any",
                "conditions": {"resource_labels": {"kind": "script"}},
            },
        ],
    )

    permissions = await _fetch_all_what_can_i(auth_client)
    step_entries = [p for p in permissions if "step_type:write" in p["actions"] and p["effect"] == "deny"]
    assert step_entries, "what_can_i must report the step-type deny"
    for entry in step_entries:
        assert entry["policy_name"] == "mixed-step-policy"
        assert "/" not in entry["policy_name"]


# ============================================================================
# POST /authz/who_can
# ============================================================================


@pytest.mark.asyncio
async def test_who_can_excludes_denied_user(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    test_user: User,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    """who_can drops users whose step type is denied by a deny policy."""
    await make_admin(test_db_session, test_user)

    denied_user = await user_factory(username="denied-scripter", email="denied-scripter@test.local")
    await make_admin(test_db_session, denied_user)
    await _attach_deny_policy(test_db_session, denied_user, "deny-script-for-whocan", "script")

    auth_as(test_user)
    response = await auth_client.post(
        "/api/v1/authz/who_can",
        json={
            "action": "write",
            "resource_type": "step_type",
            "resource_labels": {"kind": "script"},
            "limit": 100,
        },
    )
    assert response.status_code == 200
    usernames = [u["username"] for u in response.json()["resources"]]
    assert usernames, "the admin without the deny must be listed"
    assert "denied-scripter" not in usernames
