"""Client for communicating with workflow engine for form prompt signals.

This client handles sending form submission signals to the workflow engine
using the existing activity signal endpoint. It follows the established
HTTP client patterns with retry logic and graceful error handling.
"""

import asyncio
from types import TracebackType
from typing import Any
from uuid import UUID

import httpx
import structlog

from syntara.core.config.base import get_settings
from syntara.core.tls.http_client import build_internal_http_client
from syntara.workflows.utils.url import generate_activity_signal_url

# HTTP status code constants for error classification
_HTTP_STATUS_MIN_SERVER_ERROR = 500

logger = structlog.stdlib.get_logger(__name__)


class WorkflowApiClient:
    """Client for communicating with workflow engine for form signals.

    This client provides reliable communication with the workflow engine
    for sending form prompt signals. It includes retry logic with
    exponential backoff to handle transient failures gracefully.

    Uses WorkflowClientSettings from configuration for retry and timeout parameters.

    """

    def __init__(self) -> None:
        """Initialize the workflow API client.

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

    async def __aenter__(self) -> "WorkflowApiClient":
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

    async def send_form_signal(
        self,
        execution_id: UUID,
        form_prompt_id: str,
        form_response: dict[str, Any],
        temporal_activity_id: str,
    ) -> None:
        """Send form submission signal to workflow engine.

        This method sends a form submission signal to the workflow engine
        using the existing activity signal endpoint. It includes retry logic
        with exponential backoff for reliability.

        The form_response dict contains the validated and cleaned form field
        data that will be made available to the workflow.

        Args:
            execution_id: Workflow execution ID
            form_prompt_id: ID of the form prompt activity in workflow
            form_response: Validated form field data (key-value pairs)
            temporal_activity_id: Temporal activity ID to complete

        Raises:
            httpx.RequestError: If signal delivery fails after all retries
            httpx.HTTPStatusError: If workflow returns non-retryable error

        Note:
            Signal failures should be logged but not revert the form submission
            (graceful degradation). The caller should handle exceptions and
            continue processing.

        """
        signal_url = generate_activity_signal_url(execution_id, temporal_activity_id)

        # Build signal payload with form response data
        signal_payload = {
            "signal_data": form_response,
        }

        logger.info(
            "Sending form submission signal to workflow",
            execution_id=execution_id,
            form_prompt_id=form_prompt_id,
            signal_url=signal_url,
            field_count=len(form_response),
        )

        # Retry logic with exponential backoff
        last_error: httpx.HTTPError | None = None

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
                    "Form submission signal sent successfully",
                    execution_id=execution_id,
                    form_prompt_id=form_prompt_id,
                    attempt=attempt,
                    response_status=response.status_code,
                )
                return

            except httpx.HTTPError as e:
                last_error = e

                # Check if we should retry
                is_last_attempt = attempt == self.max_retries
                should_retry = self._is_retryable_error(e) and not is_last_attempt

                if not should_retry:
                    logger.exception(
                        "Form submission signal failed - non-retryable error or max attempts reached",
                        execution_id=execution_id,
                        form_prompt_id=form_prompt_id,
                        attempt=attempt,
                    )
                    raise

                # Calculate exponential backoff with growth factor and cap
                backoff = self.retry_backoff_base * (self.backoff_growth_factor**attempt)
                backoff = min(backoff, self.max_backoff_seconds)
                logger.warning(
                    "Form submission signal failed - retrying with backoff",
                    execution_id=execution_id,
                    form_prompt_id=form_prompt_id,
                    attempt=attempt,
                    max_retries=self.max_retries,
                    backoff_seconds=backoff,
                    error_type=type(e).__name__,
                    error=str(e),
                )
                await asyncio.sleep(backoff)

        # This should never be reached due to the raise in the loop
        if last_error:
            raise last_error
        msg = "Signal sending failed: no result and no error"
        raise RuntimeError(msg)
