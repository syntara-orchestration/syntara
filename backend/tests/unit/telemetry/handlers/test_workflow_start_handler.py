"""Unit tests for WorkflowStartTelemetryHandler."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from syntara.telemetry.events.workflow_execution import WorkflowExecutionStartEvent
from syntara.telemetry.handlers.workflow_start import WorkflowStartTelemetryHandler
from syntara.workflows.audit.execution_started import WorkflowStartEvent
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName


class TestWorkflowStartTelemetryHandler:
    """Tests for the WorkflowStartTelemetryHandler."""

    @patch("syntara.telemetry.handlers.workflow_start.get_telemetry_registry")
    def test_emits_event_with_correct_fields(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-test-123"
        mock_get_registry.return_value = registry

        execution_id = uuid4()
        workflow_id = uuid4()
        request_id = uuid4()
        domain_event = WorkflowStartEvent(
            execution_id=execution_id,
            workflow_id=workflow_id,
            workflow_name="test-workflow",
            trigger_type=ActivityName.MANUAL_TRIGGER,
            request_id=request_id,
        )
        result = WorkflowStartTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_called_once()
        event = registry.send_event.call_args[0][0]
        assert isinstance(event, WorkflowExecutionStartEvent)
        assert event.workflow_execution_id == str(execution_id)
        assert event.trigger_type == ActivityName.MANUAL_TRIGGER
        assert event.interface is None
        assert event.entitlement_id == "ent-test-123"
        assert event.request_id == request_id

    @patch("syntara.telemetry.handlers.workflow_start.get_telemetry_registry")
    def test_skips_when_not_initialized(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = False
        mock_get_registry.return_value = registry

        domain_event = WorkflowStartEvent(
            execution_id=uuid4(),
            workflow_id=uuid4(),
            workflow_name="wf",
        )
        result = WorkflowStartTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_not_called()

    @patch("syntara.telemetry.handlers.workflow_start.get_telemetry_registry")
    def test_does_not_raise_on_exception(self, mock_get_registry: MagicMock) -> None:
        mock_get_registry.side_effect = RuntimeError("boom")

        domain_event = WorkflowStartEvent(
            execution_id=uuid4(),
            workflow_id=uuid4(),
            workflow_name="wf",
        )
        result = WorkflowStartTelemetryHandler().handle(domain_event)
        assert result is None

    @patch("syntara.telemetry.handlers.workflow_start.get_telemetry_registry")
    def test_handles_no_trigger_type(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-test-456"
        mock_get_registry.return_value = registry

        domain_event = WorkflowStartEvent(
            execution_id=uuid4(),
            workflow_id=uuid4(),
            workflow_name="wf",
        )
        result = WorkflowStartTelemetryHandler().handle(domain_event)

        assert result is None
        event = registry.send_event.call_args[0][0]
        assert event.trigger_type is None
        assert event.interface is None

    @patch("syntara.telemetry.handlers.workflow_start.get_telemetry_registry")
    def test_passes_interface_through(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-test-789"
        mock_get_registry.return_value = registry

        domain_event = WorkflowStartEvent(
            execution_id=uuid4(),
            workflow_id=uuid4(),
            workflow_name="wf",
            trigger_type=ActivityName.WEBHOOK_TRIGGER,
            interface="ui",
        )
        WorkflowStartTelemetryHandler().handle(domain_event)

        event = registry.send_event.call_args[0][0]
        assert event.interface == "ui"
        assert event.trigger_type == ActivityName.WEBHOOK_TRIGGER
