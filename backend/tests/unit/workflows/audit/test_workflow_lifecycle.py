"""Unit tests for workflow lifecycle domain audit events and handlers."""

# mypy: disable-error-code="attr-defined"

from datetime import UTC, datetime
from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.audit.outbox.models import AuditEventSource
from syntara.audit.outbox.worker import _build_otel_log_record
from syntara.workflows.audit.workflow_lifecycle import (
    WorkflowAction,
    WorkflowLifecycleEvent,
    WorkflowLifecycleHandler,
)

WORKFLOW_ID = uuid4()
PROJECT_ID = uuid4()
ACTOR_ID = uuid4()


class TestWorkflowLifecycleHandler:
    """Tests for WorkflowLifecycleHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(WorkflowLifecycleHandler, AuditEventHandler)

    def test_workflow_created_sets_resource_fields(self) -> None:
        event = WorkflowLifecycleEvent(
            workflow_id=WORKFLOW_ID,
            workflow_name="Deploy to Production",
            action=WorkflowAction.CREATED,
            actor_id=ACTOR_ID,
            version=1,
            project_id=PROJECT_ID,
        )
        result = WorkflowLifecycleHandler().handle(event)

        assert result.event_category == EventCategory.USER_ACTION
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.actor_id == ACTOR_ID
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


def test_workflow_deleted_records_referencing_parent_ids() -> None:
    """A confirmed deletion of a referenced workflow records the affected parent ids and count."""
    parent_a = uuid4()
    parent_b = uuid4()
    event = WorkflowLifecycleEvent(
        workflow_id=WORKFLOW_ID,
        workflow_name="Shared sub-workflow",
        action=WorkflowAction.DELETED,
        actor_id=ACTOR_ID,
        project_id=PROJECT_ID,
        referencing_parent_ids=[parent_a, parent_b],
    )

    result = WorkflowLifecycleHandler().handle(event)

    assert result.event_action == "workflow_deleted"
    assert result.event_status == EventStatus.SUCCESS
    assert result.actor_id == ACTOR_ID
    assert result.workflow_id == WORKFLOW_ID
    assert set(result.structured_data.referencing_parent_ids) == {str(parent_a), str(parent_b)}
    assert result.structured_data.referencing_parent_count == 2


def test_workflow_deleted_attributes_are_available_to_otel(override_settings) -> None:
    """The existing OTEL audit pipeline exposes workflow, actor, status and parent ids."""
    parent_a = uuid4()
    parent_b = uuid4()
    event = WorkflowLifecycleEvent(
        workflow_id=WORKFLOW_ID,
        workflow_name="Shared sub-workflow",
        action=WorkflowAction.DELETED,
        actor_id=ACTOR_ID,
        project_id=PROJECT_ID,
        referencing_parent_ids=[parent_a, parent_b],
    )

    audit_event = WorkflowLifecycleHandler().handle(event)
    with override_settings(otel_service_name="syntara-test"):
        record = _build_otel_log_record(audit_event, datetime.now(UTC), AuditEventSource.BUSINESS_EVENT)

    attributes = record.log_record.attributes
    assert attributes is not None
    assert attributes["actor_id"] == str(ACTOR_ID)
    assert attributes["workflow_id"] == str(WORKFLOW_ID)
    assert attributes["event_status"] == EventStatus.SUCCESS.value
    structured_data = attributes["structured_data"]
    assert isinstance(structured_data, dict)
    assert structured_data["referencing_parent_ids"] == [str(parent_a), str(parent_b)]
    assert structured_data["referencing_parent_count"] == 2


def test_workflow_deleted_without_references_omits_parent_fields() -> None:
    """Deleting an unreferenced workflow does not add the parent-id audit fields."""
    event = WorkflowLifecycleEvent(
        workflow_id=WORKFLOW_ID,
        workflow_name="Lonely workflow",
        action=WorkflowAction.DELETED,
        project_id=PROJECT_ID,
    )

    result = WorkflowLifecycleHandler().handle(event)

    assert not hasattr(result.structured_data, "referencing_parent_ids")
