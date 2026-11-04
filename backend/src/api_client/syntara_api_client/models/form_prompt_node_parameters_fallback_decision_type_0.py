from enum import Enum


class FormPromptNodeParametersFallbackDecisionType0(str, Enum):
    FALLBACK = "fallback"
    SUBMIT = "submit"

    def __str__(self) -> str:
        return str(self.value)
