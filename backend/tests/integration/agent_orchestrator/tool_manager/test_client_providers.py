"""Integration tests for ToolManagerClient MCP integrations with real backend."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.tool_manager.tool_manager_client import ToolManagerClient
from syntara.core.models import User
from syntara.integrations.models.integration import Integration, IntegrationRead, IntegrationType
from syntara.integrations.models.integration_configuration import MCPServerConfiguration


@pytest_asyncio.fixture
async def tool_manager_client(jwt_client: AsyncClient) -> ToolManagerClient:
    """Create ToolManagerClient that uses the test server with small page size.

    Uses a small page size (3) to test pagination with multiple integrations.
    """
    client = ToolManagerClient(base_url="http://test/api/v1", limit=3)
    await client.close()

    client.session = AsyncClient(
        transport=jwt_client._transport,
        base_url="http://test/api/v1",
        headers=dict(jwt_client.headers),  # Copy JWT auth headers
    )

    return client


@pytest_asyncio.fixture
async def multiple_test_mcp_integrations(test_db_session: AsyncSession, test_user: User) -> list[Integration]:
    """Create multiple MCP server integrations for testing."""
    integrations = [
        Integration(
            name="Alpha Integration",
            description="First integration for testing",
            integration_type=IntegrationType.MCP_SERVER,
            configuration=MCPServerConfiguration(
                integration_type="mcp_server",
                base_url="https://alpha.example.com",
            ),
            enabled=True,
            scope="global",
            created_by=test_user.id,
            updated_by=test_user.id,
        ),
        Integration(
            name="Beta Integration",
            description="Second integration for testing",
            integration_type=IntegrationType.MCP_SERVER,
            configuration=MCPServerConfiguration(
                integration_type="mcp_server",
                base_url="https://beta.example.com",
            ),
            enabled=False,
            scope="global",
            created_by=test_user.id,
            updated_by=test_user.id,
        ),
        Integration(
            name="Gamma Integration",
            description="Third integration for testing",
            integration_type=IntegrationType.MCP_SERVER,
            configuration=MCPServerConfiguration(
                integration_type="mcp_server",
                base_url="https://gamma.example.com",
            ),
            enabled=True,
            scope="global",
            created_by=test_user.id,
            updated_by=test_user.id,
        ),
        Integration(
            name="Delta Integration",
            description="Fourth integration for testing",
            integration_type=IntegrationType.MCP_SERVER,
            configuration=MCPServerConfiguration(
                integration_type="mcp_server",
                base_url="https://delta.example.com",
            ),
            enabled=True,
            scope="global",
            created_by=test_user.id,
            updated_by=test_user.id,
        ),
        Integration(
            name="Echo Integration",
            description="Fifth integration for testing",
            integration_type=IntegrationType.MCP_SERVER,
            configuration=MCPServerConfiguration(
                integration_type="mcp_server",
                base_url="https://echo.example.com",
            ),
            enabled=False,
            scope="global",
            created_by=test_user.id,
            updated_by=test_user.id,
        ),
        Integration(
            name="Foxtrot Integration",
            description="Sixth integration for testing",
            integration_type=IntegrationType.MCP_SERVER,
            configuration=MCPServerConfiguration(
                integration_type="mcp_server",
                base_url="https://foxtrot.example.com",
            ),
            enabled=True,
            scope="global",
            created_by=test_user.id,
            updated_by=test_user.id,
        ),
    ]

    for integration in integrations:
        test_db_session.add(integration)

    await test_db_session.commit()

    for integration in integrations:
        await test_db_session.refresh(integration)

    return integrations


class TestToolManagerClientMCPIntegrationsIntegration:
    """Integration tests for ToolManagerClient MCP integrations with real backend."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("multiple_test_mcp_integrations")
    async def test_get_all_mcp_integrations_returns_all_integrations(
        self,
        tool_manager_client: ToolManagerClient,
        multiple_test_mcp_integrations: list[Integration],
    ) -> None:
        """Test ToolManagerClient returns all MCP integrations without client-side filtering.

        Creates 6 integrations: 4 enabled + 2 disabled.
        Client should return ALL 6 integrations - filtering is done at service layer.
        """
        retrieved_integrations = await tool_manager_client.get_all_mcp_integrations()

        expected_count = len(multiple_test_mcp_integrations)

        assert len(retrieved_integrations) == expected_count

        expected_names = {i.name for i in multiple_test_mcp_integrations}
        retrieved_names = {i.name for i in retrieved_integrations}

        assert retrieved_names == expected_names

        enabled = [i for i in retrieved_integrations if i.enabled]
        disabled = [i for i in retrieved_integrations if not i.enabled]
        assert len(enabled) == 4
        assert len(disabled) == 2

        for integration in retrieved_integrations:
            assert isinstance(integration, IntegrationRead)
            assert integration.id is not None
            assert integration.name is not None
            assert integration.configuration is not None
            assert integration.created_at is not None
            assert integration.updated_at is not None
            assert integration.created_by is not None
            assert integration.integration_type == IntegrationType.MCP_SERVER
