"""Visibility tests for the list_invocations endpoint.

Verifies that the VisibilityFilter added to GET /invocations correctly
scopes results by project. Currently invocation:read is admin-only, so
the VisibilityFilter provides defense-in-depth — if project-scoped roles
gain invocation:read in the future, results will be properly scoped.

Tests here focus on:
  - Admin sees all invocations across all projects (unrestricted visibility)
  - Non-admin roles (user, auditor, no-role) are denied access (403)
  - Service-level filtering returns only invocations from allowed projects
"""

from collections.abc import Awaitable, Callable
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models.invocation import Invocation, InvocationStatus
from syntara.agent_orchestrator.services import InvocationService
from syntara.authz.engine import AllowedProjectsResult
from syntara.authz.models import Project
from syntara.core.models import User
from tests.integration.api.conftest import (
    make_admin,
    make_auditor,
    make_user_role,
)

BASE_URL = "/api/v1/invocations"


async def _create_invocation(
    session: AsyncSession,
    *,
    project_id: str,
    created_by: str,
    prompt: str = "test prompt",
    session_id: str | None = None,
) -> Invocation:
    """Insert an invocation directly into the database."""
    inv = Invocation(
        project_id=project_id,
        created_by=created_by,
        prompt=prompt,
        session_id=session_id or f"vis-test-{uuid4().hex[:8]}",
        status=InvocationStatus.COMPLETED,
    )
    session.add(inv)
    await session.commit()
    await session.refresh(inv)
    return inv


class TestAdminVisibility:
    """Admin sees all invocations regardless of project."""

    @pytest.mark.asyncio
    async def test_admin_sees_invocations_across_projects(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        admin = await user_factory(username=f"vis-adm-{uuid4().hex[:6]}", email=f"vis-adm-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)

        project_a = Project(name=f"vis-a-{uuid4().hex[:8]}", description="A")
        project_b = Project(name=f"vis-b-{uuid4().hex[:8]}", description="B")
        test_db_session.add(project_a)
        test_db_session.add(project_b)
        await test_db_session.commit()
        await test_db_session.refresh(project_a)
        await test_db_session.refresh(project_b)

        session_tag = f"adm-vis-{uuid4().hex[:8]}"
        inv_a = await _create_invocation(
            test_db_session,
            project_id=str(project_a.id),
            created_by=str(admin.id),
            session_id=session_tag,
        )
        inv_b = await _create_invocation(
            test_db_session,
            project_id=str(project_b.id),
            created_by=str(admin.id),
            session_id=session_tag,
        )

        auth_as(admin)
        resp = await auth_client.get(f"{BASE_URL}?session_id={session_tag}")
        assert resp.status_code == 200
        ids = {r["id"] for r in resp.json()["resources"]}
        assert str(inv_a.id) in ids
        assert str(inv_b.id) in ids

    @pytest.mark.asyncio
    async def test_admin_sees_empty_list_when_no_invocations(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        admin = await user_factory(username=f"vis-adm2-{uuid4().hex[:6]}", email=f"vis-adm2-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.get(f"{BASE_URL}?session_id=nonexistent-{uuid4().hex[:8]}")
        assert resp.status_code == 200
        assert resp.json()["resources"] == []


class TestNonAdminDenied:
    """Non-admin roles are denied access to invocations (invocation:read is admin-only)."""

    @pytest.mark.asyncio
    async def test_user_role_gets_403(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        user = await user_factory(username=f"vis-usr-{uuid4().hex[:6]}", email=f"vis-usr-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.get(BASE_URL)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_auditor_gets_403(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        auditor = await user_factory(username=f"vis-aud-{uuid4().hex[:6]}", email=f"vis-aud-{uuid4().hex[:6]}@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.get(BASE_URL)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_no_role_gets_403(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        user = await user_factory(username=f"vis-nr-{uuid4().hex[:6]}", email=f"vis-nr-{uuid4().hex[:6]}@test.com")
        auth_as(user)

        resp = await auth_client.get(BASE_URL)
        assert resp.status_code == 403


class TestServiceLevelFiltering:
    """Verify allowed_projects filtering at the service layer actually scopes results."""

    @pytest.mark.asyncio
    async def test_restricted_projects_returns_only_matching_invocations(
        self,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
    ) -> None:
        user = await user_factory(username=f"vis-svc-{uuid4().hex[:6]}", email=f"vis-svc-{uuid4().hex[:6]}@test.com")
        service = InvocationService(test_db_session, user)

        project_a = Project(name=f"vis-svc-a-{uuid4().hex[:8]}", description="A")
        project_b = Project(name=f"vis-svc-b-{uuid4().hex[:8]}", description="B")
        test_db_session.add(project_a)
        test_db_session.add(project_b)
        await test_db_session.commit()
        await test_db_session.refresh(project_a)
        await test_db_session.refresh(project_b)

        session_tag = f"svc-vis-{uuid4().hex[:8]}"
        inv_a = await _create_invocation(
            test_db_session,
            project_id=str(project_a.id),
            created_by=str(user.id),
            session_id=session_tag,
        )
        await _create_invocation(
            test_db_session,
            project_id=str(project_b.id),
            created_by=str(user.id),
            session_id=session_tag,
        )

        restricted = AllowedProjectsResult(all_projects=False, project_ids=[project_a.id])
        result = await service.list_invocations(
            query_params_items=[("session_id", session_tag)],
            allowed_projects=restricted,
        )

        ids = {str(r.id) for r in result.resources}
        assert str(inv_a.id) in ids
        assert len(result.resources) == 1

    @pytest.mark.asyncio
    async def test_all_projects_returns_invocations_from_every_project(
        self,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
    ) -> None:
        user = await user_factory(username=f"vis-svc2-{uuid4().hex[:6]}", email=f"vis-svc2-{uuid4().hex[:6]}@test.com")
        service = InvocationService(test_db_session, user)

        project_a = Project(name=f"vis-svc2-a-{uuid4().hex[:8]}", description="A")
        project_b = Project(name=f"vis-svc2-b-{uuid4().hex[:8]}", description="B")
        test_db_session.add(project_a)
        test_db_session.add(project_b)
        await test_db_session.commit()
        await test_db_session.refresh(project_a)
        await test_db_session.refresh(project_b)

        session_tag = f"svc-vis2-{uuid4().hex[:8]}"
        await _create_invocation(
            test_db_session,
            project_id=str(project_a.id),
            created_by=str(user.id),
            session_id=session_tag,
        )
        await _create_invocation(
            test_db_session,
            project_id=str(project_b.id),
            created_by=str(user.id),
            session_id=session_tag,
        )

        unrestricted = AllowedProjectsResult(all_projects=True, project_ids=[])
        result = await service.list_invocations(
            query_params_items=[("session_id", session_tag)],
            allowed_projects=unrestricted,
        )

        assert len(result.resources) == 2

    @pytest.mark.asyncio
    async def test_empty_project_list_returns_no_invocations(
        self,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
    ) -> None:
        user = await user_factory(username=f"vis-svc3-{uuid4().hex[:6]}", email=f"vis-svc3-{uuid4().hex[:6]}@test.com")
        service = InvocationService(test_db_session, user)

        project = Project(name=f"vis-svc3-{uuid4().hex[:8]}", description="C")
        test_db_session.add(project)
        await test_db_session.commit()
        await test_db_session.refresh(project)

        session_tag = f"svc-vis3-{uuid4().hex[:8]}"
        await _create_invocation(
            test_db_session,
            project_id=str(project.id),
            created_by=str(user.id),
            session_id=session_tag,
        )

        restricted = AllowedProjectsResult(all_projects=False, project_ids=[])
        result = await service.list_invocations(
            query_params_items=[("session_id", session_tag)],
            allowed_projects=restricted,
        )

        assert len(result.resources) == 0
