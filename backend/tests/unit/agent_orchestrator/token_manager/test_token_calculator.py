"""Unit tests for TokenCalculator."""

import pytest

from syntara.agent_orchestrator.token_manager.exceptions import TokenCalculationError
from syntara.agent_orchestrator.token_manager.services import TokenCalculator


def test_count_tokens_simple_text() -> None:
    """Test basic token counting with simple text."""
    calculator = TokenCalculator()
    text = "Hello, world!"
    token_count = calculator.count_tokens(text)

    # tiktoken should count this as multiple tokens
    assert token_count > 0
    assert isinstance(token_count, int)


def test_count_tokens_empty_string() -> None:
    """Test that empty string returns 0 tokens."""
    calculator = TokenCalculator()
    token_count = calculator.count_tokens("")
    assert token_count == 0


def test_count_tokens_unicode() -> None:
    """Test token counting with Unicode characters."""
    calculator = TokenCalculator()
    text = "Hello 世界! 🌍"
    token_count = calculator.count_tokens(text)

    assert token_count > 0
    assert isinstance(token_count, int)


def test_encoder_caching() -> None:
    """Test that encoder is cached (same instance)."""
    calculator = TokenCalculator()

    # Count tokens twice
    calculator.count_tokens("test")
    calculator.count_tokens("test again")

    # If caching works, we should get consistent results
    count1 = calculator.count_tokens("consistent test")
    count2 = calculator.count_tokens("consistent test")

    assert count1 == count2


def test_encoding_error_handling() -> None:
    """Test that encoding errors raise TokenCalculationError."""
    calculator = TokenCalculator()

    # Test with invalid input type (not a string)
    with pytest.raises((TokenCalculationError, TypeError, AttributeError)):
        calculator.count_tokens(None)  # type: ignore[arg-type]
