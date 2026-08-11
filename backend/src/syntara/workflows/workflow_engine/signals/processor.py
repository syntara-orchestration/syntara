"""Signal processor for workflow activity signals.

This module provides centralized signal processing logic for workflow activities,
handling both success and failure signals received from external services (e.g., agent orchestrator).
"""

import contextlib
from typing import Any

from temporalio import workflow
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.common import (
    DEFAULT_RETRYABLE_ERROR_CODES,
    ActivityExecutionError,
    extract_error_code,
)

_USER_FRIENDLY_MESSAGES: dict[str, str] = {
    "AuthenticationError": ("Authentication failed. Check that your credentials are valid and have not expired."),
    "AuthError": ("Authentication failed. Check that your credentials are valid and have not expired."),
    "RateLimitError": "The request was rate-limited. The workflow will retry automatically.",
    "NetworkError": ("A network error occurred. Check your connection and verify the service endpoint is reachable."),
    "TimeoutError": "The request timed out. The service may be under heavy load or unreachable.",
    "ServerError": "The service encountered an internal error. This is usually temporary.",
    "ValidationError": "The request was invalid. Check the step configuration and input values.",
    "LLMConfigurationError": ("The AI model configuration is invalid. Check the model name and parameters."),
    "ToolDiscoveryError": "Failed to discover available tools. Check tool configuration and connectivity.",
    "ToolSelectionUnavailableError": (
        "A selected tool is not available. Verify the tool is enabled and properly configured."
    ),
    "CredentialResolutionError": (
        "Failed to resolve credentials for this step. Check that the credential exists and is accessible."
    ),
    "EmptyLLMResponseError": "The AI model returned an empty response. Try simplifying the prompt or retrying.",
}


def _format_user_message(error_type: str, error_message: str) -> str:
    if error_type in _USER_FRIENDLY_MESSAGES:
        friendly_message = _USER_FRIENDLY_MESSAGES[error_type]
        return f"{friendly_message} Details: {error_message}"
    return f"An unexpected error occurred: {error_message}"


class WorkflowSignalProcessor:
    """Processor for workflow activity signals.

    This class provides static methods for processing activity signals,
    validating their status, and transforming them into appropriate
    responses or exceptions for workflow execution.

    This mirrors the WorkflowSignalClient on the agent orchestrator side,
    creating a symmetric signal handling architecture.
    """

    @staticmethod
    def process_signal(
        signal_data: dict[str, Any],
        activity_id: str,
        execution_id: str,
        retry_policy_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process activity signal and handle both success and failure cases.

        Uses a whitelist approach for error code retry decisions (aligned with Kubernetes patterns).
        Only error codes in the retryableErrors list will be retried.

        Args:
            signal_data: The signal data from the activity (contains status, result, or error)
            activity_id: ID of the activity that sent the signal
            execution_id: Workflow execution ID for logging
            retry_policy_config: Activity's retry policy configuration (optional)
                Should contain 'retryableErrors' (list[int]) - whitelist of codes to retry
                Defaults to [408, 429, 500, 502, 503, 504] if not specified

        Returns:
            Signal data for successful signals (status="completed")

        Raises:
            ApplicationError: If signal indicates non-retryable failure (error code not in whitelist)
            ActivityExecutionError: If signal indicates retryable failure (error code in whitelist)

        """
        signal_status = signal_data.get("status")

        if signal_status == "failed":
            # Extract error information and raise exception
            error_info = signal_data.get("error", {})
            error_message = error_info.get("message", "Agent execution failed")
            error_type = error_info.get("error_type", "UnknownError")

            # Log only if in workflow context (workflow.logger requires workflow event loop)
            with contextlib.suppress(Exception):  # Silently skip logging if not in workflow context
                workflow.logger.error(
                    f"Agentic activity {activity_id} failed: {error_type}: {error_message}",
                    extra={
                        "activity_id": activity_id,
                        "execution_id": execution_id,
                        "error_type": error_type,
                        "error_message": error_message,
                    },
                )

            msg = _format_user_message(error_type, error_message)

            # Extract error code from message (works for HTTP status codes AND exit codes)
            error_code = extract_error_code(error_message)

            # Get retryable error codes from retry policy config (whitelist approach)
            # Default: common transient server errors that should be retried
            retryable_codes: frozenset[int] | list[int] = DEFAULT_RETRYABLE_ERROR_CODES
            if retry_policy_config:
                config_codes = retry_policy_config.get("retryableErrors")
                if config_codes is not None:
                    retryable_codes = config_codes

            # Determine if error is retryable based on whitelist
            # - If no error code extracted: non-retryable (fail fast)
            # - If error code NOT in whitelist: non-retryable
            # - If error code IN whitelist: retryable
            is_retryable = error_code in retryable_codes if error_code else False

            if not is_retryable:
                # Non-retryable error - raise ApplicationError to tell Temporal not to retry
                raise ApplicationError(
                    msg,
                    type=f"ErrorCode{error_code}" if error_code else error_type,
                    non_retryable=True,
                )
            # Retryable error - raise normal exception so workflow may retry
            raise ActivityExecutionError(msg)

        # Success case - return signal data for output mapping
        # The signal_data contains the agent result
        # Pass it directly to output mapping processing (don't extract "result" field)
        # The output mappings (e.g., $.result.answer) will navigate the full structure
        return signal_data
