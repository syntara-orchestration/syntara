"""Unit tests for WorkflowVersionExportedTelemetryHandler."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from syntara.telemetry.events.workflow_version import (
    WorkflowVersionExportedEvent as WorkflowVersionExportedTelemetryEvent,
)
from syntara.telemetry.handlers.workflow_version_exported import WorkflowVersionExportedTelemetryHandler
from syntara.workflows.audit.workflow_version import WorkflowVersionExportedEvent


class TestWorkflowVersionExportedTelemetryHandler:
    """Tests for the WorkflowVersionExportedTelemetryHandler."""

    @patch("syntara.telemetry.handlers.workflow_version_exported.get_telemetry_registry")
    def test_emits_event_with_correct_fields(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-test-export"
        mock_get_registry.return_value = registry

        workflow_id = uuid4()
        domain_event = WorkflowVersionExportedEvent(
            workflow_id=workflow_id,
            version=5,
            workflow_name="test-wf",
        )
        result = WorkflowVersionExportedTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_called_once()
        event = registry.send_event.call_args[0][0]
        assert isinstance(event, WorkflowVersionExportedTelemetryEvent)
        assert event.workflow_id == str(workflow_id)
        assert event.version == 5
        assert event.workflow_name == "test-wf"
        assert event.entitlement_id == "ent-test-export"

    @patch("syntara.telemetry.handlers.workflow_version_exported.get_telemetry_registry")
    def test_skips_when_not_initialized(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = False
        mock_get_registry.return_value = registry

        domain_event = WorkflowVersionExportedEvent(
            workflow_id=uuid4(),
            version=2,
            workflow_name="test-wf",
        )
        result = WorkflowVersionExportedTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_not_called()

    @patch("syntara.telemetry.handlers.workflow_version_exported.get_telemetry_registry")
    def test_does_not_raise_on_exception(self, mock_get_registry: MagicMock) -> None:
        mock_get_registry.side_effect = RuntimeError("boom")

        domain_event = WorkflowVersionExportedEvent(
            workflow_id=uuid4(),
            version=1,
            workflow_name="test-wf",
        )
        result = WorkflowVersionExportedTelemetryHandler().handle(domain_event)
        assert result is None
