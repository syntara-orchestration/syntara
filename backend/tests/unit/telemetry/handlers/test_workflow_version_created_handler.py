"""Unit tests for WorkflowVersionCreatedTelemetryHandler."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from syntara.telemetry.events.workflow_version import (
    WorkflowVersionCreatedEvent as WorkflowVersionCreatedTelemetryEvent,
)
from syntara.telemetry.handlers.workflow_version_created import WorkflowVersionCreatedTelemetryHandler
from syntara.workflows.audit.workflow_version import WorkflowVersionCreatedEvent


class TestWorkflowVersionCreatedTelemetryHandler:
    """Tests for the WorkflowVersionCreatedTelemetryHandler."""

    @patch("syntara.telemetry.handlers.workflow_version_created.get_telemetry_registry")
    def test_emits_event_with_correct_fields(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-test-456"
        mock_get_registry.return_value = registry

        workflow_id = uuid4()
        domain_event = WorkflowVersionCreatedEvent(workflow_id=workflow_id, version=5, workflow_name="test-wf")
        result = WorkflowVersionCreatedTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_called_once()
        event = registry.send_event.call_args[0][0]
        assert isinstance(event, WorkflowVersionCreatedTelemetryEvent)
        assert event.workflow_id == str(workflow_id)
        assert event.version == 5
        assert event.entitlement_id == "ent-test-456"

    @patch("syntara.telemetry.handlers.workflow_version_created.get_telemetry_registry")
    def test_skips_when_not_initialized(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = False
        mock_get_registry.return_value = registry

        domain_event = WorkflowVersionCreatedEvent(workflow_id=uuid4(), version=3, workflow_name="test-wf")
        result = WorkflowVersionCreatedTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_not_called()

    @patch("syntara.telemetry.handlers.workflow_version_created.get_telemetry_registry")
    def test_does_not_raise_on_exception(self, mock_get_registry: MagicMock) -> None:
        mock_get_registry.side_effect = RuntimeError("boom")

        domain_event = WorkflowVersionCreatedEvent(workflow_id=uuid4(), version=1, workflow_name="test-wf")
        result = WorkflowVersionCreatedTelemetryHandler().handle(domain_event)
        assert result is None
