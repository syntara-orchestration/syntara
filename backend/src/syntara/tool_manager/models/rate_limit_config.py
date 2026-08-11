"""RateLimitConfig SQLModel definition for database storage.

This module contains the RateLimitConfig SQLModel class that extends UserOwnedResource
with rate limiting configuration fields as defined in the OpenAPI specification.
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import String
from sqlmodel import DateTime, Field

from syntara.core.constants import FieldLimits
from syntara.core.models.base.user_owned import UserOwnedResource


class TargetType(str, Enum):
    """Rate limit target scope types."""

    PROVIDER = "provider"
    TOOL = "tool"
    USER = "user"


class RateLimit(UserOwnedResource, table=True):
    """Rate limit configuration for providers, tools, and users.

    Defines usage limits and time windows at provider, tool, and user levels.
    This model matches the RateLimit schema from the metrics contract.

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

    __tablename__ = "rate_limits"

    target_type: TargetType = Field(description="Limit scope: provider, tool, or user", index=True)

    target_id: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Target identifier (UUID for provider/tool, string for user)",
        index=True,
    )

    target_name: str | None = Field(
        default=None,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Human-readable target name for display",
    )

    requests_per_window: int = Field(ge=1, description="Maximum requests allowed")

    window_duration_seconds: int = Field(ge=1, description="Time window in seconds")

    burst_allowance: int = Field(default=0, ge=0, description="Additional burst requests")

    enabled: bool = Field(default=True, description="Whether limit is active")

    current_usage: int = Field(default=0, ge=0, description="Current usage count in window")

    usage_reset_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        nullable=True,
        description="When current usage counter resets",
    )
