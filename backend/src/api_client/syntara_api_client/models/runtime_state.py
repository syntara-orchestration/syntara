from enum import Enum


class RuntimeState(str, Enum):
    ACTIVE = "active"
    BACKOFF = "backoff"
    BLOCKED = "blocked"
    DRAINING = "draining"
    STARTING = "starting"
    STOPPED = "stopped"

    def __str__(self) -> str:
        return str(self.value)
