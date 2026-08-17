"""Retry and recovery utilities for LLM adapter operations.

This module provides retry logic for handling transient failures in LLM adapter
calls, including error classification, exponential backoff with jitter, and
comprehensive logging for observability.
"""

import asyncio
import functools
import random
import time
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

import httpx
import openai
import structlog
from fastapi import HTTPException

from syntara.core.config.base import AdapterRetrySettings, get_settings
from syntara.core.exceptions import RetryableError

# HTTP status code constants for error classification
_HTTP_STATUS_MIN_SERVER_ERROR = 500
_HTTP_STATUS_MAX_SERVER_ERROR = 600

# Specific retryable HTTP status codes for fallback error handling
# Uses httpx.codes constants to avoid hardcoded magic numbers
_RETRYABLE_HTTP_STATUS_CODES = frozenset(
    {
        httpx.codes.INTERNAL_SERVER_ERROR,  # 500
        httpx.codes.BAD_GATEWAY,  # 502
        httpx.codes.SERVICE_UNAVAILABLE,  # 503
        httpx.codes.GATEWAY_TIMEOUT,  # 504
        httpx.codes.TOO_MANY_REQUESTS,  # 429
    }
)

T = TypeVar("T", bound=Callable[..., Any])

logger = structlog.stdlib.get_logger(__name__)


def is_retryable_error(error: Exception) -> bool:
    """Classify exception as retryable or non-retryable.

    GenericAgent receives exceptions from OpenAI SDK (transitive dependency
    via langchain-openai), which wraps httpx errors. This function handles
    both exception hierarchies for proper classification.

    Retryable errors (OpenAI SDK - primary):
    - openai.APIConnectionError (wraps httpx.ConnectError - network failures)
    - openai.APITimeoutError (wraps httpx.TimeoutException - timeouts)
    - openai.RateLimitError (HTTP 429 rate limiting)
    - openai.APIStatusError with status 500, 502, 503, 504 (server errors)

    Retryable errors (httpx - defensive fallback):
    - httpx.HTTPStatusError with status 500, 502, 503, 504, 429
    - httpx.TimeoutException
    - httpx.ConnectTimeout
    - httpx.ReadTimeout
    - httpx.ConnectError
    - asyncio.TimeoutError (from asyncio.wait_for)

    Non-retryable errors:
    - openai.AuthenticationError (HTTP 401)
    - openai.BadRequestError (HTTP 400)
    - openai.APIStatusError with 4xx status
    - ValueError, KeyError, AttributeError (programming errors)
    - All other unexpected exceptions

    Args:
        error: Exception to classify

    Returns:
        True if error should trigger retry, False otherwise

    """
    # Check Syntara RetryableError marker and OpenAI SDK exceptions (primary path)
    if isinstance(
        error,
        RetryableError | openai.APIConnectionError | openai.APITimeoutError | openai.RateLimitError,
    ):
        return True

    # Check non-retryable OpenAI SDK exceptions
    if isinstance(error, openai.AuthenticationError | openai.BadRequestError):
        return False

    if isinstance(error, openai.APIStatusError):
        return _HTTP_STATUS_MIN_SERVER_ERROR <= error.status_code < _HTTP_STATUS_MAX_SERVER_ERROR

    # Check httpx exceptions (defensive fallback)
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in _RETRYABLE_HTTP_STATUS_CODES

    # Check fastapi exceptions (defensive fallback)
    if isinstance(error, HTTPException):
        return error.status_code in _RETRYABLE_HTTP_STATUS_CODES

    # Check timeout exceptions
    return isinstance(
        error,
        httpx.TimeoutException | httpx.ConnectTimeout | httpx.ReadTimeout | httpx.ConnectError | asyncio.TimeoutError,
    )


def calculate_backoff(attempt: int, settings: AdapterRetrySettings) -> float:
    """Calculate exponential backoff delay with jitter.

    Uses exponential backoff formula with jitter to prevent thundering herd:
    - base_delay = initial_backoff_seconds * (backoff_growth_factor ** attempt)
    - capped_delay = min(base_delay, max_backoff_seconds)
    - jitter = capped_delay * random.uniform(-0.1, 0.1)
    - final_delay = capped_delay + jitter

    Args:
        attempt: Current retry attempt number (0-indexed)
        settings: Retry configuration settings

    Returns:
        Delay in seconds (with jitter applied)

    """
    base_delay = settings.adapter_initial_backoff_seconds * (settings.adapter_backoff_growth_factor**attempt)
    capped_delay = min(base_delay, settings.adapter_max_backoff_seconds)
    # Standard random is sufficient for backoff jitter (non-cryptographic use)
    jitter = capped_delay * random.uniform(-0.1, 0.1)  # noqa: S311
    return capped_delay + jitter


def _extract_invocation_context(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[Any, Any]:
    """Extract invocation_id and turn_id from function arguments.

    Searches through both kwargs and positional args to find invocation context.
    This handles both regular functions and instance methods where args[0] is 'self'.

    Args:
        args: Positional arguments (may include 'self' for instance methods)
        kwargs: Keyword arguments

    Returns:
        Tuple of (invocation_id, turn_id)

    """
    # Extract from kwargs first
    invocation_id = kwargs.get("invocation_id")
    turn_id = kwargs.get("turn_id")

    # If not in kwargs, search through args for a dict-like state object
    # This handles both regular functions and instance methods
    if invocation_id is None:
        for arg in args:
            if isinstance(arg, Mapping):
                invocation_id = arg.get("invocation_id")
                turn_id = arg.get("turn_id")
                if invocation_id is not None:
                    break

    return invocation_id, turn_id


def retry_with_backoff(func: T) -> T:  # noqa: C901, UP047
    """Add retry logic with exponential backoff to async functions.

    This decorator wraps async functions to automatically retry on transient
    failures using exponential backoff with jitter. It handles:
    - Error classification (retryable vs non-retryable)
    - Per-attempt timeout enforcement
    - Exponential backoff with jitter
    - Comprehensive logging with invocation_id and turn_id
    - Interruption handling during backoff

    Note: C901 (complexity) is ignored because this implements a retry state
    machine with multiple error paths and logging requirements. The complexity
    is justified and extracting functions would reduce readability.

    Args:
        func: Async function to wrap with retry logic

    Returns:
        Wrapped function with retry behavior

    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        """Implement retry logic."""
        settings = get_settings()
        max_retries = settings.adapter_max_retries
        timeout = settings.adapter_request_timeout_seconds

        # Extract invocation_id and turn_id from arguments
        invocation_id, turn_id = _extract_invocation_context(args, kwargs)

        # Build log context string
        log_context = f"invocation_id={invocation_id}"
        if turn_id is not None:
            log_context += f" turn_id={turn_id}"

        attempt = 0
        start_time = time.time()
        last_error: Exception | None = None

        while attempt <= max_retries:
            try:
                # Execute with timeout
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)

                # Log success if we had previous failures
                if attempt > 0:
                    total_time = time.time() - start_time
                    logger.info(
                        "Retry succeeded on attempt",
                        attempt=attempt,
                        max_retries=max_retries,
                        context=log_context,
                        total_time=total_time,
                    )

                return result

            except asyncio.CancelledError:
                # Handle interruption during execution or backoff
                logger.warning("Operation cancelled", context=log_context)
                raise

            except Exception as error:
                last_error = error

                # Classify error
                if not is_retryable_error(error):
                    # Non-retryable error - fail immediately
                    logger.warning(
                        "Non-retryable error",
                        context=log_context,
                        error_type=type(error).__name__,
                    )
                    raise

                # Check if we can retry
                if attempt >= max_retries:
                    # Exhausted retries
                    total_time = time.time() - start_time
                    logger.warning(
                        "All retries exhausted",
                        context=log_context,
                        attempts=attempt + 1,
                        total_time=total_time,
                        final_error=type(error).__name__,
                    )
                    raise

                # Calculate backoff and sleep
                delay = calculate_backoff(attempt, settings)
                logger.debug(
                    "Retry attempt after error",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    context=log_context,
                    error_type=type(error).__name__,
                    delay=delay,
                )

                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    # Handle interruption during backoff sleep
                    logger.warning("Backoff interrupted", context=log_context)
                    raise

                attempt += 1

        # This should never be reached, but handle it defensively
        if last_error:
            raise last_error
        msg = "Retry logic error: no result and no error"
        raise RuntimeError(msg)

    return wrapper  # type: ignore[return-value]
