"""Client for communicating with workflow engine for form prompt signals.

This client handles sending form submission signals to the workflow engine
using the existing activity signal endpoint. It follows the established
HTTP client patterns with retry logic and graceful error handling.
"""

from typing import Any
from uuid import UUID

from syntara.core.utils.http_retry_client import BaseHttpRetryClient


class WorkflowApiClient(BaseHttpRetryClient):
    """Client for communicating with workflow engine for form signals.

    This client provides reliable communication with the workflow engine
    for sending form prompt signals. It includes retry logic with
    exponential backoff to handle transient failures gracefully.

    Uses WorkflowClientSettings from configuration for retry and timeout parameters.

    Inherits BaseHttpRetryClient, which handles the retry and backoff logic.

    """

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
        # Build signal payload with form response data
        signal_payload = {
            "signal_data": form_response,
        }

        # Prepare logging context
        log_context = {
            "form_prompt_id": form_prompt_id,
            "field_count": len(form_response),
        }

        # Delegate to base class retry logic
        await self._send_signal_with_retry(
            execution_id=execution_id,
            temporal_activity_id=temporal_activity_id,
            signal_payload=signal_payload,
            log_context=log_context,
            operation_name="form submission",
        )
