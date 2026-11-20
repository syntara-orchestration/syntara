from enum import Enum


class IntegrationType(str, Enum):
    ANSIBLE_AUTOMATION_PLATFORM = "ansible_automation_platform"
    LLM_PROVIDER = "llm_provider"
    MCP_SERVER = "mcp_server"

    def __str__(self) -> str:
        return str(self.value)
