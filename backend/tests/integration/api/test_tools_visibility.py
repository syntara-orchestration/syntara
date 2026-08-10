"""Integration-scoped visibility tests for tool endpoints.

Verifies that tools inherit visibility from their parent integration:
  - Admin sees tools from all integrations
  - User (no project role) sees tools from global integrations only
  - Project-user sees tools from global + assigned project integrations
  - Authenticated user with no roles gets 403
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

TOOLS_URL = "/api/v1/tools"


async def _create_integration_with_tool(
    session: AsyncSession,
    user: User,
    *,
    scope: IntegrationScope = IntegrationScope.GLOBAL,
    tool_name: str | None = None,
) -> tuple[Integration, Tool]:
    """Create an integration with one tool and return both."""
    suffix = uuid4().hex[:8]
    integration = Integration(
        name=f"vis-intg-{suffix}",
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
        name=tool_name or f"vis-tool-{suffix}",
        integration_id=integration.id,
        namespaced_name=f"vis-{suffix}::tool",
        created_by=user.id,
    )
    session.add(tool)
    await session.commit()
    return integration, tool


async def _assign_to_project(session: AsyncSession, integration: Integration, project: Project) -> None:
    session.add(IntegrationProjectAssignment(integration_id=integration.id, project_id=project.id))
    await session.commit()


class TestNoRoleToolAccess:
    """Authenticated user with no roles gets 403 on tool endpoints."""

    async def test_no_role_cannot_list_tools(
        self,
        auth_client: AsyncClient,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        user = await user_factory(username=f"tv-nr-{uuid4().hex[:6]}", email=f"tv-nr-{uuid4().hex[:6]}@test.com")
        auth_as(user)

        resp = await auth_client.get(TOOLS_URL)
        assert resp.status_code == 403

    async def test_no_role_cannot_get_tool(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        _, tool = await _create_integration_with_tool(test_db_session, test_user)

        user = await user_factory(username=f"tv-nrg-{uuid4().hex[:6]}", email=f"tv-nrg-{uuid4().hex[:6]}@test.com")
        auth_as(user)

        resp = await auth_client.get(f"{TOOLS_URL}/{tool.id}")
        assert resp.status_code == 403


class TestAdminToolVisibility:
    """Admin sees tools from all integrations."""

    async def test_admin_sees_all_tools(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        _, global_tool = await _create_integration_with_tool(test_db_session, test_user, tool_name="admin-global-tool")
        _, project_tool = await _create_integration_with_tool(
            test_db_session, test_user, scope=IntegrationScope.PROJECT, tool_name="admin-project-tool"
        )

        admin = await user_factory(username=f"tv-adm-{uuid4().hex[:6]}", email=f"tv-adm-{uuid4().hex[:6]}@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.get(TOOLS_URL)
        assert resp.status_code == 200
        tool_ids = {r["id"] for r in resp.json()["resources"]}
        assert str(global_tool.id) in tool_ids
        assert str(project_tool.id) in tool_ids


class TestUserToolVisibility:
    """User role (no project assignments) sees only tools from global integrations."""

    async def test_user_sees_tools_from_global_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        _, global_tool = await _create_integration_with_tool(test_db_session, test_user)

        user = await user_factory(username=f"tv-ug-{uuid4().hex[:6]}", email=f"tv-ug-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.get(TOOLS_URL)
        assert resp.status_code == 200
        tool_ids = {r["id"] for r in resp.json()["resources"]}
        assert str(global_tool.id) in tool_ids

    async def test_user_cannot_see_tools_from_project_scoped_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        _, project_tool = await _create_integration_with_tool(
            test_db_session, test_user, scope=IntegrationScope.PROJECT
        )

        user = await user_factory(username=f"tv-up-{uuid4().hex[:6]}", email=f"tv-up-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.get(TOOLS_URL)
        assert resp.status_code == 200
        tool_ids = {r["id"] for r in resp.json()["resources"]}
        assert str(project_tool.id) not in tool_ids

    async def test_user_cannot_get_tool_from_project_scoped_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        _, project_tool = await _create_integration_with_tool(
            test_db_session, test_user, scope=IntegrationScope.PROJECT
        )

        user = await user_factory(username=f"tv-ugt-{uuid4().hex[:6]}", email=f"tv-ugt-{uuid4().hex[:6]}@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.get(f"{TOOLS_URL}/{project_tool.id}")
        assert resp.status_code == 404


class TestProjectUserToolVisibility:
    """Project-user sees tools from global + assigned project integrations."""

    async def test_project_user_sees_tools_from_assigned_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        project = Project(name=f"tv-proj-{uuid4().hex[:8]}")
        test_db_session.add(project)
        await test_db_session.commit()
        await test_db_session.refresh(project)

        project_int, project_tool = await _create_integration_with_tool(
            test_db_session, test_user, scope=IntegrationScope.PROJECT
        )
        await _assign_to_project(test_db_session, project_int, project)

        user = await user_factory(username=f"tv-pua-{uuid4().hex[:6]}", email=f"tv-pua-{uuid4().hex[:6]}@test.com")
        await make_project_user(test_db_session, user, project)
        auth_as(user)

        resp = await auth_client.get(TOOLS_URL)
        assert resp.status_code == 200
        tool_ids = {r["id"] for r in resp.json()["resources"]}
        assert str(project_tool.id) in tool_ids

    async def test_project_user_cannot_see_tools_from_unassigned_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        project_a = Project(name=f"tv-pa-{uuid4().hex[:8]}")
        project_b = Project(name=f"tv-pb-{uuid4().hex[:8]}")
        test_db_session.add(project_a)
        test_db_session.add(project_b)
        await test_db_session.commit()
        await test_db_session.refresh(project_a)
        await test_db_session.refresh(project_b)

        int_b, tool_b = await _create_integration_with_tool(test_db_session, test_user, scope=IntegrationScope.PROJECT)
        await _assign_to_project(test_db_session, int_b, project_b)

        user = await user_factory(username=f"tv-pun-{uuid4().hex[:6]}", email=f"tv-pun-{uuid4().hex[:6]}@test.com")
        await make_project_user(test_db_session, user, project_a)
        auth_as(user)

        resp = await auth_client.get(TOOLS_URL)
        assert resp.status_code == 200
        tool_ids = {r["id"] for r in resp.json()["resources"]}
        assert str(tool_b.id) not in tool_ids

    async def test_project_user_sees_tools_from_global_integration(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
        test_user: User,
    ) -> None:
        project = Project(name=f"tv-pg-{uuid4().hex[:8]}")
        test_db_session.add(project)
        await test_db_session.commit()
        await test_db_session.refresh(project)

        _, global_tool = await _create_integration_with_tool(test_db_session, test_user)

        user = await user_factory(username=f"tv-pug-{uuid4().hex[:6]}", email=f"tv-pug-{uuid4().hex[:6]}@test.com")
        await make_project_user(test_db_session, user, project)
        auth_as(user)

        resp = await auth_client.get(TOOLS_URL)
        assert resp.status_code == 200
        tool_ids = {r["id"] for r in resp.json()["resources"]}
        assert str(global_tool.id) in tool_ids
