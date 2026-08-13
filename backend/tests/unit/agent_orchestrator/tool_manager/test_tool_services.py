"""Unit tests for tool services in Agent Orchestrator.

Tests the tool discovery, retrieval, and error reporting functions
in the tool_services module.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest
from langchain_core.tools import BaseTool

from syntara.agent_orchestrator.tool_manager import tool_services
from syntara.integrations.models.integration import (
    IntegrationRead,
    IntegrationStatus,
    IntegrationType,
)
from syntara.integrations.models.integration_configuration import MCPServerConfiguration
from syntara.tool_manager.models.tool import ToolWithParameters


def _make_integration(
    name: str = "Test Integration",
    *,
    enabled: bool = True,
    status: IntegrationStatus = IntegrationStatus.AVAILABLE,
) -> IntegrationRead:
    """Create a sample IntegrationRead for testing."""
    return IntegrationRead(
        id=uuid4(),
        name=name,
        integration_type=IntegrationType.MCP_SERVER,
        enabled=enabled,
        validation_status=status,
        scope="global",
        configuration=MCPServerConfiguration(
            integration_type="mcp_server",
            base_url="http://localhost:8080",
        ),
        management_credential_id=None,
        last_validated_at=None,
        validation_error=None,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        created_by=uuid4(),
        updated_by=None,
        labels={},
    )


class TestToolServices:
    """Test tool services functions."""

    async def test_tool_discovery_functions(
        self,
        tool_manager_client: Mock,
        sample_mcp_integrations: list[IntegrationRead],
        sample_tools: list[ToolWithParameters],
    ) -> None:
        """Test that tool discovery functions work correctly."""
        # Setup mock responses
        tool_manager_client.get_all_mcp_integrations.return_value = sample_mcp_integrations
        tool_manager_client.get_all_tools.return_value = sample_tools

        # Mock the ToolManagerClient context manager
        with patch("syntara.agent_orchestrator.tool_manager.tool_services.ToolManagerClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = tool_manager_client
            mock_client_class.return_value.__aexit__.return_value = None

            # Test tool discovery functions directly
            all_integrations = await tool_services._discover_mcp_integrations()
            enabled_tools, disabled_tools = await tool_services._discover_tools()

            assert len(all_integrations) == 2  # All sample integrations returned
            assert len(enabled_tools) == 3  # 4 total tools - 1 disabled = 3 enabled
            assert len(disabled_tools) == 1  # 1 disabled tool in fixtures
            tool_manager_client.get_all_mcp_integrations.assert_called_once()
            tool_manager_client.get_all_tools.assert_called_once()

    async def test_tool_status_update_on_execution_failure(
        self, tool_manager_client: Mock, sample_tools: list[ToolWithParameters]
    ) -> None:
        """Test that tool status update function works correctly."""
        tool_manager_client.get_all_tools.return_value = sample_tools

        # Mock the ToolManagerClient context manager
        with patch("syntara.agent_orchestrator.tool_manager.tool_services.ToolManagerClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = tool_manager_client
            mock_client_class.return_value.__aexit__.return_value = None

            # Test tool status update function directly
            await tool_services.report_tool_execution_failure(tool_id=uuid4(), error_message="Connection timeout")

            tool_manager_client.update_tool_status.assert_called_once()

    async def test_discovery_failure_raises_tool_discovery_error(self, tool_manager_client: Mock) -> None:
        """Discovery must raise ToolDiscoveryError instead of returning [] on API failure."""
        from syntara.agent_orchestrator.exceptions import ToolDiscoveryError

        tool_manager_client.get_all_mcp_integrations.side_effect = ConnectionError("Tool Manager unavailable")

        # Mock the ToolManagerClient context manager
        with patch("syntara.agent_orchestrator.tool_manager.tool_services.ToolManagerClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = tool_manager_client
            mock_client_class.return_value.__aexit__.return_value = None

            with pytest.raises(
                ToolDiscoveryError,
                match=r"Failed to discover MCP integrations: ConnectionError: Tool Manager unavailable",
            ):
                await tool_services._discover_mcp_integrations()

    async def test_discover_tools_failure_raises_tool_discovery_error(self, tool_manager_client: Mock) -> None:
        """Tool discovery must raise ToolDiscoveryError instead of returning empty lists."""
        from syntara.agent_orchestrator.exceptions import ToolDiscoveryError

        tool_manager_client.get_all_tools.side_effect = ConnectionError("Tool Manager unavailable")

        with patch("syntara.agent_orchestrator.tool_manager.tool_services.ToolManagerClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = tool_manager_client
            mock_client_class.return_value.__aexit__.return_value = None

            with pytest.raises(
                ToolDiscoveryError,
                match=r"Failed to discover tools from Tool Manager: ConnectionError: Tool Manager unavailable",
            ):
                await tool_services._discover_tools()

    async def test_retrieve_tools_propagates_discovery_failure(self, tool_manager_client: Mock) -> None:
        """ToolRetriever.retrieve_tools must re-raise discovery failures after audit."""
        from syntara.agent_orchestrator.exceptions import ToolDiscoveryError

        tool_manager_client.get_all_mcp_integrations.side_effect = ConnectionError("Tool Manager unavailable")

        with patch("syntara.agent_orchestrator.tool_manager.tool_services.ToolManagerClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = tool_manager_client
            mock_client_class.return_value.__aexit__.return_value = None

            retriever = tool_services.ToolRetriever("session-abc", uuid4(), execution_id=uuid4())
            with pytest.raises(ToolDiscoveryError):
                await retriever.retrieve_tools()

    async def test_retrieve_tools_fails_when_enabled_tools_cannot_be_provisioned(
        self,
        tool_manager_client: Mock,
        sample_mcp_integrations: list[IntegrationRead],
        sample_tools: list[ToolWithParameters],
    ) -> None:
        """ALL/SELECTED must fail closed when MCP yields zero tools (connectivity/soft-skip)."""
        from syntara.agent_orchestrator.exceptions import ToolDiscoveryError

        tool_manager_client.get_all_mcp_integrations.return_value = sample_mcp_integrations
        tool_manager_client.get_all_tools.return_value = sample_tools

        with (
            patch("syntara.agent_orchestrator.tool_manager.tool_services.ToolManagerClient") as mock_client_class,
            patch(
                "syntara.agent_orchestrator.tool_manager.tool_services._retrieve_base_tools_from_integrations",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            mock_client_class.return_value.__aenter__.return_value = tool_manager_client
            mock_client_class.return_value.__aexit__.return_value = None

            retriever = tool_services.ToolRetriever("session-abc", uuid4(), execution_id=uuid4())
            with pytest.raises(
                ToolDiscoveryError,
                match=r"none could be provisioned from their owning MCP integrations \(enabled=",
            ):
                await retriever.retrieve_tools()

    async def test_retrieve_tools_fails_when_mcp_tools_do_not_match_enabled(
        self,
        tool_manager_client: Mock,
        sample_mcp_integrations: list[IntegrationRead],
        sample_tools: list[ToolWithParameters],
    ) -> None:
        """Fail closed must blame registry/match drift when MCP returned tools but 0 matched."""
        from syntara.agent_orchestrator.exceptions import ToolDiscoveryError
        from syntara.agent_orchestrator.tool_manager.types import NamespacedBaseTool

        tool_manager_client.get_all_mcp_integrations.return_value = sample_mcp_integrations
        tool_manager_client.get_all_tools.return_value = sample_tools

        # Use an owning integration ID so the scoped count is >0 (drift scenario).
        from tests.unit.agent_orchestrator.tool_manager.conftest import INTEGRATION_1_ID

        unmatched = [
            NamespacedBaseTool(
                integration_id=INTEGRATION_1_ID,
                integration_name="dev_tools",
                tool_name="unrelated_tool",
                base_tool=MagicMock(spec=BaseTool),
            )
        ]

        with (
            patch("syntara.agent_orchestrator.tool_manager.tool_services.ToolManagerClient") as mock_client_class,
            patch(
                "syntara.agent_orchestrator.tool_manager.tool_services._retrieve_base_tools_from_integrations",
                new_callable=AsyncMock,
                return_value=unmatched,
            ),
        ):
            mock_client_class.return_value.__aenter__.return_value = tool_manager_client
            mock_client_class.return_value.__aexit__.return_value = None

            retriever = tool_services.ToolRetriever("session-abc", uuid4(), execution_id=uuid4())
            with pytest.raises(
                ToolDiscoveryError,
                match=r"Owning integrations returned 1 tool\(s\) but none matched",
            ):
                await retriever.retrieve_tools()

    def test_require_provisioned_tools_distinguishes_empty_mcp_vs_zero_match(self) -> None:
        """Guard messages must distinguish MCP emptiness from post-filter zero-match."""
        from syntara.agent_orchestrator.exceptions import ToolDiscoveryError
        from syntara.agent_orchestrator.tool_manager.types import NamespacedBaseTool

        owning_integration_id = uuid4()
        other_integration_id = uuid4()
        enabled = [
            ToolWithParameters(
                id=uuid4(),
                name="code_search",
                namespaced_name="dev_tools::code_search",
                description="Search",
                integration_id=owning_integration_id,
                enabled=True,
                status="available",
                parameters=[],
                created_by=uuid4(),
            )
        ]

        # No MCP tools at all → connectivity/provisioning blame
        with pytest.raises(ToolDiscoveryError, match=r"none could be provisioned from their owning MCP"):
            tool_services._require_provisioned_tools_when_enabled(enabled, [], namespaced_tools=[])

        # Owning integration returned tools but none matched → registry drift blame
        owning_tools = [
            NamespacedBaseTool(
                integration_id=owning_integration_id,
                integration_name="dev_tools",
                tool_name="unmatched_tool",
                base_tool=MagicMock(spec=BaseTool),
            )
            for _ in range(3)
        ]
        with pytest.raises(ToolDiscoveryError, match=r"Owning integrations returned 3 tool\(s\) but none matched"):
            tool_services._require_provisioned_tools_when_enabled(enabled, [], namespaced_tools=owning_tools)

        # Only unrelated integration returned tools → still connectivity blame (owning count = 0)
        unrelated_tools = [
            NamespacedBaseTool(
                integration_id=other_integration_id,
                integration_name="other_mcp",
                tool_name="some_tool",
                base_tool=MagicMock(spec=BaseTool),
            )
        ]
        with pytest.raises(ToolDiscoveryError, match=r"none could be provisioned from their owning MCP"):
            tool_services._require_provisioned_tools_when_enabled(enabled, [], namespaced_tools=unrelated_tools)

        # No enabled tools → no raise
        tool_services._require_provisioned_tools_when_enabled([], [], namespaced_tools=[])

        # Provisioned tools present → no raise
        tool_services._require_provisioned_tools_when_enabled(enabled, [MagicMock(spec=BaseTool)], namespaced_tools=owning_tools)

    async def test_retrieve_tools_allows_empty_when_no_enabled_tools(
        self,
        tool_manager_client: Mock,
        sample_mcp_integrations: list[IntegrationRead],
    ) -> None:
        """Zero provisioned tools is OK when Tool Manager reports no enabled tools."""
        tool_manager_client.get_all_mcp_integrations.return_value = sample_mcp_integrations
        tool_manager_client.get_all_tools.return_value = []

        with (
            patch("syntara.agent_orchestrator.tool_manager.tool_services.ToolManagerClient") as mock_client_class,
            patch(
                "syntara.agent_orchestrator.tool_manager.tool_services._retrieve_base_tools_from_integrations",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            mock_client_class.return_value.__aenter__.return_value = tool_manager_client
            mock_client_class.return_value.__aexit__.return_value = None

            retriever = tool_services.ToolRetriever("session-abc", uuid4(), execution_id=uuid4())
            result = await retriever.retrieve_tools()
            assert result == []

    async def test_tool_retrieval_integration(
        self,
        tool_manager_client: Mock,
        sample_mcp_integrations: list[IntegrationRead],
        sample_tools: list[ToolWithParameters],
    ) -> None:
        """Test the full tool retrieval workflow."""
        # Setup successful responses
        tool_manager_client.get_all_mcp_integrations.return_value = sample_mcp_integrations
        tool_manager_client.get_all_tools.return_value = sample_tools

        # Mock MCP client to return some tools
        mock_tool = Mock(spec=BaseTool)
        mock_tool.name = "code_search"

        with (
            patch("syntara.agent_orchestrator.tool_manager.tool_services.ToolManagerClient") as mock_client_class,
            patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient") as mock_mcp_client_class,
        ):
            # Setup Tool Manager client
            mock_client_class.return_value.__aenter__.return_value = tool_manager_client
            mock_client_class.return_value.__aexit__.return_value = None

            # Setup MCP client (mocked at the provider level)
            mock_mcp_instance = Mock()
            mock_mcp_client_class.return_value = mock_mcp_instance
            mock_mcp_instance.get_tools = AsyncMock(return_value=[mock_tool])

            # Test the full retrieval process
            session_id = "session-abc"
            invocation_id = uuid4()
            execution_id = uuid4()
            retriever = tool_services.ToolRetriever(session_id, invocation_id, execution_id=execution_id)
            result = await retriever.retrieve_tools()

            # Should return filtered tools
            assert isinstance(result, list)
            # Verify the retrieval process was executed
            tool_manager_client.get_all_mcp_integrations.assert_called_once()
            tool_manager_client.get_all_tools.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_single_integration_error_handling(self, test_provider_factory) -> None:
        """Test that _process_single_integration returns empty list on adapter.get_base_tools() exception."""
        integration_id = uuid4()
        integration = _make_integration("Test Integration")
        integration = IntegrationRead(**{**integration.model_dump(), "id": integration_id})

        # Patch MockMCPProvider to raise exception
        with (
            patch("syntara.agent_orchestrator.tool_manager.tool_services.ToolManagerClient"),
            patch("syntara.agent_orchestrator.tool_manager.tool_services.get_provider_factory"),
            patch(
                "tests.unit.fixtures.mock_mcp_provider.MockMCPProvider.get_base_tools",
                side_effect=RuntimeError("Connection failed to MCP server"),
            ),
        ):
            # Call _process_single_integration
            result = await tool_services._process_single_integration(integration, test_provider_factory)

            # Should return empty list due to exception (no state mutation)
            assert result == []

    @pytest.mark.asyncio
    async def test_process_single_integration_error_handling_graceful(self, test_provider_factory) -> None:
        """Test graceful handling when provider raises an exception."""
        integration = _make_integration("Test Integration")

        # Patch MockMCPProvider to raise exception
        with (
            patch("syntara.agent_orchestrator.tool_manager.tool_services.ToolManagerClient"),
            patch(
                "tests.unit.fixtures.mock_mcp_provider.MockMCPProvider.get_base_tools",
                side_effect=ValueError("Invalid configuration parameter"),
            ),
        ):
            # Call _process_single_integration - should not raise exception
            result = await tool_services._process_single_integration(integration, test_provider_factory)

            # Should return empty list due to exception (no state mutation)
            assert result == []

    async def test_tool_retriever_class(
        self,
        tool_manager_client: Mock,
        sample_mcp_integrations: list[IntegrationRead],
        sample_tools: list[ToolWithParameters],
    ) -> None:
        """Test that the ToolRetriever class works correctly."""
        # Setup mock responses
        tool_manager_client.get_all_mcp_integrations.return_value = sample_mcp_integrations
        tool_manager_client.get_all_tools.return_value = sample_tools

        # Mock MCP client to return some tools
        mock_tool = Mock(spec=BaseTool)
        mock_tool.name = "code_search"

        with (
            patch("syntara.agent_orchestrator.tool_manager.tool_services.ToolManagerClient") as mock_client_class,
            patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient") as mock_mcp_client_class,
        ):
            # Setup Tool Manager client
            mock_client_class.return_value.__aenter__.return_value = tool_manager_client
            mock_client_class.return_value.__aexit__.return_value = None

            # Setup MCP client
            mock_mcp_instance = Mock()
            mock_mcp_client_class.return_value = mock_mcp_instance
            mock_mcp_instance.get_tools = AsyncMock(return_value=[mock_tool])

            # Test the ToolRetriever class
            session_id = "session-abc"
            invocation_id = uuid4()
            execution_id = uuid4()
            retriever = tool_services.ToolRetriever(session_id, invocation_id, execution_id)

            # Verify initial state
            assert retriever.invocation_id == invocation_id
            assert retriever.all_integrations == []
            assert retriever.enabled_tools == []
            assert retriever.disabled_tools == []
            assert retriever.namespaced_tools == []

            # Test retrieval
            result = await retriever.retrieve_tools()

            # Should return filtered tools and populate state
            assert isinstance(result, list)
            assert len(retriever.all_integrations) == 2
            assert len(retriever.enabled_tools) == 3
            assert len(retriever.disabled_tools) == 1

            # Should return exactly 1 filtered tool (only code_search is mocked from MCP)
            assert len(result) == 1

            # Verify that the returned BaseTool has tool_id metadata
            code_search_tool = result[0]
            assert code_search_tool.name == "code_search"
            assert hasattr(code_search_tool, "metadata")
            assert code_search_tool.metadata is not None
            assert "tool_id" in code_search_tool.metadata

            # Find the corresponding ToolWithParameters to verify the tool_id matches
            code_search_tool_data = next(tool for tool in sample_tools if tool.name == "code_search")
            expected_tool_id = str(code_search_tool_data.id)
            assert code_search_tool.metadata["tool_id"] == expected_tool_id

            # Verify the retrieval process was executed
            tool_manager_client.get_all_mcp_integrations.assert_called_once()
            tool_manager_client.get_all_tools.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_single_integration_calls_credential_resolver(self, test_provider_factory) -> None:
        """_process_single_integration calls credential_resolver with integration_id when present."""
        integration = _make_integration("auth-integration")

        credential_resolver = AsyncMock(return_value="resolved-bearer-token")

        captured_params: dict[str, Any] = {}
        original_prepare = tool_services._prepare_config_params

        def capturing_prepare(p, api_key=None) -> dict[str, Any]:
            result = original_prepare(p, api_key=api_key)
            captured_params["api_key"] = api_key
            return result

        with patch.object(tool_services, "_prepare_config_params", side_effect=capturing_prepare):
            result = await tool_services._process_single_integration(
                integration, test_provider_factory, credential_resolver
            )

        credential_resolver.assert_awaited_once_with(integration.id)
        assert captured_params["api_key"] == "resolved-bearer-token"
        assert len(result) == 1  # MockMCPProvider returns one tool (echo_tool)

    @pytest.mark.asyncio
    async def test_process_single_integration_no_resolver_no_api_key(self, test_provider_factory) -> None:
        """Without a credential_resolver, MCPProvider is instantiated without api_key (unauthenticated)."""
        integration = _make_integration("open-integration")

        captured_params: dict[str, Any] = {}
        original_prepare = tool_services._prepare_config_params

        def capturing_prepare(p, api_key=None) -> dict[str, Any]:
            result = original_prepare(p, api_key=api_key)
            captured_params["api_key"] = api_key
            return result

        with patch.object(tool_services, "_prepare_config_params", side_effect=capturing_prepare):
            result = await tool_services._process_single_integration(integration, test_provider_factory, None)

        assert captured_params["api_key"] is None
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_prepare_config_params_includes_api_key_when_provided(self) -> None:
        """_prepare_config_params injects api_key into kwargs when provided."""
        integration = _make_integration("my-integration")

        params = tool_services._prepare_config_params(integration, api_key="secret-token")
        assert params["api_key"] == "secret-token"
        assert params["base_url"] == "http://localhost:8080"
        assert params["integration_id"] == integration.id
        assert params["integration_name"] == integration.name

    @pytest.mark.asyncio
    async def test_prepare_config_params_omits_api_key_when_none(self) -> None:
        """_prepare_config_params does not include api_key key when api_key is None."""
        integration = _make_integration("my-integration")

        params = tool_services._prepare_config_params(integration, api_key=None)
        assert "api_key" not in params
