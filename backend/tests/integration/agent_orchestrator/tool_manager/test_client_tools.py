"""Integration tests for ToolManagerClient with real backend."""

from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from httpx import AsyncClient

from syntara.agent_orchestrator.tool_manager.tool_manager_client import ToolManagerClient
from syntara.tool_manager.models import Tool

if TYPE_CHECKING:
    from tests.integration.helpers.tool_manager import ToolFactory


@pytest_asyncio.fixture
async def mixed_test_tools(tool_factory: "ToolFactory") -> list[Tool]:
    """Create test tools with mixed enabled/disabled states for filtering verification."""
    return await tool_factory.create_tools(
        count=15,  # Total tools: 10 enabled + 5 disabled
        name_prefix="Client Test Tool",
        namespace_prefix="client_test",
        statuses=None,  # All AVAILABLE
        enabled_states=[
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            False,
            False,
            False,
            False,
            False,
        ],  # 10 enabled, 5 disabled
    )


@pytest_asyncio.fixture
async def tool_manager_client(jwt_client: AsyncClient) -> ToolManagerClient:
    """Create ToolManagerClient that uses the test server with small page size.

    The jwt_client fixture provides an AsyncClient connected to the test FastAPI
    application via ASGI transport with JWT authentication. We reuse this transport
    and headers for ToolManagerClient.
    Uses a small page size (5) to test pagination with 15 total tools.
    """
    # Create ToolManagerClient with small page size to test pagination
    client = ToolManagerClient(base_url="http://test/api/v1", limit=5)
    await client.close()

    # Replace the default HTTP client with the test client's transport and auth headers
    # Use the same transport as jwt_client (which connects to the test app)
    # Create a new session using the test transport but with the correct base URL
    client.session = AsyncClient(
        transport=jwt_client._transport,
        base_url="http://test/api/v1",
        headers=dict(jwt_client.headers),  # Copy JWT auth headers
    )

    return client


class TestToolManagerClientIntegration:
    """Integration tests for ToolManagerClient with real backend."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mixed_test_tools")
    async def test_get_all_tools_returns_all_tools(
        self,
        tool_manager_client: ToolManagerClient,
    ) -> None:
        """Test ToolManagerClient returns all tools without client-side filtering.

        Creates 15 total tools (10 enabled + 5 disabled) with page size of 5.
        Client should return ALL 15 tools - filtering is done at service layer.
        """
        # Use ToolManagerClient to retrieve tools
        retrieved_tools = await tool_manager_client.get_all_tools()

        # Verify we got all 15 tools (enabled + disabled)
        assert len(retrieved_tools) == 15

        # Create mapping of all tool names (tools 1-15)
        expected_names = {f"Client Test Tool {i + 1}" for i in range(15)}
        retrieved_names = {tool.name for tool in retrieved_tools}

        # Verify all tools are present (no client-side filtering)
        assert retrieved_names == expected_names

        # Verify we have both enabled and disabled tools
        enabled_tools = [t for t in retrieved_tools if t.enabled]
        disabled_tools = [t for t in retrieved_tools if not t.enabled]
        assert len(enabled_tools) == 10  # Expected enabled count from fixture
        assert len(disabled_tools) == 5  # Expected disabled count from fixture

        # Verify basic tool structure
        for tool in retrieved_tools:
            assert tool.status.value == "available"
            assert tool.name.startswith("Client Test Tool")
            assert tool.namespaced_name.startswith("client_test::")

        # Verify tools have the expected structure with parameters
        for tool in retrieved_tools:
            # ToolWithParameters should have parameters attribute
            assert hasattr(tool, "parameters")
            assert isinstance(tool.parameters, list)

            # Verify core tool fields
            assert tool.id is not None
            assert tool.name is not None
            assert tool.description is not None
            assert tool.namespaced_name is not None
            assert tool.created_at is not None
            assert tool.updated_at is not None
