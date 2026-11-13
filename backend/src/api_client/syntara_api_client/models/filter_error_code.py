from enum import Enum


class FilterErrorCode(str, Enum):
    FILTER_EVALUATION_FAILED = "filter_evaluation_failed"
    FILTER_INVALID_INPUT = "filter_invalid_input"
    FILTER_NON_BOOLEAN = "filter_non_boolean"
    FILTER_WRONG_TYPE = "filter_wrong_type"

    def __str__(self) -> str:
        return str(self.value)
