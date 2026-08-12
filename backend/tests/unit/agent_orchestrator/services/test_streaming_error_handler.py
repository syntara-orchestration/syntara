"""Unit tests for streaming error classification.

Simplified test suite focusing on:
- Error classification logic for all error types
- Classifier precedence and edge cases
- Invocation ID handling
"""

from uuid import uuid4

import pytest

from syntara.agent_orchestrator.services.error_handler import (
    ERROR_TYPE_BASE_URI,
    classify_streaming_error,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("exception", "expected_code", "expected_retryable"),
    [
        # Timeout errors
        (TimeoutError("Request timed out after 30 seconds"), "STREAM_TIMEOUT", True),
        # Rate limit errors
        (Exception("API rate limit exceeded, please retry later"), "RATE_LIMIT_EXCEEDED", True),
        (Exception("HTTP 429: Too Many Requests"), "RATE_LIMIT_EXCEEDED", True),
        # Authentication errors
        (Exception("Unauthorized: Invalid API key"), "AUTHENTICATION_FAILED", False),
        (Exception("HTTP 401: Unauthorized"), "AUTHENTICATION_FAILED", False),
        (Exception("HTTP 403: Forbidden"), "AUTHENTICATION_FAILED", False),
        # Upstream server errors
        (Exception("HTTP 500: Internal Server Error"), "UPSTREAM_ERROR", True),
        (Exception("HTTP 502: Bad Gateway"), "UPSTREAM_ERROR", True),
        (Exception("HTTP 503: Service Unavailable"), "UPSTREAM_ERROR", True),
        # Network errors
        (Exception("Connection refused by host"), "CONNECTION_ERROR", True),
        (Exception("Network unreachable"), "CONNECTION_ERROR", True),
        (Exception("Network connection timeout"), "CONNECTION_ERROR", True),
        # Unknown errors
        (ValueError("Invalid input format"), "UNKNOWN_ERROR", False),
        (Exception("Something went wrong"), "UNKNOWN_ERROR", False),
        (Exception(""), "UNKNOWN_ERROR", False),
    ],
    ids=[
        "timeout",
        "rate_limit_message",
        "rate_limit_status",
        "auth_message",
        "auth_401",
        "auth_403",
        "upstream_500",
        "upstream_502",
        "upstream_503",
        "network_refused",
        "network_unreachable",
        "network_timeout",
        "unknown_value_error",
        "unknown_generic",
        "unknown_empty",
    ],
)
def test_error_classification(
    exception: Exception,
    expected_code: str,
    expected_retryable: bool,  # noqa: FBT001
) -> None:
    """Test error classification for all error types."""
    invocation_id = uuid4()
    error = classify_streaming_error(exception, invocation_id)

    assert error.code == expected_code
    assert error.retryable == expected_retryable
    assert error.instance == f"/invocations/{invocation_id}"
    assert error.detail is not None
    assert error.type is not None
    assert error.title is not None
    assert error.type.startswith("https://")
    assert ERROR_TYPE_BASE_URI in error.type


@pytest.mark.parametrize(
    ("message", "expected_code"),
    [
        ("UNAUTHORIZED", "AUTHENTICATION_FAILED"),
        ("Network UNREACHABLE", "CONNECTION_ERROR"),
        ("HTTP 503", "UPSTREAM_ERROR"),
        ("RATE LIMIT EXCEEDED", "RATE_LIMIT_EXCEEDED"),
    ],
    ids=["auth_caps", "network_caps", "upstream_caps", "rate_limit_caps"],
)
def test_case_insensitive_matching(message: str, expected_code: str) -> None:
    """Test all error matching is case-insensitive."""
    error = classify_streaming_error(Exception(message))
    assert error.code == expected_code


def test_mixed_error_signals_priority() -> None:
    """Test that first matching classifier wins when multiple signals present."""
    # Message has both rate limit and connection keywords
    exception = Exception("Connection failed: Rate limit exceeded")
    error = classify_streaming_error(exception)

    # Rate limit should match first (comes before connection check)
    assert error.code == "RATE_LIMIT_EXCEEDED"


def test_multiple_invocations_independent() -> None:
    """Test that different invocation IDs produce different instance fields."""
    exception = TimeoutError("Timeout")
    invocation_id1 = uuid4()
    invocation_id2 = uuid4()

    error1 = classify_streaming_error(exception, invocation_id1)
    error2 = classify_streaming_error(exception, invocation_id2)

    assert error1.instance == f"/invocations/{invocation_id1}"
    assert error2.instance == f"/invocations/{invocation_id2}"
    assert error1.instance != error2.instance
