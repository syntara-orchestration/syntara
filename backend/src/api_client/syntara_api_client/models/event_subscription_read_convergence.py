from enum import Enum


class EventSubscriptionReadConvergence(str, Enum):
    APPLIED = "applied"
    PENDING = "pending"

    def __str__(self) -> str:
        return str(self.value)
