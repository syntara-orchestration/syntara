"""Tool bulk update request and response models."""

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator
from sqlmodel import SQLModel

from syntara.core.exceptions import SafeValueError

MAX_BULK_UPDATES: int = 50


class ToolBulkUpdate(SQLModel):
    """Request model for bulk updating tool status.

    Attributes:
        tool_ids: List of tool UUIDs to update (max 50)
        enabled: Enable or disable the Tool.

    """

    tool_ids: list[UUID] = Field(
        max_length=MAX_BULK_UPDATES, description=f"List of tool UUIDs to update (max {MAX_BULK_UPDATES})"
    )

    enabled: bool = Field(description="Enable/disable the Tool")

    @field_validator("tool_ids")
    @classmethod
    def validate_tool_ids(cls, v: list[UUID]) -> list[UUID]:
        """Validate tool_ids list is not empty and within limits."""
        if not v:
            msg = "tool_ids cannot be empty"
            raise SafeValueError(msg)
        if len(v) > MAX_BULK_UPDATES:
            msg = f"Cannot update more than {MAX_BULK_UPDATES} tools at once"
            raise SafeValueError(msg)
        return v

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",  # Reject unknown fields
    )  # type: ignore[assignment]


class ToolBulkUpdateResponse(SQLModel):
    """Response model for bulk tool update."""

    updated_count: int = Field(description="Number of tools updated")
    skipped_count: int = Field(description="Number of tool IDs not found or not in scope")
    updated_at: datetime = Field(description="Timestamp of the update")
