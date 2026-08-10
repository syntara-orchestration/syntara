"""Unit tests for MCPProvider implementation.

Tests cover:
- MCPProvider implementation of ToolProviderAdapter protocol
- Langchain MultiServerMCPClient integration
- Connection validation with various scenarios
- Tool discovery and refresh functionality
- Tool schema retrieval
- Tool validation with error handling
- Error conditions and timeout scenarios
- Configuration and client management
"""
# mypy: disable-error-code=unreachable

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest
from httpx import HTTPStatusError, Request, Response
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from syntara.tool_manager.exceptions import ToolNotFoundError
from syntara.tool_manager.lib.providers.mcp.mcp_provider import MCPProvider
from syntara.tool_manager.models import (
    Tool,
    ToolParameterType,
    ToolProviderValidationResult,
    ToolSchema,
    ToolStatus,
    ToolValidationResult,
)


class TestMCPProvider:
    """Test suite for MCPProvider implementation."""

    def test_mcp_provider_initialization_defaults(self) -> None:
        """Test MCPProvider initialization with default values."""
        base_url = "http://localhost:8765/mcp"
        api_key = "test-key"

        provider = MCPProvider(base_url=base_url, api_key=api_key)

        assert provider._base_url == base_url
        assert provider._api_key == api_key
        assert provider.integration_name == "mcp-integration"
        assert isinstance(provider.integration_id, UUID)
        assert provider._client is None
        assert provider._tools_cache == {}

    def test_mcp_provider_initialization_custom(self) -> None:
        """Test MCPProvider initialization with custom values."""
        base_url = "http://custom:9000/mcp"
        api_key = "custom-key"
        provider_id = uuid4()
        provider_name = "custom-mcp"

        provider = MCPProvider(
            base_url=base_url,
            api_key=api_key,
            integration_id=provider_id,
            integration_name=provider_name,
        )

        assert provider._base_url == base_url
        assert provider._api_key == api_key
        assert provider.integration_name == provider_name
        assert provider.integration_id == provider_id

    def test_mcp_provider_initialization_without_api_key(self) -> None:
        """Test MCPProvider initialization without api_key (credentials resolved at call time)."""
        base_url = "http://localhost:8765/mcp"
        provider_id = uuid4()
        provider_name = "test-mcp"

        provider = MCPProvider(
            base_url=base_url,
            api_key=None,
            integration_id=provider_id,
            integration_name=provider_name,
        )

        assert provider._base_url == base_url
        assert provider._api_key is None
        assert provider.integration_name == provider_name
        assert provider.integration_id == provider_id
        assert provider._client is None
        assert provider._tools_cache == {}

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_get_client_success(self, mock_client_class: Mock) -> None:
        """Test successful MCP client initialization."""
        # Setup
        mock_client_instance = AsyncMock()
        mock_client_class.return_value = mock_client_instance

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Execute
        client = await provider._get_client()

        # Verify
        assert client == mock_client_instance
        assert provider._client == mock_client_instance

        # Verify client was configured correctly
        mock_client_class.assert_called_once()
        call_args = mock_client_class.call_args[0][0]
        expected_config = {
            "mcp-integration": {
                "transport": "streamable_http",
                "url": "http://localhost:8765/mcp",
                "headers": {"Authorization": "Bearer test-key"},
            }
        }
        assert call_args == expected_config

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_get_client_without_api_key(self, mock_client_class: Mock) -> None:
        """Test MCP client initialization without API key (empty string)."""
        # Setup
        mock_client_instance = AsyncMock()
        mock_client_class.return_value = mock_client_instance

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="")

        # Execute
        client = await provider._get_client()

        # Verify
        assert client == mock_client_instance

        # Verify client config doesn't include headers
        call_args = mock_client_class.call_args[0][0]
        assert "headers" not in call_args["mcp-integration"]

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_get_client_with_none_api_key(self, mock_client_class: Mock) -> None:
        """Test MCP client initialization with None API key."""
        # Setup
        mock_client_instance = AsyncMock()
        mock_client_class.return_value = mock_client_instance

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key=None)

        # Execute
        client = await provider._get_client()

        # Verify
        assert client == mock_client_instance

        # Verify client config doesn't include headers
        call_args = mock_client_class.call_args[0][0]
        assert "headers" not in call_args["mcp-integration"]

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_get_client_cached(self, mock_client_class: Mock) -> None:
        """Test that client is cached and not recreated."""
        # Setup
        mock_client_instance = AsyncMock()
        mock_client_class.return_value = mock_client_instance

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Execute multiple calls
        client1 = await provider._get_client()
        client2 = await provider._get_client()

        # Verify
        assert client1 == client2
        assert client1 == mock_client_instance
        mock_client_class.assert_called_once()  # Should only be called once

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_get_client_initialization_error(self, mock_client_class: Mock) -> None:
        """Test MCP client initialization error handling."""
        # Setup
        mock_client_class.side_effect = RuntimeError("Client init failed")

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Execute and verify
        with pytest.raises(ConnectionError, match="Failed to initialize MCP client: Client init failed"):
            await provider._get_client()

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_validate_connection_success(self, mock_client_class: Mock) -> None:
        """Test successful connection validation."""
        # Setup
        mock_client = AsyncMock()
        mock_client.get_tools.return_value = [Mock(), Mock()]  # Mock 2 tools
        mock_client_class.return_value = mock_client

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Execute
        result = await provider.validate_connection()

        # Verify
        assert isinstance(result, ToolProviderValidationResult)
        assert result.valid is True
        assert result.provider_type == "mcp"
        assert isinstance(result.validated_at, datetime)
        assert result.error is None
        assert result.timeout is False

        mock_client.get_tools.assert_called_once()

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_validate_connection_timeout(self, mock_client_class: Mock) -> None:
        """Test connection validation timeout handling with retries."""
        # Setup
        mock_client = AsyncMock()
        mock_client.get_tools.side_effect = TimeoutError("Timed out")
        mock_client_class.return_value = mock_client

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Execute
        result = await provider.validate_connection()

        # Verify
        assert isinstance(result, ToolProviderValidationResult)
        assert result.valid is False
        assert result.provider_type == "mcp"
        assert isinstance(result.validated_at, datetime)
        assert result.error is not None
        assert "Timed out" in result.error
        assert result.timeout is True

        # Timeouts are retriable — all 3 attempts should be made
        assert mock_client.get_tools.call_count == 3

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_validate_connection_connection_error(self, mock_client_class: Mock) -> None:
        """Test connection validation with connection error."""
        # Setup
        mock_client = AsyncMock()
        mock_client.get_tools.side_effect = ConnectionError("Network error")
        mock_client_class.return_value = mock_client

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Execute
        result = await provider.validate_connection()

        # Verify
        assert isinstance(result, ToolProviderValidationResult)
        assert result.valid is False
        assert result.provider_type == "mcp"
        assert isinstance(result.validated_at, datetime)
        assert result.error is not None
        assert "Network error" in result.error
        assert result.timeout is False

        mock_client.get_tools.assert_called_once()

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_validate_connection_nested_exception_groups(self, mock_client_class: Mock) -> None:
        """Test connection validation with nested ExceptionGroups."""
        # Setup
        mock_client = AsyncMock()

        # Create HTTPStatusError instances - need Request and Response objects
        mock_request = Request("GET", "http://test.com")

        # Create responses with different status codes
        unauthorized_response = Response(401, request=mock_request)
        server_error_response = Response(500, request=mock_request)

        # Create HTTPStatusError instances
        server_error = HTTPStatusError("Internal Server Error", request=mock_request, response=server_error_response)
        nested_unauthorized_error = HTTPStatusError(
            "Nested Unauthorized", request=mock_request, response=unauthorized_response
        )

        # Create nested ExceptionGroup containing an UNAUTHORIZED HTTPStatusError
        nested_group = ExceptionGroup("Nested HTTP errors", [nested_unauthorized_error])

        # Create main ExceptionGroup with multiple HTTPStatusError instances and nested ExceptionGroup
        exception_group = ExceptionGroup("HTTP connection errors", [server_error, nested_group])

        mock_client.get_tools.side_effect = exception_group
        mock_client_class.return_value = mock_client

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Execute - should now handle nested ExceptionGroups properly
        result = await provider.validate_connection()

        # Verify
        assert isinstance(result, ToolProviderValidationResult)
        assert result.valid is False
        assert result.provider_type == "mcp"
        assert isinstance(result.validated_at, datetime)
        assert result.error is not None

        # Should contain error messages for all HTTPStatusErrors
        # The nested UNAUTHORIZED error should be sanitized specially
        assert "MCP session failed to establish connection - Unauthorized" in result.error
        assert "Connection validation failed with HTTP error" in result.error

        mock_client.get_tools.assert_called_once()

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_validate_connection_session_terminated(self, mock_client_class: Mock) -> None:
        """Test connection validation with session termination error."""
        # Setup
        mock_client = AsyncMock()
        mock_client.get_tools.side_effect = RuntimeError("Session terminated unexpectedly")
        mock_client_class.return_value = mock_client

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Execute and verify
        with pytest.raises(RuntimeError, match="Session terminated unexpectedly"):
            await provider.validate_connection()

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_validate_connection_general_error(self, mock_client_class: Mock) -> None:
        """Test connection validation with general error returning validation result."""
        # Setup
        mock_client = AsyncMock()
        mock_client.get_tools.side_effect = ValueError("Invalid response format")
        mock_client_class.return_value = mock_client

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Execute and verify
        with pytest.raises(ValueError, match="Invalid response format"):
            await provider.validate_connection()

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_refresh_tools_success(self, mock_client_class: Mock) -> None:
        """Test successful tool refresh."""
        # Setup
        mock_tool1 = self._create_mock_langchain_tool("calculate_sum", "Calculate sum of two numbers")
        mock_tool2 = self._create_mock_langchain_tool("get_greeting", "Generate greeting")

        mock_client = AsyncMock()
        mock_client.get_tools.return_value = [mock_tool1, mock_tool2]
        mock_client_class.return_value = mock_client

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Execute
        tools = await provider.refresh_tools()

        # Verify
        assert isinstance(tools, list)
        assert len(tools) == 2

        # Check tool properties
        tool_names = {tool.name for tool in tools}
        assert tool_names == {"calculate_sum", "get_greeting"}

        for tool in tools:
            assert isinstance(tool, Tool)
            # integration_id is not set by MCPProvider; it is set by IntegrationService when persisting
            assert tool.namespaced_name.startswith("mcp-integration::")
            assert tool.status == ToolStatus.AVAILABLE
            assert tool.last_refreshed_at is not None

        # Verify tools are cached
        assert len(provider._tools_cache) == 2
        assert "calculate_sum" in provider._tools_cache
        assert "get_greeting" in provider._tools_cache

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_refresh_tools_with_conversion_error(self, mock_client_class: Mock) -> None:
        """Test tool refresh with tool conversion errors."""
        # Setup
        mock_tool_good = self._create_mock_langchain_tool("good_tool", "Good tool")
        mock_tool_bad = Mock()
        mock_tool_bad.name = "bad_tool"
        mock_tool_bad.description = None  # This will cause conversion to fail

        mock_client = AsyncMock()
        mock_client.get_tools.return_value = [mock_tool_good, mock_tool_bad]
        mock_client_class.return_value = mock_client

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Execute
        tools = await provider.refresh_tools()

        # Verify - should only get the good tool
        assert len(tools) == 1
        assert tools[0].name == "good_tool"

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_refresh_tools_timeout(self, mock_client_class: Mock) -> None:
        """Test tool refresh timeout handling."""
        # Setup
        mock_client = AsyncMock()
        mock_client.get_tools.side_effect = TimeoutError()
        mock_client_class.return_value = mock_client

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Execute and verify
        with pytest.raises(TimeoutError, match="Tool retrieval timed out after 30s"):
            await provider.refresh_tools()

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_refresh_tools_connection_error(self, mock_client_class: Mock) -> None:
        """Test tool refresh connection error handling."""
        # Setup
        mock_client = AsyncMock()
        mock_client.get_tools.side_effect = RuntimeError("Server unavailable")
        mock_client_class.return_value = mock_client

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Execute and verify
        with pytest.raises(ConnectionError, match="Tool retrieval failed: Server unavailable"):
            await provider.refresh_tools()

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_get_base_tools_success(self, mock_client_class: Mock) -> None:
        """Test successful retrieval of base tools."""
        # Setup
        mock_client = AsyncMock()
        mock_tools = [
            self._create_mock_langchain_tool("tool1", "First tool"),
            self._create_mock_langchain_tool("tool2", "Second tool"),
        ]
        mock_client.get_tools.return_value = mock_tools
        mock_client_class.return_value = mock_client

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Execute
        base_tools = await provider.get_base_tools()

        # Verify
        assert len(base_tools) == 2
        assert base_tools[0].name == "tool1"
        assert base_tools[1].name == "tool2"
        mock_client.get_tools.assert_called_once()

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_get_base_tools_timeout(self, mock_client_class: Mock) -> None:
        """Test base tools retrieval timeout handling."""
        # Setup
        mock_client = AsyncMock()
        mock_client.get_tools.side_effect = TimeoutError()
        mock_client_class.return_value = mock_client

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Execute and verify
        with pytest.raises(TimeoutError, match="Tool retrieval timed out after 30s"):
            await provider.get_base_tools()

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_get_base_tools_connection_error(self, mock_client_class: Mock) -> None:
        """Test base tools retrieval connection error handling."""
        # Setup
        mock_client = AsyncMock()
        mock_client.get_tools.side_effect = RuntimeError("Server unavailable")
        mock_client_class.return_value = mock_client

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Execute and verify
        with pytest.raises(ConnectionError, match="Tool retrieval failed: Server unavailable"):
            await provider.get_base_tools()

    @pytest.mark.asyncio
    async def test_get_tool_schema_success(self) -> None:
        """Test successful tool schema retrieval."""
        # Setup
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Mock cached tool
        mock_langchain_tool = self._create_mock_langchain_tool("test_tool", "Test tool description")
        provider._tools_cache["test_tool"] = {
            "langchain_tool": mock_langchain_tool,
            "schema": {"type": "object", "properties": {"message": {"type": "string", "description": "Input message"}}},
        }

        # Execute
        schema = await provider.get_tool_schema("test_tool")

        # Verify
        assert isinstance(schema, ToolSchema)
        assert schema.name == "test_tool"
        assert schema.description == "Test tool description"
        assert schema.input_schema["type"] == "object"
        assert "message" in schema.input_schema["properties"]
        assert schema.output_schema is None
        assert schema.examples is None

    @pytest.mark.asyncio
    async def test_get_tool_schema_not_found(self) -> None:
        """Test tool schema retrieval for non-existent tool."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Execute and verify
        with pytest.raises(ToolNotFoundError, match="Tool 'nonexistent' not found in provider mcp-integration"):
            await provider.get_tool_schema("nonexistent")

    @pytest.mark.asyncio
    async def test_get_tool_schema_retrieval_error(self) -> None:
        """Test tool schema retrieval with general error."""
        # Setup
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Mock cached tool with problematic data
        mock_tool = Mock()
        mock_tool.description.side_effect = RuntimeError("Description access failed")
        provider._tools_cache["error_tool"] = {"langchain_tool": mock_tool, "schema": {}}

        # Execute and verify
        with pytest.raises(ConnectionError, match="Failed to get schema for tool 'error_tool'"):
            await provider.get_tool_schema("error_tool")

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_validate_tool_success(self, mock_client_class: Mock) -> None:
        """Test successful tool validation."""
        # Setup
        mock_client = AsyncMock()
        mock_client.get_tools.return_value = []  # For connectivity check
        mock_client_class.return_value = mock_client

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Mock cached tool with simple schema
        mock_langchain_tool = self._create_mock_langchain_tool("test_tool", "Test tool")
        provider._tools_cache["test_tool"] = {"langchain_tool": mock_langchain_tool, "schema": {}}

        # Execute
        result = await provider.validate_tool("test_tool", {"message": "test"})

        # Verify
        assert isinstance(result, ToolValidationResult)
        assert result.success is True
        assert result.status == "success"
        assert "validation completed successfully" in result.message
        assert isinstance(result.validated_at, datetime)

    @pytest.mark.asyncio
    async def test_validate_tool_not_found(self) -> None:
        """Test tool validation for non-existent tool."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Execute and verify
        with pytest.raises(ToolNotFoundError, match="Tool 'nonexistent' not found in provider mcp-integration"):
            await provider.validate_tool("nonexistent")

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_validate_tool_schema_validation_error(self, mock_client_class: Mock) -> None:
        """Test tool validation with schema validation error."""
        # Setup
        mock_client = AsyncMock()
        mock_client.get_tools.return_value = []
        mock_client_class.return_value = mock_client

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Create tool with Pydantic schema that will fail validation
        class TestSchema(BaseModel):
            required_field: str

        mock_langchain_tool = Mock()
        mock_langchain_tool.args_schema = TestSchema

        provider._tools_cache["test_tool"] = {"langchain_tool": mock_langchain_tool, "schema": {}}

        # Execute - provide params that don't match schema
        result = await provider.validate_tool("test_tool", {"wrong_field": "value"})

        # Verify
        assert result.success is False
        assert result.status == "failure"
        assert "Schema validation failed" in result.message

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_validate_tool_connectivity_error(self, mock_client_class: Mock) -> None:
        """Test tool validation with connectivity error."""
        # Setup
        mock_client = AsyncMock()
        mock_client.get_tools.side_effect = ConnectionError("Connection failed")
        mock_client_class.return_value = mock_client

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Mock cached tool
        mock_langchain_tool = self._create_mock_langchain_tool("test_tool", "Test tool")
        provider._tools_cache["test_tool"] = {"langchain_tool": mock_langchain_tool, "schema": {}}

        # Execute
        result = await provider.validate_tool("test_tool")

        # Verify
        assert result.success is False
        assert result.status == "failure"
        assert "Connectivity check failed" in result.message

    @pytest.mark.asyncio
    @patch("syntara.tool_manager.lib.providers.mcp.mcp_provider.MultiServerMCPClient")
    async def test_validate_tool_connectivity_timeout(self, mock_client_class: Mock) -> None:
        """Test tool validation with connectivity timeout (returns error result)."""
        # Setup
        mock_client = AsyncMock()
        mock_client.get_tools.side_effect = TimeoutError()
        mock_client_class.return_value = mock_client

        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Mock cached tool
        mock_langchain_tool = self._create_mock_langchain_tool("test_tool", "Test tool")
        provider._tools_cache["test_tool"] = {"langchain_tool": mock_langchain_tool, "schema": {}}

        # Execute - connectivity timeout returns error result, doesn't raise
        result = await provider.validate_tool("test_tool")

        # Verify
        assert result.success is False
        assert result.status == "failure"
        assert "Connectivity check failed" in result.message

    def test_validate_tool_schema_no_schema(self) -> None:
        """Test tool schema validation with no schema."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        mock_tool = Mock()
        mock_tool.args_schema = None

        valid, error = provider._validate_tool_schema(mock_tool, {"any": "params"})

        assert valid is True
        assert error is None

    def test_validate_tool_schema_pydantic_success(self) -> None:
        """Test tool schema validation with Pydantic schema success."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        class TestSchema(BaseModel):
            message: str

        mock_tool = Mock()
        mock_tool.args_schema = TestSchema

        valid, error = provider._validate_tool_schema(mock_tool, {"message": "test"})

        assert valid is True
        assert error is None

    def test_validate_tool_schema_pydantic_error(self) -> None:
        """Test tool schema validation with Pydantic schema error."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        class TestSchema(BaseModel):
            required_field: str

        mock_tool = Mock()
        mock_tool.args_schema = TestSchema

        valid, error = provider._validate_tool_schema(mock_tool, {"wrong_field": "value"})

        assert valid is False
        assert error is not None

    def test_validate_tool_schema_non_pydantic(self) -> None:
        """Test tool schema validation with non-Pydantic schema."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        mock_tool = Mock()
        mock_tool.args_schema = {"type": "object"}  # Plain dict schema

        valid, error = provider._validate_tool_schema(mock_tool, {"any": "params"})

        assert valid is True
        assert error is None

    def test_build_validation_error_message_all_valid(self) -> None:
        """Test validation error message building with all validations passing."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        message = provider._build_validation_error_message(
            schema_valid=True,
            schema_error=None,
            connectivity_valid=True,
            connectivity_error=None,
        )

        assert message is None

    def test_build_validation_error_message_schema_error(self) -> None:
        """Test validation error message building with schema error."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        message = provider._build_validation_error_message(
            schema_valid=False,
            schema_error="Invalid schema",
            connectivity_valid=True,
            connectivity_error=None,
        )

        assert message == "Schema validation failed: Invalid schema"

    def test_build_validation_error_message_connectivity_error(self) -> None:
        """Test validation error message building with connectivity error."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        message = provider._build_validation_error_message(
            schema_valid=True,
            schema_error=None,
            connectivity_valid=False,
            connectivity_error="Connection timeout",
        )

        assert message == "Connectivity check failed: Connection timeout"

    def test_build_validation_error_message_both_errors(self) -> None:
        """Test validation error message building with both errors."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        message = provider._build_validation_error_message(
            schema_valid=False,
            schema_error="Invalid schema",
            connectivity_valid=False,
            connectivity_error="Connection timeout",
        )

        assert message == "Schema validation failed: Invalid schema; Connectivity check failed: Connection timeout"

    def test_convert_langchain_tool_to_tool(self) -> None:
        """Test conversion of langchain tool to Tool model."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Create mock langchain tool with schema
        mock_langchain_tool = self._create_mock_langchain_tool_with_schema(
            "test_tool",
            "Test tool description",
            {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Input message"},
                    "count": {"type": "integer", "description": "Repeat count"},
                },
                "required": ["message"],
            },
        )

        # Execute
        tool = provider._convert_langchain_tool_to_tool(mock_langchain_tool)

        # Verify
        assert isinstance(tool, Tool)
        assert tool.name == "test_tool"
        assert tool.namespaced_name == "mcp-integration::test_tool"
        assert tool.description == "Test tool description"
        # integration_id is not set by MCPProvider; it is set by IntegrationService when persisting
        assert tool.status == ToolStatus.AVAILABLE
        assert len(tool.parameters) == 2

        # Check parameters
        param_names = {p.name for p in tool.parameters}
        assert param_names == {"message", "count"}

        # Check required parameter
        message_param = next(p for p in tool.parameters if p.name == "message")
        assert message_param.required is True
        assert message_param.type == ToolParameterType.STRING

        count_param = next(p for p in tool.parameters if p.name == "count")
        assert count_param.required is False
        assert count_param.type == ToolParameterType.NUMBER

        # Verify tool is cached
        assert "test_tool" in provider._tools_cache
        assert provider._tools_cache["test_tool"]["langchain_tool"] == mock_langchain_tool

    def test_extract_tool_schema_pydantic(self) -> None:
        """Test schema extraction from Pydantic BaseModel."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        class TestSchema(BaseModel):
            message: str

        mock_tool = Mock()
        mock_tool.args_schema = TestSchema

        schema = provider._extract_tool_schema(mock_tool)

        assert isinstance(schema, dict)
        # The actual schema structure depends on Pydantic version, so just check it's not empty
        assert len(schema) > 0

    def test_extract_tool_schema_dict(self) -> None:
        """Test schema extraction from dict schema."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        schema_dict = {"type": "object", "properties": {"message": {"type": "string"}}}

        mock_tool = Mock()
        mock_tool.args_schema = schema_dict

        schema = provider._extract_tool_schema(mock_tool)

        assert schema == schema_dict

    def test_extract_tool_schema_none(self) -> None:
        """Test schema extraction with no schema."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        mock_tool = Mock()
        mock_tool.args_schema = None

        schema = provider._extract_tool_schema(mock_tool)

        assert schema == {}

    def test_create_tool_parameters_empty_schema(self) -> None:
        """Test tool parameter creation with empty schema."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        parameters = provider._create_tool_parameters({})

        assert parameters == []

    def test_create_tool_parameters_full_schema(self) -> None:
        """Test tool parameter creation with full schema."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        schema = {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Input message",
                    "default": "hello",
                    "examples": ["hello", "world"],
                },
                "count": {"type": "integer", "description": "Repeat count"},
                "enabled": {"type": "boolean", "description": "Enable feature"},
            },
            "required": ["message"],
        }

        parameters = provider._create_tool_parameters(schema)

        assert len(parameters) == 3

        # Check message parameter
        message_param = next(p for p in parameters if p.name == "message")
        assert message_param.type == ToolParameterType.STRING
        assert message_param.description == "Input message"
        assert message_param.required is True
        assert message_param.default_value == {"value": "hello"}
        assert message_param.example_value == {"value": "hello"}

        # Check count parameter
        count_param = next(p for p in parameters if p.name == "count")
        assert count_param.type == ToolParameterType.NUMBER
        assert count_param.required is False

        # Check boolean parameter
        enabled_param = next(p for p in parameters if p.name == "enabled")
        assert enabled_param.type == ToolParameterType.BOOLEAN

    def test_convert_json_type_to_tool_parameter_type(self) -> None:
        """Test JSON type to ToolParameterType conversion."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Test all mappings
        assert provider._convert_json_type_to_tool_parameter_type("string") == ToolParameterType.STRING
        assert provider._convert_json_type_to_tool_parameter_type("number") == ToolParameterType.NUMBER
        assert provider._convert_json_type_to_tool_parameter_type("integer") == ToolParameterType.NUMBER
        assert provider._convert_json_type_to_tool_parameter_type("boolean") == ToolParameterType.BOOLEAN
        assert provider._convert_json_type_to_tool_parameter_type("object") == ToolParameterType.OBJECT
        assert provider._convert_json_type_to_tool_parameter_type("array") == ToolParameterType.ARRAY

        # Test unknown type defaults to STRING
        assert provider._convert_json_type_to_tool_parameter_type("unknown") == ToolParameterType.STRING

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        """Test MCP client cleanup."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Set up some state
        provider._client = Mock()
        provider._tools_cache = {"tool1": {}, "tool2": {}}

        # Execute
        await provider.close()

        # Verify
        assert provider._client is None
        assert provider._tools_cache == {}

    @pytest.mark.asyncio
    async def test_close_with_error(self) -> None:
        """Test MCP client cleanup with error."""
        provider = MCPProvider(base_url="http://localhost:8765/mcp", api_key="test-key")

        # Set up mock client that raises error
        mock_client = Mock()
        mock_client.close.side_effect = RuntimeError("Close failed")
        provider._client = mock_client

        # Execute - should not raise
        await provider.close()

        # Verify cleanup still happened
        assert provider._client is None
        assert provider._tools_cache == {}

    def _create_mock_langchain_tool(self, name: str, description: str) -> Mock:
        """Create a mock langchain tool."""
        mock_tool = Mock(spec=BaseTool)
        mock_tool.name = name
        mock_tool.description = description
        mock_tool.args_schema = None
        return mock_tool

    def _create_mock_langchain_tool_with_schema(self, name: str, description: str, schema: dict[str, Any]) -> Mock:
        """Create a mock langchain tool with schema."""
        mock_tool = Mock(spec=BaseTool)
        mock_tool.name = name
        mock_tool.description = description

        # Create a mock schema that looks like Pydantic
        mock_schema = Mock()
        mock_schema.model_json_schema.return_value = schema
        mock_tool.args_schema = mock_schema

        return mock_tool
