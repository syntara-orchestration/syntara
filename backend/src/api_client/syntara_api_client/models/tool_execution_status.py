from enum import Enum


class ToolExecutionStatus(str, Enum):
    ERROR = "error"
    RUNNING = "running"
    SUCCESS = "success"
    TIMEOUT = "timeout"

    def __str__(self) -> str:
        return str(self.value)
