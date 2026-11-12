from enum import Enum


class TextFieldDisplay(str, Enum):
    MASKED = "masked"
    MULTI_LINE = "multi_line"
    SINGLE_LINE = "single_line"

    def __str__(self) -> str:
        return str(self.value)
