from enum import Enum


class RecoveryPolicy(str, Enum):
    CURRENT_END = "current_end"
    RETAINED_BEGINNING = "retained_beginning"

    def __str__(self) -> str:
        return str(self.value)
