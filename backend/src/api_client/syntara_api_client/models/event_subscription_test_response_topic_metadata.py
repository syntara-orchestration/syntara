from enum import Enum


class EventSubscriptionTestResponseTopicMetadata(str, Enum):
    FAILED = "failed"
    UNVERIFIED = "unverified"
    VERIFIED = "verified"

    def __str__(self) -> str:
        return str(self.value)
