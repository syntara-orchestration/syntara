"""Unit tests for workflow lifecycle domain audit events and handlers."""

# mypy: disable-error-code="attr-defined"

from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.workflows.audit.workflow_lifecycle import (
    WorkflowAction,
    WorkflowLifecycleEvent,
    WorkflowLifecycleHandler,
)

WORKFLOW_ID = uuid4()
PROJECT_ID = uuid4()


class TestWorkflowLifecycleHandler:
    """Tests for WorkflowLifecycleHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(WorkflowLifecycleHandler, AuditEventHandler)

    def test_workflow_created_sets_resource_fields(self) -> None:
        event = WorkflowLifecycleEvent(
            workflow_id=WORKFLOW_ID,
            workflow_name="Deploy to Production",
            action=WorkflowAction.CREATED,
            version=1,
            project_id=PROJECT_ID,
        )
        result = WorkflowLifecycleHandler().handle(event)

        assert result.event_category == EventCategory.USER_ACTION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "workflow_created"
        assert result.event_message == "Workflow created: Deploy to Production"
        assert result.source_component == "syntara.workflows"
        assert result.workflow_id == WORKFLOW_ID
        assert result.resource_urn == f"urn:syntara:workflow:{WORKFLOW_ID}"
        assert result.resource_name == "Deploy to Production"
        assert isinstance(result.structured_data, AuditContextData)
        assert result.structured_data.data_type == "workflow-lifecycle"
        assert result.structured_data.action == "created"
        assert result.structured_data.workflow_name == "Deploy to Production"
        assert result.structured_data.version == 1
        assert result.structured_data.project_id == str(PROJECT_ID)

    def test_workflow_updated(self) -> None:
        event = WorkflowLifecycleEvent(
            workflow_id=WORKFLOW_ID,
            workflow_name="Deploy to Production",
            action=WorkflowAction.UPDATED,
            version=3,
        )
        result = WorkflowLifecycleHandler().handle(event)

        assert result.event_action == "workflow_updated"
        assert result.structured_data.version == 3
        assert "project_id" not in result.structured_data.model_dump(exclude_none=True)

    def test_workflow_deleted(self) -> None:
        event = WorkflowLifecycleEvent(
            workflow_id=WORKFLOW_ID,
            workflow_name="Old Workflow",
            action=WorkflowAction.DELETED,
        )
        result = WorkflowLifecycleHandler().handle(event)

        assert result.event_action == "workflow_deleted"
        assert result.event_message == "Workflow deleted: Old Workflow"

    def test_error_state(self) -> None:
        event = WorkflowLifecycleEvent(
            workflow_id=WORKFLOW_ID,
            workflow_name="Deploy to Production",
            action=WorkflowAction.CREATED,
            error_type="IntegrityError",
        )
        result = WorkflowLifecycleHandler().handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.event_status == EventStatus.ERROR
        assert result.structured_data.error_type == "IntegrityError"

    def test_error_state_preserves_action_in_event_action(self) -> None:
        """Error-path audit events must retain the original action for forensics."""
        for action in (
            WorkflowAction.CREATED,
            WorkflowAction.UPDATED,
            WorkflowAction.DELETED,
        ):
            event = WorkflowLifecycleEvent(
                workflow_id=WORKFLOW_ID,
                workflow_name="My Workflow",
                action=action,
                error_type="IntegrityError",
            )
            result = WorkflowLifecycleHandler().handle(event)

            assert result.event_severity == EventSeverity.ERROR
            assert result.event_status == EventStatus.ERROR
            assert result.event_action == f"workflow_{action}"
            assert result.structured_data.error_type == "IntegrityError"

    def test_error_state_without_version(self) -> None:
        """Error-path events omit version since the commit never succeeded."""
        event = WorkflowLifecycleEvent(
            workflow_id=WORKFLOW_ID,
            workflow_name="Deploy to Production",
            action=WorkflowAction.UPDATED,
            error_type="OperationalError",
        )
        result = WorkflowLifecycleHandler().handle(event)

        assert result.event_severity == EventSeverity.ERROR
        assert result.structured_data.error_type == "OperationalError"
        assert "version" not in result.structured_data.model_dump(exclude_none=True)
