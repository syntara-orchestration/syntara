"""Error classification and handling for streaming exceptions.

Provides structured error classification for LLM streaming failures following
RFC 9457 Problem Details format for WebSocket error events.
"""

from uuid import UUID

from syntara.agent_orchestrator.exceptions import AgentTimeoutError, ToolDiscoveryError, ToolSelectionUnavailableError
from syntara.core.models.error import ErrorData

# Base URI for error types
ERROR_TYPE_BASE_URI = "https://api.example.com/errors"


def _build_instance_uri(invocation_id: UUID | None) -> str | None:
    """Build instance URI for error context."""
    return f"/invocations/{invocation_id}" if invocation_id else None


def _contains_any(text: str, keywords: list[str]) -> bool:
    """Check if text contains any of the given keywords."""
    return any(keyword in text for keyword in keywords)


def _is_rate_limit_error(error_msg: str) -> bool:
    """Check if error indicates rate limiting."""
    return _contains_any(error_msg, ["rate limit", "429"])


def _is_auth_error(error_msg: str) -> bool:
    """Check if error indicates authentication failure."""
    return _contains_any(error_msg, ["unauthorized", "403", "401"])


def _is_server_error(error_msg: str) -> bool:
    """Check if error indicates server-side failure."""
    return _contains_any(error_msg, ["500", "502", "503"])


def _is_network_error(error_msg: str) -> bool:
    """Check if error indicates network connectivity issue."""
    return _contains_any(error_msg, ["connection", "network", "unreachable"])


def _classify_by_exception_type(exception: Exception, instance: str | None) -> ErrorData | None:
    """Classify exceptions by type before message heuristics.

    Tool discovery/selection failures and timeouts are classified here so their
    embedded cause names (e.g. ``ConnectionError``) are not mismatched by the
    message-based heuristics downstream.
    """
    if isinstance(exception, ToolDiscoveryError):
        return ErrorData(
            type=f"{ERROR_TYPE_BASE_URI}/tool-discovery-error",
            title="Tool Discovery Failed",
            detail=(
                "Required tools could not be discovered or provisioned."
                " Check integration connectivity and tool configuration."
            ),
            code="TOOL_DISCOVERY_FAILED",
            retryable=False,
            instance=instance,
        )

    if isinstance(exception, ToolSelectionUnavailableError):
        return ErrorData(
            type=f"{ERROR_TYPE_BASE_URI}/tool-selection-unavailable",
            title="Selected Tools Unavailable",
            detail="None of the requested tools could be provisioned. Verify tool availability and integration status.",
            code="TOOL_SELECTION_UNAVAILABLE",
            retryable=False,
            instance=instance,
        )

    if isinstance(exception, AgentTimeoutError):
        return ErrorData(
            type=f"{ERROR_TYPE_BASE_URI}/timeout-error",
            title="Agent Timeout",
            detail=str(exception),
            code="AGENT_TIMEOUT",
            retryable=False,
            instance=instance,
        )

    if isinstance(exception, TimeoutError):
        return ErrorData(
            type=f"{ERROR_TYPE_BASE_URI}/timeout-error",
            title="Streaming Timeout",
            detail="LLM streaming request timed out. Please try again.",
            code="STREAM_TIMEOUT",
            retryable=True,
            instance=instance,
        )

    return None


def classify_streaming_error(exception: Exception, invocation_id: UUID | None = None) -> ErrorData:
    """Classify streaming exception into RFC 9457 Problem Details format.

    Args:
        exception: Exception raised during streaming
        invocation_id: Optional invocation ID for the instance field

    Returns:
        ErrorData model with RFC 9457 fields: type, title, detail, code, retryable, instance

    Examples:
        >>> error = classify_streaming_error(TimeoutError())
        >>> error.type
        'https://api.example.com/errors/timeout-error'
        >>> error.retryable
        True

    """
    instance = _build_instance_uri(invocation_id)

    typed = _classify_by_exception_type(exception, instance)
    if typed is not None:
        return typed

    error_msg = str(exception).lower()

    # Rate limiting (429 status)
    if _is_rate_limit_error(error_msg):
        return ErrorData(
            type=f"{ERROR_TYPE_BASE_URI}/llm-error",
            title="LLM Rate Limit Exceeded",
            detail="OpenRouter API rate limit exceeded. Please try again in a few moments.",
            code="RATE_LIMIT_EXCEEDED",
            retryable=True,
            instance=instance,
        )

    # Authentication errors (401/403)
    if _is_auth_error(error_msg):
        return ErrorData(
            type=f"{ERROR_TYPE_BASE_URI}/llm-error",
            title="LLM Authentication Failed",
            detail="Failed to authenticate with LLM provider. Please check your API configuration.",
            code="AUTHENTICATION_FAILED",
            retryable=False,
            instance=instance,
        )

    # Server errors (5xx)
    if _is_server_error(error_msg):
        return ErrorData(
            type=f"{ERROR_TYPE_BASE_URI}/network-error",
            title="Upstream Service Error",
            detail="LLM provider is experiencing issues. Please try again later.",
            code="UPSTREAM_ERROR",
            retryable=True,
            instance=instance,
        )

    # Connection/network errors
    if _is_network_error(error_msg):
        return ErrorData(
            type=f"{ERROR_TYPE_BASE_URI}/network-error",
            title="Network Connection Error",
            detail="Failed to connect to LLM provider. Please check your network connection.",
            code="CONNECTION_ERROR",
            retryable=True,
            instance=instance,
        )

    # Default to non-retryable LLM error
    return ErrorData(
        type=f"{ERROR_TYPE_BASE_URI}/llm-error",
        title="LLM Streaming Error",
        detail="An unexpected error occurred during LLM streaming. Please try again.",
        code="UNKNOWN_ERROR",
        retryable=False,
        instance=instance,
    )
