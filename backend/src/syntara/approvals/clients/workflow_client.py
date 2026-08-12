"""Client for communicating with workflow engine for approval signals.

This client handles sending approval decision signals to the workflow engine
using the existing activity signal endpoint. It follows the established
HTTP client patterns with retry logic and graceful error handling.
"""

import asyncio
from types import TracebackType
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
    """Client for communicating with workflow engine for approval signals.

    This client provides reliable communication with the workflow engine
    for sending approval decision signals. It includes retry logic with
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

    async def send_approval_signal(
        self,
        execution_id: UUID,
        approval_node_id: str,
        decision: str,
        approval_id: UUID,
        decided_by: str,
        decided_at: str,
        decision_notes: str | None = None,
    ) -> None:
        """Send approval decision signal to workflow engine.

        This method sends an approval decision signal to the workflow engine
        using the existing activity signal endpoint. It includes retry logic
        with exponential backoff for reliability.

        Field names in the payload match the approval resultSchema so the
        workflow engine can use them directly without remapping.

        Args:
            execution_id: Workflow execution ID
            approval_node_id: ID of the approval activity in workflow
            decision: Decision outcome ('approved' or 'rejected')
            approval_id: ID of the approval request
            decided_by: Username of the user who made the decision
            decided_at: ISO 8601 timestamp of when the decision was made
            decision_notes: Optional notes provided by the approver

        Raises:
            httpx.RequestError: If signal delivery fails after all retries
            httpx.HTTPStatusError: If workflow returns non-retryable error

        Note:
            Per research.md, signal failures should be logged but not revert
            the approval decision (graceful degradation). The caller should
            handle exceptions and continue processing.

        """
        # Generate the signal URL using workflow utils
        signal_url = generate_activity_signal_url(execution_id, approval_node_id)

        # Build signal payload with fields matching the approval resultSchema
        signal_payload = {
            "signal_data": {
                "decision": decision,
                "decided_by": decided_by,
                "decided_at": decided_at,
                "decision_notes": decision_notes,
            }
        }

        logger.info(
            "Sending approval signal to workflow",
            execution_id=execution_id,
            approval_node_id=approval_node_id,
            decision=decision,
            approval_id=approval_id,
            signal_url=signal_url,
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
                    "Approval signal sent successfully",
                    execution_id=execution_id,
                    approval_node_id=approval_node_id,
                    decision=decision,
                    approval_id=approval_id,
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
                        "Approval signal failed - non-retryable error or max attempts reached",
                        execution_id=execution_id,
                        approval_node_id=approval_node_id,
                        decision=decision,
                        approval_id=approval_id,
                        attempt=attempt,
                    )
                    raise

                # Calculate exponential backoff with growth factor and cap
                backoff = self.retry_backoff_base * (self.backoff_growth_factor**attempt)
                backoff = min(backoff, self.max_backoff_seconds)
                logger.warning(
                    "Approval signal failed - retrying with backoff",
                    execution_id=execution_id,
                    approval_node_id=approval_node_id,
                    decision=decision,
                    approval_id=approval_id,
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
