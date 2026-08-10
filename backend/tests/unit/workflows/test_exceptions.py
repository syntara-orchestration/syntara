"""Unit tests for workflow exception classes.

Covers exception hierarchy, constructors, attributes, and decorator registration.
"""

import importlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest

import syntara.workflows.exceptions
from syntara.workflows.exceptions import (
    BuiltinWorkflowDeleteError,
    BuiltinWorkflowMissingError,
    BuiltinWorkflowModifyError,
    ExecutionInTerminalStateError,
    ExecutionNotFoundError,
    ExecutionNotRetryableError,
    PayloadTooLargeError,
    ScheduledTriggerError,
    ScheduledTriggerNotFoundError,
    ScheduledTriggerSyncError,
    TemporalUnavailableError,
    TriggerValidationError,
    WebhookTriggerError,
    WebhookTriggerNotFoundError,
    WebhookTriggerPathConflictError,
    WorkflowDefinitionInvalidError,
    WorkflowError,
    WorkflowNameConflictError,
    WorkflowNotFoundError,
    WorkflowNotPublishedError,
    WorkflowPublishValidationError,
    WorkflowValidationError,
    WorkflowVersionConflictError,
    WorkflowVersionNotFoundError,
)
from syntara.workflows.models.validation_finding import (
    ValidationCategory,
    ValidationFinding,
    ValidationResult,
    ValidationSeverity,
)


def _sample_validation_result() -> ValidationResult:
    """Build a simple validation result with one error finding."""
    return ValidationResult.from_findings(
        [
            ValidationFinding(
                severity=ValidationSeverity.error,
                category=ValidationCategory.schema_violation,
                message="test error",
            ),
        ]
    )


class TestModuleLevelCoverage:
    """Force re-execution of module-level code for coverage tracking.

    The exceptions module is imported during pytest_configure (before coverage
    starts). Reloading ensures class definitions and decorators are tracked.
    """

    def test_module_reload_covers_class_definitions(self) -> None:
        importlib.reload(syntara.workflows.exceptions)


class TestWorkflowErrorHierarchy:
    """All workflow exceptions inherit from WorkflowError."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            WorkflowValidationError,
            WorkflowDefinitionInvalidError,
            WorkflowPublishValidationError,
            WorkflowNotFoundError,
            WorkflowNameConflictError,
            WorkflowVersionNotFoundError,
            WorkflowNotPublishedError,
            ExecutionNotFoundError,
            ExecutionInTerminalStateError,
            ExecutionNotRetryableError,
            TemporalUnavailableError,
            TriggerValidationError,
            PayloadTooLargeError,
            BuiltinWorkflowDeleteError,
            BuiltinWorkflowModifyError,
            BuiltinWorkflowMissingError,
            WorkflowVersionConflictError,
            WebhookTriggerError,
            WebhookTriggerNotFoundError,
            WebhookTriggerPathConflictError,
            ScheduledTriggerError,
            ScheduledTriggerNotFoundError,
            ScheduledTriggerSyncError,
        ],
    )
    def test_inherits_from_workflow_error(self, exc_class: type) -> None:
        assert issubclass(exc_class, WorkflowError)


class TestWorkflowValidationError:
    """Test WorkflowValidationError constructor and message attribute."""

    def test_message(self) -> None:
        exc = WorkflowValidationError("bad input")
        assert str(exc) == "bad input"
        assert exc.message == "bad input"


class TestWorkflowDefinitionInvalidError:
    """Test WorkflowDefinitionInvalidError stores validation_result."""

    def test_stores_validation_result(self) -> None:
        result = _sample_validation_result()
        exc = WorkflowDefinitionInvalidError(result)
        assert exc.validation_result is result
        assert str(exc) == "Workflow definition validation failed"


class TestWorkflowPublishValidationError:
    """Test WorkflowPublishValidationError stores validation_result."""

    def test_stores_validation_result(self) -> None:
        result = _sample_validation_result()
        exc = WorkflowPublishValidationError(result)
        assert exc.validation_result is result
        assert str(exc) == "Cannot publish workflow with validation errors or warnings"


class TestWorkflowNotFoundError:
    """Test WorkflowNotFoundError with ID or name lookup."""

    def test_with_id(self) -> None:
        wf_id = uuid4()
        exc = WorkflowNotFoundError(wf_id)
        assert exc.workflow_id == wf_id
        assert exc.workflow_name is None
        assert str(wf_id) in str(exc)

    def test_with_name(self) -> None:
        exc = WorkflowNotFoundError(workflow_name="My Workflow")
        assert exc.workflow_id is None
        assert exc.workflow_name == "My Workflow"
        assert "My Workflow" in str(exc)

    def test_with_no_args(self) -> None:
        exc = WorkflowNotFoundError()
        assert exc.workflow_id is None
        assert exc.workflow_name is None


class TestWorkflowNameConflictError:
    """Test WorkflowNameConflictError stores the conflicting name."""

    def test_stores_name(self) -> None:
        exc = WorkflowNameConflictError("duplicate-workflow")
        assert exc.name == "duplicate-workflow"
        assert "duplicate-workflow" in str(exc)


class TestWorkflowVersionNotFoundError:
    """Test WorkflowVersionNotFoundError stores workflow ID and version."""

    def test_stores_id_and_version(self) -> None:
        wf_id = uuid4()
        exc = WorkflowVersionNotFoundError(wf_id, 3)
        assert exc.workflow_id == wf_id
        assert exc.version == 3
        assert str(wf_id) in str(exc)
        assert "3" in str(exc)


class TestWorkflowNotPublishedError:
    """Test WorkflowNotPublishedError stores workflow ID."""

    def test_stores_workflow_id(self) -> None:
        wf_id = uuid4()
        exc = WorkflowNotPublishedError(wf_id)
        assert exc.workflow_id == wf_id
        assert str(wf_id) in str(exc)


class TestExecutionNotFoundError:
    """Test ExecutionNotFoundError stores execution ID."""

    def test_stores_execution_id(self) -> None:
        exec_id = uuid4()
        exc = ExecutionNotFoundError(exec_id)
        assert exc.execution_id == exec_id
        assert str(exec_id) in str(exc)


class TestExecutionInTerminalStateError:
    """Test ExecutionInTerminalStateError stores execution state metadata."""

    def test_stores_all_attributes(self) -> None:
        exec_id = uuid4()
        exc = ExecutionInTerminalStateError(exec_id, "completed", "cancel")
        assert exc.execution_id == exec_id
        assert exc.status == "completed"
        assert exc.operation == "cancel"
        assert "cancel" in str(exc)
        assert "completed" in str(exc)

    def test_default_operation(self) -> None:
        exec_id = uuid4()
        exc = ExecutionInTerminalStateError(exec_id, "failed")
        assert exc.operation == "modify"


class TestExecutionNotRetryableError:
    """Test ExecutionNotRetryableError stores execution ID and reason."""

    def test_stores_id_and_reason(self) -> None:
        exec_id = uuid4()
        exc = ExecutionNotRetryableError(exec_id, "still running")
        assert exc.execution_id == exec_id
        assert exc.reason == "still running"
        assert "still running" in str(exc)


class TestTemporalUnavailableError:
    """Test TemporalUnavailableError with explicit and default operation."""

    def test_stores_operation(self) -> None:
        exc = TemporalUnavailableError("workflow execution")
        assert exc.operation == "workflow execution"
        assert "workflow execution" in str(exc)

    def test_default_operation(self) -> None:
        exc = TemporalUnavailableError()
        assert exc.operation == "operation"


class TestTriggerValidationError:
    """Test TriggerValidationError stores the validation message."""

    def test_message(self) -> None:
        exc = TriggerValidationError("'name' is required")
        assert str(exc) == "'name' is required"
        assert exc.message == "'name' is required"


class TestPayloadTooLargeError:
    """Test PayloadTooLargeError stores the size message."""

    def test_message(self) -> None:
        exc = PayloadTooLargeError("Payload exceeds 1MB")
        assert str(exc) == "Payload exceeds 1MB"
        assert exc.message == "Payload exceeds 1MB"


class TestBuiltinWorkflowDeleteError:
    """Test BuiltinWorkflowDeleteError stores workflow name."""

    def test_stores_name(self) -> None:
        exc = BuiltinWorkflowDeleteError("System Workflow")
        assert exc.workflow_name == "System Workflow"
        assert "cannot be deleted" in str(exc)


class TestBuiltinWorkflowModifyError:
    """Test BuiltinWorkflowModifyError stores workflow name."""

    def test_stores_name(self) -> None:
        exc = BuiltinWorkflowModifyError("System Workflow")
        assert exc.workflow_name == "System Workflow"
        assert "cannot be modified" in str(exc)


class TestBuiltinWorkflowMissingError:
    """Test BuiltinWorkflowMissingError stores workflow name."""

    def test_stores_name(self) -> None:
        exc = BuiltinWorkflowMissingError("Required Workflow")
        assert exc.workflow_name == "Required Workflow"
        assert "missing" in str(exc)


class TestWorkflowVersionConflictError:
    """Test WorkflowVersionConflictError stores conflict metadata."""

    def test_stores_all_metadata(self) -> None:
        wf_id = uuid4()
        created_at = datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC)
        exc = WorkflowVersionConflictError(
            workflow_id=wf_id,
            current_version=5,
            expected_version=4,
            created_by_username="alice",
            created_at=created_at,
            current_version_name="v5-draft",
        )
        assert exc.workflow_id == wf_id
        assert exc.current_version == 5
        assert exc.expected_version == 4
        assert exc.created_by_username == "alice"
        assert exc.created_at == created_at
        assert exc.current_version_name == "v5-draft"

    def test_default_version_name_is_none(self) -> None:
        wf_id = uuid4()
        exc = WorkflowVersionConflictError(
            workflow_id=wf_id,
            current_version=2,
            expected_version=1,
            created_by_username="bob",
            created_at=datetime.now(tz=UTC),
        )
        assert exc.current_version_name is None


class TestWebhookTriggerErrorHierarchy:
    """Test that webhook trigger exceptions inherit from WebhookTriggerError."""

    def test_webhook_trigger_not_found_is_webhook_error(self) -> None:
        assert issubclass(WebhookTriggerNotFoundError, WebhookTriggerError)

    def test_webhook_trigger_path_conflict_is_webhook_error(self) -> None:
        assert issubclass(WebhookTriggerPathConflictError, WebhookTriggerError)


class TestWebhookTriggerNotFoundError:
    """Test WebhookTriggerNotFoundError stores path and trigger type."""

    def test_stores_path_and_type(self) -> None:
        exc = WebhookTriggerNotFoundError("/my-hook", "webhook_trigger")
        assert exc.webhook_path == "/my-hook"
        assert exc.trigger_type == "webhook_trigger"
        assert "/my-hook" in str(exc)


class TestWebhookTriggerPathConflictError:
    """Test WebhookTriggerPathConflictError stores the conflicting path."""

    def test_stores_path(self) -> None:
        exc = WebhookTriggerPathConflictError("/taken-path")
        assert exc.webhook_path == "/taken-path"
        assert "/taken-path" in str(exc)


class TestScheduledTriggerErrorHierarchy:
    """Test that scheduled trigger exceptions inherit from ScheduledTriggerError."""

    def test_not_found_is_scheduled_error(self) -> None:
        assert issubclass(ScheduledTriggerNotFoundError, ScheduledTriggerError)

    def test_sync_error_is_scheduled_error(self) -> None:
        assert issubclass(ScheduledTriggerSyncError, ScheduledTriggerError)


class TestScheduledTriggerNotFoundError:
    """Test ScheduledTriggerNotFoundError stores schedule ID."""

    def test_stores_schedule_id(self) -> None:
        exc = ScheduledTriggerNotFoundError("sched-123")
        assert exc.schedule_id == "sched-123"
        assert "sched-123" in str(exc)


class TestScheduledTriggerSyncError:
    """Test ScheduledTriggerSyncError stores workflow ID and trigger count."""

    def test_stores_workflow_id_and_count(self) -> None:
        exc = ScheduledTriggerSyncError("wf-abc", 3)
        assert exc.workflow_id == "wf-abc"
        assert exc.trigger_count == 3
        assert "wf-abc" in str(exc)
