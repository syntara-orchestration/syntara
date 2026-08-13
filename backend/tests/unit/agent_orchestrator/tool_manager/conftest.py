"""Configuration and shared fixtures for tool_manager unit tests.

Provides fast retry settings and common test fixtures for integrations,
tools, and mock clients used across tool manager unit tests.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import httpx
import pytest
import respx
from langchain_core.tools import BaseTool

from syntara.agent_orchestrator.tool_manager.tool_manager_client import ToolManagerClient
from syntara.agent_orchestrator.tool_manager.types import NamespacedBaseTool
from syntara.integrations.models.integration import (
    IntegrationRead,
    IntegrationStatus,
    IntegrationType,
)
from syntara.integrations.models.integration_configuration import MCPServerConfiguration
from syntara.tool_manager.models.tool import ToolWithParameters


class PaginationMockFactory:
    """Factory for creating paginated API response mocks."""

    @staticmethod
    def create_paginated_response(pages: list[dict[str, Any]]) -> Callable[[Any], httpx.Response]:
        """Create a mock response function for paginated API calls.

        Args:
            pages: List of page data, each containing:
                - resources: List of resource objects for this page
                - total_count: Total number of resources across all pages
                - next: Next cursor (None for last page)

        Returns:
            Mock response function that can be used with respx.mock(side_effect=...)

        Example:
            pages = [
                {"resources": [item1], "total_count": 2, "next": "cursor_123"},
                {"resources": [item2], "total_count": 2, "next": None}
            ]
            mock_response = PaginationMockFactory.create_paginated_response(pages)
            respx.get(...).mock(side_effect=mock_response)

        """
        call_count = 0

        def mock_response(request) -> httpx.Response:
            nonlocal call_count
            call_count += 1

            if call_count <= len(pages):
                page_data = pages[call_count - 1]
                return httpx.Response(200, json=page_data)

            # If we somehow get more requests than pages, return empty last page
            return httpx.Response(200, json={"resources": [], "total_count": 0, "next": None})

        return mock_response


@contextmanager
def mock_paginated_api(url_pattern: str, pages: list[dict[str, Any]]) -> Iterator[None]:
    """Context manager for mocking paginated API responses.

    Args:
        url_pattern: URL pattern to match (regex string)
        pages: List of page data dictionaries

    Example:
        pages = [
            {"resources": [integration1], "total_count": 2, "next": "cursor_123"},
            {"resources": [integration2], "total_count": 2, "next": None}
        ]

        with mock_paginated_api(r".*integrations.*", pages):
            # Test code that makes paginated requests
            result = await client.get_all_mcp_integrations()

    """
    mock_response = PaginationMockFactory.create_paginated_response(pages)

    with respx.mock:
        respx.get(url__regex=url_pattern).mock(side_effect=mock_response)
        yield


def _make_integration(
    name: str = "dev_tools",
    *,
    integration_id: UUID | None = None,
    enabled: bool = True,
    base_url: str = "http://localhost:3001/mcp",
) -> IntegrationRead:
    """Create a sample IntegrationRead for testing."""
    user_id = uuid4()
    return IntegrationRead(
        id=integration_id or uuid4(),
        name=name,
        integration_type=IntegrationType.MCP_SERVER,
        enabled=enabled,
        validation_status=IntegrationStatus.AVAILABLE,
        scope="global",
        configuration=MCPServerConfiguration(
            integration_type="mcp_server",
            base_url=base_url,
        ),
        management_credential_id=None,
        last_validated_at=None,
        validation_error=None,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        created_by=user_id,
        updated_by=None,
        labels={},
    )


# Stable integration IDs used across fixtures so NamespacedBaseTool and
# ToolWithParameters refer to the same integrations.
INTEGRATION_1_ID = UUID("00000000-0000-0000-0000-000000000001")
INTEGRATION_2_ID = UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture
def sample_mcp_integrations() -> list[IntegrationRead]:
    """Sample MCP server integrations for testing."""
    return [
        _make_integration("dev_tools", integration_id=INTEGRATION_1_ID, base_url="http://localhost:3001/mcp"),
        _make_integration("file_tools", integration_id=INTEGRATION_2_ID, base_url="http://localhost:3002/mcp"),
    ]


# Keep for backward compat in existing tests that need it
@pytest.fixture
def sample_tool_providers() -> list[IntegrationRead]:
    """Alias for sample_mcp_integrations for backward compat."""
    return [
        _make_integration("dev_tools", integration_id=INTEGRATION_1_ID, base_url="http://localhost:3001/mcp"),
        _make_integration("file_tools", integration_id=INTEGRATION_2_ID, base_url="http://localhost:3002/mcp"),
    ]


@pytest.fixture
def mock_langchain_base_tools() -> list[Mock]:
    """Mock LangChain BaseTools from MCP servers."""
    tool1 = Mock(spec=BaseTool)
    tool1.name = "code_search"
    tool1.description = "Search for code patterns"

    tool2 = Mock(spec=BaseTool)
    tool2.name = "file_read"
    tool2.description = "Read file contents"

    tool3 = Mock(spec=BaseTool)
    tool3.name = "build_project"
    tool3.description = "Build the project"

    # Tool exists in MCP but not in Tool Manager registry
    tool4 = Mock(spec=BaseTool)
    tool4.name = "unregistered_tool"
    tool4.description = "Tool not in Tool Manager"

    return [tool1, tool2, tool3, tool4]


@pytest.fixture
def mock_namespaced_tools(mock_langchain_base_tools: list[Mock]) -> list[NamespacedBaseTool]:
    """Mock NamespacedBaseTool instances from MCP servers."""
    return [
        NamespacedBaseTool(
            integration_id=INTEGRATION_1_ID,
            integration_name="dev_tools",
            tool_name="code_search",
            base_tool=mock_langchain_base_tools[0],
        ),
        NamespacedBaseTool(
            integration_id=INTEGRATION_2_ID,
            integration_name="file_tools",
            tool_name="file_read",
            base_tool=mock_langchain_base_tools[1],
        ),
        NamespacedBaseTool(
            integration_id=INTEGRATION_1_ID,
            integration_name="dev_tools",
            tool_name="build_project",
            base_tool=mock_langchain_base_tools[2],
        ),
        NamespacedBaseTool(
            integration_id=INTEGRATION_1_ID,
            integration_name="dev_tools",
            tool_name="unregistered_tool",
            base_tool=mock_langchain_base_tools[3],
        ),
    ]


@pytest.fixture
def sample_tools() -> list[ToolWithParameters]:
    """Sample tools from Tool Manager for testing."""
    user_id = uuid4()
    return [
        ToolWithParameters(
            id=uuid4(),
            name="code_search",
            namespaced_name="dev_tools::code_search",
            description="Search for code patterns",
            integration_id=INTEGRATION_1_ID,
            enabled=True,
            status="available",
            parameters=[],
            created_by=user_id,
        ),
        ToolWithParameters(
            id=uuid4(),
            name="file_read",
            namespaced_name="file_tools::file_read",
            description="Read file contents",
            integration_id=INTEGRATION_2_ID,
            enabled=True,
            status="available",
            parameters=[],
            created_by=user_id,
        ),
        ToolWithParameters(
            id=uuid4(),
            name="disabled_tool",
            namespaced_name="dev_tools::disabled_tool",
            description="A disabled tool",
            integration_id=INTEGRATION_1_ID,
            enabled=False,
            status="available",
            parameters=[],
            created_by=user_id,
        ),
        ToolWithParameters(
            id=uuid4(),
            name="missing_tool",
            namespaced_name="dev_tools::missing_tool",
            description="Tool missing from MCP server",
            integration_id=INTEGRATION_1_ID,
            enabled=True,
            status="available",
            parameters=[],
            created_by=user_id,
        ),
    ]


@pytest.fixture
async def tool_manager_client() -> Mock:
    """Mock Tool Manager client for testing."""
    client = Mock(spec=ToolManagerClient)
    client.get_all_mcp_integrations = AsyncMock()
    client.get_all_tools = AsyncMock()
    client.update_tool_status = AsyncMock()
    client.close = AsyncMock()
    return client
