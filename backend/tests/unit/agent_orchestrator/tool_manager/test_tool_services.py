"""Unit tests for tool services in Agent Orchestrator.

Tests the tool discovery, retrieval, and error reporting functions
in the tool_services module.
"""

import re
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
                match=r"owning MCP integrations returned no tools",
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
        from tests.unit.agent_orchestrator.tool_manager.conftest import INTEGRATION_1_ID

        # Single owning integration so soft-skip of a sibling owner cannot flip the message.
        single_owner_tools = [t for t in sample_tools if t.integration_id == INTEGRATION_1_ID]
        tool_manager_client.get_all_mcp_integrations.return_value = sample_mcp_integrations
        tool_manager_client.get_all_tools.return_value = single_owner_tools

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
                match=r"owning integrations returned 1 tool\(s\) but none matched",
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
        with pytest.raises(ToolDiscoveryError, match=r"owning MCP integrations returned no tools"):
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
        with pytest.raises(ToolDiscoveryError, match=r"owning integrations returned 3 tool\(s\) but none matched"):
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
        with pytest.raises(ToolDiscoveryError, match=r"owning MCP integrations returned no tools"):
            tool_services._require_provisioned_tools_when_enabled(enabled, [], namespaced_tools=unrelated_tools)

        # ALL with no enabled tools → no raise
        tool_services._require_provisioned_tools_when_enabled([], [], namespaced_tools=[])

        # Provisioned tools present → no raise
        tool_services._require_provisioned_tools_when_enabled(
            enabled, [MagicMock(spec=BaseTool)], namespaced_tools=owning_tools
        )

    def test_require_provisioned_tools_mixed_soft_skip_and_unmatched_sibling(self) -> None:
        """Multi-owner: soft-skipped A + unmatched tools from B must not pure-blame drift."""
        from syntara.agent_orchestrator.exceptions import ToolDiscoveryError
        from syntara.agent_orchestrator.tool_manager.types import NamespacedBaseTool

        integration_a = uuid4()
        integration_b = uuid4()
        enabled = [
            ToolWithParameters(
                id=uuid4(),
                name="tool_a",
                namespaced_name="mcp_a::tool_a",
                description="A",
                integration_id=integration_a,
                enabled=True,
                status="available",
                parameters=[],
                created_by=uuid4(),
            ),
            ToolWithParameters(
                id=uuid4(),
                name="tool_b",
                namespaced_name="mcp_b::tool_b",
                description="B",
                integration_id=integration_b,
                enabled=True,
                status="available",
                parameters=[],
                created_by=uuid4(),
            ),
        ]
        # A soft-skipped (no tools); B returned unmatched tools only
        sibling_unmatched = [
            NamespacedBaseTool(
                integration_id=integration_b,
                integration_name="mcp_b",
                tool_name="unrelated_on_b",
                base_tool=MagicMock(spec=BaseTool),
            )
        ]
        with pytest.raises(
            ToolDiscoveryError,
            match=r"one or more owning MCP integrations returned no tools while others returned 1 unmatched",
        ):
            tool_services._require_provisioned_tools_when_enabled(enabled, [], namespaced_tools=sibling_unmatched)

    def test_require_provisioned_tools_selected_total_soft_skip_raises_selection_unavailable(
        self,
    ) -> None:
        """SELECTED zero-provision via soft-skip must raise ToolSelectionUnavailableError with IDs and cause."""
        from syntara.agent_orchestrator.exceptions import ToolSelectionUnavailableError

        owning_integration_id = uuid4()
        enabled_tool_id = uuid4()
        selected_ids = [str(enabled_tool_id)]
        enabled = [
            ToolWithParameters(
                id=enabled_tool_id,
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
        # Total soft-skip (no MCP tools) → connectivity cause scoped to the selected owner
        with pytest.raises(
            ToolSelectionUnavailableError,
            match=rf"unavailable tool IDs: {re.escape(str(selected_ids))}",
        ) as exc_info:
            tool_services._require_provisioned_tools_when_enabled(
                enabled,
                [],
                namespaced_tools=[],
                tool_selection_strategy="SELECTED",
                tool_selections=set(selected_ids),
            )
        assert "check integration connectivity" in str(exc_info.value)
        assert "missing from the enabled catalog" not in str(exc_info.value)

    def test_require_provisioned_tools_selected_with_drift_includes_drift_cause(
        self,
    ) -> None:
        """SELECTED zero-provision via registry drift must include drift diagnostic."""
        from syntara.agent_orchestrator.exceptions import ToolSelectionUnavailableError
        from syntara.agent_orchestrator.tool_manager.types import NamespacedBaseTool

        owning_integration_id = uuid4()
        enabled_tool_id = uuid4()
        selected_ids = [str(enabled_tool_id)]
        enabled = [
            ToolWithParameters(
                id=enabled_tool_id,
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
        # Owning integration returned tools but none matched enabled entries
        owning_unmatched = [
            NamespacedBaseTool(
                integration_id=owning_integration_id,
                integration_name="dev_tools",
                tool_name="unmatched_tool",
                base_tool=MagicMock(spec=BaseTool),
            )
            for _ in range(2)
        ]
        with pytest.raises(
            ToolSelectionUnavailableError,
            match=rf"unavailable tool IDs: {re.escape(str(selected_ids))}",
        ) as exc_info:
            tool_services._require_provisioned_tools_when_enabled(
                enabled,
                [],
                namespaced_tools=owning_unmatched,
                tool_selection_strategy="SELECTED",
                tool_selections=set(selected_ids),
            )
        assert "check registry name/integration_id drift" in str(exc_info.value)
        assert "missing from the enabled catalog" not in str(exc_info.value)

    def test_require_provisioned_tools_selected_empty_provision_catalog_miss(
        self,
    ) -> None:
        """SELECTED IDs absent from the catalog must not blame an unrelated enabled owner."""
        from syntara.agent_orchestrator.exceptions import ToolSelectionUnavailableError

        missing_selected_id = str(uuid4())
        enabled = [
            ToolWithParameters(
                id=uuid4(),
                name="code_search",
                namespaced_name="dev_tools::code_search",
                description="Search",
                integration_id=uuid4(),
                enabled=True,
                status="available",
                parameters=[],
                created_by=uuid4(),
            )
        ]
        with pytest.raises(ToolSelectionUnavailableError) as exc_info:
            tool_services._require_provisioned_tools_when_enabled(
                enabled,
                [],
                namespaced_tools=[],
                tool_selection_strategy="SELECTED",
                tool_selections={missing_selected_id},
            )
        msg = str(exc_info.value)
        assert missing_selected_id in msg
        assert "missing from the enabled catalog" in msg
        assert "check integration connectivity" not in msg
        assert "unmatched" not in msg
        assert "none matched" not in msg

    def test_require_provisioned_tools_selected_empty_enabled_catalog(
        self,
    ) -> None:
        """SELECTED with zero enabled tools must catalog-miss, not skip the guard."""
        from syntara.agent_orchestrator.exceptions import ToolSelectionUnavailableError

        selected_ids = [str(uuid4())]
        with pytest.raises(ToolSelectionUnavailableError) as exc_info:
            tool_services._require_provisioned_tools_when_enabled(
                [],
                [],
                namespaced_tools=[],
                tool_selection_strategy="SELECTED",
                tool_selections=set(selected_ids),
            )
        msg = str(exc_info.value)
        assert selected_ids[0] in msg
        assert "missing from the enabled catalog" in msg
        assert "Enabled tools could not be provisioned" not in msg
        assert "unmatched" not in msg
        assert "none matched" not in msg

    def test_require_provisioned_tools_selected_sibling_provision_scopes_cause(
        self,
    ) -> None:
        """SELECTED with a provisioned sibling must not blame that sibling as unmatched."""
        from syntara.agent_orchestrator.exceptions import ToolSelectionUnavailableError
        from syntara.agent_orchestrator.tool_manager.types import NamespacedBaseTool

        integration_a = uuid4()
        integration_b = uuid4()
        tool_a_id = uuid4()
        tool_b_id = uuid4()
        enabled = [
            ToolWithParameters(
                id=tool_a_id,
                name="tool_a",
                namespaced_name="mcp_a::tool_a",
                description="A",
                integration_id=integration_a,
                enabled=True,
                status="available",
                parameters=[],
                created_by=uuid4(),
            ),
            ToolWithParameters(
                id=tool_b_id,
                name="tool_b",
                namespaced_name="mcp_b::tool_b",
                description="B",
                integration_id=integration_b,
                enabled=True,
                status="available",
                parameters=[],
                created_by=uuid4(),
            ),
        ]
        provisioned_b = MagicMock(spec=BaseTool)
        provisioned_b.metadata = {"tool_id": str(tool_b_id)}
        namespaced_b_matched = [
            NamespacedBaseTool(
                integration_id=integration_b,
                integration_name="mcp_b",
                tool_name="tool_b",
                base_tool=MagicMock(spec=BaseTool),
            )
        ]

        with pytest.raises(ToolSelectionUnavailableError) as exc_info:
            tool_services._require_provisioned_tools_when_enabled(
                enabled,
                [provisioned_b],
                namespaced_tools=namespaced_b_matched,
                tool_selection_strategy="SELECTED",
                tool_selections={str(tool_a_id)},
            )

        msg = str(exc_info.value)
        assert str(tool_a_id) in msg
        assert "selected tools were not among provisioned tools" in msg
        assert "check integration connectivity" in msg
        assert "unmatched" not in msg
        assert "none matched" not in msg

    def test_require_provisioned_tools_selected_sibling_missing_from_catalog(
        self,
    ) -> None:
        """SELECTED IDs absent from the enabled catalog must not use ALL zero-match wording."""
        from syntara.agent_orchestrator.exceptions import ToolSelectionUnavailableError
        from syntara.agent_orchestrator.tool_manager.types import NamespacedBaseTool

        integration_b = uuid4()
        tool_b_id = uuid4()
        missing_selected_id = str(uuid4())
        enabled = [
            ToolWithParameters(
                id=tool_b_id,
                name="tool_b",
                namespaced_name="mcp_b::tool_b",
                description="B",
                integration_id=integration_b,
                enabled=True,
                status="available",
                parameters=[],
                created_by=uuid4(),
            )
        ]
        provisioned_b = MagicMock(spec=BaseTool)
        provisioned_b.metadata = {"tool_id": str(tool_b_id)}
        namespaced_b_matched = [
            NamespacedBaseTool(
                integration_id=integration_b,
                integration_name="mcp_b",
                tool_name="tool_b",
                base_tool=MagicMock(spec=BaseTool),
            )
        ]

        with pytest.raises(ToolSelectionUnavailableError) as exc_info:
            tool_services._require_provisioned_tools_when_enabled(
                enabled,
                [provisioned_b],
                namespaced_tools=namespaced_b_matched,
                tool_selection_strategy="SELECTED",
                tool_selections={missing_selected_id},
            )

        msg = str(exc_info.value)
        assert missing_selected_id in msg
        assert "missing from the enabled catalog" in msg
        assert "unmatched" not in msg
        assert "none matched" not in msg

    async def test_retrieve_tools_selected_soft_skip_raises_selection_unavailable(
        self,
        tool_manager_client: Mock,
        sample_mcp_integrations: list[IntegrationRead],
        sample_tools: list[ToolWithParameters],
    ) -> None:
        """SELECTED + total soft-skip must raise ToolSelectionUnavailableError (not ToolDiscoveryError)."""
        from syntara.agent_orchestrator.exceptions import ToolSelectionUnavailableError

        tool_manager_client.get_all_mcp_integrations.return_value = sample_mcp_integrations
        tool_manager_client.get_all_tools.return_value = sample_tools
        enabled_tool = next(tool for tool in sample_tools if tool.enabled)
        selected_ids = [str(enabled_tool.id)]

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
                ToolSelectionUnavailableError,
                match=rf"unavailable tool IDs: {re.escape(str(selected_ids))}",
            ):
                await retriever.retrieve_tools(
                    tool_selection_strategy="SELECTED",
                    tool_selections=set(selected_ids),
                )

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

    async def test_retrieve_tools_selected_empty_enabled_catalog_raises(
        self,
        tool_manager_client: Mock,
        sample_mcp_integrations: list[IntegrationRead],
    ) -> None:
        """SELECTED must not COMPLETED+return [] when Tool Manager has no enabled tools."""
        from syntara.agent_orchestrator.exceptions import ToolSelectionUnavailableError

        tool_manager_client.get_all_mcp_integrations.return_value = sample_mcp_integrations
        tool_manager_client.get_all_tools.return_value = []
        selected_ids = [str(uuid4())]

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
            with pytest.raises(ToolSelectionUnavailableError) as exc_info:
                await retriever.retrieve_tools(
                    tool_selection_strategy="SELECTED",
                    tool_selections=set(selected_ids),
                )
            msg = str(exc_info.value)
            assert selected_ids[0] in msg
            assert "missing from the enabled catalog" in msg

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

    @pytest.mark.ssrf_enforced
    @pytest.mark.asyncio
    async def test_process_single_integration_blocks_rebound_base_url_before_dispatch(self) -> None:
        """Request-time SSRF re-check blocks a rebound/metadata base_url before adapter dispatch.

        The stored base_url may be re-pointed to a private/metadata address after write time
        (DNS rebinding). _process_single_integration re-runs the SSRF policy BEFORE creating the
        provider adapter; a block raises ValueError that is caught and the integration is skipped.
        If the re-check is removed, create_provider_instance would run against 169.254.169.254 --
        so the assert_not_called() below is what actually guards this call site.
        """
        integration = _make_integration("rebound-mcp")
        integration = IntegrationRead(
            **{
                **integration.model_dump(),
                "configuration": MCPServerConfiguration(
                    integration_type="mcp_server",
                    base_url="https://169.254.169.254",
                ),
            }
        )

        # MagicMock so create_provider_instance is a tracked mock and is_registered("mcp") is truthy.
        provider_factory = MagicMock()

        result = await tool_services._process_single_integration(integration, provider_factory)

        # Integration is skipped (empty result) and, critically, the adapter is never created.
        assert result == []
        provider_factory.create_provider_instance.assert_not_called()

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
