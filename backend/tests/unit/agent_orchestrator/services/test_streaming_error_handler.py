"""Unit tests for streaming error classification.

Simplified test suite focusing on:
- Error classification logic for all error types
- Classifier precedence and edge cases
- Invocation ID handling
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.exceptions import (
    AgentOrchestratorError,
    AgentTimeoutError,
    ToolDiscoveryError,
    ToolSelectionUnavailableError,
)
from syntara.agent_orchestrator.services.error_handler import (
    ERROR_TYPE_BASE_URI,
    classify_streaming_error,
    log_streaming_error,
    streaming_error_diagnostics,
)

pytestmark = pytest.mark.unit

# Live OpenRouter 402 body when the key is out of credits.
OPENROUTER_402_BODY: dict[str, object] = {
    "error": {
        "message": "Insufficient credits. Add more using https://openrouter.ai/settings/credits",
        "code": 402,
        "metadata": {
            "limit_source": "openrouter_credits",
            "remedy_hint": (
                "Add credits at https://openrouter.ai/settings/credits, or lower "
                "max_tokens / prompt size to fit your remaining balance."
            ),
        },
    }
}


@pytest.mark.parametrize(
    ("exception", "expected_code", "expected_retryable"),
    [
        # Timeout errors
        (TimeoutError("Request timed out after 30 seconds"), "STREAM_TIMEOUT", True),
        # Agent timeout errors (non-retryable)
        (AgentTimeoutError("Agent timed out after 300 seconds"), "AGENT_TIMEOUT", False),
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
        # Tool discovery/selection — classified by type, not message heuristics
        (
            ToolDiscoveryError("Failed to discover MCP integrations: ConnectionError: Tool Manager unavailable"),
            "TOOL_DISCOVERY_FAILED",
            False,
        ),
        (
            ToolDiscoveryError("Failed to discover tools from Tool Manager: ConnectionError: Tool Manager unavailable"),
            "TOOL_DISCOVERY_FAILED",
            False,
        ),
        (
            ToolDiscoveryError(
                "Enabled tools were discovered but none could be provisioned "
                "from their owning MCP integrations (enabled=['dev_tools::code_search']); "
                "refusing to continue without tools"
            ),
            "TOOL_DISCOVERY_FAILED",
            False,
        ),
        (
            ToolDiscoveryError(
                "Owning integrations returned 2 tool(s) but none matched enabled "
                "Tool Manager entries (enabled=['dev_tools::code_search']); "
                "refusing to continue without tools — check registry name/integration_id drift"
            ),
            "TOOL_DISCOVERY_FAILED",
            False,
        ),
        (
            ToolSelectionUnavailableError(
                "None of the requested tools could be provisioned "
                "(unavailable tool IDs: ['uuid-a', 'uuid-b']); "
                "refusing to continue the invocation without tools"
            ),
            "TOOL_SELECTION_UNAVAILABLE",
            False,
        ),
        # Insufficient credits (OpenRouter 402)
        (Exception("Error code: 402 - This request requires more credits"), "INSUFFICIENT_CREDITS", False),
        (Exception("HTTP 402: Payment Required"), "INSUFFICIENT_CREDITS", False),
        (Exception("insufficient credits on this API key"), "INSUFFICIENT_CREDITS", False),
        (Exception(str(OPENROUTER_402_BODY)), "INSUFFICIENT_CREDITS", False),
        # Unknown errors
        (ValueError("Invalid input format"), "UNKNOWN_ERROR", False),
        (Exception("Something went wrong"), "UNKNOWN_ERROR", False),
        (Exception(""), "UNKNOWN_ERROR", False),
    ],
    ids=[
        "timeout",
        "agent_timeout",
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
        "tool_discovery_connection_error",
        "tool_discovery_manager_connection_error",
        "tool_discovery_zero_provision",
        "tool_discovery_zero_match",
        "tool_selection_unavailable",
        "credits_402_message",
        "credits_http_402",
        "credits_insufficient",
        "credits_openrouter_body",
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
        ("PAYMENT REQUIRED", "INSUFFICIENT_CREDITS"),
        ("HTTP 402", "INSUFFICIENT_CREDITS"),
    ],
    ids=["auth_caps", "network_caps", "upstream_caps", "rate_limit_caps", "credits_caps", "credits_http_caps"],
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


def test_credit_error_not_unknown_streaming_error() -> None:
    """OpenRouter 402 must not fall through to UNKNOWN_ERROR / LLM Streaming Error."""
    exception = Exception("Error code: 402 - {'error': {'message': 'This request requires more credits', 'code': 402}}")
    error = classify_streaming_error(exception, uuid4())

    assert error.code == "INSUFFICIENT_CREDITS"
    assert error.retryable is False
    assert error.title == "LLM Insufficient Credits"
    assert "insufficient credits" in (error.detail or "").lower()
    assert error.code != "UNKNOWN_ERROR"


class _OpenRouterApiStatusError(Exception):
    """Stand-in for openai.APIStatusError: generic str(), payload on body/status_code."""

    def __init__(self, body: dict[str, object]) -> None:
        super().__init__("Error")
        self.status_code = 402
        self.body = body


def test_openrouter_402_body_on_exception_attributes() -> None:
    """Classify the live OpenRouter 402 payload even when it is not in str(exception)."""
    error = classify_streaming_error(_OpenRouterApiStatusError(OPENROUTER_402_BODY), uuid4())

    assert error.code == "INSUFFICIENT_CREDITS"
    assert error.retryable is False
    assert error.title == "LLM Insufficient Credits"


def test_openrouter_402_body_on_chained_cause() -> None:
    """Walk __cause__ so a wrapped AgentOrchestratorError still sees the 402 body."""
    inner = _OpenRouterApiStatusError(OPENROUTER_402_BODY)
    wrapped = AgentOrchestratorError("Execution error: Error")
    wrapped.__cause__ = inner
    error = classify_streaming_error(wrapped, uuid4())

    assert error.code == "INSUFFICIENT_CREDITS"


def test_tool_discovery_not_misclassified_as_llm_network_error() -> None:
    """ToolDiscoveryError with ConnectionError in the message must not look like LLM network failure."""
    exception = ToolDiscoveryError("Failed to discover MCP integrations: ConnectionError: Tool Manager unavailable")
    error = classify_streaming_error(exception, uuid4())

    assert error.code == "TOOL_DISCOVERY_FAILED"
    assert error.retryable is False
    assert error.title == "Tool Discovery Failed"
    assert "LLM" not in error.title
    # Stream detail uses a client-safe string; raw exception text stays in logs only.
    assert "ConnectionError" not in (error.detail or "")
    assert "Tool Manager unavailable" not in (error.detail or "")
    assert "could not be discovered" in (error.detail or "")


def test_tool_selection_not_default_llm_streaming_error() -> None:
    """ToolSelectionUnavailableError must not fall through to UNKNOWN_ERROR / LLM Streaming Error."""
    exception = ToolSelectionUnavailableError(
        "None of the requested tools could be provisioned "
        "(unavailable tool IDs: ['uuid-missing']); "
        "refusing to continue the invocation without tools"
    )
    error = classify_streaming_error(exception, uuid4())

    assert error.code == "TOOL_SELECTION_UNAVAILABLE"
    assert error.retryable is False
    assert error.title == "Selected Tools Unavailable"
    assert error.code != "UNKNOWN_ERROR"
    # Stream detail uses a client-safe string; raw exception text (incl. UUIDs) stays in logs only.
    assert "uuid-missing" not in (error.detail or "")
    assert "Verify tool availability" in (error.detail or "")


def test_tool_discovery_zero_match_uses_client_safe_detail() -> None:
    """Stream detail must use a stable client-safe string, not raw exception text."""
    raw_detail = (
        "Owning integrations returned 4 tool(s) but none matched enabled Tool Manager entries "
        "(enabled=['a::t1', 'b::t2']); refusing to continue without tools "
        "-- check registry name/integration_id drift"
    )
    error = classify_streaming_error(ToolDiscoveryError(raw_detail), uuid4())

    assert error.code == "TOOL_DISCOVERY_FAILED"
    # Client-safe detail, not the raw exception text with internal names.
    expected_detail = (
        "Required tools could not be discovered or provisioned. Check integration connectivity and tool configuration."
    )
    assert error.detail == expected_detail
    assert error.retryable is False


def test_agent_timeout_classified_as_non_retryable() -> None:
    """AgentTimeoutError produces AGENT_TIMEOUT code, is non-retryable, and preserves detail."""
    timeout_msg = "Agent execution exceeded 300s timeout"
    exception = AgentTimeoutError(timeout_msg)
    invocation_id = uuid4()

    error = classify_streaming_error(exception, invocation_id)

    assert error.code == "AGENT_TIMEOUT"
    assert error.retryable is False
    assert error.title == "Agent Timeout"
    assert error.detail == timeout_msg
    assert error.type == f"{ERROR_TYPE_BASE_URI}/timeout-error"
    assert error.instance == f"/invocations/{invocation_id}"


def test_agent_timeout_takes_precedence_over_builtin_timeout() -> None:
    """AgentTimeoutError (subclass) must not fall through to TimeoutError classifier."""
    exception = AgentTimeoutError("timeout")
    error = classify_streaming_error(exception, uuid4())

    # Must be AGENT_TIMEOUT not STREAM_TIMEOUT
    assert error.code == "AGENT_TIMEOUT"
    assert error.retryable is False


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


def test_streaming_error_diagnostics_walks_provider_body() -> None:
    """HTTP status and body on the cause must appear in log fields."""
    inner = _OpenRouterApiStatusError(OPENROUTER_402_BODY)
    wrapped = AgentOrchestratorError("Execution error: Error")
    wrapped.__cause__ = inner

    fields = streaming_error_diagnostics(wrapped)

    assert fields["error_type"] == "AgentOrchestratorError"
    assert fields["error_message"] == "Execution error: Error"
    assert fields["http_status"] == 402
    assert "openrouter_credits" in fields["provider_body"]
    assert any("_OpenRouterApiStatusError" in cause for cause in fields["cause_chain"])


def test_streaming_error_diagnostics_truncates_large_body() -> None:
    class _FatBodyError(Exception):
        def __init__(self) -> None:
            super().__init__("short")
            self.body = "x" * 5000

    fields = streaming_error_diagnostics(_FatBodyError())

    assert len(fields["provider_body"]) == 2000
    assert fields["provider_body"].endswith("...")


@patch("syntara.agent_orchestrator.services.error_handler.logger")
def test_log_streaming_error_uses_unclassified_event_for_unknown(mock_logger: MagicMock) -> None:
    """UNKNOWN_ERROR keeps a generic client detail and logs the real exception."""
    invocation_id = uuid4()
    exception = Exception("novel provider failure xyz")

    error = log_streaming_error(exception, invocation_id=invocation_id)

    assert error.code == "UNKNOWN_ERROR"
    mock_logger.exception.assert_called_once()
    event, kwargs = mock_logger.exception.call_args.args[0], mock_logger.exception.call_args.kwargs
    assert event == "Unclassified LLM streaming error"
    assert kwargs["error_code"] == "UNKNOWN_ERROR"
    assert kwargs["error_type"] == "Exception"
    assert kwargs["error_message"] == "novel provider failure xyz"
    assert kwargs["client_detail"] == "An unexpected error occurred during LLM streaming. Please try again."
    assert kwargs["invocation_id"] == str(invocation_id)


@patch("syntara.agent_orchestrator.services.error_handler.logger")
def test_log_streaming_error_includes_provider_status_and_body(mock_logger: MagicMock) -> None:
    exception = _OpenRouterApiStatusError(OPENROUTER_402_BODY)

    error = log_streaming_error(exception)

    assert error.code == "INSUFFICIENT_CREDITS"
    kwargs = mock_logger.exception.call_args.kwargs
    assert mock_logger.exception.call_args.args[0] == "Streaming orchestration failed"
    assert kwargs["http_status"] == 402
    assert "openrouter_credits" in kwargs["provider_body"]
