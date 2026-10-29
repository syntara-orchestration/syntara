"""Error classification and handling for streaming exceptions.

Provides structured error classification for LLM streaming failures following
RFC 9457 Problem Details format for WebSocket error events.
"""

from collections.abc import Callable
from typing import NamedTuple
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


def _is_tool_result_serialization_error(error_msg: str) -> bool:
    """Check if error indicates a tool result could not be checkpoint-serialized."""
    return _contains_any(error_msg, ["msgpack serializable", "not serializable"])


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


class _MessageClassifier(NamedTuple):
    """Message-keyword-based classifier entry evaluated in order."""

    predicate: Callable[[str], bool]
    type_suffix: str
    title: str
    detail: str
    code: str
    retryable: bool


_MESSAGE_CLASSIFIERS = [
    _MessageClassifier(
        _is_rate_limit_error,
        "llm-error",
        "LLM Rate Limit Exceeded",
        "OpenRouter API rate limit exceeded. Please try again in a few moments.",
        "RATE_LIMIT_EXCEEDED",
        retryable=True,
    ),
    _MessageClassifier(
        _is_auth_error,
        "llm-error",
        "LLM Authentication Failed",
        "Failed to authenticate with LLM provider. Please check your API configuration.",
        "AUTHENTICATION_FAILED",
        retryable=False,
    ),
    _MessageClassifier(
        _is_server_error,
        "network-error",
        "Upstream Service Error",
        "LLM provider is experiencing issues. Please try again later.",
        "UPSTREAM_ERROR",
        retryable=True,
    ),
    _MessageClassifier(
        _is_network_error,
        "network-error",
        "Network Connection Error",
        "Failed to connect to LLM provider. Please check your network connection.",
        "CONNECTION_ERROR",
        retryable=True,
    ),
    _MessageClassifier(
        _is_tool_result_serialization_error,
        "tool-result-serialization-error",
        "Tool Result Serialization Failed",
        "A tool call succeeded, but its result could not be serialized for checkpointing."
        " Please try again or contact support with the invocation ID.",
        "TOOL_RESULT_SERIALIZATION_FAILED",
        retryable=False,
    ),
]


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

    for classifier in _MESSAGE_CLASSIFIERS:
        if classifier.predicate(error_msg):
            return ErrorData(
                type=f"{ERROR_TYPE_BASE_URI}/{classifier.type_suffix}",
                title=classifier.title,
                detail=classifier.detail,
                code=classifier.code,
                retryable=classifier.retryable,
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
