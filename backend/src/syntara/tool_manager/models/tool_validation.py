"""Tool validation result models."""

from datetime import datetime
from typing import Any, ClassVar

from pydantic import ConfigDict
from sqlmodel import SQLModel


class ToolValidationResult(SQLModel):
    """Result of validating a tool's functionality.

    Attributes:
        success: Whether the tool validation was successful
        duration_ms: Duration of the validation in milliseconds
        status: Status of the validation (success/failure/timeout)
        message: Descriptive message about the validation result
        validated_at: Timestamp when validation was performed
        validation_output: Optional output from the validation operation

    """

    success: bool
    duration_ms: int
    status: str
    message: str
    validated_at: datetime
    validation_output: Any = None

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",  # Reject unknown fields
    )  # type: ignore[assignment]
