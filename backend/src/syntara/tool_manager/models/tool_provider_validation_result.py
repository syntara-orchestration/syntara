"""Tool provider validation result models."""

from datetime import datetime
from typing import ClassVar

from pydantic import ConfigDict
from sqlmodel import SQLModel


class ToolProviderValidationResult(SQLModel):
    """Result of validating a connection to a tool provider.

    Attributes:
        valid: Whether the connection validation was successful
        provider_type: The type of provider that was validated
        validated_at: Timestamp when validation was performed
        error: Optional error message if validation failed
        timeout: Whether the validation failed due to a timeout

    """

    valid: bool
    provider_type: str
    validated_at: datetime
    error: str | None = None
    timeout: bool = False

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",  # Reject unknown fields
    )  # type: ignore[assignment]
