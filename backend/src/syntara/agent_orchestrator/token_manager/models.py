"""Data models for token counting and validation.

This module defines SQLModel entities for token usage tracking:
- UserTokenConfig: Per-user token limit configuration
- TokenUsageRecord: Records of token usage (created with estimate, updated with actuals)

Both models inherit from BaseResource for consistent system-managed metadata.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import TIMESTAMP, Column, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from syntara.core.models.base.base_resource import BaseResource

# Type aliases for LLM token usage details
type UsageDetails = dict[str, Any]
type UsageDetailsResult = list[UsageDetails] | None


class UserTokenConfig(BaseResource, table=True):
    """Per-user token limit configuration.

    Each user has their own token limit and rolling window duration.
    The rolling window determines the time period over which token usage is tracked.

    Inherits from BaseResource:
        - id: UUID (primary key, auto-generated)
        - created_at: datetime (UTC, auto-managed)
        - updated_at: datetime (UTC, auto-managed)
        - labels: dict[str, str] (JSONB, for metadata)

    Attributes:
        user_id: Foreign key to User table (unique - one config per user)
        token_limit: Maximum tokens allowed within the rolling window (must be > 0)
        window_duration_seconds: Rolling window size in seconds (must be > 0)
        model_name: Tiktoken model name for token counting (defaults to "gpt-4")

    """

    __tablename__ = "user_token_configs"

    # Domain-specific fields (BaseResource fields inherited automatically)
    user_id: UUID = Field(foreign_key="users.id", unique=True, index=True)

    # Token limit within the rolling window
    token_limit: int = Field(gt=0, description="Maximum tokens allowed within window")

    # Rolling window duration in seconds
    window_duration_seconds: int = Field(
        gt=0,
        description="Rolling window duration in seconds (e.g., 3600 for 1 hour, 86400 for 24 hours)",
    )

    # Tiktoken model name for token encoding
    model_name: str = Field(
        default="gpt-4",
        sa_column_kwargs={"server_default": text("'gpt-4'")},
        description="Tiktoken model name for token counting (e.g., 'gpt-4', 'gpt-3.5-turbo')",
    )


class TokenUsageRecord(BaseResource, table=True):
    """Record of token usage for a user's request.

    Records follow a two-phase lifecycle:
    1. Pre-LLM: Created with token_count as tiktoken estimate and estimated_input_tokens
       set to the same value. prompt_tokens/completion_tokens/usage_details are NULL.
    2. Post-LLM: Updated with actual provider-reported token counts. token_count is
       replaced with prompt_tokens + completion_tokens (actual total).

    The token_count field is the budget-relevant value used by calculate_current_usage:
    - In-flight requests: token_count = tiktoken estimate (budget reservation)
    - Completed requests: token_count = actual total (prompt_tokens + completion_tokens)

    Inherits from BaseResource:
        - id: UUID (primary key, auto-generated)
        - created_at: datetime (when record was inserted into DB, UTC, auto-managed)
        - updated_at: datetime (UTC, auto-managed)
        - labels: dict[str, str] (JSONB, for metadata)

    Note:
        request_timestamp is separate from created_at. It represents when the actual
        request was made, while created_at represents when the record was persisted
        to the database.

    Attributes:
        user_id: Foreign key to User table
        token_count: Budget-relevant token count (starts as estimate, updated to actual)
        request_timestamp: When the request was made (used for rolling window calculation)
        request_text_hash: Optional SHA-256 hash of request text (for debugging/deduplication)
        estimated_input_tokens: Tiktoken estimate recorded before the LLM call
        prompt_tokens: Actual input tokens reported by the provider after the LLM call
        completion_tokens: Actual output tokens reported by the provider after the LLM call
        invocation_id: FK to invocations table linking record to originating invocation
        usage_details: Full provider-reported token usage breakdown (JSONB)

    """

    __tablename__ = "token_usage_records"

    __table_args__ = (
        # Partial unique index: each invocation can have at most one token record
        Index(
            "ix_token_usage_records_invocation_id_unique",
            "invocation_id",
            unique=True,
            postgresql_where=text("invocation_id IS NOT NULL"),
        ),
    )

    # Domain-specific fields (BaseResource fields inherited automatically)
    user_id: UUID = Field(foreign_key="users.id", index=True)

    # Budget-relevant token count: starts as tiktoken estimate, updated to actual total
    token_count: int = Field(ge=0, description="Number of tokens in this request")

    # When the request was made (used for rolling window calculation)
    request_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(TIMESTAMP(timezone=True), index=True),
        description="When the request was made (for rolling window filtering)",
    )

    # Optional: hash of request text for deduplication/debugging
    request_text_hash: str | None = Field(default=None, max_length=64)

    # Pre-LLM estimate (preserved for audit/comparison with actual prompt_tokens)
    estimated_input_tokens: int | None = Field(default=None, ge=0)

    # Post-LLM actual token counts from the provider
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)

    # FK to invocations table (ON DELETE SET NULL preserves token records if invocation is deleted)
    # Index is defined in __table_args__ as a partial unique index
    invocation_id: UUID | None = Field(
        default=None,
        foreign_key="invocations.id",
        ondelete="SET NULL",
    )

    # Full provider-reported token usage breakdown (list of per-call details)
    usage_details: list[dict[str, Any]] | None = Field(default=None, sa_type=JSONB)
