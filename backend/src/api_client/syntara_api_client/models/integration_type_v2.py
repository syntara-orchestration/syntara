from enum import Enum


class IntegrationTypeV2(str, Enum):
    ANSIBLE_AUTOMATION_PLATFORM = "ansible_automation_platform"
    KAFKA = "kafka"
    LLM_PROVIDER = "llm_provider"
    MCP_SERVER = "mcp_server"

    def __str__(self) -> str:
        return str(self.value)
