"""Shared exception classes for workflows module.

This module contains all custom exceptions used across workflow services,
following DRY principle by centralizing exception definitions.
"""

from datetime import datetime
from uuid import UUID

from syntara.core.exception_registry import fastapi_exception
from syntara.core.exceptions import NexusError
from syntara.workflows.models.validation_finding import ValidationResult


class WorkflowError(NexusError):
    """Base exception for all workflow errors."""


@fastapi_exception(handler="syntara.workflows.error_handlers.validation_error_handler")
class WorkflowValidationError(WorkflowError):
    """Workflow validation error."""


@fastapi_exception(handler="syntara.workflows.error_handlers.definition_invalid_handler")
class WorkflowDefinitionInvalidError(WorkflowError):
    """Raised when a workflow definition fails validation via the validate endpoint."""

    def __init__(self, validation_result: ValidationResult) -> None:
        """Initialize with the validation result."""
        self.validation_result = validation_result
        super().__init__("Workflow definition validation failed")


@fastapi_exception(handler="syntara.workflows.error_handlers.publish_validation_handler")
class WorkflowPublishValidationError(WorkflowError):
    """Raised when publishing is blocked because the workflow definition has validation issues."""

    def __init__(self, validation_result: ValidationResult) -> None:
        """Initialize with the validation result."""
        self.validation_result = validation_result
        super().__init__("Cannot publish workflow with validation errors or warnings")


@fastapi_exception(handler="syntara.workflows.error_handlers.workflow_not_found_handler")
class WorkflowNotFoundError(WorkflowError):
    """Raised when a workflow is not found."""

    def __init__(self, workflow_id: UUID | None = None, *, workflow_name: str | None = None) -> None:
        """Initialize exception with workflow ID or name."""
        self.workflow_id = workflow_id
        self.workflow_name = workflow_name
        if workflow_name:
            super().__init__(f"Workflow with name '{workflow_name}' not found")
        else:
            super().__init__(f"Workflow {workflow_id} not found")


@fastapi_exception(handler="syntara.workflows.error_handlers.workflow_name_conflict_handler")
class WorkflowNameConflictError(WorkflowError):
    """Raised when a workflow name already exists."""

    def __init__(self, name: str) -> None:
        """Initialize exception with workflow name."""
        self.name = name
        super().__init__(f"Workflow with name '{name}' already exists in this project")


@fastapi_exception(handler="syntara.workflows.error_handlers.workflow_version_not_found_handler")
class WorkflowVersionNotFoundError(WorkflowError):
    """Raised when a workflow version is not found."""

    def __init__(self, workflow_id: UUID, version: int) -> None:
        """Initialize exception with workflow ID and version."""
        self.workflow_id = workflow_id
        self.version = version
        super().__init__(f"Workflow {workflow_id} version {version} not found")


@fastapi_exception(handler="syntara.workflows.error_handlers.workflow_not_published_handler")
class WorkflowNotPublishedError(WorkflowError):
    """Raised when a triggered execution targets a workflow with no published version."""

    def __init__(self, workflow_id: UUID) -> None:
        """Initialize exception with workflow ID."""
        self.workflow_id = workflow_id
        super().__init__(f"Workflow {workflow_id} has no published version")


@fastapi_exception(handler="syntara.workflows.error_handlers.execution_not_found_handler")
class ExecutionNotFoundError(WorkflowError):
    """Raised when an execution is not found."""

    def __init__(self, execution_id: UUID) -> None:
        """Initialize exception with execution ID."""
        self.execution_id = execution_id
        super().__init__(f"Execution {execution_id} not found")


@fastapi_exception(handler="syntara.workflows.error_handlers.execution_terminal_state_handler")
class ExecutionInTerminalStateError(WorkflowError):
    """Raised when attempting to modify an execution in a terminal state."""

    def __init__(self, execution_id: UUID, status: str, operation: str = "modify") -> None:
        """Initialize exception with execution details."""
        self.execution_id = execution_id
        self.status = status
        self.operation = operation
        super().__init__(f"Cannot {operation} execution {execution_id} in {status} state")


@fastapi_exception(handler="syntara.workflows.error_handlers.execution_not_retryable_handler")
class ExecutionNotRetryableError(WorkflowError):
    """Raised when an execution cannot be retried."""

    def __init__(self, execution_id: UUID, reason: str) -> None:
        """Initialize exception with execution ID and reason."""
        self.execution_id = execution_id
        self.reason = reason
        super().__init__(f"Cannot retry execution {execution_id}: {reason}")


@fastapi_exception(handler="syntara.workflows.error_handlers.temporal_unavailable_handler")
class TemporalUnavailableError(WorkflowError):
    """Raised when Temporal service is unavailable."""

    def __init__(self, operation: str = "operation") -> None:
        """Initialize exception with operation description.

        Args:
            operation: Description of the operation that failed

        """
        self.operation = operation
        super().__init__(f"Temporal service unavailable - cannot perform {operation}")


@fastapi_exception(handler="syntara.workflows.error_handlers.workflow_concurrency_limit_handler")
class WorkflowConcurrencyLimitError(WorkflowError):
    """Raised when the active workflow count has reached the configured limit."""

    def __init__(self, limit: int, active: int) -> None:
        """Initialize with the configured limit and current active count."""
        self.limit = limit
        self.active = active
        super().__init__(
            f"Workflow concurrency limit reached: {active}/{limit} active workflows. "
            "Wait for a workflow to complete before starting a new one."
        )


# ============================================================================
# Trigger Exceptions (shared across trigger types)
# ============================================================================


@fastapi_exception(handler="syntara.workflows.error_handlers.trigger_validation_handler")
class TriggerValidationError(WorkflowError):
    """Raised when a trigger payload fails JSON Schema validation."""

    def __init__(self, message: str) -> None:
        """Initialize exception with validation message."""
        super().__init__(message)


@fastapi_exception(handler="syntara.workflows.error_handlers.payload_too_large_handler")
class PayloadTooLargeError(WorkflowError):
    """Raised when a webhook payload exceeds the size limit."""

    def __init__(self, message: str) -> None:
        """Initialize exception with size details."""
        super().__init__(message)


# ============================================================================
# Webhook Trigger Exceptions
# ============================================================================


@fastapi_exception(handler="syntara.workflows.error_handlers.builtin_workflow_delete_handler")
class BuiltinWorkflowDeleteError(WorkflowError):
    """Raised when attempting to delete a built-in workflow."""

    def __init__(self, workflow_name: str) -> None:
        """Initialize exception with workflow name."""
        self.workflow_name = workflow_name
        super().__init__(f"The built-in '{workflow_name}' workflow cannot be deleted")


@fastapi_exception(handler="syntara.workflows.error_handlers.builtin_workflow_modify_handler")
class BuiltinWorkflowModifyError(WorkflowError):
    """Raised when attempting to modify a built-in workflow."""

    def __init__(self, workflow_name: str) -> None:
        """Initialize exception with workflow name."""
        self.workflow_name = workflow_name
        super().__init__(f"The built-in '{workflow_name}' workflow cannot be modified")


@fastapi_exception(handler="syntara.workflows.error_handlers.builtin_workflow_missing_handler")
class BuiltinWorkflowMissingError(WorkflowError):
    """Raised when a required built-in workflow is not found at runtime."""

    def __init__(self, workflow_name: str) -> None:
        """Initialize exception with workflow name."""
        self.workflow_name = workflow_name
        super().__init__(f"Required built-in workflow '{workflow_name}' is missing")


@fastapi_exception(handler="syntara.workflows.error_handlers.workflow_version_conflict_handler")
class WorkflowVersionConflictError(WorkflowError):
    """Raised when a save or publish conflicts with a newer version."""

    def __init__(
        self,
        workflow_id: UUID,
        current_version: int,
        expected_version: int,
        created_by_username: str,
        created_at: datetime,
        current_version_name: str | None = None,
        expected_version_name: str | None = None,
        expected_created_at: datetime | None = None,
    ) -> None:
        """Initialize with conflict metadata."""
        self.workflow_id = workflow_id
        self.current_version = current_version
        self.expected_version = expected_version
        self.created_by_username = created_by_username
        self.created_at = created_at
        self.current_version_name = current_version_name
        self.expected_version_name = expected_version_name
        self.expected_created_at = expected_created_at
        super().__init__(f"Workflow {workflow_id} has version {current_version} but client expected {expected_version}")


class WebhookTriggerError(WorkflowError):
    """Base exception for all webhook trigger errors."""


@fastapi_exception(handler="syntara.workflows.error_handlers.webhook_trigger_not_found_handler")
class WebhookTriggerNotFoundError(WebhookTriggerError):
    """Raised when a webhook trigger is not found for the given path."""

    def __init__(self, webhook_path: str, trigger_type: str) -> None:
        """Initialize exception with webhook path and trigger type."""
        self.webhook_path = webhook_path
        self.trigger_type = trigger_type
        super().__init__(f"Webhook trigger not found for path '{webhook_path}' (type={trigger_type})")


@fastapi_exception(handler="syntara.workflows.error_handlers.webhook_trigger_path_conflict_handler")
class WebhookTriggerPathConflictError(WebhookTriggerError):
    """Raised when a webhook path already exists."""

    def __init__(self, webhook_path: str) -> None:
        """Initialize exception with webhook path."""
        self.webhook_path = webhook_path
        super().__init__(f"Webhook path '{webhook_path}' is already in use")


@fastapi_exception(handler="syntara.workflows.error_handlers.webhook_auth_required_handler")
class WebhookAuthenticationRequiredError(WebhookTriggerError):
    """Raised when a webhook request has no valid service account Bearer token."""

    def __init__(self, detail: str = "A valid service account Bearer token is required") -> None:
        """Initialize exception with detail message."""
        self.detail = detail
        super().__init__(detail)


@fastapi_exception(handler="syntara.workflows.error_handlers.webhook_sa_not_authorized_handler")
class WebhookServiceAccountNotAuthorizedError(WebhookTriggerError):
    """Raised when the service account is valid but not bound to the trigger."""

    def __init__(self, webhook_path: str, trigger_type: str, service_account_id: "UUID | None" = None) -> None:
        """Initialize exception with webhook path, trigger type, and optional SA ID."""
        self.webhook_path = webhook_path
        self.trigger_type = trigger_type
        self.service_account_id = service_account_id
        super().__init__(f"Service account is not authorized for trigger '{webhook_path}' (type={trigger_type})")


# ============================================================================
# Scheduled Trigger Exceptions
# ============================================================================


class ScheduledTriggerError(WorkflowError):
    """Base exception for all scheduled trigger errors."""


@fastapi_exception(handler="syntara.workflows.error_handlers.scheduled_trigger_not_found_handler")
class ScheduledTriggerNotFoundError(ScheduledTriggerError):
    """Raised when a scheduled trigger is not found."""

    def __init__(self, schedule_id: str) -> None:
        """Initialize exception with schedule ID."""
        self.schedule_id = schedule_id
        super().__init__(f"Scheduled trigger '{schedule_id}' not found")


@fastapi_exception(handler="syntara.workflows.error_handlers.scheduled_trigger_sync_handler")
class ScheduledTriggerSyncError(ScheduledTriggerError):
    """Raised when Temporal is unavailable for scheduled trigger operations."""

    def __init__(self, workflow_id: str, trigger_count: int) -> None:
        """Initialize exception with workflow ID and trigger count."""
        self.workflow_id = workflow_id
        self.trigger_count = trigger_count
        super().__init__(f"Scheduled trigger operation failed for workflow {workflow_id}: Temporal is unavailable")
