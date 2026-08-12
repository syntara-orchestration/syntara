"""Contract tests for the nested /integrations/{integration_id}/tools/* endpoints.

Covers list, get, and update scoped to a single integration, including the IDOR
guard that a tool belonging to a different integration is not accessible through
another integration's path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
import pytest_asyncio

from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.integration_configuration import (
    LLMProviderConfiguration,
    LLMProviderHint,
    MCPServerConfiguration,
)

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User
    from syntara.tool_manager.models import Tool
    from tests.integration.helpers.tool_manager import ToolFactory


@pytest_asyncio.fixture
async def llm_provider_integration(test_db_session: AsyncSession, test_user: User) -> Integration:
    """An LLM provider integration, used to verify type mismatch guard on tool endpoints."""
    integration = Integration(
        name=f"llm-provider-{uuid4().hex[:8]}",
        integration_type=IntegrationType.LLM_PROVIDER,
        configuration=LLMProviderConfiguration(
            integration_type="llm_provider",
            provider_hint=LLMProviderHint.OPENAI,
        ),
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    test_db_session.add(integration)
    await test_db_session.commit()
    return integration


@pytest_asyncio.fixture
async def other_mcp_integration(test_db_session: AsyncSession, test_user: User) -> Integration:
    """A second MCP integration, used to prove tools are scoped to their own integration."""
    integration = Integration(
        name=f"other-provider-{uuid4().hex[:8]}",
        integration_type=IntegrationType.MCP_SERVER,
        configuration=MCPServerConfiguration(
            integration_type="mcp_server",
            base_url="http://localhost:8080",
        ),
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    test_db_session.add(integration)
    await test_db_session.commit()
    return integration


class TestListIntegrationTools:
    """Nested list endpoint: GET /integrations/{integration_id}/tools."""

    @pytest.mark.asyncio
    async def test_list_returns_tools_for_the_integration(
        self, jwt_client: AsyncClient, test_mcp_integration: Integration, tool_factory: ToolFactory
    ) -> None:
        tools = await tool_factory.create_bulk_tools(count=3)

        response = await jwt_client.get(f"/api/v1/integrations/{test_mcp_integration.id}/tools")

        assert response.status_code == 200
        data = response.json()
        assert "resources" in data
        returned_ids = {row["id"] for row in data["resources"]}
        for tool in tools:
            assert str(tool.id) in returned_ids
        for row in data["resources"]:
            assert row["integration_id"] == str(test_mcp_integration.id)

    @pytest.mark.asyncio
    async def test_list_unknown_integration_returns_404(self, jwt_client: AsyncClient) -> None:
        response = await jwt_client.get(f"/api/v1/integrations/{uuid4()}/tools")
        assert response.status_code == 404


class TestGetIntegrationTool:
    """Nested get endpoint: GET /integrations/{integration_id}/tools/{tool_id}."""

    @pytest.mark.asyncio
    async def test_get_scoped_tool_success(
        self, jwt_client: AsyncClient, test_mcp_integration: Integration, test_tool: Tool
    ) -> None:
        response = await jwt_client.get(f"/api/v1/integrations/{test_mcp_integration.id}/tools/{test_tool.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_tool.id)
        assert data["integration_id"] == str(test_mcp_integration.id)

    @pytest.mark.asyncio
    async def test_get_tool_from_another_integration_returns_404(
        self, jwt_client: AsyncClient, other_mcp_integration: Integration, test_tool: Tool
    ) -> None:
        # test_tool belongs to test_mcp_integration, not other_mcp_integration -> IDOR guard -> 404
        response = await jwt_client.get(f"/api/v1/integrations/{other_mcp_integration.id}/tools/{test_tool.id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_unknown_tool_returns_404(
        self, jwt_client: AsyncClient, test_mcp_integration: Integration
    ) -> None:
        response = await jwt_client.get(f"/api/v1/integrations/{test_mcp_integration.id}/tools/{uuid4()}")
        assert response.status_code == 404


class TestUpdateIntegrationTool:
    """Nested update endpoint: PATCH /integrations/{integration_id}/tools/{tool_id}."""

    @pytest.mark.asyncio
    async def test_update_scoped_tool_disable_success(
        self, jwt_client: AsyncClient, test_mcp_integration: Integration, test_tool: Tool
    ) -> None:
        response = await jwt_client.patch(
            f"/api/v1/integrations/{test_mcp_integration.id}/tools/{test_tool.id}", json={"enabled": False}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_tool.id)
        assert data["enabled"] is False

    @pytest.mark.asyncio
    async def test_update_scoped_tool_enable_success(
        self, jwt_client: AsyncClient, test_mcp_integration: Integration, test_tool: Tool
    ) -> None:
        response = await jwt_client.patch(
            f"/api/v1/integrations/{test_mcp_integration.id}/tools/{test_tool.id}", json={"enabled": True}
        )

        assert response.status_code == 200
        assert response.json()["enabled"] is True

    @pytest.mark.asyncio
    async def test_update_tool_from_another_integration_returns_404(
        self, jwt_client: AsyncClient, other_mcp_integration: Integration, test_tool: Tool
    ) -> None:
        response = await jwt_client.patch(
            f"/api/v1/integrations/{other_mcp_integration.id}/tools/{test_tool.id}", json={"enabled": False}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_unknown_tool_returns_404(
        self, jwt_client: AsyncClient, test_mcp_integration: Integration
    ) -> None:
        response = await jwt_client.patch(
            f"/api/v1/integrations/{test_mcp_integration.id}/tools/{uuid4()}", json={"enabled": False}
        )
        assert response.status_code == 404


class TestBulkUpdateIntegrationTools:
    """Nested bulk update endpoint: PATCH /integrations/{integration_id}/tools/bulk_update."""

    @pytest.mark.asyncio
    async def test_bulk_update_idor_skips_tools_from_another_integration(
        self,
        jwt_client: AsyncClient,
        test_mcp_integration: Integration,
        other_mcp_integration: Integration,
        tool_factory: ToolFactory,
    ) -> None:
        tools = await tool_factory.create_bulk_tools(count=2)
        tool_ids = [str(t.id) for t in tools]

        response = await jwt_client.patch(
            f"/api/v1/integrations/{other_mcp_integration.id}/tools/bulk_update",
            json={"tool_ids": tool_ids, "enabled": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["updated_count"] == 0
        assert data["skipped_count"] == len(tool_ids)


class TestIntegrationTypeMismatch:
    """Endpoints require an MCP_SERVER integration; other types return 422."""

    @pytest.mark.asyncio
    async def test_list_tools_wrong_integration_type(
        self, jwt_client: AsyncClient, llm_provider_integration: Integration
    ) -> None:
        response = await jwt_client.get(f"/api/v1/integrations/{llm_provider_integration.id}/tools")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_tool_wrong_integration_type(
        self, jwt_client: AsyncClient, llm_provider_integration: Integration, test_tool: Tool
    ) -> None:
        response = await jwt_client.get(f"/api/v1/integrations/{llm_provider_integration.id}/tools/{test_tool.id}")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_tool_wrong_integration_type(
        self, jwt_client: AsyncClient, llm_provider_integration: Integration, test_tool: Tool
    ) -> None:
        response = await jwt_client.patch(
            f"/api/v1/integrations/{llm_provider_integration.id}/tools/{test_tool.id}",
            json={"enabled": False},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_bulk_update_tools_wrong_integration_type(
        self, jwt_client: AsyncClient, llm_provider_integration: Integration, test_tool: Tool
    ) -> None:
        response = await jwt_client.patch(
            f"/api/v1/integrations/{llm_provider_integration.id}/tools/bulk_update",
            json={"tool_ids": [str(test_tool.id)], "enabled": False},
        )
        assert response.status_code == 422
