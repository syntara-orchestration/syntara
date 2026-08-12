"""Unit tests for ToolProviderAdapter protocol.

Tests cover:
- Protocol interface verification
- Runtime checkable behavior
- Protocol conformance checking
- Implementation validation
"""

import inspect
from datetime import UTC, datetime

from langchain_core.tools import BaseTool

from syntara.tool_manager.lib.providers.base import ToolProviderAdapter
from syntara.tool_manager.lib.providers.mcp import MCPProvider
from syntara.tool_manager.models import ToolProviderValidationResult, ToolSchema, ToolValidationResult
from syntara.tool_manager.models.tool import Tool


def test_tool_provider_adapter_is_runtime_checkable() -> None:
    """Test that ToolProviderAdapter is runtime checkable."""
    # MCPProvider implements the protocol
    provider = MCPProvider(base_url="http://localhost:8080", api_key="test-key")

    # Runtime isinstance check should work
    assert isinstance(provider, ToolProviderAdapter)


def test_tool_provider_adapter_protocol_methods() -> None:
    """Test that ToolProviderAdapter protocol defines required methods."""
    # Check that protocol has the expected abstract methods
    expected_methods = {
        "validate_connection",
        "refresh_tools",
        "get_tool_schema",
        "validate_tool",
    }

    # Get all abstract methods from the protocol
    protocol_methods = set()
    for attr_name in dir(ToolProviderAdapter):
        attr = getattr(ToolProviderAdapter, attr_name)
        if hasattr(attr, "__isabstractmethod__") and attr.__isabstractmethod__:
            protocol_methods.add(attr_name)

    assert expected_methods.issubset(protocol_methods)


def test_mcp_provider_implements_protocol() -> None:
    """Test that MCPProvider correctly implements ToolProviderAdapter protocol."""
    provider = MCPProvider(base_url="http://localhost:8080", api_key="test-key")

    # Verify MCPProvider is recognized as implementing the protocol
    assert isinstance(provider, ToolProviderAdapter)

    # Verify all required methods are present and callable
    assert hasattr(provider, "validate_connection")
    assert callable(provider.validate_connection)

    assert hasattr(provider, "refresh_tools")
    assert callable(provider.refresh_tools)

    assert hasattr(provider, "get_tool_schema")
    assert callable(provider.get_tool_schema)

    assert hasattr(provider, "validate_tool")
    assert callable(provider.validate_tool)


class CompleteProvider(ToolProviderAdapter):
    """A provider that implements all required methods."""

    async def validate_connection(self) -> ToolProviderValidationResult:
        """Mock implementation."""
        return ToolProviderValidationResult(valid=True, provider_type="complete", validated_at=datetime.now(UTC))

    async def refresh_tools(self) -> list[Tool]:
        """Mock implementation."""
        return []

    async def get_tool_schema(self, tool_name: str) -> ToolSchema:
        """Mock implementation."""
        return ToolSchema(name=tool_name, description=tool_name, input_schema={})

    async def validate_tool(self, tool_name: str, parameters=None) -> ToolValidationResult:
        """Mock implementation."""
        return ToolValidationResult(
            success=True,
            duration_ms=1,
            status="",
            message=f"{tool_name}::{parameters!s}",
            validated_at=datetime.now(UTC),
        )

    async def get_base_tools(self) -> list[BaseTool]:
        """Mock implementation."""
        return []


def test_complete_provider_recognized() -> None:
    """Test that complete implementations are recognized as protocol compliant."""
    complete = CompleteProvider()

    # Should be recognized as implementing the protocol
    assert isinstance(complete, ToolProviderAdapter)


def test_protocol_typing_behavior() -> None:
    """Test protocol typing behavior with type annotations."""

    def accepts_provider(provider: ToolProviderAdapter) -> str:
        """Accept a ToolProviderAdapter."""
        return f"Provider: {type(provider).__name__}"

    # Should accept MCPProvider
    mcp_provider = MCPProvider(base_url="http://localhost:8080", api_key="test-key")
    result = accepts_provider(mcp_provider)
    assert "MCPProvider" in result

    # Should accept any object that implements the protocol
    complete_provider = CompleteProvider()
    result = accepts_provider(complete_provider)
    assert "CompleteProvider" in result


def test_protocol_method_signatures() -> None:
    """Test that protocol methods have correct signatures."""
    # Test MCPProvider has correct method signatures
    provider = MCPProvider(base_url="http://localhost:8080", api_key="test-key")

    # validate_connection should be async and take no args (except self)
    sig = inspect.signature(provider.validate_connection)
    assert len(sig.parameters) == 0  # No parameters except self (which is implicit)

    # refresh_tools should be async and take no args (except self)
    sig = inspect.signature(provider.refresh_tools)
    assert len(sig.parameters) == 0

    # get_tool_schema should take tool_name parameter
    sig = inspect.signature(provider.get_tool_schema)
    assert len(sig.parameters) == 1
    assert "tool_name" in sig.parameters

    # validate_tool should take tool_name and optional parameters
    sig = inspect.signature(provider.validate_tool)
    assert len(sig.parameters) == 2
    assert "tool_name" in sig.parameters
    assert "parameters" in sig.parameters
