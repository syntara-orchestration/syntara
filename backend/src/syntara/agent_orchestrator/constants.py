"""Constants for the agent orchestrator module."""

from enum import StrEnum


class AgentRoutes(StrEnum):
    """Constants for agent routing within the LangGraph."""

    ORCHESTRATOR = "orchestrator"
    GENERIC_AGENT = "generic_agent"
    TOOLS = "tools"
    END = "__end__"
