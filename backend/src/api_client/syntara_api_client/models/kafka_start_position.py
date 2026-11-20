from enum import Enum


class KafkaStartPosition(str, Enum):
    EARLIEST = "earliest"
    LATEST = "latest"

    def __str__(self) -> str:
        return str(self.value)
