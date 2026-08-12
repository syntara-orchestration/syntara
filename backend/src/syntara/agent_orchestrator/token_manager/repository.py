"""Data access layer for token usage and configuration.

This module provides TokenUsageRepository for database operations:
- User token configuration retrieval and updates
- Token usage record creation and post-LLM update
- Rolling window usage calculation
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.token_manager.exceptions import UserTokenConfigNotFoundError
from syntara.agent_orchestrator.token_manager.models import (
    TokenUsageRecord,
    UsageDetailsResult,
    UserTokenConfig,
)

logger = structlog.stdlib.get_logger(__name__)


class TokenUsageRepository:
    """Repository for token usage and configuration data access.

    Provides methods for:
    - Retrieving and updating user token configurations
    - Recording token usage
    - Calculating current usage within rolling windows

    This repository uses async SQLAlchemy sessions for all database operations.
    """

    async def get_user_config(self, user_id: UUID, session: AsyncSession) -> UserTokenConfig:
        """Get token configuration for a user.

        For development, if no configuration exists and this is the dev-user,
        a default configuration is created automatically.

        Args:
            user_id: The user's UUID
            session: Async database session

        Returns:
            UserTokenConfig for the user

        Raises:
            UserTokenConfigNotFoundError: If no configuration exists for the user
                (except for dev-user, which gets a default config created)

        """
        statement = select(UserTokenConfig).where(UserTokenConfig.user_id == user_id)
        result = await session.exec(statement)
        config = result.one_or_none()

        if config is None:
            raise UserTokenConfigNotFoundError(user_id)

        return config

    async def get_user_config_with_lock(self, user_id: UUID, session: AsyncSession) -> UserTokenConfig:
        """Get token configuration for a user with row-level lock.

        This method uses SELECT FOR UPDATE to acquire a row-level lock on the
        user's configuration, preventing concurrent transactions from reading
        stale data during validation. This is critical for preventing race
        conditions when multiple requests validate against the same user's limit.

        Args:
            user_id: The user's UUID
            session: Async database session

        Returns:
            UserTokenConfig for the user

        Raises:
            UserTokenConfigNotFoundError: If no configuration exists for the user

        """
        statement = select(UserTokenConfig).where(UserTokenConfig.user_id == user_id).with_for_update()
        result = await session.exec(statement)
        config = result.one_or_none()

        if config is None:
            raise UserTokenConfigNotFoundError(user_id)

        return config

    async def calculate_current_usage(
        self,
        user_id: UUID,
        window_duration_seconds: int,
        session: AsyncSession,
    ) -> int:
        """Calculate current token usage within the rolling window.

        This method sums all token usage records for the user that fall within
        the rolling time window (now - window_duration_seconds to now).

        Note on the update model: token_count starts as the tiktoken estimate
        (budget reservation for in-flight requests) and is updated to the actual
        total (prompt_tokens + completion_tokens) after the LLM call completes.
        SUM(token_count) therefore reflects estimates for in-flight invocations
        and actual totals for completed invocations — no query changes needed.

        Args:
            user_id: The user's UUID
            window_duration_seconds: Rolling window duration in seconds
            session: Async database session

        Returns:
            Total token count within the rolling window (0 if no usage)

        """
        # Calculate the cutoff time (window start)
        cutoff_time = datetime.now(UTC) - timedelta(seconds=window_duration_seconds)

        # Query for sum of token_count within the window
        statement = (
            select(func.coalesce(func.sum(TokenUsageRecord.token_count), 0))
            .where(TokenUsageRecord.user_id == user_id)
            .where(TokenUsageRecord.request_timestamp >= cutoff_time)
        )

        result = await session.exec(statement)
        total = result.one()

        return int(total)

    async def record_usage(
        self,
        user_id: UUID,
        token_count: int,
        session: AsyncSession,
        request_text_hash: str | None = None,
        estimated_input_tokens: int | None = None,
        invocation_id: UUID | None = None,
    ) -> TokenUsageRecord:
        """Record a new token usage entry.

        Creates a TokenUsageRecord with the current timestamp. The record may
        later be updated with actual token counts after the LLM call completes.

        Args:
            user_id: The user's UUID
            token_count: Number of tokens in the request (tiktoken estimate)
            session: Async database session
            request_text_hash: Optional hash of request text
            estimated_input_tokens: Tiktoken estimate preserved for audit
            invocation_id: Optional FK to invocations table

        Returns:
            The created TokenUsageRecord

        """
        record = TokenUsageRecord(
            user_id=user_id,
            token_count=token_count,
            request_text_hash=request_text_hash,
            estimated_input_tokens=estimated_input_tokens,
            invocation_id=invocation_id,
        )

        session.add(record)
        await session.flush()
        await session.refresh(record)

        return record

    async def update_user_config(
        self,
        user_id: UUID,
        token_limit: int,
        window_duration_seconds: int,
        session: AsyncSession,
    ) -> UserTokenConfig:
        """Update or create user token configuration.

        Args:
            user_id: The user's UUID
            token_limit: New token limit (must be > 0)
            window_duration_seconds: New window duration (must be > 0)
            session: Async database session

        Returns:
            The updated or created UserTokenConfig

        """
        # Try to get existing config
        statement = select(UserTokenConfig).where(UserTokenConfig.user_id == user_id)
        result = await session.exec(statement)
        config = result.one_or_none()

        if config is None:
            # Create new config
            config = UserTokenConfig(
                user_id=user_id,
                token_limit=token_limit,
                window_duration_seconds=window_duration_seconds,
            )
            session.add(config)
        else:
            # Update existing config
            config.token_limit = token_limit
            config.window_duration_seconds = window_duration_seconds

        await session.flush()
        await session.refresh(config)

        return config

    async def update_with_actual_token_usage(
        self,
        invocation_id: UUID,
        prompt_tokens: int,
        completion_tokens: int,
        token_count: int,
        usage_details: UsageDetailsResult,
        session: AsyncSession,
        user_id: UUID | None = None,
    ) -> bool:
        """Update a token usage record with actual provider-reported token counts.

        Finds the record by invocation_id and updates it with actual token data
        from the LLM provider response. If no pre-LLM record exists (e.g., when
        context assembly had no documents to validate), creates a new record with
        the actual token counts.

        Args:
            invocation_id: The invocation UUID to find the record
            prompt_tokens: Actual input tokens from the provider
            completion_tokens: Actual output tokens from the provider
            token_count: Actual total (prompt_tokens + completion_tokens)
            usage_details: Full provider-reported token breakdown (dict for single
                call, list of dicts for multiple calls)
            session: Async database session
            user_id: User UUID, required when creating a new record

        Returns:
            True if a record was found/created and updated, False otherwise

        """
        expected = prompt_tokens + completion_tokens
        if token_count != expected:
            msg = f"token_count ({token_count}) must equal prompt_tokens + completion_tokens ({expected})"
            raise ValueError(msg)

        statement = select(TokenUsageRecord).where(TokenUsageRecord.invocation_id == invocation_id)
        result = await session.exec(statement)
        record = result.one_or_none()

        if record is None:
            if user_id is None:
                logger.warning(
                    "No TokenUsageRecord found for invocation_id=%s and no user_id provided, skipping",
                    invocation_id,
                )
                return False

            logger.info(
                "No pre-LLM TokenUsageRecord found for invocation_id=%s, creating with actual tokens",
                invocation_id,
            )
            record = TokenUsageRecord(
                user_id=user_id,
                token_count=token_count,
                invocation_id=invocation_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                usage_details=usage_details,
            )
            session.add(record)
            await session.flush()
            return True

        record.prompt_tokens = prompt_tokens
        record.completion_tokens = completion_tokens
        record.token_count = token_count
        record.usage_details = usage_details

        await session.flush()

        return True
