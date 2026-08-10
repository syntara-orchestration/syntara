"""Integration tests for OrchestrationService._get_tools function.

Tests the private _get_tools function with real ToolManagerClient and database backend,
mocking only the MCP provider's underlying client to simulate different MCP server scenarios.
Tools now reference Integration directly (ToolProvider shim removed).
"""

import logging
from collections.abc import Callable
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.context_manager.planner import ContextManagerPlanner
from syntara.agent_orchestrator.services.orchestration_service import OrchestrationService
from syntara.agent_orchestrator.tool_manager.tool_manager_client import ToolManagerClient
from syntara.integrations.models.integration import Integration, IntegrationStatus, IntegrationType
from syntara.integrations.models.integration_configuration import MCPServerConfiguration
from syntara.tool_manager.models.tool import Tool, ToolStatus

logger = logging.getLogger(__name__)


def create_test_tool_manager_client(jwt_client: AsyncClient) -> Callable[..., ToolManagerClient]:
    """Create a ToolManagerClient that uses the same transport as jwt_client.

    This ensures the ToolManagerClient connects to the test app instead of making
    real HTTP requests, following the pattern from existing integration tests.
    """

    def _create_client(*_args: object, **_kwargs: object) -> ToolManagerClient:
        # Create the client with test URL
        client = ToolManagerClient(base_url="http://test/api/v1")
        # Replace its session with one using the test transport and auth headers
        client.session = AsyncClient(
            transport=jwt_client._transport,
            base_url="http://test/api/v1",
            headers=dict(jwt_client.headers),  # Copy JWT auth headers
        )
        return client

    return _create_client


async def _create_test_integration(
    test_db_session: AsyncSession,
    test_user,
    name: str = "test-mcp-integration",
    base_url: str = "https://fake-mcp-server:8000/mcp",
    *,
    enabled: bool = True,
    status: IntegrationStatus = IntegrationStatus.AVAILABLE,
) -> Integration:
    """Create a test Integration directly in the database."""
    integration = Integration(
        name=name,
        integration_type=IntegrationType.MCP_SERVER,
        configuration=MCPServerConfiguration(
            integration_type="mcp_server",
            base_url=base_url,
        ),
        enabled=enabled,
        validation_status=status,
        scope="global",
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    test_db_session.add(integration)
    await test_db_session.commit()
    return integration


class TestOrchestrationServiceGetTools:
    """Integration tests for OrchestrationService._get_tools function."""

    @pytest.fixture
    async def orchestration_service(self) -> OrchestrationService:
        """Create OrchestrationService with minimal dependencies."""
        llm = Mock(spec=ChatOpenAI)
        context_manager = Mock(spec=ContextManagerPlanner)
        return OrchestrationService(llm=llm, context_manager_planner=context_manager, tool_selection_strategy="ALL")

    @pytest.fixture
    async def test_integration_with_tools(
        self, jwt_client: AsyncClient, test_db_session: AsyncSession, test_user
    ) -> tuple[str, list[str]]:
        """Create a test integration with two tools - one enabled, one disabled.

        Returns:
            Tuple of (integration_id, [enabled_tool_id, disabled_tool_id])

        """
        integration = await _create_test_integration(test_db_session, test_user)
        integration_id = str(integration.id)

        # Create tools directly in the database using test session
        tool_1 = Tool(
            name="enabled_tool",
            namespaced_name=f"{integration.name}::enabled_tool",
            description="This tool is enabled",
            integration_id=integration.id,
            enabled=True,
            status=ToolStatus.AVAILABLE,
            parameters=[],
            created_by=test_user.id,
        )

        tool_2 = Tool(
            name="disabled_tool",
            namespaced_name=f"{integration.name}::disabled_tool",
            description="This tool is disabled",
            integration_id=integration.id,
            enabled=False,
            status=ToolStatus.AVAILABLE,
            parameters=[],
            created_by=test_user.id,
        )

        test_db_session.add(tool_1)
        test_db_session.add(tool_2)
        await test_db_session.commit()

        return integration_id, [str(tool_1.id), str(tool_2.id)]

    async def test_get_tools_with_missing_mcp_tools(
        self,
        orchestration_service: OrchestrationService,
        test_integration_with_tools: tuple[str, list[str]],
        jwt_client: AsyncClient,
    ) -> None:
        """Test _get_tools when MCP server returns zero tools.

        The retriever is read-only: it should return no tools but NOT
        mutate the tool or integration status in the database.
        """
        _integration_id, [enabled_tool_id, disabled_tool_id] = test_integration_with_tools
        session_id = "session-abc"
        invocation_id = uuid4()
        execution_id = uuid4()

        with (
            patch(
                "syntara.agent_orchestrator.tool_manager.tool_services.ToolManagerClient",
                create_test_tool_manager_client(jwt_client),
            ),
            patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient") as mock_mcp_client_class,
        ):
            mock_mcp_instance = Mock()
            mock_mcp_client_class.return_value = mock_mcp_instance
            mock_mcp_instance.get_tools = AsyncMock(return_value=[])  # No tools from MCP server

            result_tools = await orchestration_service._get_tools(session_id, invocation_id, execution_id)

            assert result_tools == []

            assert mock_mcp_client_class.called, "MultiServerMCPClient class should have been instantiated"
            assert mock_mcp_instance.get_tools.called, "get_tools should have been called"

            # Verify the enabled tool was NOT mutated (still available, still enabled)
            tool_response = await jwt_client.get(f"/api/v1/tools/{enabled_tool_id}")
            assert tool_response.status_code == 200
            enabled_tool = tool_response.json()

            assert enabled_tool["status"] == "available"
            assert enabled_tool["refresh_error"] is None
            assert enabled_tool["enabled"] is True

            # Verify that the disabled tool also remains unchanged
            tool_response = await jwt_client.get(f"/api/v1/tools/{disabled_tool_id}")
            assert tool_response.status_code == 200
            disabled_tool = tool_response.json()

            assert disabled_tool["status"] == "available"
            assert disabled_tool["enabled"] is False

    async def test_get_tools_with_matching_mcp_tool(
        self,
        orchestration_service: OrchestrationService,
        test_integration_with_tools: tuple[str, list[str]],
        jwt_client: AsyncClient,
    ) -> None:
        """Test _get_tools when MCP server returns the enabled tool.

        Should return the matching tool and keep it enabled.
        """
        _integration_id, [enabled_tool_id, disabled_tool_id] = test_integration_with_tools
        session_id = "session-abc"
        invocation_id = uuid4()
        execution_id = uuid4()

        mock_enabled_tool = Mock(spec=BaseTool)
        mock_enabled_tool.name = "enabled_tool"
        mock_enabled_tool.description = "This tool is enabled"

        with (
            patch(
                "syntara.agent_orchestrator.tool_manager.tool_services.ToolManagerClient",
                create_test_tool_manager_client(jwt_client),
            ),
            patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient") as mock_mcp_client_class,
        ):
            mock_mcp_instance = Mock()
            mock_mcp_client_class.return_value = mock_mcp_instance
            mock_mcp_instance.get_tools = AsyncMock(return_value=[mock_enabled_tool])

            result_tools = await orchestration_service._get_tools(session_id, invocation_id, execution_id)

            assert len(result_tools) == 1
            assert result_tools[0] is mock_enabled_tool

            tool_response = await jwt_client.get(f"/api/v1/tools/{enabled_tool_id}")
            assert tool_response.status_code == 200
            enabled_tool = tool_response.json()

            assert enabled_tool["status"] == "available"
            assert enabled_tool["enabled"] is True
            assert enabled_tool["refresh_error"] is None

            tool_response = await jwt_client.get(f"/api/v1/tools/{disabled_tool_id}")
            assert tool_response.status_code == 200
            disabled_tool = tool_response.json()

            assert disabled_tool["status"] == "available"
            assert disabled_tool["enabled"] is False  # Still disabled

    async def test_integration_not_mutated_when_mcp_server_unreachable(
        self,
        orchestration_service: OrchestrationService,
        jwt_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user,
    ) -> None:
        """Test that integration state is NOT mutated when MCP server is unreachable.

        The retriever is read-only: a connection failure should return no tools
        but leave the integration enabled and in AVAILABLE status.
        """
        integration = await _create_test_integration(
            test_db_session,
            test_user,
            name="unreachable-integration",
            base_url="https://unreachable-server:8000/mcp",
        )
        integration_id = str(integration.id)

        integration_tool = Tool(
            name="unreachable_tool",
            namespaced_name=f"{integration.name}::unreachable_tool",
            description="Tool from unreachable integration",
            integration_id=integration.id,
            enabled=True,
            status=ToolStatus.AVAILABLE,
            parameters=[],
            created_by=test_user.id,
        )

        test_db_session.add(integration_tool)
        await test_db_session.commit()

        session_id = "session-abc"
        invocation_id = uuid4()
        execution_id = uuid4()

        with (
            patch(
                "syntara.agent_orchestrator.tool_manager.tool_services.ToolManagerClient",
                create_test_tool_manager_client(jwt_client),
            ),
            patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient") as mock_mcp_client_class,
        ):
            mock_mcp_instance = Mock()
            mock_mcp_client_class.return_value = mock_mcp_instance
            mock_mcp_instance.get_tools = AsyncMock(side_effect=ConnectionError("Connection refused"))

            result_tools = await orchestration_service._get_tools(session_id, invocation_id, execution_id)

            assert result_tools == []

            # Verify the integration was NOT mutated
            integration_response = await jwt_client.get(f"/api/v1/integrations/{integration_id}")
            assert integration_response.status_code == 200
            updated_integration = integration_response.json()

            assert updated_integration["enabled"] is True  # Still enabled
            assert updated_integration["validation_status"] == "available"  # Still available
            assert updated_integration["validation_error"] is None  # No error set

            # Tool should also be untouched
            tool_response = await jwt_client.get(f"/api/v1/tools/{integration_tool.id}")
            assert tool_response.status_code == 200
            affected_tool = tool_response.json()

            assert affected_tool["enabled"] is True  # Still enabled
            assert affected_tool["status"] == "available"  # Still available
            assert affected_tool["refresh_error"] is None  # No error set
