from enum import Enum


class InitializationKind(str, Enum):
    ADDED_PARTITION = "added_partition"
    FIRST_ACTIVATION = "first_activation"

    def __str__(self) -> str:
        return str(self.value)
