"""Exception classes for token validation.

This module defines custom exceptions for token counting and validation:
- TokenValidationError: Base exception for all token validation errors
- TokenLimitExceededError: Raised when token limit is exceeded
- TokenCalculationError: Raised when token calculation fails
- UserTokenConfigNotFoundError: Raised when user configuration is missing
"""

from uuid import UUID

from syntara.agent_orchestrator.exceptions import AgentOrchestratorError

# User-facing copy for orchestrator/UI surfaces (no UUIDs or raw counters).
LIMIT_EXCEEDED_USER_MESSAGE = (
    "The AI Agent prompt and context exceed the model token limit. "
    "Shorten the prompt, reduce input data, or choose a model with a larger context window."
)


class TokenValidationError(AgentOrchestratorError):
    """Base exception for all token validation errors."""


class TokenLimitExceededError(TokenValidationError):
    """Raised when a user's token limit is exceeded.

    This exception contains structured information about the limit violation,
    including current usage, the configured limit, and the tokens in the current request.
    The exception message is user-facing; use attributes / to_dict() for diagnostics.
    """

    def __init__(
        self,
        user_id: UUID,
        current_usage: int,
        token_limit: int,
        request_tokens: int,
        message: str | None = None,
    ) -> None:
        """Initialize TokenLimitExceededError with detailed context.

        Args:
            user_id: The user who exceeded their limit
            current_usage: Current token usage within the rolling window
            token_limit: The configured token limit
            request_tokens: Tokens in the current request
            message: Optional custom message (user-facing default if not provided)

        """
        self.user_id = user_id
        self.current_usage = current_usage
        self.token_limit = token_limit
        self.request_tokens = request_tokens

        if message is None:
            message = LIMIT_EXCEEDED_USER_MESSAGE

        super().__init__(message)

    def to_dict(self) -> dict[str, int | str]:
        """Convert exception details to dictionary for structured logging or API responses.

        Returns:
            Dictionary with user_id, current_usage, token_limit, request_tokens, and message

        """
        return {
            "user_id": str(self.user_id),
            "current_usage": self.current_usage,
            "token_limit": self.token_limit,
            "request_tokens": self.request_tokens,
            "total_would_be": self.current_usage + self.request_tokens,
            "message": str(self),
        }


class TokenCalculationError(TokenValidationError):
    """Raised when token calculation fails.

    This can occur due to encoding errors, invalid input, or tiktoken failures.
    """


class UserTokenConfigNotFoundError(TokenValidationError):
    """Raised when a user's token configuration is not found.

    This indicates that no token limit has been configured for the user.
    """

    def __init__(self, user_id: UUID, message: str | None = None) -> None:
        """Initialize UserTokenConfigNotFoundError.

        Args:
            user_id: The user whose configuration was not found
            message: Optional custom message

        """
        self.user_id = user_id

        if message is None:
            message = f"Token configuration not found for user {user_id}"

        super().__init__(message)
