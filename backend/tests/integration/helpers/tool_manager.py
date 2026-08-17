"""Helper functions for Tools."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.integrations.models.integration import Integration
from syntara.tool_manager.models import Tool, ToolStatus
from syntara.tool_manager.models.tool import ToolParameter, ToolParameterType


@asynccontextmanager
async def wait_for_tool_status(
    client: AsyncClient, tool_id: str, expected_status: str, max_wait_time: float = 10.0, wait_interval: float = 0.2
) -> AsyncGenerator[dict[str, Any] | None, None]:
    """Context manager that waits for a tool to reach a specific status.

    This is useful for testing scenarios where tools may be automatically disabled
    or their status changes due to background processes.

    Args:
        client: The HTTP client to use for polling
        tool_id: The ID of the tool to monitor
        expected_status: The status to wait for (e.g., "error", "active")
        max_wait_time: Maximum time to wait in seconds (default: 10.0)
        wait_interval: How often to check in seconds (default: 0.2)

    Yields:
        The final tool data after status change or timeout

    """
    elapsed_time = 0.0
    final_data: dict[str, Any] | None = None

    while elapsed_time < max_wait_time:
        # Check the current status of the tool
        status_response = await client.get(f"/api/v1/tools/{tool_id}")
        if status_response.status_code == 200:
            status_data = status_response.json()
            if status_data.get("status") == expected_status:
                final_data = status_data
                break

        await asyncio.sleep(wait_interval)
        elapsed_time += wait_interval

    # If we didn't get the expected status, get the current state for testing
    if final_data is None:
        status_response = await client.get(f"/api/v1/tools/{tool_id}")
        if status_response.status_code == 200:
            final_data = status_response.json()

    yield final_data


class ToolFactory:
    """Factory class for creating test tools with configurable properties."""

    def __init__(self, session: AsyncSession, integration: Integration, user: User) -> None:
        """Initialize the ToolFactory with database session and required entities.

        Args:
            session: AsyncSession for database operations
            integration: Integration instance to associate with created tools
            user: User instance to set as creator/updater of tools

        """
        self.session = session
        self.integration = integration
        self.user = user

    async def create_tools(
        self,
        count: int,
        name_prefix: str = "Test Tool",
        namespace_prefix: str = "test",
        statuses: list[ToolStatus] | None = None,
        enabled_states: list[bool] | None = None,
        descriptions: list[str] | None = None,
    ) -> list[Tool]:
        """Create multiple tools with configurable properties.

        Args:
            count: Number of tools to create
            name_prefix: Prefix for tool names (will be followed by numbers)
            namespace_prefix: Prefix for namespaced names
            statuses: List of statuses to cycle through (defaults to AVAILABLE)
            enabled_states: List of enabled states to cycle through (defaults to True)
            descriptions: List of descriptions to cycle through (defaults to generic descriptions)

        Returns:
            List of created Tool objects

        """
        if statuses is None:
            statuses = [ToolStatus.AVAILABLE]
        if enabled_states is None:
            enabled_states = [True]
        if descriptions is None:
            descriptions = [f"{name_prefix} for testing"]

        tools = []
        for i in range(count):
            status = statuses[i % len(statuses)]
            enabled = enabled_states[i % len(enabled_states)]
            description = descriptions[i % len(descriptions)]

            tool = Tool(
                integration_id=self.integration.id,
                name=f"{name_prefix} {i + 1}",
                description=description,
                namespaced_name=f"{namespace_prefix}::{name_prefix.lower().replace(' ', '_')}_{i + 1}",
                enabled=enabled,
                status=status,
                created_by=self.user.id,
                updated_by=self.user.id,
            )
            tools.append(tool)
            self.session.add(tool)

        await self.session.commit()

        for tool in tools:
            await self.session.refresh(tool)

        return tools

    async def create_bulk_tools(self, count: int = 3) -> list[Tool]:
        """Create tools suitable for bulk update testing."""
        return await self.create_tools(
            count=count,
            name_prefix="Bulk Test Tool",
            namespace_prefix="test",
            statuses=[ToolStatus.AVAILABLE],
            enabled_states=[True, True, False],  # Mix of enabled states for testing
        )

    async def create_concurrency_tools(self, count: int = 6) -> list[Tool]:
        """Create tools suitable for concurrency testing."""
        return await self.create_tools(
            count=count,
            name_prefix="Concurrency Tool",
            namespace_prefix="test",
            statuses=[ToolStatus.AVAILABLE],
            enabled_states=[True],  # All enabled for concurrency tests
        )

    async def create_list_tools(self) -> list[Tool]:
        """Create tools suitable for list/filter testing with varied properties."""
        # Predefined set of tools with specific names and properties for list testing
        tool_configs = [
            ("Alpha Tool", "test::alpha_tool", True, ToolStatus.AVAILABLE, "First tool for testing"),
            ("Beta Tool", "test::beta_tool", False, ToolStatus.ERROR, "Second tool for testing"),
            ("Gamma Tool", "test::gamma_tool", True, ToolStatus.AVAILABLE, "Third tool for testing"),
            ("Delta Tool", "test::delta_tool", False, ToolStatus.ERROR, "Fourth tool for testing"),
            ("Echo Tool", "test::echo_tool", False, ToolStatus.MISSING, "Fifth tool for testing"),
            ("Foxtrot Tool", "test::foxtrot_tool", True, ToolStatus.AVAILABLE, "Sixth tool for testing"),
        ]

        tools = []
        for name, namespaced_name, enabled, status, description in tool_configs:
            tool = Tool(
                integration_id=self.integration.id,
                name=name,
                description=description,
                namespaced_name=namespaced_name,
                enabled=enabled,
                status=status,
                created_by=self.user.id,
                updated_by=self.user.id,
            )
            tools.append(tool)
            self.session.add(tool)

        await self.session.commit()

        for tool in tools:
            await self.session.refresh(tool)

        return tools

    async def create_tools_with_parameters(self) -> list[Tool]:
        """Create tools with parameters for testing eager loading scenarios.

        Creates a variety of tools each with multiple parameters to test:
        - Eager loading of parameters in list operations
        - Parameter serialization in API responses
        - N+1 query prevention

        Returns:
            List of Tool objects with associated ToolParameter objects

        """
        # Define tools with their parameters
        tool_configs: list[dict[str, Any]] = [
            {
                "name": "Calculator Tool",
                "namespaced_name": "test::calculator_tool",
                "description": "Mathematical calculator with multiple parameter types",
                "enabled": True,
                "status": ToolStatus.AVAILABLE,
                "parameters": [
                    {
                        "name": "operation",
                        "type": ToolParameterType.STRING,
                        "description": "Mathematical operation to perform",
                        "required": True,
                    },
                    {
                        "name": "operand_a",
                        "type": ToolParameterType.NUMBER,
                        "description": "First number for calculation",
                        "required": True,
                    },
                    {
                        "name": "operand_b",
                        "type": ToolParameterType.NUMBER,
                        "description": "Second number for calculation",
                        "required": True,
                    },
                    {
                        "name": "precision",
                        "type": ToolParameterType.NUMBER,
                        "description": "Decimal precision for result",
                        "required": False,
                        "default_value": {"value": 2},
                    },
                ],
            },
            {
                "name": "Text Processor Tool",
                "namespaced_name": "test::text_processor_tool",
                "description": "Text processing tool with string and boolean parameters",
                "enabled": True,
                "status": ToolStatus.AVAILABLE,
                "parameters": [
                    {
                        "name": "input_text",
                        "type": ToolParameterType.STRING,
                        "description": "Text to process",
                        "required": True,
                    },
                    {
                        "name": "case_sensitive",
                        "type": ToolParameterType.BOOLEAN,
                        "description": "Whether processing should be case sensitive",
                        "required": False,
                        "default_value": {"value": False},
                    },
                    {
                        "name": "max_length",
                        "type": ToolParameterType.NUMBER,
                        "description": "Maximum length of processed text",
                        "required": False,
                        "default_value": {"value": 1000},
                    },
                ],
            },
            {
                "name": "Data Export Tool",
                "namespaced_name": "test::data_export_tool",
                "description": "Tool for exporting data with complex parameters",
                "enabled": False,
                "status": ToolStatus.ERROR,
                "parameters": [
                    {
                        "name": "export_format",
                        "type": ToolParameterType.STRING,
                        "description": "Format for data export (json, csv, xml)",
                        "required": True,
                    },
                    {
                        "name": "include_headers",
                        "type": ToolParameterType.BOOLEAN,
                        "description": "Whether to include column headers",
                        "required": False,
                        "default_value": {"value": True},
                    },
                    {
                        "name": "compression_level",
                        "type": ToolParameterType.NUMBER,
                        "description": "Compression level (0-9)",
                        "required": False,
                    },
                    {
                        "name": "metadata",
                        "type": ToolParameterType.OBJECT,
                        "description": "Additional metadata for export",
                        "required": False,
                        "example_value": {"author": "test", "version": "1.0"},
                    },
                    {
                        "name": "filters",
                        "type": ToolParameterType.ARRAY,
                        "description": "Array of filters to apply",
                        "required": False,
                        "example_value": {"filters": ["active", "recent"]},
                    },
                ],
            },
        ]

        tools = []
        for tool_config in tool_configs:
            # Create the tool
            tool = Tool(
                integration_id=self.integration.id,
                name=tool_config["name"],
                description=tool_config["description"],
                namespaced_name=tool_config["namespaced_name"],
                enabled=tool_config["enabled"],
                status=tool_config["status"],
                created_by=self.user.id,
                updated_by=self.user.id,
            )
            tools.append(tool)
            self.session.add(tool)

        # Create parameters for each tool
        for tool, tool_config in zip(tools, tool_configs, strict=True):
            for param_config in tool_config["parameters"]:
                parameter = ToolParameter(
                    tool_id=tool.id,
                    name=param_config["name"],
                    type=param_config["type"],
                    description=param_config["description"],
                    required=param_config["required"],
                    default_value=param_config.get("default_value"),
                    example_value=param_config.get("example_value"),
                )
                self.session.add(parameter)

        # Commit all changes
        await self.session.commit()

        # Refresh tools to get updated relationships
        for tool in tools:
            await self.session.refresh(tool)

        return tools
