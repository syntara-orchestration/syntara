from enum import Enum


class BatchFormPromptStatus(str, Enum):
    CANCELLED = "cancelled"
    EXPIRED = "expired"

    def __str__(self) -> str:
        return str(self.value)
