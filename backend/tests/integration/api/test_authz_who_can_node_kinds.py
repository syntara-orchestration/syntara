"""Step-type policies through HTTP, real resolution, and real Rego evaluation."""

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.engine import AuthzRequest, authorize
from syntara.authz.evaluator import evaluate_policy_input
from syntara.authz.models import Project, RoleAssignment
from syntara.authz.models.role import Role
from syntara.authz.services.policy_service import PolicyService
from syntara.core.models import User


def _statement(effect: str, *, kind: str | None = None) -> dict[str, Any]:
    statement: dict[str, Any] = {"effect": effect, "actions": ["step_type:write"], "scope": "any"}
    if kind:
        statement["conditions"] = {"resource_labels": {"kind": kind}}
    return statement


async def _assign_policy(
    db: AsyncSession, user: User, name: str, statements: list[dict[str, Any]], project_id: UUID | None = None
) -> Role:
    await PolicyService(db, user).create_policy(name=name, statements=statements)
    role = Role(name=f"{name}-role", policy_names=[name], labels={})
    db.add(role)
    await db.flush()
    db.add(RoleAssignment(principal_id=user.id, role_name=role.name, project_id=project_id))
    await db.commit()
    return role


class _RealEvaluator:
    """Use the production normalization path for direct engine comparisons."""

    def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def health(self) -> bool:
        return True

    def evaluate(self, authz_input: dict[str, Any]) -> dict[str, Any]:
        return evaluate_policy_input(authz_input)


@pytest.mark.asyncio
@pytest.mark.parametrize("project_scoped", [False, True])
async def test_can_i_reports_exact_effective_statement(
    auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User, *, project_scoped: bool
) -> None:
    db = test_db_session
    project = Project(name="payments", labels={})
    db.add(project)
    await db.commit()
    await _assign_policy(db, test_user, "allow-all-step-types", [_statement("allow")])
    role = await _assign_policy(
        db,
        test_user,
        "a-mixed-policy",
        [_statement("allow", kind="http_request"), _statement("deny", kind="script")],
        project.id if project_scoped else None,
    )
    if project_scoped:
        other = Project(name="other", labels={})
        db.add(other)
        await db.flush()
        db.add(RoleAssignment(principal_id=test_user.id, role_name=role.name, project_id=other.id))
        await db.commit()
    await _assign_policy(
        db, test_user, "z-second-deny", [_statement("deny", kind="script")], project.id if project_scoped else None
    )

    for context in (project.name, str(project.id)):
        response = await auth_client.post(
            "/api/v1/authz/can_i",
            json={
                "action": "write",
                "resource_type": "step_type",
                "resource_labels": {"kind": "script"},
                "resource_project": context,
            },
        )
        assert response.status_code == 200, response.text
        assert response.json() == {
            "allowed": False,
            "denied": True,
            "matched_policy": "",
            "denial_reason": "policy_deny",
            "denied_by": "a-mixed-policy",
        }
    for kind, context in (("http_request", "payments"), ("script", "unassigned-project")):
        response = await auth_client.post(
            "/api/v1/authz/can_i",
            json={
                "action": "write",
                "resource_type": "step_type",
                "resource_labels": {"kind": kind},
                "resource_project": context,
            },
        )
        assert response.json()["allowed"] is (kind != "script" or project_scoped)

    permissions = await auth_client.post("/api/v1/authz/what_can_i", json={"limit": 100})
    assert permissions.status_code == 200, permissions.text
    mixed = [entry for entry in permissions.json()["resources"] if entry["policy_name"] == "a-mixed-policy"]
    assert {entry["effect"] for entry in mixed} == {"allow", "deny"}
    assert all("/1" not in entry["policy_name"] and "@" not in entry["policy_name"] for entry in mixed)


@pytest.mark.asyncio
async def test_global_and_project_assignment_of_same_policy_are_distinct(
    auth_client: AsyncClient, test_db_session: AsyncSession, test_user: User
) -> None:
    db = test_db_session
    project = Project(name="payments", labels={})
    db.add(project)
    await db.commit()
    role = await _assign_policy(db, test_user, "same-deny", [_statement("deny", kind="script")], project.id)
    db.add(RoleAssignment(principal_id=test_user.id, role_name=role.name))
    await db.commit()
    result = await authorize(
        db,
        _RealEvaluator(),
        AuthzRequest(
            user_id=test_user.id,
            action="write",
            resource_type="step_type",
            resource_id="",
            resource_labels={"kind": "script"},
            resource_project="payments",
        ),
    )
    assert {entry["name"] for entry in result.effective_policies if entry.get("policy_name") == "same-deny"} == {
        "same-deny",
        "same-deny@payments",
    }


@pytest.mark.asyncio
async def test_who_can_excludes_explicit_and_implicit_denials_and_keeps_pagination(
    admin_client: AsyncClient, test_db_session: AsyncSession, user_factory: Callable[..., Awaitable[User]]
) -> None:
    db = test_db_session
    allowed = await user_factory(username="step-allowed", email="step-allowed@example.com")
    denied = await user_factory(username="step-denied", email="step-denied@example.com")
    implicit = await user_factory(username="step-no-allow", email="step-no-allow@example.com")
    for user in (allowed, denied):
        await _assign_policy(db, user, f"allow-{user.username}", [_statement("allow")])
    await _assign_policy(db, denied, "deny-script", [_statement("deny", kind="script")])
    for kind in ("script", "http_request"):
        usernames: list[str] = []
        cursor = None
        while True:
            body = {
                "action": "write",
                "resource_type": "step_type",
                "resource_labels": {"kind": kind},
                "limit": 1,
                "include_total": True,
            }
            if cursor:
                body["cursor"] = cursor
            response = await admin_client.post("/api/v1/authz/who_can", json=body)
            assert response.status_code == 200, response.text
            data = response.json()
            usernames.extend(user["username"] for user in data["resources"])
            assert data["total"] == (1 if kind == "script" else 2)
            cursor = data.get("next")
            if not cursor:
                break
        assert set(usernames) == ({allowed.username} if kind == "script" else {allowed.username, denied.username})
        assert implicit.username not in usernames


@pytest.mark.asyncio
async def test_who_can_keeps_existing_query_gate(
    auth_client: AsyncClient, user_factory: Callable[..., Awaitable[User]], auth_as: Callable[[User], None]
) -> None:
    limited = await user_factory(username="limited-step-query", email="limited-step-query@example.com")
    auth_as(limited)
    response = await auth_client.post(
        "/api/v1/authz/who_can",
        json={
            "action": "write",
            "resource_type": "step_type",
            "resource_labels": {"kind": "script"},
            "resource_project": "payments",
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_missing_allow_is_reported_by_can_i(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/authz/can_i",
        json={
            "action": "write",
            "resource_type": "step_type",
            "resource_labels": {"kind": "script"},
            "resource_project": "payments",
        },
    )
    assert response.json()["allowed"] is False
    assert response.json()["denied"] is False
    assert response.json()["denied_by"] == ""


@pytest.mark.asyncio
async def test_policy_api_and_project_api_accept_denies_and_reject_invalid_updates(
    auth_client: AsyncClient, test_db_session: AsyncSession
) -> None:
    project = Project(name="payments", labels={})
    test_db_session.add(project)
    await test_db_session.commit()
    for path, scope in (("/api/v1/policies", "any"), (f"/api/v1/projects/{project.id}/policies", "project")):
        statement = {**_statement("deny", kind="script"), "scope": scope}
        created = await auth_client.post(path, json={"name": f"deny-{scope}", "statements": [statement]})
        assert created.status_code == 201, created.text
        policy_id = created.json()["id"]
        for method in ("PATCH", "PUT"):
            updated = await auth_client.request(method, f"{path}/{policy_id}", json={"statements": [statement]})
            assert updated.status_code == 200, updated.text
            invalid = await auth_client.request(
                method,
                f"{path}/{policy_id}",
                json={"name": "invalid-rename", "statements": [{**statement, "actions": ["policy:delete"]}]},
            )
            assert invalid.status_code == 422, invalid.text
            assert "policy:delete" in invalid.json()["detail"]
        stored = await auth_client.get(f"{path}/{policy_id}")
        assert stored.json()["name"] == f"deny-{scope}"
        assert stored.json()["statements"] == [statement]

    invalid_kind = await auth_client.post(
        "/api/v1/policies", json={"name": "unknown-kind", "statements": [_statement("deny", kind="scritp")]}
    )
    assert invalid_kind.status_code == 422
    assert "scritp" in invalid_kind.json()["detail"]
