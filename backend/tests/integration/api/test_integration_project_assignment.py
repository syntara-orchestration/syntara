"""Integration tests for the integration project assignment endpoints.

Tests the full HTTP lifecycle for:
  POST   /integrations/{id}/projects/{project_id}   (assign)
  DELETE /integrations/{id}/projects/{project_id}   (unassign)
  GET    /integrations/{id}/projects                (list)

Permission enforcement: assign/unassign require integration:update (admin only).
Listing requires integration:read (via VisibilityFilter).
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models import Project
from syntara.core.models import User
from syntara.integrations.models.integration import IntegrationProjectAssignment
from tests.integration.api.conftest import (
    make_admin,
    make_auditor,
    make_project_admin,
    make_project_user,
    make_user_role,
    mcp_payload,
)

BASE_URL = "/api/v1/integrations"


async def _create_project(session: AsyncSession, name: str | None = None) -> Project:
    project = Project(name=name or f"pa-proj-{uuid4().hex[:8]}", description="Test project")
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def _admin_setup(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
    *,
    scope: str = "project",
    assign: bool = False,
) -> tuple[User, Project, str]:
    """Create admin, project, and integration. Optionally assign the project."""
    admin = await user_factory(username=f"pa-adm-{uuid4().hex[:6]}", email=f"pa-adm-{uuid4().hex[:6]}@test.com")
    await make_admin(test_db_session, admin)
    auth_as(admin)

    project = await _create_project(test_db_session)

    resp = await auth_client.post(BASE_URL, json=mcp_payload(scope=scope))
    assert resp.status_code == 201
    integration_id: str = resp.json()["id"]

    if assign:
        resp = await auth_client.post(f"{BASE_URL}/{integration_id}/projects/{project.id}")
        assert resp.status_code == 201

    return admin, project, integration_id


# ---------------------------------------------------------------------------
# Two-project setup for cross-project visibility tests
# ---------------------------------------------------------------------------


async def _two_project_setup(
    auth_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> tuple[User, Project, Project, str]:
    """Create admin, two projects, and an integration assigned to both."""
    admin = await user_factory(username=f"pa-2p-{uuid4().hex[:6]}", email=f"pa-2p-{uuid4().hex[:6]}@test.com")
    await make_admin(test_db_session, admin)
    auth_as(admin)

    project_a = await _create_project(test_db_session, name=f"pa-a-{uuid4().hex[:8]}")
    project_b = await _create_project(test_db_session, name=f"pa-b-{uuid4().hex[:8]}")

    resp = await auth_client.post(BASE_URL, json=mcp_payload(scope="project"))
    assert resp.status_code == 201
    integration_id: str = resp.json()["id"]

    await auth_client.post(f"{BASE_URL}/{integration_id}/projects/{project_a.id}")
    await auth_client.post(f"{BASE_URL}/{integration_id}/projects/{project_b.id}")

    return admin, project_a, project_b, integration_id


class TestProjectAssignmentLifecycle:
    """Full HTTP lifecycle: create integration -> assign -> list -> unassign."""

    async def test_assign_list_unassign_lifecycle(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        _, project, integration_id = await _admin_setup(auth_client, test_db_session, user_factory, auth_as)

        resp = await auth_client.post(f"{BASE_URL}/{integration_id}/projects/{project.id}")
        assert resp.status_code == 201
        body = resp.json()
        assert body["project_id"] == str(project.id)
        assert body["project_name"] == project.name
        assert "created_at" in body

        row = (
            await test_db_session.exec(
                select(IntegrationProjectAssignment).where(
                    IntegrationProjectAssignment.integration_id == integration_id,
                    IntegrationProjectAssignment.project_id == project.id,
                )
            )
        ).one_or_none()
        assert row is not None

        resp = await auth_client.get(f"{BASE_URL}/{integration_id}/projects")
        assert resp.status_code == 200
        resources = resp.json()["resources"]
        assert len(resources) == 1
        assert resources[0]["project_id"] == str(project.id)

        resp = await auth_client.delete(f"{BASE_URL}/{integration_id}/projects/{project.id}")
        assert resp.status_code == 204

        row = (
            await test_db_session.exec(
                select(IntegrationProjectAssignment).where(
                    IntegrationProjectAssignment.integration_id == integration_id,
                    IntegrationProjectAssignment.project_id == project.id,
                )
            )
        ).one_or_none()
        assert row is None

        resp = await auth_client.get(f"{BASE_URL}/{integration_id}/projects")
        assert resp.status_code == 200
        assert len(resp.json()["resources"]) == 0

    async def test_assign_idempotent(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        _, project, integration_id = await _admin_setup(auth_client, test_db_session, user_factory, auth_as)

        resp1 = await auth_client.post(f"{BASE_URL}/{integration_id}/projects/{project.id}")
        assert resp1.status_code == 201
        resp2 = await auth_client.post(f"{BASE_URL}/{integration_id}/projects/{project.id}")
        assert resp2.status_code == 201

        dt1 = datetime.fromisoformat(resp1.json()["created_at"])
        dt2 = datetime.fromisoformat(resp2.json()["created_at"])
        assert dt1 == dt2
        assert (datetime.now(UTC) - dt1).total_seconds() < 60

    async def test_unassign_idempotent(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        _, _, integration_id = await _admin_setup(auth_client, test_db_session, user_factory, auth_as)

        resp = await auth_client.delete(f"{BASE_URL}/{integration_id}/projects/{uuid4()}")
        assert resp.status_code == 204

    async def test_project_ids_in_get_response(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        _, project, integration_id = await _admin_setup(
            auth_client, test_db_session, user_factory, auth_as, assign=True
        )

        resp = await auth_client.get(f"{BASE_URL}/{integration_id}")
        assert resp.status_code == 200
        assert resp.json()["project_ids"] == [str(project.id)]


class TestProjectAssignmentScopeErrors:
    """Scope enforcement: cannot assign projects to global-scoped integrations."""

    async def test_assign_to_global_scoped_returns_422(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        _, project, integration_id = await _admin_setup(
            auth_client, test_db_session, user_factory, auth_as, scope="global"
        )

        resp = await auth_client.post(f"{BASE_URL}/{integration_id}/projects/{project.id}")
        assert resp.status_code == 422
        assert "global-scoped" in resp.json()["detail"]

    async def test_assign_nonexistent_project_returns_404(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        _, _, integration_id = await _admin_setup(auth_client, test_db_session, user_factory, auth_as)

        resp = await auth_client.post(f"{BASE_URL}/{integration_id}/projects/{uuid4()}")
        assert resp.status_code == 404
        assert "project" in resp.json()["detail"].lower()

    async def test_assign_nonexistent_integration_returns_404(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        admin = await user_factory(username=f"pa-nei-{uuid4().hex[:6]}", email=f"pa-nei-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        project = await _create_project(test_db_session)

        resp = await auth_client.post(f"{BASE_URL}/{uuid4()}/projects/{project.id}")
        assert resp.status_code == 404
        assert "integration" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Permission tests: non-admin roles cannot assign/unassign
# ---------------------------------------------------------------------------

_ROLE_MAKERS: dict[str, Any] = {
    "user": lambda session, user, _project: make_user_role(session, user),
    "auditor": lambda session, user, _project: make_auditor(session, user),
    "project-admin": lambda session, user, project: make_project_admin(session, user, project),
    "project-user": lambda session, user, project: make_project_user(session, user, project),
}


@pytest.mark.parametrize("role", ["user", "auditor", "project-admin", "project-user"])
class TestNonAdminCannotMutateAssignments:
    """Non-admin roles (user, auditor, project-admin, project-user) cannot assign/unassign."""

    async def test_cannot_assign_project(
        self,
        role: str,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        _, project, integration_id = await _admin_setup(auth_client, test_db_session, user_factory, auth_as)

        limited_user = await user_factory(
            username=f"pa-{role[:3]}-{uuid4().hex[:6]}", email=f"pa-{role[:3]}-{uuid4().hex[:6]}@test.com"
        )
        await _ROLE_MAKERS[role](test_db_session, limited_user, project)
        auth_as(limited_user)

        resp = await auth_client.post(f"{BASE_URL}/{integration_id}/projects/{project.id}")
        assert resp.status_code == 403

    async def test_cannot_unassign_project(
        self,
        role: str,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        _, project, integration_id = await _admin_setup(
            auth_client, test_db_session, user_factory, auth_as, assign=True
        )

        limited_user = await user_factory(
            username=f"pa-{role[:3]}-{uuid4().hex[:6]}", email=f"pa-{role[:3]}-{uuid4().hex[:6]}@test.com"
        )
        await _ROLE_MAKERS[role](test_db_session, limited_user, project)
        auth_as(limited_user)

        resp = await auth_client.delete(f"{BASE_URL}/{integration_id}/projects/{project.id}")
        assert resp.status_code == 403


class TestAuditorCanListAssignments:
    """Auditors have read access to project assignments."""

    async def test_auditor_can_list_integration_projects(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        _, _, integration_id = await _admin_setup(auth_client, test_db_session, user_factory, auth_as, assign=True)

        auditor = await user_factory(username=f"pa-aud-{uuid4().hex[:6]}", email=f"pa-aud-{uuid4().hex[:6]}@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.get(f"{BASE_URL}/{integration_id}/projects")
        assert resp.status_code == 200
        assert len(resp.json()["resources"]) >= 1


class TestCrossProjectVisibility:
    """Project-user on Project A cannot see Project B's data."""

    async def test_project_user_only_sees_own_project_assignments(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        _, project_a, project_b, integration_id = await _two_project_setup(
            auth_client, test_db_session, user_factory, auth_as
        )

        user_a = await user_factory(username=f"pa-xpu-{uuid4().hex[:6]}", email=f"pa-xpu-{uuid4().hex[:6]}@test.com")
        await make_project_user(test_db_session, user_a, project_a)
        auth_as(user_a)

        resp = await auth_client.get(f"{BASE_URL}/{integration_id}/projects")
        assert resp.status_code == 200
        returned_project_ids = {r["project_id"] for r in resp.json()["resources"]}
        assert str(project_a.id) in returned_project_ids
        assert str(project_b.id) not in returned_project_ids

    async def test_project_ids_filtered_on_get(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        _, project_a, _, integration_id = await _two_project_setup(auth_client, test_db_session, user_factory, auth_as)

        user_a = await user_factory(username=f"pa-fpgu-{uuid4().hex[:6]}", email=f"pa-fpgu-{uuid4().hex[:6]}@test.com")
        await make_project_user(test_db_session, user_a, project_a)
        auth_as(user_a)

        resp = await auth_client.get(f"{BASE_URL}/{integration_id}")
        assert resp.status_code == 200
        assert resp.json()["project_ids"] == [str(project_a.id)]

    async def test_project_ids_filtered_on_list(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        _, project_a, _, integration_id = await _two_project_setup(auth_client, test_db_session, user_factory, auth_as)

        user_a = await user_factory(username=f"pa-fplu-{uuid4().hex[:6]}", email=f"pa-fplu-{uuid4().hex[:6]}@test.com")
        await make_project_user(test_db_session, user_a, project_a)
        auth_as(user_a)

        resp = await auth_client.get(BASE_URL)
        assert resp.status_code == 200
        matching = [r for r in resp.json()["resources"] if r["id"] == integration_id]
        assert len(matching) == 1
        assert matching[0]["project_ids"] == [str(project_a.id)]
