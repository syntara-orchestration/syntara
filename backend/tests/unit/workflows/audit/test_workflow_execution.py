"""Unit tests for WorkflowExecutionErrorEvent audit handler."""

from uuid import uuid4

from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.telemetry.events.workflow_error import TimedOutComponent
from syntara.workflows.audit.execution_error import (
    WorkflowExecutionErrorEvent,
    WorkflowExecutionErrorHandler,
)

EXECUTION_ID = uuid4()
WORKFLOW_ID = uuid4()
REQUEST_ID = uuid4()


class TestWorkflowExecutionErrorHandler:
    """Tests for WorkflowExecutionErrorHandler."""

    def test_produces_audit_event_for_workflow_timeout(self) -> None:
        event = WorkflowExecutionErrorEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            timed_out_component=TimedOutComponent.WORKFLOW,
            configured_timeout_seconds=3600.0,
            elapsed_time_ms=3600000,
            error_type="WorkflowTimedOut",
            request_id=REQUEST_ID,
        )

        handler = WorkflowExecutionErrorHandler()
        audit_event = handler.handle(event)

        assert audit_event is not None
        assert audit_event.event_category == EventCategory.WORKFLOW_EVENT
        assert audit_event.event_severity == EventSeverity.ERROR
        assert audit_event.event_status == EventStatus.ERROR
        assert audit_event.event_action == "workflow_execution_error"
        assert audit_event.source_component == "syntara.workflows.engine"
        assert audit_event.execution_id == EXECUTION_ID
        assert audit_event.workflow_id == WORKFLOW_ID
        assert audit_event.activity_id is None

    def test_produces_audit_event_for_activity_timeout(self) -> None:
        event = WorkflowExecutionErrorEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            timed_out_component=TimedOutComponent.ACTIVITY,
            configured_timeout_seconds=30.0,
            elapsed_time_ms=30500,
            activity_id="script-1",
            error_type="ActivityTimedOut",
            request_id=REQUEST_ID,
        )

        handler = WorkflowExecutionErrorHandler()
        audit_event = handler.handle(event)

        assert audit_event is not None
        assert audit_event.activity_id == "script-1"
        assert audit_event.execution_id == EXECUTION_ID

    def test_structured_data_fields(self) -> None:
        event = WorkflowExecutionErrorEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            timed_out_component=TimedOutComponent.ACTIVITY,
            configured_timeout_seconds=30.0,
            elapsed_time_ms=30500,
            activity_id="http-1",
            retry_count=2,
            error_type="ConnectionError",
            retry_reason="Connection refused",
        )

        handler = WorkflowExecutionErrorHandler()
        audit_event = handler.handle(event)

        assert audit_event is not None
        data = audit_event.structured_data
        assert data.data_type == "workflow-execution-error"
        assert data.error_type == "ConnectionError"
        assert data.timed_out_component == "activity"  # type: ignore[attr-defined]
        assert data.configured_timeout_seconds == 30.0  # type: ignore[attr-defined]
        assert data.elapsed_time_ms == 30500  # type: ignore[attr-defined]
        assert data.retry_count == 2  # type: ignore[attr-defined]
        assert data.retry_reason == "Connection refused"  # type: ignore[attr-defined]

    def test_event_message_includes_component_and_error_type(self) -> None:
        event = WorkflowExecutionErrorEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            timed_out_component=TimedOutComponent.WORKFLOW,
            configured_timeout_seconds=60.0,
            elapsed_time_ms=60000,
            error_type="WorkflowTimedOut",
        )

        handler = WorkflowExecutionErrorHandler()
        audit_event = handler.handle(event)

        assert audit_event is not None
        assert "workflow" in audit_event.event_message
        assert "WorkflowTimedOut" in audit_event.event_message

    def test_event_message_fallback_when_no_error_type(self) -> None:
        event = WorkflowExecutionErrorEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            timed_out_component=TimedOutComponent.ACTIVITY,
            configured_timeout_seconds=30.0,
            elapsed_time_ms=30000,
        )

        handler = WorkflowExecutionErrorHandler()
        audit_event = handler.handle(event)

        assert audit_event is not None
        assert "timeout" in audit_event.event_message

    def test_none_workflow_id_accepted(self) -> None:
        event = WorkflowExecutionErrorEvent(
            execution_id=EXECUTION_ID,
            workflow_id=None,
            timed_out_component=TimedOutComponent.WORKFLOW,
            configured_timeout_seconds=60.0,
            elapsed_time_ms=60000,
        )

        handler = WorkflowExecutionErrorHandler()
        audit_event = handler.handle(event)

        assert audit_event is not None
        assert audit_event.workflow_id is None

    def test_resource_fields_with_workflow_id_and_name(self) -> None:
        """Resource fields use workflow_id for URN and workflow_name for resource_name."""
        event = WorkflowExecutionErrorEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            timed_out_component=TimedOutComponent.WORKFLOW,
            configured_timeout_seconds=60.0,
            elapsed_time_ms=60000,
            error_type="WorkflowTimedOut",
            workflow_name="Deploy to Production",
        )

        handler = WorkflowExecutionErrorHandler()
        audit_event = handler.handle(event)

        assert audit_event.resource_urn == f"urn:syntara:workflow:{WORKFLOW_ID}"
        assert audit_event.resource_name == "Deploy to Production"

    def test_resource_fields_with_workflow_id_without_name(self) -> None:
        """Resource URN is set even when workflow_name is None."""
        event = WorkflowExecutionErrorEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            timed_out_component=TimedOutComponent.WORKFLOW,
            configured_timeout_seconds=60.0,
            elapsed_time_ms=60000,
            error_type="WorkflowTimedOut",
            workflow_name=None,
        )

        handler = WorkflowExecutionErrorHandler()
        audit_event = handler.handle(event)

        assert audit_event.resource_urn == f"urn:syntara:workflow:{WORKFLOW_ID}"
        assert audit_event.resource_name is None

    def test_resource_fields_without_workflow_id(self) -> None:
        """Resource URN is None when workflow_id is None."""
        event = WorkflowExecutionErrorEvent(
            execution_id=EXECUTION_ID,
            workflow_id=None,
            timed_out_component=TimedOutComponent.WORKFLOW,
            configured_timeout_seconds=60.0,
            elapsed_time_ms=60000,
            workflow_name="Some Workflow",
        )

        handler = WorkflowExecutionErrorHandler()
        audit_event = handler.handle(event)

        assert audit_event.resource_urn is None
        assert audit_event.resource_name == "Some Workflow"
