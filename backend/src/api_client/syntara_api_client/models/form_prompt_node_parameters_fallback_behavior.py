from enum import Enum


class FormPromptNodeParametersFallbackBehavior(str, Enum):
    FAIL = "fail"
    FALLBACK = "fallback"

    def __str__(self) -> str:
        return str(self.value)
