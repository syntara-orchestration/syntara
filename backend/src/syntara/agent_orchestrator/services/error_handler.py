"""Error classification and handling for streaming exceptions.

Provides structured error classification for LLM streaming failures following
RFC 9457 Problem Details format for WebSocket error events.
"""

from typing import Any
from uuid import UUID

import structlog

from syntara.agent_orchestrator.exceptions import AgentTimeoutError, ToolDiscoveryError, ToolSelectionUnavailableError
from syntara.core.models.error import ErrorData

# Base URI for error types
ERROR_TYPE_BASE_URI = "https://api.example.com/errors"
_MAX_DIAGNOSTIC_CHARS = 2000

logger = structlog.stdlib.get_logger(__name__)


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


def _is_credit_error(error_msg: str) -> bool:
    """Check if error indicates the LLM provider rejected the request for credits."""
    return _contains_any(
        error_msg,
        [
            "402",
            "insufficient credit",
            "payment required",
            "requires more credit",
            "openrouter_credits",
        ],
    )


def _http_status_code(exception: BaseException) -> int | None:
    """Return an HTTP status from the exception or its ``response``, if present."""
    status = getattr(exception, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exception, "response", None)
    nested = getattr(response, "status_code", None)
    return nested if isinstance(nested, int) else None


def _truncate_diagnostic(value: str, limit: int = _MAX_DIAGNOSTIC_CHARS) -> str:
    """Cap log fields so provider payloads cannot flood a log line."""
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."


def streaming_error_diagnostics(exception: Exception) -> dict[str, Any]:
    """Structured log fields for an LLM streaming failure.

    Walks ``__cause__`` / ``__context__`` so a wrapped ``AgentOrchestratorError``
    still surfaces the provider HTTP status and body (OpenAI SDK keeps those on
    ``status_code`` / ``body``, not always in ``str(exception)``).
    """
    fields: dict[str, Any] = {
        "error_type": type(exception).__name__,
        "error_message": _truncate_diagnostic(str(exception)),
    }
    status: int | None = None
    body: str | None = None
    causes: list[str] = []
    current: BaseException | None = exception
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if current is not exception:
            causes.append(f"{type(current).__name__}: {_truncate_diagnostic(str(current), limit=500)}")
        if status is None:
            status = _http_status_code(current)
        if body is None:
            raw_body = getattr(current, "body", None)
            if raw_body:
                body = _truncate_diagnostic(str(raw_body))
            else:
                response = getattr(current, "response", None)
                text = getattr(response, "text", None)
                if text:
                    body = _truncate_diagnostic(text)
        current = current.__cause__ or current.__context__
    if status is not None:
        fields["http_status"] = status
    if body is not None:
        fields["provider_body"] = body
    if causes:
        fields["cause_chain"] = causes
    return fields


def _exception_text(exception: Exception) -> str:
    """Flatten ``str()``, ``body``, and HTTP status for keyword classification.

    OpenRouter 402 payloads often live on ``exception.body`` (OpenAI SDK) rather
    than in ``str(exception)``:

        {'error': {'message': 'Insufficient credits. Add more using ...',
                   'code': 402,
                   'metadata': {'limit_source': 'openrouter_credits', ...}}}
    """
    parts: list[str] = []
    current: BaseException | None = exception
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(str(current))
        body = getattr(current, "body", None)
        if body:
            parts.append(str(body))
        response = getattr(current, "response", None)
        text = getattr(response, "text", None)
        if text:
            parts.append(text)
        status = _http_status_code(current)
        if status is not None:
            parts.append(f"status_code {status}")
        current = current.__cause__ or current.__context__
    return " ".join(parts).lower()


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


def _classify_by_error_message(error_msg: str, instance: str | None) -> ErrorData | None:
    """Classify by keywords in the exception message. First match wins."""
    if _is_rate_limit_error(error_msg):
        return ErrorData(
            type=f"{ERROR_TYPE_BASE_URI}/llm-error",
            title="LLM Rate Limit Exceeded",
            detail="OpenRouter API rate limit exceeded. Please try again in a few moments.",
            code="RATE_LIMIT_EXCEEDED",
            retryable=True,
            instance=instance,
        )

    if _is_auth_error(error_msg):
        return ErrorData(
            type=f"{ERROR_TYPE_BASE_URI}/llm-error",
            title="LLM Authentication Failed",
            detail="Failed to authenticate with LLM provider. Please check your API configuration.",
            code="AUTHENTICATION_FAILED",
            retryable=False,
            instance=instance,
        )

    if _is_credit_error(error_msg):
        return ErrorData(
            type=f"{ERROR_TYPE_BASE_URI}/llm-error",
            title="LLM Insufficient Credits",
            detail="The LLM provider rejected the request due to insufficient credits.",
            code="INSUFFICIENT_CREDITS",
            retryable=False,
            instance=instance,
        )

    if _is_server_error(error_msg):
        return ErrorData(
            type=f"{ERROR_TYPE_BASE_URI}/network-error",
            title="Upstream Service Error",
            detail="LLM provider is experiencing issues. Please try again later.",
            code="UPSTREAM_ERROR",
            retryable=True,
            instance=instance,
        )

    if _is_network_error(error_msg):
        return ErrorData(
            type=f"{ERROR_TYPE_BASE_URI}/network-error",
            title="Network Connection Error",
            detail="Failed to connect to LLM provider. Please check your network connection.",
            code="CONNECTION_ERROR",
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

    by_message = _classify_by_error_message(_exception_text(exception), instance)
    if by_message is not None:
        return by_message

    return ErrorData(
        type=f"{ERROR_TYPE_BASE_URI}/llm-error",
        title="LLM Streaming Error",
        detail="An unexpected error occurred during LLM streaming. Please try again.",
        code="UNKNOWN_ERROR",
        retryable=False,
        instance=instance,
    )


def log_streaming_error(
    exception: Exception,
    *,
    invocation_id: UUID | None = None,
    classified: ErrorData | None = None,
) -> ErrorData:
    """Log an LLM streaming failure with provider diagnostics.

    Client-facing ``ErrorData.detail`` stays generic for ``UNKNOWN_ERROR``. The
    log line carries the real exception type, message, HTTP status, provider
    body, and cause chain so operators can diagnose OpenRouter/LLM failures.
    """
    error_data = classified or classify_streaming_error(exception, invocation_id)
    event = (
        "Unclassified LLM streaming error" if error_data.code == "UNKNOWN_ERROR" else "Streaming orchestration failed"
    )
    logger.exception(
        event,
        invocation_id=str(invocation_id) if invocation_id is not None else None,
        error_code=error_data.code,
        error_title=error_data.title,
        client_detail=error_data.detail,
        **streaming_error_diagnostics(exception),
    )
    return error_data
