"""Base provider interface and protocols for tool management system."""

from abc import abstractmethod
from typing import Any, Protocol, runtime_checkable

from langchain_core.tools import BaseTool

from syntara.tool_manager.models import (
    Tool,
    ToolProviderValidationResult,
    ToolSchema,
    ToolValidationResult,
)


@runtime_checkable
class ToolProviderAdapter(Protocol):
    """Protocol for tool provider adapters.

    This protocol defines the interface that all tool providers must implement
    to integrate with the syntara tool management system. Providers can be local
    or remote services that expose tools via various protocols.
    """

    @abstractmethod
    async def validate_connection(self) -> ToolProviderValidationResult:
        """Validate connection to the tool provider.

        Returns:
            ToolProviderValidationResult containing validation details

        """

    @abstractmethod
    async def refresh_tools(self) -> list[Tool]:
        """Refresh and discover tools from the provider.

        Fetches the current list of tools available from this provider.
        This method should be idempotent and can be called multiple times
        to update the tool registry.

        Returns:
            list[Tool]: List of available tools with their schemas

        Raises:
            ProviderError: If tool discovery fails
            TimeoutError: If operation times out
            ConnectionError: If unable to communicate with provider

        """

    @abstractmethod
    async def get_tool_schema(self, tool_name: str) -> ToolSchema:
        """Get detailed schema for a specific tool.

        Args:
            tool_name: Name of the tool to get schema for

        Returns:
            ToolSchema containing tool schema with input/output specifications

        Raises:
            ToolNotFoundError: If tool doesn't exist on provider
            ProviderError: If schema retrieval fails
            TimeoutError: If operation times out

        """

    @abstractmethod
    async def validate_tool(self, tool_name: str, parameters: dict[str, Any] | None = None) -> ToolValidationResult:
        """Validate tool functionality and server communication.

        This method validates that the tool can be called and communicates properly
        with the provider. It does not execute the tool for actual work, but
        validates connectivity and basic functionality.

        Args:
            tool_name: Name of the tool to validate
            parameters: Optional minimal parameters for validation

        Returns:
            ToolValidationResult containing validation details

        Raises:
            ToolNotFoundError: If tool doesn't exist on provider
            ProviderError: If tool validation fails due to provider issues
            TimeoutError: If validation times out

        """

    @abstractmethod
    async def get_base_tools(self) -> list[BaseTool]:
        """Get LangChain BaseTools from provider without conversion.

        Returns raw BaseTools for use in Agent Orchestrator without
        converting to Tool domain models. This enables direct use of
        LangChain tools for agent execution.

        Returns:
            list[BaseTool]: Raw LangChain tools from provider

        Raises:
            ProviderError: If tool retrieval fails
            TimeoutError: If operation times out
            ConnectionError: If unable to communicate with provider

        """
