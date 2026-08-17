"""Unit tests for token manager exception user-facing messages."""

from uuid import uuid4

from syntara.agent_orchestrator.token_manager.exceptions import (
    LIMIT_EXCEEDED_USER_MESSAGE,
    TokenLimitExceededError,
)


class TestTokenLimitExceededError:
    """Tests for TokenLimitExceededError message and structured fields."""

    def test_default_message_is_user_friendly_without_internal_ids(self) -> None:
        """Default str() must match AGENT-10 copy and omit UUID/counters."""
        user_id = uuid4()
        error = TokenLimitExceededError(
            user_id=user_id,
            current_usage=9500,
            token_limit=10000,
            request_tokens=1000,
        )

        assert str(error) == LIMIT_EXCEEDED_USER_MESSAGE
        assert str(user_id) not in str(error)
        assert "9500" not in str(error)
        assert "10000" not in str(error)
        assert "1000" not in str(error)
        assert "Token limit exceeded for user" not in str(error)

    def test_structured_fields_remain_available_for_diagnostics(self) -> None:
        """Attributes and to_dict keep counters for logging without leaking via str()."""
        user_id = uuid4()
        error = TokenLimitExceededError(
            user_id=user_id,
            current_usage=9500,
            token_limit=10000,
            request_tokens=1000,
        )

        assert error.user_id == user_id
        assert error.current_usage == 9500
        assert error.token_limit == 10000
        assert error.request_tokens == 1000
        assert error.to_dict() == {
            "user_id": str(user_id),
            "current_usage": 9500,
            "token_limit": 10000,
            "request_tokens": 1000,
            "total_would_be": 10500,
            "message": LIMIT_EXCEEDED_USER_MESSAGE,
        }

    def test_custom_message_override_still_supported(self) -> None:
        """Callers can still pass an explicit message when needed."""
        error = TokenLimitExceededError(
            user_id=uuid4(),
            current_usage=1,
            token_limit=1,
            request_tokens=1,
            message="custom override",
        )

        assert str(error) == "custom override"
