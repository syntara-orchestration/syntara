"""Role-based authorization tests for the integrations endpoints.

Tests the permission matrix for the integrations resource:
  - read      (list, get): admin, auditor, user (global); project-user/admin/auditor (project-scoped)
  - read-all  (visibility): admin, auditor only — grants unrestricted visibility
  - create:                  admin only
  - update:                  admin only
  - delete:                  admin only

Users with the 'user' role see global-scoped integrations only (they have
integration:read but not integration:read-all). Project-role users see global
integrations plus project-scoped integrations assigned to their projects.
Admins and auditors have unrestricted read access. Authenticated users with
no roles are denied access (403).
"""

from collections.abc import Awaitable, Callable
from uuid import uuid4

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models import Project
from syntara.core.models import User
from syntara.integrations.models.integration import IntegrationProjectAssignment, IntegrationScope
from tests.integration.api.conftest import (
    make_admin,
    make_auditor,
    make_project_user,
    make_user_role,
    mcp_payload,
)

BASE_URL = "/api/v1/integrations"


# ============================================================================
# No role (authenticated only) — denied all access
# ============================================================================


class TestNoRolePermissions:
    """Authenticated user with no roles is denied all integration access."""

    async def test_no_role_cannot_list(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        user = await user_factory(username=f"nr-lst-{uuid4().hex[:6]}", email=f"nr-lst-{uuid4().hex[:6]}@test.com")
        auth_as(user)

        resp = await auth_client.get(BASE_URL)
        assert resp.status_code == 403

    async def test_no_role_cannot_get(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        admin = await user_factory(username=f"nr-adm-{uuid4().hex[:6]}", email=f"nr-adm-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        resp = await auth_client.post(BASE_URL, json=mcp_payload())
        assert resp.status_code == 201
        integration_id = resp.json()["id"]

        user = await user_factory(username=f"nr-get-{uuid4().hex[:6]}", email=f"nr-get-{uuid4().hex[:6]}@test.com")
        auth_as(user)
        resp = await auth_client.get(f"{BASE_URL}/{integration_id}")
        assert resp.status_code == 403


# ============================================================================
# User role — can see global integrations, denied mutations
# ============================================================================


class TestUserPermissions:
    """User role sees global-scoped integrations but cannot mutate them."""

    async def test_user_can_list_global_integrations(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """User role can list integrations and sees global-scoped ones."""
        admin = await user_factory(username=f"ai-lst-{uuid4().hex[:6]}", email=f"ai-lst-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        resp = await auth_client.post(BASE_URL, json=mcp_payload())
        assert resp.status_code == 201

        user = await user_factory(username=f"ui-list-{uuid4().hex[:6]}", email=f"ui-list-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.get(BASE_URL)
        assert resp.status_code == 200
        resources = resp.json()["resources"]
        assert len(resources) >= 1
        assert all(r["scope"] == IntegrationScope.GLOBAL for r in resources)

    async def test_user_cannot_create(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """User role cannot create an integration."""
        user = await user_factory(username=f"ui-crt-{uuid4().hex[:6]}", email=f"ui-crt-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.post(BASE_URL, json=mcp_payload())
        assert resp.status_code == 403

    async def test_user_can_get_global_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """User role can retrieve a global-scoped integration by ID."""
        admin = await user_factory(username=f"ai-get-{uuid4().hex[:6]}", email=f"ai-get-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        resp = await auth_client.post(BASE_URL, json=mcp_payload())
        assert resp.status_code == 201
        integration_id = resp.json()["id"]

        user = await user_factory(username=f"ui-get-{uuid4().hex[:6]}", email=f"ui-get-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)
        resp = await auth_client.get(f"{BASE_URL}/{integration_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == integration_id

    async def test_user_cannot_get_project_scoped_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """User role without project assignment cannot see a project-scoped integration."""
        admin = await user_factory(username=f"ai-psc-{uuid4().hex[:6]}", email=f"ai-psc-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        resp = await auth_client.post(BASE_URL, json=mcp_payload(scope="project"))
        assert resp.status_code == 201
        integration_id = resp.json()["id"]

        user = await user_factory(username=f"ui-psc-{uuid4().hex[:6]}", email=f"ui-psc-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)
        resp = await auth_client.get(f"{BASE_URL}/{integration_id}")
        assert resp.status_code == 404

    async def test_user_cannot_patch(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """User role cannot update an integration."""
        admin = await user_factory(username=f"ai-ptch-{uuid4().hex[:6]}", email=f"ai-ptch-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        resp = await auth_client.post(BASE_URL, json=mcp_payload())
        assert resp.status_code == 201
        integration_id = resp.json()["id"]

        user = await user_factory(username=f"ui-ptch-{uuid4().hex[:6]}", email=f"ui-ptch-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)
        resp = await auth_client.patch(f"{BASE_URL}/{integration_id}", json={"enabled": False})
        assert resp.status_code == 403

    async def test_user_cannot_delete(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """User role cannot delete an integration."""
        admin = await user_factory(username=f"ai-del-{uuid4().hex[:6]}", email=f"ai-del-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        resp = await auth_client.post(BASE_URL, json=mcp_payload())
        assert resp.status_code == 201
        integration_id = resp.json()["id"]

        user = await user_factory(username=f"ui-del-{uuid4().hex[:6]}", email=f"ui-del-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)
        resp = await auth_client.delete(f"{BASE_URL}/{integration_id}")
        assert resp.status_code == 403


# ============================================================================
# Auditor role — read-only access
# ============================================================================


class TestAuditorPermissions:
    """Auditor role can read integrations but cannot mutate them."""

    async def test_auditor_can_list(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Auditor can list integrations."""
        auditor = await user_factory(username=f"aud-lst-{uuid4().hex[:6]}", email=f"aud-lst-{uuid4().hex[:6]}@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.get(BASE_URL)
        assert resp.status_code == 200

    async def test_auditor_can_get(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Auditor can retrieve an integration by ID."""
        admin = await user_factory(username=f"ai-aget-{uuid4().hex[:6]}", email=f"ai-aget-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        resp = await auth_client.post(BASE_URL, json=mcp_payload())
        assert resp.status_code == 201
        integration_id = resp.json()["id"]

        auditor = await user_factory(username=f"aud-get-{uuid4().hex[:6]}", email=f"aud-get-{uuid4().hex[:6]}@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)
        resp = await auth_client.get(f"{BASE_URL}/{integration_id}")
        assert resp.status_code == 200

    async def test_auditor_cannot_create(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Auditor cannot create an integration."""
        auditor = await user_factory(username=f"aud-crt-{uuid4().hex[:6]}", email=f"aud-crt-{uuid4().hex[:6]}@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.post(BASE_URL, json=mcp_payload())
        assert resp.status_code == 403

    async def test_auditor_cannot_patch(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Auditor cannot update an integration."""
        admin = await user_factory(username=f"ai-aptch-{uuid4().hex[:6]}", email=f"ai-aptch-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        resp = await auth_client.post(BASE_URL, json=mcp_payload())
        assert resp.status_code == 201
        integration_id = resp.json()["id"]

        auditor = await user_factory(
            username=f"aud-ptch-{uuid4().hex[:6]}", email=f"aud-ptch-{uuid4().hex[:6]}@test.com"
        )
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)
        resp = await auth_client.patch(f"{BASE_URL}/{integration_id}", json={"enabled": False})
        assert resp.status_code == 403

    async def test_auditor_cannot_delete(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Auditor cannot delete an integration."""
        admin = await user_factory(username=f"ai-adel-{uuid4().hex[:6]}", email=f"ai-adel-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        resp = await auth_client.post(BASE_URL, json=mcp_payload())
        assert resp.status_code == 201
        integration_id = resp.json()["id"]

        auditor = await user_factory(username=f"aud-del-{uuid4().hex[:6]}", email=f"aud-del-{uuid4().hex[:6]}@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)
        resp = await auth_client.delete(f"{BASE_URL}/{integration_id}")
        assert resp.status_code == 403


# ============================================================================
# Project-scoped user — sees global + assigned project integrations
# ============================================================================


class TestProjectUserPermissions:
    """Project-user role sees global integrations plus project-scoped integrations for their projects."""

    async def test_project_user_can_list_global_integrations(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Project-user can list and sees global integrations."""
        admin = await user_factory(username=f"ai-pul-{uuid4().hex[:6]}", email=f"ai-pul-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        resp = await auth_client.post(BASE_URL, json=mcp_payload())
        assert resp.status_code == 201

        project = Project(name=f"proj-pu-{uuid4().hex[:8]}", description="test")
        test_db_session.add(project)
        await test_db_session.commit()
        await test_db_session.refresh(project)

        user = await user_factory(username=f"pu-lst-{uuid4().hex[:6]}", email=f"pu-lst-{uuid4().hex[:6]}@test.com")
        await make_project_user(test_db_session, user, project)
        auth_as(user)

        resp = await auth_client.get(BASE_URL)
        assert resp.status_code == 200
        resources = resp.json()["resources"]
        assert len(resources) >= 1

    async def test_project_user_can_see_assigned_project_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Project-user sees project-scoped integrations assigned to their project."""
        admin = await user_factory(username=f"ai-pua-{uuid4().hex[:6]}", email=f"ai-pua-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        resp = await auth_client.post(BASE_URL, json=mcp_payload(scope="project"))
        assert resp.status_code == 201
        integration_id = resp.json()["id"]

        project = Project(name=f"proj-pua-{uuid4().hex[:8]}", description="test")
        test_db_session.add(project)
        await test_db_session.commit()
        await test_db_session.refresh(project)

        assignment = IntegrationProjectAssignment(
            integration_id=integration_id,
            project_id=project.id,
        )
        test_db_session.add(assignment)
        await test_db_session.commit()

        user = await user_factory(username=f"pu-asg-{uuid4().hex[:6]}", email=f"pu-asg-{uuid4().hex[:6]}@test.com")
        await make_project_user(test_db_session, user, project)
        auth_as(user)

        resp = await auth_client.get(f"{BASE_URL}/{integration_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == integration_id

    async def test_project_user_cannot_see_unassigned_project_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Project-user cannot see project-scoped integrations assigned to other projects."""
        admin = await user_factory(username=f"ai-pun-{uuid4().hex[:6]}", email=f"ai-pun-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        resp = await auth_client.post(BASE_URL, json=mcp_payload(scope="project"))
        assert resp.status_code == 201
        integration_id = resp.json()["id"]

        project_a = Project(name=f"proj-a-{uuid4().hex[:8]}", description="project A")
        project_b = Project(name=f"proj-b-{uuid4().hex[:8]}", description="project B")
        test_db_session.add(project_a)
        test_db_session.add(project_b)
        await test_db_session.commit()
        await test_db_session.refresh(project_a)
        await test_db_session.refresh(project_b)

        assignment = IntegrationProjectAssignment(
            integration_id=integration_id,
            project_id=project_b.id,
        )
        test_db_session.add(assignment)
        await test_db_session.commit()

        user = await user_factory(username=f"pu-una-{uuid4().hex[:6]}", email=f"pu-una-{uuid4().hex[:6]}@test.com")
        await make_project_user(test_db_session, user, project_a)
        auth_as(user)

        resp = await auth_client.get(f"{BASE_URL}/{integration_id}")
        assert resp.status_code == 404

    async def test_project_user_list_excludes_unassigned_project_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Project-user list response excludes project-scoped integrations assigned to other projects."""
        admin = await user_factory(username=f"ai-pul2-{uuid4().hex[:6]}", email=f"ai-pul2-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)
        resp = await auth_client.post(BASE_URL, json=mcp_payload(scope="project"))
        assert resp.status_code == 201
        integration_id = resp.json()["id"]

        project_a = Project(name=f"proj-la-{uuid4().hex[:8]}", description="project A")
        project_b = Project(name=f"proj-lb-{uuid4().hex[:8]}", description="project B")
        test_db_session.add(project_a)
        test_db_session.add(project_b)
        await test_db_session.commit()
        await test_db_session.refresh(project_a)
        await test_db_session.refresh(project_b)

        assignment = IntegrationProjectAssignment(
            integration_id=integration_id,
            project_id=project_b.id,
        )
        test_db_session.add(assignment)
        await test_db_session.commit()

        user = await user_factory(username=f"pu-lst2-{uuid4().hex[:6]}", email=f"pu-lst2-{uuid4().hex[:6]}@test.com")
        await make_project_user(test_db_session, user, project_a)
        auth_as(user)

        resp = await auth_client.get(BASE_URL)
        assert resp.status_code == 200
        ids = [r["id"] for r in resp.json()["resources"]]
        assert integration_id not in ids
