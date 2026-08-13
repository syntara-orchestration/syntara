"""Tool filtering logic for matching LangChain BaseTools with Tool Manager tools.

This module provides filtering functionality to match LangChain BaseTools retrieved
from MCP servers with ToolWithParameters from Tool Manager using (integration_id, name)
matching, which is immune to integration renames.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from uuid import UUID

    from langchain_core.tools import BaseTool

    from syntara.agent_orchestrator.tool_manager.types import NamespacedBaseTool
    from syntara.tool_manager.models.tool import ToolWithParameters

logger = structlog.stdlib.get_logger(__name__)


def filter_base_tools_by_enabled(
    namespaced_tools: list[NamespacedBaseTool],
    enabled_tools: list[ToolWithParameters],
) -> list[NamespacedBaseTool]:
    """Filter NamespacedBaseTools by enabled ToolWithParameters using (integration_id, name).

    Matches on the stable (integration_id, short_name) pair rather than the
    display-oriented namespaced_name string, so integration renames do not
    break tool resolution.

    Args:
        namespaced_tools: List of NamespacedBaseTool from MCP servers
        enabled_tools: List of enabled ToolWithParameters from Tool Manager

    Returns:
        List of NamespacedBaseTools that match enabled ToolWithParameters

    """
    if not namespaced_tools or not enabled_tools:
        return []

    enabled_keys: set[tuple[UUID, str]] = {(tool.integration_id, tool.name) for tool in enabled_tools}

    filtered_tools = []
    for nbt in namespaced_tools:
        key = (nbt.integration_id, nbt.tool_name)
        if key in enabled_keys:
            filtered_tools.append(nbt)
            logger.debug("Including enabled tool", tool_name=nbt.namespaced_name)
        else:
            logger.debug("Excluding tool (not enabled or not registered)", tool_name=nbt.namespaced_name)

    logger.info("Filtered tools from base tools", filtered_count=len(filtered_tools), base_count=len(namespaced_tools))
    return filtered_tools


def enhance_namespaced_tools_with_metadata(
    namespaced_tools: list[NamespacedBaseTool],
    enabled_tools: list[ToolWithParameters],
) -> list[BaseTool]:
    """Enhance NamespacedBaseTools with metadata from Tool Manager.

    Uses (integration_id, name) for matching, making it immune to renames.

    Args:
        namespaced_tools: List of NamespacedBaseTools (integration_id, integration_name, tool_name, BaseTool)
        enabled_tools: List of enabled ToolWithParameters from Tool Manager

    Returns:
        List of BaseTools enhanced with metadata

    """
    if not namespaced_tools or not enabled_tools:
        return [nbt.base_tool for nbt in namespaced_tools]

    key_to_db_info: dict[tuple[UUID, str], tuple[UUID, str, str]] = {
        (tool.integration_id, tool.name): (tool.id, str(tool.integration_id), tool.namespaced_name)
        for tool in enabled_tools
    }

    enhanced_tools = []
    for nbt in namespaced_tools:
        key = (nbt.integration_id, nbt.tool_name)
        if key in key_to_db_info:
            tool_id, integration_id, db_namespaced_name = key_to_db_info[key]

            if not hasattr(nbt.base_tool, "metadata") or nbt.base_tool.metadata is None:
                nbt.base_tool.metadata = {}
            nbt.base_tool.metadata["tool_id"] = str(tool_id)
            nbt.base_tool.metadata["namespaced_name"] = db_namespaced_name
            nbt.base_tool.metadata["integration_id"] = integration_id

            logger.debug("Enhanced tool with metadata", tool_name=nbt.namespaced_name, tool_id=tool_id)
        else:
            logger.warning("Could not find tool_id for tool", tool_name=nbt.namespaced_name)

        enhanced_tools.append(nbt.base_tool)

    logger.info("Enhanced tools with metadata", enhanced_count=len(enhanced_tools))
    return enhanced_tools
