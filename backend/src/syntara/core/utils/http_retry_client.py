"""Base HTTP client with retry logic for workflow signal operations.

This module provides a base class for HTTP clients that need to send requests
with exponential backoff retry logic. It consolidates common retry and HTTP
client patterns used across workflow signal clients (approvals, forms, etc.).
"""

import asyncio
from types import TracebackType
from typing import Any, Self
from uuid import UUID

import httpx
import structlog

from syntara.core.config.base import get_settings
from syntara.core.tls.http_client import build_internal_http_client
from syntara.workflows.utils.url import generate_activity_signal_url

# HTTP status code constants for error classification
_HTTP_STATUS_MIN_SERVER_ERROR = 500

logger = structlog.stdlib.get_logger(__name__)


class BaseHttpRetryClient:
    """Base HTTP client with retry logic for workflow signal operations.

    This base class provides:
    - HTTP client initialization with timeout configuration
    - Async context manager support
    - Retry logic with exponential backoff
    - Error classification for retryable vs non-retryable errors

    Subclasses should implement domain-specific signal methods that use the
    provided `_send_signal_with_retry` method.
    """

    def __init__(self) -> None:
        """Initialize the HTTP retry client.

        Uses WorkflowClientSettings from application configuration.
        """
        settings = get_settings()

        self.timeout = settings.workflow_client_request_timeout_seconds
        self.max_retries = settings.workflow_client_max_retries
        self.retry_backoff_base = settings.workflow_client_initial_backoff_seconds
        self.backoff_growth_factor = settings.workflow_client_backoff_growth_factor
        self.max_backoff_seconds = settings.workflow_client_max_backoff_seconds

        # Create HTTP client with timeout configuration
        self.http_client = build_internal_http_client(
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=True,
        )

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        await self.http_client.aclose()

    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if an error should trigger a retry.

        Args:
            error: The exception to check

        Returns:
            True if the error is retryable, False otherwise

        """
        # Retry on connection and timeout errors
        if isinstance(error, httpx.ConnectError | httpx.TimeoutException):
            return True

        # Retry on server errors (5xx), not client errors (4xx)
        if isinstance(error, httpx.HTTPStatusError):
            return error.response.status_code >= _HTTP_STATUS_MIN_SERVER_ERROR

        return False

    async def _send_signal_with_retry(
        self,
        execution_id: UUID,
        temporal_activity_id: str,
        signal_payload: dict[str, Any],
        log_context: dict[str, Any],
        operation_name: str,
    ) -> None:
        """Send a signal to a workflow activity with retry logic.

        This method handles the common retry pattern with exponential backoff.
        Subclasses should prepare the signal payload and logging context, then
        call this method to perform the actual HTTP POST with retries.

        Args:
            execution_id: Workflow execution ID
            temporal_activity_id: Temporal activity ID to complete
            signal_payload: The signal payload to send (already wrapped in signal_data)
            log_context: Additional structured logging context for this operation
            operation_name: Human-readable operation name for logging (e.g., "approval", "form submission")

        Raises:
            httpx.RequestError: If signal delivery fails after all retries
            httpx.HTTPStatusError: If workflow returns non-retryable error

        Note:
            Signal failures should be logged but may not need to revert the
            database operation (graceful degradation). The caller should handle
            exceptions appropriately for their domain.

        """
        signal_url = generate_activity_signal_url(execution_id, temporal_activity_id)

        logger.info(
            "Sending %s signal to workflow",
            operation_name,
            execution_id=execution_id,
            signal_url=signal_url,
            **log_context,
        )

        # Retry logic with exponential backoff
        for attempt in range(self.max_retries + 1):
            try:
                auth_headers = {
                    "Content-Type": "application/json",
                }
                response = await self.http_client.post(
                    signal_url,
                    json=signal_payload,
                    headers=auth_headers,
                )
                response.raise_for_status()

                logger.info(
                    "%s signal sent successfully",
                    operation_name.capitalize(),
                    execution_id=execution_id,
                    attempt=attempt,
                    response_status=response.status_code,
                    **log_context,
                )
                return

            except httpx.HTTPError as e:
                # Check if we should retry
                is_last_attempt = attempt == self.max_retries
                should_retry = self._is_retryable_error(e) and not is_last_attempt

                if not should_retry:
                    logger.exception(
                        "%s signal failed - non-retryable error or max attempts reached",
                        operation_name.capitalize(),
                        execution_id=execution_id,
                        attempt=attempt,
                        **log_context,
                    )
                    raise

                # Calculate exponential backoff with growth factor and cap
                backoff = self.retry_backoff_base * (self.backoff_growth_factor**attempt)
                backoff = min(backoff, self.max_backoff_seconds)
                logger.warning(
                    "%s signal failed - retrying with backoff",
                    operation_name.capitalize(),
                    execution_id=execution_id,
                    attempt=attempt,
                    max_retries=self.max_retries,
                    backoff_seconds=backoff,
                    error_type=type(e).__name__,
                    error=str(e),
                    **log_context,
                )
                await asyncio.sleep(backoff)

        # Unreachable: loop either returns (success) or raises (all errors)
        msg = f"{operation_name.capitalize()} signal sending failed: loop completed without success or error"
        raise RuntimeError(msg)
