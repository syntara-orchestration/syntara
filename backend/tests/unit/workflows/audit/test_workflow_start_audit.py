"""Unit tests for WorkflowStartEvent audit handler."""

# mypy: disable-error-code="attr-defined"

from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.workflows.audit.execution_started import WorkflowStartEvent, WorkflowStartHandler
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

EXECUTION_ID = uuid4()
WORKFLOW_ID = uuid4()
REQUEST_ID = uuid4()


class TestWorkflowStartHandler:
    """Tests for WorkflowStartHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(WorkflowStartHandler, AuditEventHandler)

    def test_produces_audit_event_with_resource_fields(self) -> None:
        event = WorkflowStartEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            workflow_name="Deploy to Production",
            trigger_type=ActivityName.MANUAL_TRIGGER,
            request_id=REQUEST_ID,
        )
        result = WorkflowStartHandler().handle(event)

        assert result.event_category == EventCategory.WORKFLOW_EVENT
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "workflow_execution_started"
        assert result.event_message == "Workflow execution started: Deploy to Production"
        assert result.source_component == "syntara.workflows"
        assert result.execution_id == EXECUTION_ID
        assert result.workflow_id == WORKFLOW_ID
        assert result.resource_urn == f"urn:syntara:workflow:{WORKFLOW_ID}"
        assert result.resource_name == "Deploy to Production"
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "workflow-execution-started"
        assert result.structured_data.workflow_name == "Deploy to Production"
        assert result.structured_data.trigger_type == ActivityName.MANUAL_TRIGGER.value

    def test_interface_in_structured_data(self) -> None:
        """Interface is propagated to structured_data when set."""
        event = WorkflowStartEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            workflow_name="Deploy to Production",
            trigger_type=ActivityName.MANUAL_TRIGGER,
            interface="rest_api",
            request_id=REQUEST_ID,
        )
        result = WorkflowStartHandler().handle(event)

        assert result.structured_data.interface == "rest_api"

    def test_interface_absent_when_none(self) -> None:
        """Interface is omitted from structured_data when None."""
        event = WorkflowStartEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            workflow_name="Deploy to Production",
        )
        result = WorkflowStartHandler().handle(event)

        assert "interface" not in result.structured_data.model_dump(exclude_none=True)

    def test_trigger_type_optional(self) -> None:
        event = WorkflowStartEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            workflow_name="Deploy to Production",
        )
        result = WorkflowStartHandler().handle(event)

        assert "trigger_type" not in result.structured_data.model_dump(exclude_none=True)
