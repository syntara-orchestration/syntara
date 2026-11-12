"""Sanitized failures while preparing a shared CEL filter."""

from enum import StrEnum


class FilterValidationCode(StrEnum):
    """Safe compiler failures; types below the dynamic input root are checked at runtime."""

    INVALID_EXPRESSION = "filter_invalid_expression"
    INVALID_SYNTAX = "filter_invalid_syntax"
    UNSUPPORTED_VARIABLE = "filter_unsupported_variable"
    UNSUPPORTED_FUNCTION = "filter_unsupported_function"
    UNSUPPORTED_CONSTRUCT = "filter_unsupported_construct"
    INVALID_MACRO = "filter_invalid_macro"
    NON_BOOLEAN = "filter_non_boolean"


class FilterValidationError(ValueError):
    """Reject a configuration without exposing source text or parser diagnostics."""

    def __init__(self, code: FilterValidationCode, *, line: int | None = None, column: int | None = None) -> None:
        """Store the safe validation code as the exception message."""
        self.code = code
        self.line = line
        self.column = column
        super().__init__(code.value)
