"""Unit tests for WorkflowVersionUnpublishedTelemetryHandler."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from syntara.telemetry.events.workflow_version import (
    WorkflowVersionUnpublishedEvent as WorkflowVersionUnpublishedTelemetryEvent,
)
from syntara.telemetry.handlers.workflow_version_unpublished import WorkflowVersionUnpublishedTelemetryHandler
from syntara.workflows.audit.workflow_version import WorkflowVersionUnpublishedEvent


class TestWorkflowVersionUnpublishedTelemetryHandler:
    """Tests for the WorkflowVersionUnpublishedTelemetryHandler."""

    @patch("syntara.telemetry.handlers.workflow_version_unpublished.get_telemetry_registry")
    def test_emits_event_with_correct_fields(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-test-321"
        mock_get_registry.return_value = registry

        workflow_id = uuid4()
        project_id = uuid4()
        domain_event = WorkflowVersionUnpublishedEvent(
            workflow_id=workflow_id,
            workflow_name="test-wf",
            version=4,
            project_id=project_id,
        )
        result = WorkflowVersionUnpublishedTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_called_once()
        event = registry.send_event.call_args[0][0]
        assert isinstance(event, WorkflowVersionUnpublishedTelemetryEvent)
        assert event.workflow_id == str(workflow_id)
        assert event.version == 4
        assert event.workflow_name == "test-wf"
        assert event.project_id == str(project_id)
        assert event.error_type is None
        assert event.entitlement_id == "ent-test-321"

    @patch("syntara.telemetry.handlers.workflow_version_unpublished.get_telemetry_registry")
    def test_skips_when_not_initialized(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = False
        mock_get_registry.return_value = registry

        domain_event = WorkflowVersionUnpublishedEvent(
            workflow_id=uuid4(),
            workflow_name="test-wf",
            version=2,
        )
        result = WorkflowVersionUnpublishedTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_not_called()

    @patch("syntara.telemetry.handlers.workflow_version_unpublished.get_telemetry_registry")
    def test_does_not_raise_on_exception(self, mock_get_registry: MagicMock) -> None:
        mock_get_registry.side_effect = RuntimeError("boom")

        domain_event = WorkflowVersionUnpublishedEvent(
            workflow_id=uuid4(),
            workflow_name="test-wf",
            version=1,
        )
        result = WorkflowVersionUnpublishedTelemetryHandler().handle(domain_event)
        assert result is None
