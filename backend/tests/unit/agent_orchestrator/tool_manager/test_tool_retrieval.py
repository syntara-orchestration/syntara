"""Tests for ToolManagerClient tool retrieval and filtering functionality."""

from typing import Any
from uuid import uuid4

import httpx
import pytest
import respx

from syntara.agent_orchestrator.tool_manager.tool_manager_client import ToolManagerClient
from syntara.tool_manager.models.tool import ToolParameter, ToolParameterType, ToolStatus, ToolWithParameters

from .conftest import mock_paginated_api


class TestToolRetrieval:
    """Test tool retrieval and filtering scenarios."""

    @pytest.fixture
    def sample_tool_response(self) -> dict[str, Any]:
        """Sample tool response from Tool Manager API."""
        tool_id = str(uuid4())
        integration_id = str(uuid4())
        return {
            "id": tool_id,
            "name": "test_tool",
            "description": "Test tool for unit tests",
            "integration_id": integration_id,
            "namespaced_name": "test_provider::test_tool",
            "enabled": True,
            "status": "available",
            "parameters": [
                {
                    "id": str(uuid4()),
                    "name": "query",
                    "type": "string",
                    "description": "Search query parameter",
                    "required": True,
                    "default_value": None,
                    "example_value": {"value": "example search"},
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "labels": {},
                }
            ],
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "created_by": str(uuid4()),
            "labels": {},
        }

    @pytest.fixture
    def client(self) -> ToolManagerClient:
        """Create client instance for testing."""
        return ToolManagerClient(base_url="http://test-api/api/v1", timeout=30.0)

    @respx.mock
    async def test_get_all_tools_success(self, client: ToolManagerClient, sample_tool_response: dict[str, Any]) -> None:
        """Test successful retrieval of all tools."""
        # Mock successful API response
        respx.get("http://test-api/api/v1/tools").mock(
            return_value=httpx.Response(200, json={"resources": [sample_tool_response], "total_count": 1, "next": None})
        )

        tools = await client.get_all_tools()

        assert len(tools) == 1
        tool = tools[0]
        assert isinstance(tool, ToolWithParameters)
        assert tool.name == "test_tool"
        assert tool.namespaced_name == "test_provider::test_tool"
        assert tool.enabled is True
        assert tool.status == ToolStatus.AVAILABLE
        assert len(tool.parameters) == 1

        param = tool.parameters[0]
        assert isinstance(param, ToolParameter)
        assert param.name == "query"
        assert param.type == ToolParameterType.STRING
        assert param.required is True

    @respx.mock
    async def test_get_all_tools_no_filter(self, client: ToolManagerClient) -> None:
        """Test that all tools are requested without enabled filter."""
        # Mock API response
        respx.get("http://test-api/api/v1/tools").mock(
            return_value=httpx.Response(200, json={"resources": [], "total_count": 0})
        )

        await client.get_all_tools()

        # Verify the API was called without enabled filter
        request = respx.calls.last.request
        assert "enabled=true" not in str(request.url)

    @respx.mock
    async def test_get_all_tools_empty_response(self, client: ToolManagerClient) -> None:
        """Test handling of empty tools list."""
        respx.get("http://test-api/api/v1/tools").mock(
            return_value=httpx.Response(200, json={"resources": [], "total_count": 0})
        )

        tools = await client.get_all_tools()

        assert tools == []

    @respx.mock
    async def test_get_all_tools_multiple_parameters(self, client: ToolManagerClient) -> None:
        """Test tool with multiple parameters."""
        tool_id = str(uuid4())
        complex_tool = {
            "id": tool_id,
            "name": "complex_tool",
            "description": "Tool with multiple parameters",
            "integration_id": str(uuid4()),
            "namespaced_name": "provider::complex_tool",
            "enabled": True,
            "status": "available",
            "parameters": [
                {
                    "id": str(uuid4()),
                    "name": "input_text",
                    "type": "string",
                    "description": "Input text parameter",
                    "required": True,
                    "default_value": None,
                    "example_value": {"value": "Hello world"},
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "labels": {},
                },
                {
                    "id": str(uuid4()),
                    "name": "max_length",
                    "type": "number",
                    "description": "Maximum length of output",
                    "required": False,
                    "default_value": {"value": 100},
                    "example_value": {"value": 200},
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "labels": {},
                },
                {
                    "id": str(uuid4()),
                    "name": "include_metadata",
                    "type": "boolean",
                    "description": "Include metadata in response",
                    "required": False,
                    "default_value": {"value": False},
                    "example_value": {"value": True},
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "labels": {},
                },
            ],
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "created_by": str(uuid4()),
            "labels": {},
        }

        respx.get("http://test-api/api/v1/tools").mock(
            return_value=httpx.Response(200, json={"resources": [complex_tool], "total_count": 1, "next": None})
        )

        tools = await client.get_all_tools()

        assert len(tools) == 1
        tool = tools[0]
        assert len(tool.parameters) == 3

        # Verify different parameter types
        params_by_name = {p.name: p for p in tool.parameters}
        assert params_by_name["input_text"].type == ToolParameterType.STRING
        assert params_by_name["input_text"].required is True
        assert params_by_name["max_length"].type == ToolParameterType.NUMBER
        assert params_by_name["max_length"].required is False
        assert params_by_name["include_metadata"].type == ToolParameterType.BOOLEAN
        assert params_by_name["include_metadata"].required is False

    @respx.mock
    @pytest.mark.usefixtures("fast_retry_settings")
    async def test_get_all_tools_api_error(self, client: ToolManagerClient) -> None:
        """Test handling of API errors during tool retrieval."""
        respx.get("http://test-api/api/v1/tools").mock(return_value=httpx.Response(500, text="Internal server error"))

        with pytest.raises(httpx.HTTPStatusError):
            await client.get_all_tools()

    @respx.mock
    @pytest.mark.usefixtures("fast_retry_settings")
    async def test_get_all_tools_timeout(self, client: ToolManagerClient) -> None:
        """Test handling of timeout during tool retrieval."""
        respx.get("http://test-api/api/v1/tools").mock(side_effect=httpx.TimeoutException("Request timeout"))

        with pytest.raises(httpx.TimeoutException):
            await client.get_all_tools()

    @respx.mock
    @pytest.mark.usefixtures("fast_retry_settings")
    async def test_get_all_tools_network_error(self, client: ToolManagerClient) -> None:
        """Test handling of network errors during tool retrieval."""
        respx.get("http://test-api/api/v1/tools").mock(side_effect=httpx.ConnectError("Connection failed"))

        with pytest.raises(httpx.ConnectError):
            await client.get_all_tools()

    async def test_get_all_tools_pagination(self, client: ToolManagerClient) -> None:
        """Test handling of paginated tool responses."""
        # Define paginated response data
        tools_page1 = [
            {
                "id": str(uuid4()),
                "name": "tool_1",
                "description": "First tool",
                "integration_id": str(uuid4()),
                "namespaced_name": "provider::tool_1",
                "enabled": True,
                "status": "available",
                "parameters": [],
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "created_by": str(uuid4()),
                "labels": {},
            }
        ]

        tools_page2 = [
            {
                "id": str(uuid4()),
                "name": "tool_2",
                "description": "Second tool",
                "integration_id": str(uuid4()),
                "namespaced_name": "provider::tool_2",
                "enabled": True,
                "status": "available",
                "parameters": [],
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "created_by": str(uuid4()),
                "labels": {},
            }
        ]

        # Use the context manager for cleaner pagination mocking
        pages = [
            {"resources": tools_page1, "total_count": 2, "next": "cursor_456"},
            {"resources": tools_page2, "total_count": 2, "next": None},
        ]

        with mock_paginated_api(r".*tools.*", pages):
            tools = await client.get_all_tools()

        assert len(tools) == 2
        assert tools[0].name == "tool_1"
        assert tools[1].name == "tool_2"

    @respx.mock
    async def test_get_all_tools_status_filtering(self, client: ToolManagerClient) -> None:
        """Test that tools with different statuses are handled correctly."""
        # Include tools with different statuses - only available ones should be usable
        mixed_status_tools = [
            {
                "id": str(uuid4()),
                "name": "available_tool",
                "description": "Available tool",
                "integration_id": str(uuid4()),
                "namespaced_name": "provider::available_tool",
                "enabled": True,
                "status": "available",
                "parameters": [],
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "created_by": str(uuid4()),
                "labels": {},
            },
            {
                "id": str(uuid4()),
                "name": "error_tool",
                "description": "Tool in error state",
                "integration_id": str(uuid4()),
                "namespaced_name": "provider::error_tool",
                "enabled": True,  # enabled but has error status
                "status": "error",
                "refresh_error": "Failed to load tool",
                "parameters": [],
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "created_by": str(uuid4()),
                "labels": {},
            },
        ]

        respx.get("http://test-api/api/v1/tools").mock(
            return_value=httpx.Response(200, json={"resources": mixed_status_tools, "total_count": 2, "next": None})
        )

        tools = await client.get_all_tools()

        # Both tools should be returned (filtering by status is handled at service level)
        assert len(tools) == 2
        available_tools = [t for t in tools if t.status == ToolStatus.AVAILABLE]
        error_tools = [t for t in tools if t.status == ToolStatus.ERROR]
        assert len(available_tools) == 1
        assert len(error_tools) == 1
        assert error_tools[0].refresh_error == "Failed to load tool"
