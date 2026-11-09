from enum import Enum


class MetricsCategoryType(str, Enum):
    AGENT = "agent"
    API = "api"
    AUTHORIZATION = "authorization"
    CACHE = "cache"
    DATABASE = "database"
    ERROR = "error"
    EXECUTION_SERVICE = "execution_service"
    LLM = "llm"
    RETRY = "retry"
    SYSTEM_OVERHEAD = "system_overhead"
    SYSTEM_WIDE = "system_wide"
    TEMPORAL_WORKER = "temporal_worker"
    TOOL = "tool"
    WORKFLOW = "workflow"
    WORKFLOW_ENGINE = "workflow_engine"

    def __str__(self) -> str:
        return str(self.value)
