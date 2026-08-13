"""Unit tests for WorkflowVersionRestoredTelemetryHandler."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from syntara.telemetry.events.workflow_version import (
    WorkflowVersionRestoredEvent as WorkflowVersionRestoredTelemetryEvent,
)
from syntara.telemetry.handlers.workflow_version_restored import WorkflowVersionRestoredTelemetryHandler
from syntara.workflows.audit.workflow_version import WorkflowVersionRestoredEvent


class TestWorkflowVersionRestoredTelemetryHandler:
    """Tests for the WorkflowVersionRestoredTelemetryHandler."""

    @patch("syntara.telemetry.handlers.workflow_version_restored.get_telemetry_registry")
    def test_emits_event_with_correct_fields(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-test-456"
        mock_get_registry.return_value = registry

        workflow_id = uuid4()
        domain_event = WorkflowVersionRestoredEvent(
            workflow_id=workflow_id,
            workflow_name="test-wf",
            restored_from_version=3,
            new_version=7,
        )
        result = WorkflowVersionRestoredTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_called_once()
        event = registry.send_event.call_args[0][0]
        assert isinstance(event, WorkflowVersionRestoredTelemetryEvent)
        assert event.workflow_id == str(workflow_id)
        assert event.restored_from_version == 3
        assert event.new_version == 7
        assert event.entitlement_id == "ent-test-456"

    @patch("syntara.telemetry.handlers.workflow_version_restored.get_telemetry_registry")
    def test_skips_when_not_initialized(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = False
        mock_get_registry.return_value = registry

        domain_event = WorkflowVersionRestoredEvent(
            workflow_id=uuid4(),
            workflow_name="test-wf",
            restored_from_version=2,
            new_version=5,
        )
        result = WorkflowVersionRestoredTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_not_called()

    @patch("syntara.telemetry.handlers.workflow_version_restored.get_telemetry_registry")
    def test_does_not_raise_on_exception(self, mock_get_registry: MagicMock) -> None:
        mock_get_registry.side_effect = RuntimeError("boom")

        domain_event = WorkflowVersionRestoredEvent(
            workflow_id=uuid4(),
            workflow_name="test-wf",
            restored_from_version=1,
            new_version=4,
        )
        result = WorkflowVersionRestoredTelemetryHandler().handle(domain_event)
        assert result is None
