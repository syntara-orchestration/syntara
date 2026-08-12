"""Unit tests for WorkflowVersionPublishedTelemetryHandler."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from syntara.telemetry.events.workflow_version import (
    WorkflowVersionPublishedEvent as WorkflowVersionPublishedTelemetryEvent,
)
from syntara.telemetry.handlers.workflow_version_published import WorkflowVersionPublishedTelemetryHandler
from syntara.workflows.audit.workflow_version import WorkflowVersionPublishedEvent


class TestWorkflowVersionPublishedTelemetryHandler:
    """Tests for the WorkflowVersionPublishedTelemetryHandler."""

    @patch("syntara.telemetry.handlers.workflow_version_published.get_telemetry_registry")
    def test_emits_event_with_correct_fields(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-test-789"
        mock_get_registry.return_value = registry

        workflow_id = uuid4()
        project_id = uuid4()
        domain_event = WorkflowVersionPublishedEvent(
            workflow_id=workflow_id,
            workflow_name="test-wf",
            version=3,
            project_id=project_id,
        )
        result = WorkflowVersionPublishedTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_called_once()
        event = registry.send_event.call_args[0][0]
        assert isinstance(event, WorkflowVersionPublishedTelemetryEvent)
        assert event.workflow_id == str(workflow_id)
        assert event.version == 3
        assert event.workflow_name == "test-wf"
        assert event.project_id == str(project_id)
        assert event.error_type is None
        assert event.entitlement_id == "ent-test-789"

    @patch("syntara.telemetry.handlers.workflow_version_published.get_telemetry_registry")
    def test_skips_when_not_initialized(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = False
        mock_get_registry.return_value = registry

        domain_event = WorkflowVersionPublishedEvent(
            workflow_id=uuid4(),
            workflow_name="test-wf",
            version=2,
        )
        result = WorkflowVersionPublishedTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_not_called()

    @patch("syntara.telemetry.handlers.workflow_version_published.get_telemetry_registry")
    def test_does_not_raise_on_exception(self, mock_get_registry: MagicMock) -> None:
        mock_get_registry.side_effect = RuntimeError("boom")

        domain_event = WorkflowVersionPublishedEvent(
            workflow_id=uuid4(),
            workflow_name="test-wf",
            version=1,
        )
        result = WorkflowVersionPublishedTelemetryHandler().handle(domain_event)
        assert result is None
