from enum import Enum


class KafkaOffsetGapPolicy(str, Enum):
    EARLIEST = "earliest"
    FAIL = "fail"
    LATEST = "latest"

    def __str__(self) -> str:
        return str(self.value)
