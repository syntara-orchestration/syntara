"""UsageCounter SQLModel definition for database storage.

This module contains the UsageCounter SQLModel class that extends UserOwnedResource
with usage tracking fields as defined in the OpenAPI specification.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import DateTime, Field

from syntara.core.constants import FieldLimits
from syntara.core.models.base.user_owned import UserOwnedResource


class CounterType(str, Enum):
    """Usage counter scope types."""

    PROVIDER = "provider"
    TOOL = "tool"
    USER = "user"
    PROVIDER_USER = "provider_user"
    TOOL_USER = "tool_user"


class WindowDuration(str, Enum):
    """Time window duration types."""

    HOUR = "hour"
    DAY = "day"
    MONTH = "month"


class UsageCounter(UserOwnedResource, table=True):
    """Usage counter for cumulative statistics tracking.

    Maintains cumulative usage statistics with rolling time window calculations.

    Inherits from UserOwnedResource:
        id: UUID primary key
        created_at: Creation timestamp
        updated_at: Last update timestamp
        created_by: UUID of user who created the resource
        updated_by: Optional UUID of user who last updated the resource
        deleted_at: Optional timestamp when resource was soft deleted
        deleted_by: Optional UUID of user who performed the soft delete
        labels: Optional key-value metadata
    """

    __tablename__ = "usage_counters"

    counter_type: CounterType = Field(
        description="Counter scope: provider, tool, user, provider_user, tool_user", index=True
    )

    tool_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("tools.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        description="Foreign key to Tool",
    )

    integration_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("integrations.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        description="Foreign key to Integration",
    )

    user_id: UUID | None = Field(default=None, description="User identifier", index=True)

    time_window: str = Field(
        min_length=1,
        max_length=FieldLimits.TIME_WINDOW_MAX_LENGTH,
        sa_type=String(FieldLimits.TIME_WINDOW_MAX_LENGTH),  # type: ignore[call-overload]
        description="Time window identifier (e.g., '2025-01-01-14')",
        index=True,
    )

    window_duration: WindowDuration = Field(description="Window duration: hour, day, month")

    request_count: int = Field(default=0, ge=0, description="Number of requests in window")

    success_count: int = Field(default=0, ge=0, description="Number of successful requests")

    error_count: int = Field(default=0, ge=0, description="Number of failed requests")

    timeout_count: int = Field(
        default=0, ge=0, description="Number of timed-out requests", sa_column_kwargs={"server_default": "0"}
    )

    total_duration_ms: int = Field(default=0, ge=0, description="Total execution time in milliseconds")

    window_start: datetime = Field(
        description="Window start timestamp",
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        index=True,
    )
    window_end: datetime = Field(
        description="Window end timestamp",
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        index=True,
    )
