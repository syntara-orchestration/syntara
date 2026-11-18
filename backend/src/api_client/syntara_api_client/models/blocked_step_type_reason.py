from enum import Enum


class BlockedStepTypeReason(str, Enum):
    EXPLICIT_DENY = "explicit_deny"
    NO_MATCHING_ALLOW = "no_matching_allow"

    def __str__(self) -> str:
        return str(self.value)
