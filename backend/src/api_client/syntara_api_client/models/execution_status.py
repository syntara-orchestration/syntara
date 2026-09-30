from enum import Enum


class ExecutionStatus(str, Enum):
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    DENIED = "denied"
    FAILED = "failed"
    PAUSED = "paused"
    PENDING = "pending"
    RUNNING = "running"

    def __str__(self) -> str:
        return str(self.value)
