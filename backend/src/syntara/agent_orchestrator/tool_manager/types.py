"""Type definitions for the Tool Manager module."""

from typing import NamedTuple
from uuid import UUID

from langchain_core.tools import BaseTool

from syntara.tool_manager.models.tool import ToolWithParameters


class NamespacedBaseTool(NamedTuple):
    """A BaseTool with its integration context for matching and display."""

    integration_id: UUID
    integration_name: str
    tool_name: str
    base_tool: BaseTool

    @property
    def namespaced_name(self) -> str:
        """Return the display name as 'integration_name::tool_name'."""
        return f"{self.integration_name}::{self.tool_name}"


# Type alias for tool discovery results: (enabled_tools, disabled_tools)
ToolDiscoveryResult = tuple[list[ToolWithParameters], list[ToolWithParameters]]
