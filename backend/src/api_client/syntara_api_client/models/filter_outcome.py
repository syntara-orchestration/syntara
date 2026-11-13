from enum import Enum


class FilterOutcome(str, Enum):
    EVALUATION_ERROR = "evaluation_error"
    MATCH = "match"
    NO_MATCH = "no_match"

    def __str__(self) -> str:
        return str(self.value)
