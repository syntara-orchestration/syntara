from enum import Enum


class FormPromptStatus(str, Enum):
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    PENDING = "pending"
    SUBMITTED = "submitted"

    def __str__(self) -> str:
        return str(self.value)
