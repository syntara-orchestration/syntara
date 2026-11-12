"""Integration tests for the step-type permissions endpoint (ANSTRAT-2533 P6).

Exercises the full round trip — real policy resolution and real Rego
evaluation — for ``GET /api/v1/node_kinds?project_id=<uuid>``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest
from sqlmodel import select

from syntara.authz.models import Project, RoleAssignment
from syntara.authz.models.role import Role
from syntara.authz.resolver import AUTHENTICATED_GROUP_NAME
from syntara.authz.services.policy_service import PolicyService
from syntara.core.models.group import Group, user_groups

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User

_NODE_KINDS_URL = "/api/v1/node_kinds"


async def _make_role_assignment(db: AsyncSession, user: User, role_name: str) -> None:
    """Assign a named role to a user via a dedicated group."""
    from uuid import uuid4

    group = Group(id=uuid4(), name=f"{role_name}-grp-{uuid4()}", description="", labels={})
    db.add(group)
    await db.flush()
    db.add(RoleAssignment(id=uuid4(), group_id=group.id, role_name=role_name))
    from sqlalchemy import insert

    await db.exec(insert(user_groups).values(user_id=user.id, group_id=group.id))
    await db.commit()


def _statement(effect: str, *, kind: str | None = None, scope: str = "any") -> dict[str, Any]:
    statement: dict[str, Any] = {"effect": effect, "actions": ["step_type:write"], "scope": scope}
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


def _by_kind(payload: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {entry["kind"]: entry for entry in payload}


async def _make_project(db: AsyncSession, name: str) -> Project:
    project = Project(name=name, labels={})
    db.add(project)
    await db.commit()
    return project


@pytest.fixture
async def author_user(user_factory: Callable[..., Awaitable[User]], test_db_session: AsyncSession) -> User:
    """A user whose only step-type grant is the built-in step-author role."""
    user = await user_factory(username="step-author-user", email="step-author@example.com")
    await _make_role_assignment(test_db_session, user, "step-author")
    return user


@pytest.fixture
async def author_client(base_client: AsyncClient, author_user: User) -> AsyncClient:
    from syntara.api.main import app
    from syntara.auth.dependencies import get_current_user

    async def override() -> User:
        return author_user

    app.dependency_overrides[get_current_user] = override
    return base_client


class TestListNodeKinds:
    """GET /node_kinds reports the registry with the caller's verdicts."""

    @pytest.mark.asyncio
    async def test_requires_project_id(self, author_client: AsyncClient) -> None:
        resp = await author_client.get(_NODE_KINDS_URL)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_unknown_project_returns_404(self, author_client: AsyncClient) -> None:
        resp = await author_client.get(_NODE_KINDS_URL, params={"project_id": str(UUID(int=0))})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_default_allow_reports_every_kind_writable(
        self, author_client: AsyncClient, author_user: User, test_db_session: AsyncSession
    ) -> None:
        project = await _make_project(test_db_session, "payments")
        resp = await author_client.get(_NODE_KINDS_URL, params={"project_id": str(project.id)})
        assert resp.status_code == 200, resp.text
        entries = _by_kind(resp.json())
        assert set(entries) >= {"script", "http_request", "condition", "manual_trigger", "agentic"}
        assert "internal_activity" not in entries
        for entry in entries.values():
            assert entry["can_write"] is True
            assert entry["blocked_by"] is None
        assert entries["script"]["category"] == "action"
        assert entries["condition"]["category"] == "flow_control"
        assert entries["manual_trigger"]["category"] == "trigger"

    @pytest.mark.asyncio
    async def test_project_deny_blocks_only_in_that_project(
        self, author_client: AsyncClient, author_user: User, test_db_session: AsyncSession
    ) -> None:
        db = test_db_session
        payments = await _make_project(db, "payments")
        other = await _make_project(db, "other")
        await _assign_policy(
            db,
            author_user,
            "no-scripts-in-payments",
            [_statement("deny", kind="script", scope="project")],
            payments.id,
        )

        blocked = _by_kind((await author_client.get(_NODE_KINDS_URL, params={"project_id": str(payments.id)})).json())
        assert blocked["script"]["can_write"] is False
        assert blocked["script"]["blocked_by"] == {
            "kind": "script",
            "label": "Script",
            "reason": "explicit_deny",
            "policy": "no-scripts-in-payments",
            "scope": "project",
            "project": "payments",
        }
        assert blocked["http_request"]["can_write"] is True

        elsewhere = _by_kind((await author_client.get(_NODE_KINDS_URL, params={"project_id": str(other.id)})).json())
        assert elsewhere["script"]["can_write"] is True
        assert elsewhere["script"]["blocked_by"] is None

    @pytest.mark.asyncio
    async def test_global_deny_blocks_in_every_project(
        self, author_client: AsyncClient, author_user: User, test_db_session: AsyncSession
    ) -> None:
        db = test_db_session
        first = await _make_project(db, "first")
        second = await _make_project(db, "second")
        await _assign_policy(db, author_user, "no-scripts-anywhere", [_statement("deny", kind="script")])

        for project in (first, second):
            response = await author_client.get(_NODE_KINDS_URL, params={"project_id": str(project.id)})
            entries = _by_kind(response.json())
            assert entries["script"]["can_write"] is False
            assert entries["script"]["blocked_by"] is not None
            assert entries["script"]["blocked_by"]["reason"] == "explicit_deny"
            assert entries["script"]["blocked_by"]["policy"] == "no-scripts-anywhere"
            assert entries["script"]["blocked_by"]["scope"] == "any"
            assert entries["script"]["blocked_by"]["project"] is None

    @pytest.mark.asyncio
    async def test_missing_allow_reports_no_matching_allow(
        self,
        base_client: AsyncClient,
        user_factory: Callable[..., Awaitable[User]],
        test_db_session: AsyncSession,
    ) -> None:
        """Without the built-in allow the engine default is deny, with no policy to name."""
        from syntara.api.main import app
        from syntara.auth.dependencies import get_current_user

        plain_user = await user_factory(username="no-step-author", email="no-step-author@example.com")
        # R8: an administrator changed the role assignment so the built-in
        # step-author allow no longer applies — the engine default is deny,
        # with no policy to attribute.
        auth_group = (await test_db_session.exec(select(Group).where(Group.name == AUTHENTICATED_GROUP_NAME))).first()
        assert auth_group is not None
        stale = (
            await test_db_session.exec(
                select(RoleAssignment).where(
                    RoleAssignment.role_name == "step-author", RoleAssignment.group_id == auth_group.id
                )
            )
        ).all()
        for assignment in stale:
            await test_db_session.delete(assignment)
        await test_db_session.commit()

        async def override() -> User:
            return plain_user

        app.dependency_overrides[get_current_user] = override
        try:
            project = await _make_project(test_db_session, "payments")
            resp = await base_client.get(_NODE_KINDS_URL, params={"project_id": str(project.id)})
            assert resp.status_code == 200, resp.text
            entries = _by_kind(resp.json())
            assert entries["script"]["can_write"] is False
            assert entries["script"]["blocked_by"] == {
                "kind": "script",
                "label": "Script",
                "reason": "no_matching_allow",
                "policy": None,
                "scope": None,
                "project": "payments",
            }
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    @pytest.mark.asyncio
    async def test_admin_with_deny_is_denied(
        self, auth_client: AsyncClient, test_user: User, test_db_session: AsyncSession
    ) -> None:
        """There is no admin exemption: a deny beats the admin's grants."""
        db = test_db_session
        project = await _make_project(db, "payments")
        await _assign_policy(db, test_user, "deny-scripts-for-admin", [_statement("deny", kind="script")])
        entries = _by_kind((await auth_client.get(_NODE_KINDS_URL, params={"project_id": str(project.id)})).json())
        assert entries["script"]["can_write"] is False
        assert entries["script"]["blocked_by"]["policy"] == "deny-scripts-for-admin"

    @pytest.mark.asyncio
    async def test_no_kill_switch_write_route(self, author_client: AsyncClient) -> None:
        """The 1750-era kill switch is not ported: only GET exists."""
        resp = await author_client.put(f"{_NODE_KINDS_URL}/script/enabled", json={"enabled": False})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_one_request_evaluates_every_step_type(
        self, author_client: AsyncClient, author_user: User, test_db_session: AsyncSession
    ) -> None:
        """Every registered kind appears exactly once, in registry declaration order."""
        project = await _make_project(test_db_session, "payments")
        resp = await author_client.get(_NODE_KINDS_URL, params={"project_id": str(project.id)})
        kinds = [entry["kind"] for entry in resp.json()]
        assert len(kinds) == len(set(kinds))
        from syntara.workflows.node_kinds_router import _ALL_GRANTABLE_KINDS

        assert kinds == list(_ALL_GRANTABLE_KINDS)
