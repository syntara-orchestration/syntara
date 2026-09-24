"""Client for communicating with workflow engine for approval signals.

This client handles sending approval decision signals to the workflow engine
using the existing activity signal endpoint. It follows the established
HTTP client patterns with retry logic and graceful error handling.
"""

from uuid import UUID

from syntara.core.utils.http_retry_client import BaseHttpRetryClient


class WorkflowApiClient(BaseHttpRetryClient):
    """Client for communicating with workflow engine for approval signals.

    This client provides reliable communication with the workflow engine
    for sending approval decision signals. It includes retry logic with
    exponential backoff to handle transient failures gracefully.

    Uses WorkflowClientSettings from configuration for retry and timeout parameters.

    Inherits BaseHttpRetryClient, which handles the retry and backoff logic.

    """

    async def send_approval_signal(
        self,
        execution_id: UUID,
        approval_node_id: str,
        decision: str,
        approval_id: UUID,
        decided_by: str,
        decided_at: str,
        decision_notes: str | None = None,
        temporal_activity_id: str | None = None,
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
            temporal_activity_id: Temporal activity ID to complete. Defaults to
                ``approval_node_id`` for rows created before this field existed.

        Raises:
            httpx.RequestError: If signal delivery fails after all retries
            httpx.HTTPStatusError: If workflow returns non-retryable error

        Note:
            Per research.md, signal failures should be logged but not revert
            the approval decision (graceful degradation). The caller should
            handle exceptions and continue processing.

        """
        activity_id = temporal_activity_id or approval_node_id

        # Build signal payload with fields matching the approval resultSchema
        signal_payload = {
            "signal_data": {
                "decision": decision,
                "decided_by": decided_by,
                "decided_at": decided_at,
                "decision_notes": decision_notes,
            }
        }

        # Prepare logging context
        log_context = {
            "approval_node_id": approval_node_id,
            "decision": decision,
            "approval_id": approval_id,
        }

        # Delegate to base class retry logic
        await self._send_signal_with_retry(
            execution_id=execution_id,
            temporal_activity_id=activity_id,
            signal_payload=signal_payload,
            log_context=log_context,
            operation_name="approval",
        )
