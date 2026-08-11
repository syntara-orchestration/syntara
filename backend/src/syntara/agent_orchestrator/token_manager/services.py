"""Services for token counting and validation.

This module provides:
- TokenCalculator: Wraps tiktoken for token counting
- TokenValidationService: Orchestrates validation logic
"""

from functools import lru_cache
from uuid import UUID

import structlog
import tiktoken
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.token_manager.exceptions import (
    TokenCalculationError,
    TokenLimitExceededError,
)
from syntara.agent_orchestrator.token_manager.repository import TokenUsageRepository

logger = structlog.stdlib.get_logger(__name__)


@lru_cache(maxsize=128)
def _get_encoder(model_name: str = "gpt-4") -> tiktoken.Encoding:
    """Get tiktoken encoder for the specified model, cached for performance.

    The encoder is cached to avoid repeated initialization overhead.
    Using @lru_cache ensures encoders are created only once per model.

    Args:
        model_name: Name of the tiktoken model (e.g., "gpt-4", "gpt-3.5-turbo")

    Returns:
        tiktoken.Encoding instance for the specified model

    """
    # Map non-OpenAI models to gpt-4 for token counting
    # tiktoken only supports OpenAI models, so we use gpt-4 as a reasonable approximation
    supported_models = ["gpt-4", "gpt-3.5-turbo", "gpt-4-turbo", "gpt-4o"]

    if model_name not in supported_models:
        logger.debug("Model not supported by tiktoken, using 'gpt-4' for token counting", model_name=model_name)
        model_name = "gpt-4"

    return tiktoken.encoding_for_model(model_name)


@lru_cache(maxsize=1024)
def _count_tokens_cached(text: str, model_name: str) -> int:
    """Count tokens with caching for repeated text inputs.

    This cached function avoids re-encoding identical text strings,
    which is particularly beneficial when the same content is checked
    multiple times during compression decisions.

    Args:
        text: The text string to tokenize
        model_name: Tiktoken model name to use

    Returns:
        Number of tokens in the text

    """
    encoder = _get_encoder(model_name)
    return len(encoder.encode(text))


class TokenCalculator:
    """Calculator for counting tokens in text using OpenAI's tiktoken library.

    This class wraps tiktoken functionality and provides a clean interface
    for token counting. The encoder is cached for performance.

    Example:
        calculator = TokenCalculator()
        tokens = calculator.count_tokens("Hello, world!")

    """

    def count_tokens(self, text: str, model_name: str = "gpt-4") -> int:
        """Count the number of tokens in the given text.

        Uses OpenAI's tiktoken library with the specified model encoding to accurately
        count tokens as they would be counted by GPT models. Results are cached
        via _count_tokens_cached to avoid re-encoding identical text.

        Args:
            text: The text string to tokenize
            model_name: Tiktoken model name to use (defaults to "gpt-4")

        Returns:
            Number of tokens in the text

        Raises:
            TokenCalculationError: If tokenization fails

        """
        if not isinstance(text, str):
            msg = f"Expected string input, got {type(text).__name__}"  # type: ignore[unreachable]
            raise TokenCalculationError(msg)

        if not text:
            return 0

        try:
            return _count_tokens_cached(text, model_name)
        except Exception as e:
            logger.exception(
                "Token calculation failed",
                model_name=model_name,
                text_length=len(text),
                error=str(e),
            )
            msg = f"Failed to calculate tokens: {e}"
            raise TokenCalculationError(msg) from e


class TokenValidationService:
    """Service for validating token usage against user limits.

    This service orchestrates token counting, usage tracking, and limit validation.
    It coordinates the TokenCalculator and TokenUsageRepository to provide a
    complete token validation workflow.

    Example:
        service = TokenValidationService()
        await service.validate_and_record(
            user_id=user.id,
            request_text="Hello, world!",
            session=db_session
        )

    """

    def __init__(
        self,
        calculator: TokenCalculator | None = None,
        repository: TokenUsageRepository | None = None,
    ) -> None:
        """Initialize TokenValidationService with dependencies.

        Args:
            calculator: TokenCalculator instance (creates default if not provided)
            repository: TokenUsageRepository instance (creates default if not provided)

        """
        self.calculator = calculator or TokenCalculator()
        self.repository = repository or TokenUsageRepository()

    async def validate_and_record(
        self,
        user_id: UUID,
        request_text: str,
        session: AsyncSession,
        invocation_id: UUID | None = None,
    ) -> int:
        """Validate token limit and record usage.

        This method performs the complete validation workflow:
        1. Get user's token configuration with row-level locking
        2. Count tokens in the request
        3. Calculate current usage within the rolling window
        4. Check if request would exceed the limit
        5. Record the usage if allowed
        6. Raise exception if limit would be exceeded

        The method uses SELECT FOR UPDATE row-level locking to prevent race
        conditions when multiple concurrent requests validate against the same
        user's token limit.

        Args:
            user_id: The user's UUID
            request_text: The text of the request to validate
            session: Async database session
            invocation_id: Optional invocation UUID for linking the token usage record

        Returns:
            Number of tokens in the request

        Raises:
            TokenLimitExceededError: If the request would exceed the user's token limit
            UserTokenConfigNotFoundError: If no configuration exists for the user
            TokenCalculationError: If token counting fails

        """
        # Get user configuration first to determine model for token counting
        # Note: Using non-locking read for model_name lookup, actual validation uses locking
        config_prelim = await self.repository.get_user_config(user_id, session)

        # Count tokens in the request using user's configured model
        request_tokens = self.calculator.count_tokens(request_text, model_name=config_prelim.model_name)

        # Row-level locking prevents race conditions (SELECT FOR UPDATE)
        # The session factory pattern provides transaction isolation - each call
        # operates in its own short-lived session. The caller is responsible for
        # committing the transaction to persist changes.

        # Get user configuration with row-level lock (SELECT FOR UPDATE)
        # This prevents concurrent requests from reading stale usage data
        config = await self.repository.get_user_config_with_lock(user_id, session)

        # Calculate current usage within the rolling window
        current_usage = await self.repository.calculate_current_usage(
            user_id=user_id,
            window_duration_seconds=config.window_duration_seconds,
            session=session,
        )

        # Check if request would exceed limit
        if current_usage + request_tokens > config.token_limit:
            logger.warning(
                "Token limit exceeded",
                user_id=str(user_id),
                current_usage=current_usage,
                token_limit=config.token_limit,
                request_tokens=request_tokens,
                would_total=current_usage + request_tokens,
            )
            raise TokenLimitExceededError(
                user_id=user_id,
                current_usage=current_usage,
                token_limit=config.token_limit,
                request_tokens=request_tokens,
            )

        # Record the usage with estimated_input_tokens for audit comparison
        await self.repository.record_usage(
            user_id=user_id,
            token_count=request_tokens,
            session=session,
            estimated_input_tokens=request_tokens,
            invocation_id=invocation_id,
        )

        logger.info(
            "Token usage validated and recorded",
            user_id=str(user_id),
            request_tokens=request_tokens,
            current_usage=current_usage,
            new_total=current_usage + request_tokens,
            token_limit=config.token_limit,
            model_name=config_prelim.model_name,
        )

        return request_tokens

    async def get_current_usage(
        self,
        user_id: UUID,
        session: AsyncSession,
    ) -> dict[str, int]:
        """Get current token usage statistics for a user.

        Args:
            user_id: The user's UUID
            session: Async database session

        Returns:
            Dictionary with:
                - current_usage: Tokens used within the rolling window
                - token_limit: User's configured limit
                - remaining: Tokens remaining before limit
                - window_duration_seconds: Rolling window duration

        Raises:
            UserTokenConfigNotFoundError: If no configuration exists for the user

        """
        # Get user configuration
        config = await self.repository.get_user_config(user_id, session)

        # Calculate current usage
        current_usage = await self.repository.calculate_current_usage(
            user_id=user_id,
            window_duration_seconds=config.window_duration_seconds,
            session=session,
        )

        return {
            "current_usage": current_usage,
            "token_limit": config.token_limit,
            "remaining": max(0, config.token_limit - current_usage),
            "window_duration_seconds": config.window_duration_seconds,
        }
