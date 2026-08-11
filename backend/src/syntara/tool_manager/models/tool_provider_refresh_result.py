"""Tool provider refresh result models."""

from datetime import datetime
from typing import ClassVar

from pydantic import ConfigDict
from sqlmodel import SQLModel


class ToolProviderRefreshResult(SQLModel):
    """Result of refreshing tools from a tool provider.

    Attributes:
        refreshed_count: Number of new tools discovered and added
        updated_count: Number of existing tools that were updated
        disabled_count: Number of tools that were disabled (not found in provider)
        refreshed_at: Timestamp when refresh operation was performed

    """

    refreshed_count: int
    updated_count: int
    disabled_count: int
    refreshed_at: datetime

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",  # Reject unknown fields
    )  # type: ignore[assignment]
