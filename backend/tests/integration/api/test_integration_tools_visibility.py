"""Visibility tests for integration-scoped tool endpoints.

Mirrors test_tools_visibility.py but covers /integrations/{id}/tools/*
which uses _require_visible_mcp_server (a different code path from the
top-level /tools endpoints).
"""

from collections.abc import Awaitable, Callable
from uuid import uuid4

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models import Project
from syntara.core.models import User
from syntara.integrations.models.integration import (
    Integration,
    IntegrationProjectAssignment,
    IntegrationScope,
    IntegrationType,
)
from syntara.integrations.models.integration_configuration import MCPServerConfiguration
from syntara.tool_manager.models import Tool
from tests.integration.api.conftest import (
    make_admin,
    make_project_user,
    make_user_role,
)


async def _create_integration_with_tool(
    session: AsyncSession,
    user: User,
    *,
    scope: IntegrationScope = IntegrationScope.GLOBAL,
    tool_name: str | None = None,
) -> tuple[Integration, Tool]:
    suffix = uuid4().hex[:8]
    integration = Integration(
        name=f"iv-intg-{suffix}",
        integration_type=IntegrationType.MCP_SERVER,
        scope=scope,
        configuration=MCPServerConfiguration(
            integration_type="mcp_server",
            base_url="http://localhost:8080",
        ),
        created_by=user.id,
        updated_by=user.id,
    )
    session.add(integration)
    await session.flush()

    tool = Tool(
        name=tool_name or f"iv-tool-{suffix}",
        integration_id=integration.id,
        namespaced_name=f"iv-{suffix}::tool",
        created_by=user.id,
    )
    session.add(tool)
    await session.commit()
    return integration, tool


async def _assign_to_project(session: AsyncSession, integration: Integration, project: Project) -> None:
    session.add(IntegrationProjectAssignment(integration_id=integration.id, project_id=project.id))
    await session.commit()


class TestAdminIntegrationToolVisibility:
    """Admin can access integration-scoped tool endpoints for any integration."""

    async def test_admin_can_list_tools_for_any_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        integration, tool = await _create_integration_with_tool(
            test_db_session, test_user, scope=IntegrationScope.PROJECT
        )

        admin = await user_factory(username=f"iv-adm-{uuid4().hex[:6]}", email=f"iv-adm-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.get(f"/api/v1/integrations/{integration.id}/tools")
        assert resp.status_code == 200
        tool_ids = {r["id"] for r in resp.json()["resources"]}
        assert str(tool.id) in tool_ids

    async def test_admin_can_get_tool_for_any_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        integration, tool = await _create_integration_with_tool(
            test_db_session, test_user, scope=IntegrationScope.PROJECT
        )

        admin = await user_factory(username=f"iv-admg-{uuid4().hex[:6]}", email=f"iv-admg-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.get(f"/api/v1/integrations/{integration.id}/tools/{tool.id}")
        assert resp.status_code == 200


class TestUserIntegrationToolVisibility:
    """User role (no project assignments) sees integration-scoped tools from global integrations only."""

    async def test_user_can_list_tools_for_global_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        integration, _tool = await _create_integration_with_tool(test_db_session, test_user)

        user = await user_factory(username=f"iv-ug-{uuid4().hex[:6]}", email=f"iv-ug-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.get(f"/api/v1/integrations/{integration.id}/tools")
        assert resp.status_code == 200

    async def test_user_cannot_access_project_scoped_integration_tools(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        integration, _tool = await _create_integration_with_tool(
            test_db_session, test_user, scope=IntegrationScope.PROJECT
        )

        user = await user_factory(username=f"iv-up-{uuid4().hex[:6]}", email=f"iv-up-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.get(f"/api/v1/integrations/{integration.id}/tools")
        assert resp.status_code == 404

    async def test_user_cannot_get_tool_from_project_scoped_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        integration, tool = await _create_integration_with_tool(
            test_db_session, test_user, scope=IntegrationScope.PROJECT
        )

        user = await user_factory(username=f"iv-ugt-{uuid4().hex[:6]}", email=f"iv-ugt-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.get(f"/api/v1/integrations/{integration.id}/tools/{tool.id}")
        assert resp.status_code == 404


class TestProjectUserIntegrationToolVisibility:
    """Project-user sees integration-scoped tools from global + assigned project integrations."""

    async def test_project_user_can_access_assigned_integration_tools(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        project = Project(name=f"iv-proj-{uuid4().hex[:8]}")
        test_db_session.add(project)
        await test_db_session.commit()
        await test_db_session.refresh(project)

        integration, tool = await _create_integration_with_tool(
            test_db_session, test_user, scope=IntegrationScope.PROJECT
        )
        await _assign_to_project(test_db_session, integration, project)

        user = await user_factory(username=f"iv-pua-{uuid4().hex[:6]}", email=f"iv-pua-{uuid4().hex[:6]}@test.com")
        await make_project_user(test_db_session, user, project)
        auth_as(user)

        resp = await auth_client.get(f"/api/v1/integrations/{integration.id}/tools")
        assert resp.status_code == 200
        tool_ids = {r["id"] for r in resp.json()["resources"]}
        assert str(tool.id) in tool_ids

    async def test_project_user_cannot_access_unassigned_integration_tools(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        project_a = Project(name=f"iv-pa-{uuid4().hex[:8]}")
        project_b = Project(name=f"iv-pb-{uuid4().hex[:8]}")
        test_db_session.add(project_a)
        test_db_session.add(project_b)
        await test_db_session.commit()
        await test_db_session.refresh(project_a)
        await test_db_session.refresh(project_b)

        integration_b, _tool_b = await _create_integration_with_tool(
            test_db_session, test_user, scope=IntegrationScope.PROJECT
        )
        await _assign_to_project(test_db_session, integration_b, project_b)

        user = await user_factory(username=f"iv-pun-{uuid4().hex[:6]}", email=f"iv-pun-{uuid4().hex[:6]}@test.com")
        await make_project_user(test_db_session, user, project_a)
        auth_as(user)

        resp = await auth_client.get(f"/api/v1/integrations/{integration_b.id}/tools")
        assert resp.status_code == 404

    async def test_project_user_can_access_global_integration_tools(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        project = Project(name=f"iv-pg-{uuid4().hex[:8]}")
        test_db_session.add(project)
        await test_db_session.commit()
        await test_db_session.refresh(project)

        integration, tool = await _create_integration_with_tool(test_db_session, test_user)

        user = await user_factory(username=f"iv-pug-{uuid4().hex[:6]}", email=f"iv-pug-{uuid4().hex[:6]}@test.com")
        await make_project_user(test_db_session, user, project)
        auth_as(user)

        resp = await auth_client.get(f"/api/v1/integrations/{integration.id}/tools")
        assert resp.status_code == 200
        tool_ids = {r["id"] for r in resp.json()["resources"]}
        assert str(tool.id) in tool_ids
