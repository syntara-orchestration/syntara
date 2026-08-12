"""Unit tests for execution lifecycle domain audit events and handlers."""

# mypy: disable-error-code="attr-defined"

from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.workflows.audit.execution_lifecycle import (
    ExecutionAction,
    ExecutionLifecycleEvent,
    ExecutionLifecycleHandler,
)

EXECUTION_ID = uuid4()
WORKFLOW_ID = uuid4()


class TestExecutionLifecycleHandler:
    """Tests for ExecutionLifecycleHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(ExecutionLifecycleHandler, AuditEventHandler)

    def test_execution_started(self) -> None:
        event = ExecutionLifecycleEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            workflow_name="Deploy to Production",
            action=ExecutionAction.STARTED,
            mode="standard",
        )
        result = ExecutionLifecycleHandler().handle(event)

        assert result.event_category == EventCategory.WORKFLOW_EVENT
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "execution_started"
        assert result.event_message == "Execution started: Deploy to Production"
        assert result.source_component == "syntara.workflows"
        assert result.execution_id == EXECUTION_ID
        assert result.workflow_id == WORKFLOW_ID
        assert result.resource_urn == f"urn:syntara:workflow:{WORKFLOW_ID}"
        assert result.resource_name == "Deploy to Production"
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "execution-lifecycle"
        assert result.structured_data.action == "started"
        assert result.structured_data.mode == "standard"

    def test_execution_cancelled(self) -> None:
        event = ExecutionLifecycleEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            workflow_name="Deploy to Production",
            action=ExecutionAction.CANCELLED,
            mode="test",
        )
        result = ExecutionLifecycleHandler().handle(event)

        assert result.event_action == "execution_cancelled"
        assert result.event_message == "Execution cancelled: Deploy to Production"
        assert result.structured_data.mode == "test"

    def test_error_state(self) -> None:
        event = ExecutionLifecycleEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            workflow_name="Deploy to Production",
            action=ExecutionAction.STARTED,
            error_type="TemporalUnavailableError",
        )
        result = ExecutionLifecycleHandler().handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.structured_data.error_type == "TemporalUnavailableError"
