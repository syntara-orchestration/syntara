"""Unit tests for workflow version audit handlers."""

# mypy: disable-error-code="attr-defined"

from uuid import uuid4

from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.workflows.audit.workflow_version import (
    WorkflowVersionCreatedEvent,
    WorkflowVersionCreatedHandler,
    WorkflowVersionExportedEvent,
    WorkflowVersionExportedHandler,
    WorkflowVersionPublishedEvent,
    WorkflowVersionPublishedHandler,
    WorkflowVersionRestoredEvent,
    WorkflowVersionRestoredHandler,
    WorkflowVersionUnpublishedEvent,
    WorkflowVersionUnpublishedHandler,
)

WORKFLOW_ID = uuid4()
PROJECT_ID = uuid4()


class TestWorkflowVersionCreatedHandler:
    """Tests for WorkflowVersionCreatedHandler."""

    def test_produces_audit_event(self) -> None:
        event = WorkflowVersionCreatedEvent(workflow_id=WORKFLOW_ID, workflow_name="test-wf", version=3)
        audit_event = WorkflowVersionCreatedHandler().handle(event)

        assert audit_event is not None
        assert audit_event.event_category == EventCategory.WORKFLOW_EVENT
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.event_action == "workflow_version_created"
        assert audit_event.source_component == "syntara.workflows"
        assert audit_event.workflow_id == WORKFLOW_ID
        assert audit_event.resource_urn == f"urn:syntara:workflow:{WORKFLOW_ID}"
        assert audit_event.resource_name == "test-wf"
        assert audit_event.event_message == "Workflow version 3 created"

    def test_structured_data_contains_version(self) -> None:
        event = WorkflowVersionCreatedEvent(workflow_id=WORKFLOW_ID, workflow_name="test-wf", version=5)
        audit_event = WorkflowVersionCreatedHandler().handle(event)

        assert audit_event.structured_data.data_type == "workflow-version-created"
        assert audit_event.structured_data.version == 5

    def test_change_summary_included_in_structured_data(self) -> None:
        """AC1-4: Auto-generated change summary appears in audit log structured data."""
        summary = {
            "nodes_added": [{"id": "http_node", "type": "http_request"}],
            "nodes_removed": [],
            "nodes_modified": [],
            "edges_added": [],
            "edges_removed": ["n1 -> n2"],
        }
        event = WorkflowVersionCreatedEvent(
            workflow_id=WORKFLOW_ID,
            workflow_name="test-wf",
            version=3,
            change_summary=summary,
        )
        audit_event = WorkflowVersionCreatedHandler().handle(event)

        assert audit_event.structured_data.change_summary == summary

    def test_no_change_summary_omitted_from_structured_data(self) -> None:
        event = WorkflowVersionCreatedEvent(
            workflow_id=WORKFLOW_ID,
            workflow_name="test-wf",
            version=1,
        )
        audit_event = WorkflowVersionCreatedHandler().handle(event)

        assert getattr(audit_event.structured_data, "change_summary", None) is None


class TestWorkflowVersionPublishedHandler:
    """Tests for WorkflowVersionPublishedHandler."""

    def test_produces_audit_event(self) -> None:
        event = WorkflowVersionPublishedEvent(workflow_id=WORKFLOW_ID, workflow_name="test-wf", version=2)
        audit_event = WorkflowVersionPublishedHandler().handle(event)

        assert audit_event is not None
        assert audit_event.event_category == EventCategory.USER_ACTION
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.event_action == "workflow_version_published"
        assert audit_event.source_component == "syntara.workflows"
        assert audit_event.workflow_id == WORKFLOW_ID
        assert audit_event.resource_urn == f"urn:syntara:workflow:{WORKFLOW_ID}"
        assert audit_event.resource_name == "test-wf"
        assert audit_event.event_message == "Workflow version 2 published"

    def test_structured_data_contains_version(self) -> None:
        event = WorkflowVersionPublishedEvent(workflow_id=WORKFLOW_ID, workflow_name="test-wf", version=3)
        audit_event = WorkflowVersionPublishedHandler().handle(event)

        assert audit_event.structured_data.data_type == "workflow-version-published"
        assert audit_event.structured_data.version == 3

    def test_error_state(self) -> None:
        event = WorkflowVersionPublishedEvent(
            workflow_id=WORKFLOW_ID, workflow_name="test-wf", version=2, error_type="OperationalError"
        )
        audit_event = WorkflowVersionPublishedHandler().handle(event)

        assert audit_event.event_severity == EventSeverity.ERROR
        assert audit_event.event_status == EventStatus.ERROR
        assert audit_event.structured_data.error_type == "OperationalError"

    def test_project_id_included(self) -> None:
        event = WorkflowVersionPublishedEvent(
            workflow_id=WORKFLOW_ID, workflow_name="test-wf", version=2, project_id=PROJECT_ID
        )
        audit_event = WorkflowVersionPublishedHandler().handle(event)

        assert audit_event.structured_data.project_id == str(PROJECT_ID)


class TestWorkflowVersionUnpublishedHandler:
    """Tests for WorkflowVersionUnpublishedHandler."""

    def test_produces_audit_event(self) -> None:
        event = WorkflowVersionUnpublishedEvent(workflow_id=WORKFLOW_ID, workflow_name="test-wf", version=4)
        audit_event = WorkflowVersionUnpublishedHandler().handle(event)

        assert audit_event is not None
        assert audit_event.event_category == EventCategory.USER_ACTION
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.event_action == "workflow_version_unpublished"
        assert audit_event.source_component == "syntara.workflows"
        assert audit_event.workflow_id == WORKFLOW_ID
        assert audit_event.resource_urn == f"urn:syntara:workflow:{WORKFLOW_ID}"
        assert audit_event.resource_name == "test-wf"
        assert audit_event.event_message == "Workflow version 4 unpublished"

    def test_structured_data_contains_version(self) -> None:
        event = WorkflowVersionUnpublishedEvent(workflow_id=WORKFLOW_ID, workflow_name="test-wf", version=1)
        audit_event = WorkflowVersionUnpublishedHandler().handle(event)

        assert audit_event.structured_data.data_type == "workflow-version-unpublished"
        assert audit_event.structured_data.version == 1

    def test_error_state(self) -> None:
        event = WorkflowVersionUnpublishedEvent(
            workflow_id=WORKFLOW_ID, workflow_name="test-wf", version=4, error_type="IntegrityError"
        )
        audit_event = WorkflowVersionUnpublishedHandler().handle(event)

        assert audit_event.event_severity == EventSeverity.ERROR
        assert audit_event.event_status == EventStatus.ERROR
        assert audit_event.structured_data.error_type == "IntegrityError"

    def test_project_id_included(self) -> None:
        event = WorkflowVersionUnpublishedEvent(
            workflow_id=WORKFLOW_ID, workflow_name="test-wf", version=4, project_id=PROJECT_ID
        )
        audit_event = WorkflowVersionUnpublishedHandler().handle(event)

        assert audit_event.structured_data.project_id == str(PROJECT_ID)


class TestWorkflowVersionRestoredHandler:
    """Tests for WorkflowVersionRestoredHandler."""

    def test_produces_audit_event(self) -> None:
        event = WorkflowVersionRestoredEvent(
            workflow_id=WORKFLOW_ID, workflow_name="test-wf", restored_from_version=2, new_version=6
        )
        audit_event = WorkflowVersionRestoredHandler().handle(event)

        assert audit_event is not None
        assert audit_event.event_category == EventCategory.USER_ACTION
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.event_action == "workflow_version_restored"
        assert audit_event.source_component == "syntara.workflows"
        assert audit_event.workflow_id == WORKFLOW_ID
        assert audit_event.resource_urn == f"urn:syntara:workflow:{WORKFLOW_ID}"
        assert audit_event.resource_name == "test-wf"
        assert "version 2" in audit_event.event_message
        assert "version 6" in audit_event.event_message

    def test_structured_data_contains_versions(self) -> None:
        event = WorkflowVersionRestoredEvent(
            workflow_id=WORKFLOW_ID, workflow_name="test-wf", restored_from_version=1, new_version=4
        )
        audit_event = WorkflowVersionRestoredHandler().handle(event)

        assert audit_event.structured_data.data_type == "workflow-version-restored"
        assert audit_event.structured_data.restored_from_version == 1
        assert audit_event.structured_data.new_version == 4

    def test_error_state(self) -> None:
        event = WorkflowVersionRestoredEvent(
            workflow_id=WORKFLOW_ID,
            workflow_name="test-wf",
            restored_from_version=1,
            new_version=3,
            error_type="IntegrityError",
        )
        audit_event = WorkflowVersionRestoredHandler().handle(event)

        assert audit_event.event_severity == EventSeverity.ERROR
        assert audit_event.event_status == EventStatus.ERROR
        assert audit_event.structured_data.error_type == "IntegrityError"

    def test_project_id_included(self) -> None:
        event = WorkflowVersionRestoredEvent(
            workflow_id=WORKFLOW_ID,
            workflow_name="test-wf",
            restored_from_version=1,
            new_version=3,
            project_id=PROJECT_ID,
        )
        audit_event = WorkflowVersionRestoredHandler().handle(event)

        assert audit_event.structured_data.project_id == str(PROJECT_ID)


class TestWorkflowVersionExportedHandler:
    """Tests for WorkflowVersionExportedHandler."""

    def test_produces_audit_event(self) -> None:
        event = WorkflowVersionExportedEvent(workflow_id=WORKFLOW_ID, version=2, workflow_name="test-wf")
        audit_event = WorkflowVersionExportedHandler().handle(event)

        assert audit_event is not None
        assert audit_event.event_category == EventCategory.USER_ACTION
        assert audit_event.event_severity == EventSeverity.INFO
        assert audit_event.event_status == EventStatus.SUCCESS
        assert audit_event.event_action == "workflow_version_exported"
        assert audit_event.source_component == "syntara.workflows"
        assert audit_event.workflow_id == WORKFLOW_ID
        assert audit_event.resource_urn == f"urn:syntara:workflow:{WORKFLOW_ID}"
        assert audit_event.resource_name == "test-wf"
        assert audit_event.event_message == "Workflow version 2 exported"

    def test_structured_data_contains_version(self) -> None:
        event = WorkflowVersionExportedEvent(workflow_id=WORKFLOW_ID, version=4, workflow_name="test-wf")
        audit_event = WorkflowVersionExportedHandler().handle(event)

        assert audit_event.structured_data.data_type == "workflow-version-exported"
        assert audit_event.structured_data.version == 4
