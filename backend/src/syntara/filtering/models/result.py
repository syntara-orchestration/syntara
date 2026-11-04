"""Immutable filter decisions with sanitized, machine-readable error codes."""

from enum import StrEnum
from typing import ClassVar, Self

from pydantic import ConfigDict, model_validator
from sqlmodel import SQLModel


class FilterOutcome(StrEnum):
    """Content decisions without persistence or acknowledgement authority."""

    MATCH = "match"
    NO_MATCH = "no_match"
    EVALUATION_ERROR = "evaluation_error"


class FilterErrorCode(StrEnum):
    """Safe categories that never contain expression or input contents."""

    INVALID_INPUT = "filter_invalid_input"
    NON_BOOLEAN = "filter_non_boolean"
    WRONG_TYPE = "filter_wrong_type"
    EVALUATION_FAILED = "filter_evaluation_failed"


class FilterResult(SQLModel):
    """One evaluation result; callers own any delivery or audit effects."""

    outcome: FilterOutcome
    error_code: FilterErrorCode | None = None

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)  # type: ignore[assignment]

    @model_validator(mode="after")
    def validate_error_code(self) -> Self:
        """Require an error code exactly when evaluation failed."""
        if (self.outcome == FilterOutcome.EVALUATION_ERROR) != (self.error_code is not None):
            msg = "Only evaluation errors must carry a filter error code"
            raise ValueError(msg)
        return self
