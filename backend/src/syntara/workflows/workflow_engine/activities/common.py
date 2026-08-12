"""Common utilities for workflow activities.

This module provides shared functionality for all activity types including:
- Retryable error code constants
- Error code extraction from messages
- Base exception classes
"""

import re

# Heartbeat keys for describe-probe coordination.
# HEARTBEAT_STOP_MONITOR: signals the sync-service describe probe to stop
# polling and push a SyntheticActivityStarted event.
# HEARTBEAT_PARTIAL_OUTPUT_KEY: optional dict of early output data to persist
# to the DB before the activity completes (e.g. job_id, job_url).
HEARTBEAT_STOP_MONITOR = "stop_monitor"
HEARTBEAT_PARTIAL_OUTPUT_KEY = "partial_output"

# Default retryable HTTP status codes (whitelist approach).
# Only transient errors that typically self-resolve belong here.
# 429: Too Many Requests - Rate limiting, retry with backoff
# 502: Bad Gateway - Upstream server error, often transient
# 503: Service Unavailable - Service temporarily down
# 504: Gateway Timeout - Upstream timeout, often transient
DEFAULT_RETRYABLE_ERROR_CODES: frozenset[int] = frozenset({429, 502, 503, 504})


def is_retryable_http_status(status_code: int) -> bool:
    """Check whether an HTTP status code is retryable."""
    return status_code in DEFAULT_RETRYABLE_ERROR_CODES


class ActivityExecutionError(Exception):
    """Base exception for all activity execution errors.

    This base class provides common structure for activity-specific errors,
    allowing metadata to be attached to exceptions.

    Subclasses should explicitly declare their attributes for type safety.
    """


def extract_error_code(error_message: str) -> int | None:
    """Extract numeric error code from error message.

    Works for both HTTP status codes and process exit codes.
    Context-aware: the same number can represent different error types
    depending on the executor (HTTP status code vs exit code).

    Args:
        error_message: Error message from activity execution.
            Expected patterns:
            - HTTP status codes: "Error code: 401", "status code: 404"
            - Exit codes: "Exit code: 127", "exited with code 1"
            - Generic: "code: 500", "code=404", "code': 401"

    Returns:
        Extracted numeric error code, or None if no code found.

    Examples:
        >>> extract_error_code("Error code: 401 - {'error': {'message': 'User not found.'}}")
        401
        >>> extract_error_code("Script exited with code 127")
        127
        >>> extract_error_code("Connection failed")
        None

    """
    patterns = [
        r"(?:status|error|exit)\s*code[:\s=]+(\d+)",  # status code: 401, exit code: 127
        r"code[:\s='\"]+(\d+)",  # code: 500, code=404, code': 401
        r"exited\s+with\s+(?:code\s+)?(\d+)",  # exited with code 1, exited with 127
    ]

    for pattern in patterns:
        match = re.search(pattern, error_message, re.IGNORECASE)
        if match:
            return int(match.group(1))

    return None
