"""Role-based authorization tests for the tool_manager endpoints.

Tests the permission matrix for the tool resource:
  - read  (list, get): user, auditor, admin
  - update (patch, bulk_update): admin only
  - unauthenticated: 401 on all endpoints
"""

from collections.abc import Awaitable, Callable
from uuid import uuid4

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.integrations.models.integration import Integration
from syntara.tool_manager.models import Tool
from tests.integration.api.conftest import (
    make_admin,
    make_auditor,
    make_user_role,
)

BASE_URL = "/api/v1/tools"
INTEGRATION_TOOLS_URL = "/api/v1/integrations/{integration_id}/tools"


# ============================================================================
# User role — read access, no update access
# ============================================================================


class TestUserRolePermissions:
    """Regular users can read tools but cannot update them."""

    async def test_user_can_list_tools(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """User role can list tools."""
        user = await user_factory(username=f"u-lst-{uuid4().hex[:6]}", email=f"u-lst-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.get(BASE_URL)
        assert resp.status_code == 200
        assert isinstance(resp.json()["resources"], list)

    async def test_user_can_get_tool(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """User role can retrieve a tool by ID."""
        user = await user_factory(username=f"u-get-{uuid4().hex[:6]}", email=f"u-get-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.get(f"{BASE_URL}/{test_tool.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == str(test_tool.id)

    async def test_user_cannot_patch_tool(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """User role cannot update a tool."""
        user = await user_factory(username=f"u-ptch-{uuid4().hex[:6]}", email=f"u-ptch-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.patch(f"{BASE_URL}/{test_tool.id}", json={"enabled": False})
        assert resp.status_code == 403

    async def test_user_cannot_bulk_update_tools(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """User role cannot bulk-update tools."""
        user = await user_factory(username=f"u-blk-{uuid4().hex[:6]}", email=f"u-blk-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.patch(
            f"/api/v1/integrations/{test_tool.integration_id}/tools/bulk_update",
            json={"tool_ids": [str(test_tool.id)], "enabled": False},
        )
        assert resp.status_code == 403


# ============================================================================
# Auditor role — read-only access
# ============================================================================


class TestAuditorPermissions:
    """Auditor role can read tools but cannot update them."""

    async def test_auditor_can_list_tools(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Auditor can list tools."""
        auditor = await user_factory(username=f"aud-lst-{uuid4().hex[:6]}", email=f"aud-lst-{uuid4().hex[:6]}@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.get(BASE_URL)
        assert resp.status_code == 200

    async def test_auditor_can_get_tool(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Auditor can retrieve a tool by ID."""
        auditor = await user_factory(username=f"aud-get-{uuid4().hex[:6]}", email=f"aud-get-{uuid4().hex[:6]}@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.get(f"{BASE_URL}/{test_tool.id}")
        assert resp.status_code == 200

    async def test_auditor_cannot_patch_tool(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Auditor cannot update a tool."""
        auditor = await user_factory(
            username=f"aud-ptch-{uuid4().hex[:6]}", email=f"aud-ptch-{uuid4().hex[:6]}@test.com"
        )
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.patch(f"{BASE_URL}/{test_tool.id}", json={"enabled": False})
        assert resp.status_code == 403

    async def test_auditor_cannot_bulk_update_tools(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Auditor cannot bulk-update tools."""
        auditor = await user_factory(username=f"aud-blk-{uuid4().hex[:6]}", email=f"aud-blk-{uuid4().hex[:6]}@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.patch(
            f"/api/v1/integrations/{test_tool.integration_id}/tools/bulk_update",
            json={"tool_ids": [str(test_tool.id)], "enabled": False},
        )
        assert resp.status_code == 403


# ============================================================================
# Admin role — full access
# ============================================================================


class TestAdminPermissions:
    """Admin has full read and update access to tool endpoints."""

    async def test_admin_can_list_tools(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Admin can list tools."""
        admin = await user_factory(username=f"adm-lst-{uuid4().hex[:6]}", email=f"adm-lst-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.get(BASE_URL)
        assert resp.status_code == 200

    async def test_admin_can_get_tool(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Admin can retrieve a tool by ID."""
        admin = await user_factory(username=f"adm-get-{uuid4().hex[:6]}", email=f"adm-get-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.get(f"{BASE_URL}/{test_tool.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == str(test_tool.id)

    async def test_admin_can_patch_tool(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Admin can update a tool."""
        admin = await user_factory(username=f"adm-ptch-{uuid4().hex[:6]}", email=f"adm-ptch-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.patch(f"{BASE_URL}/{test_tool.id}", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    async def test_admin_can_bulk_update_tools(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Admin can bulk-update tools."""
        admin = await user_factory(username=f"adm-blk-{uuid4().hex[:6]}", email=f"adm-blk-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.patch(
            f"/api/v1/integrations/{test_tool.integration_id}/tools/bulk_update",
            json={"tool_ids": [str(test_tool.id)], "enabled": False},
        )
        assert resp.status_code == 200


# ============================================================================
# Unauthenticated — all endpoints return 401
# ============================================================================


class TestUnauthenticatedAccess:
    """All tool endpoints require authentication."""

    async def test_unauthenticated_cannot_list_tools(
        self,
        base_client: AsyncClient,
    ) -> None:
        """Unauthenticated request to list tools returns 401."""
        resp = await base_client.get(BASE_URL)
        assert resp.status_code == 401

    async def test_unauthenticated_cannot_get_tool(
        self,
        base_client: AsyncClient,
        test_tool: Tool,
    ) -> None:
        """Unauthenticated request to get a tool returns 401."""
        resp = await base_client.get(f"{BASE_URL}/{test_tool.id}")
        assert resp.status_code == 401

    async def test_unauthenticated_cannot_patch_tool(
        self,
        base_client: AsyncClient,
        test_tool: Tool,
    ) -> None:
        """Unauthenticated request to patch a tool returns 401."""
        resp = await base_client.patch(f"{BASE_URL}/{test_tool.id}", json={"enabled": False})
        assert resp.status_code == 401

    async def test_unauthenticated_cannot_bulk_update_tools(
        self,
        base_client: AsyncClient,
        test_tool: Tool,
    ) -> None:
        """Unauthenticated request to bulk-update tools returns 401."""
        resp = await base_client.patch(
            f"/api/v1/integrations/{test_tool.integration_id}/tools/bulk_update",
            json={"tool_ids": [str(test_tool.id)], "enabled": False},
        )
        assert resp.status_code == 401


# ============================================================================
# Integration-scoped tool list RBAC
# ============================================================================


class TestIntegrationScopedListToolsAuthz:
    """RBAC for GET /integrations/{integration_id}/tools."""

    async def test_user_can_list_integration_tools(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_mcp_integration: Integration,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        user = await user_factory(username=f"it-usr-{uuid4().hex[:6]}", email=f"it-usr-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.get(INTEGRATION_TOOLS_URL.format(integration_id=test_mcp_integration.id))
        assert resp.status_code == 200

    async def test_auditor_can_list_integration_tools(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_mcp_integration: Integration,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        auditor = await user_factory(username=f"it-aud-{uuid4().hex[:6]}", email=f"it-aud-{uuid4().hex[:6]}@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.get(INTEGRATION_TOOLS_URL.format(integration_id=test_mcp_integration.id))
        assert resp.status_code == 200

    async def test_admin_can_list_integration_tools(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_mcp_integration: Integration,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        admin = await user_factory(username=f"it-adm-{uuid4().hex[:6]}", email=f"it-adm-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.get(INTEGRATION_TOOLS_URL.format(integration_id=test_mcp_integration.id))
        assert resp.status_code == 200

    async def test_unauthenticated_cannot_list_integration_tools(
        self,
        base_client: AsyncClient,
        test_mcp_integration: Integration,
    ) -> None:
        resp = await base_client.get(INTEGRATION_TOOLS_URL.format(integration_id=test_mcp_integration.id))
        assert resp.status_code == 401


class TestIntegrationScopedGetToolAuthz:
    """RBAC for GET /integrations/{integration_id}/tools/{tool_id}."""

    async def test_user_can_get_integration_tool(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_mcp_integration: Integration,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        user = await user_factory(username=f"itg-usr-{uuid4().hex[:6]}", email=f"itg-usr-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.get(
            f"{INTEGRATION_TOOLS_URL.format(integration_id=test_mcp_integration.id)}/{test_tool.id}"
        )
        assert resp.status_code == 200

    async def test_auditor_can_get_integration_tool(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_mcp_integration: Integration,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        auditor = await user_factory(username=f"itg-aud-{uuid4().hex[:6]}", email=f"itg-aud-{uuid4().hex[:6]}@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.get(
            f"{INTEGRATION_TOOLS_URL.format(integration_id=test_mcp_integration.id)}/{test_tool.id}"
        )
        assert resp.status_code == 200

    async def test_admin_can_get_integration_tool(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_mcp_integration: Integration,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        admin = await user_factory(username=f"itg-adm-{uuid4().hex[:6]}", email=f"itg-adm-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.get(
            f"{INTEGRATION_TOOLS_URL.format(integration_id=test_mcp_integration.id)}/{test_tool.id}"
        )
        assert resp.status_code == 200

    async def test_unauthenticated_cannot_get_integration_tool(
        self,
        base_client: AsyncClient,
        test_tool: Tool,
        test_mcp_integration: Integration,
    ) -> None:
        resp = await base_client.get(
            f"{INTEGRATION_TOOLS_URL.format(integration_id=test_mcp_integration.id)}/{test_tool.id}"
        )
        assert resp.status_code == 401


class TestIntegrationScopedUpdateToolAuthz:
    """RBAC for PATCH /integrations/{integration_id}/tools/{tool_id}."""

    async def test_user_cannot_update_integration_tool(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_mcp_integration: Integration,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        user = await user_factory(username=f"itu-usr-{uuid4().hex[:6]}", email=f"itu-usr-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.patch(
            f"{INTEGRATION_TOOLS_URL.format(integration_id=test_mcp_integration.id)}/{test_tool.id}",
            json={"enabled": False},
        )
        assert resp.status_code == 403

    async def test_auditor_cannot_update_integration_tool(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_mcp_integration: Integration,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        auditor = await user_factory(username=f"itu-aud-{uuid4().hex[:6]}", email=f"itu-aud-{uuid4().hex[:6]}@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.patch(
            f"{INTEGRATION_TOOLS_URL.format(integration_id=test_mcp_integration.id)}/{test_tool.id}",
            json={"enabled": False},
        )
        assert resp.status_code == 403

    async def test_admin_can_update_integration_tool(
        self,
        auth_client: AsyncClient,
        test_tool: Tool,
        test_mcp_integration: Integration,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        admin = await user_factory(username=f"itu-adm-{uuid4().hex[:6]}", email=f"itu-adm-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.patch(
            f"{INTEGRATION_TOOLS_URL.format(integration_id=test_mcp_integration.id)}/{test_tool.id}",
            json={"enabled": False},
        )
        assert resp.status_code == 200

    async def test_unauthenticated_cannot_update_integration_tool(
        self,
        base_client: AsyncClient,
        test_tool: Tool,
        test_mcp_integration: Integration,
    ) -> None:
        resp = await base_client.patch(
            f"{INTEGRATION_TOOLS_URL.format(integration_id=test_mcp_integration.id)}/{test_tool.id}",
            json={"enabled": False},
        )
        assert resp.status_code == 401
