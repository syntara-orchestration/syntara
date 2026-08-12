"""Unit tests for WorkflowCompletedTelemetryHandler."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from syntara.telemetry.events.workflow_execution import WorkflowExecutionCompletedEvent
from syntara.telemetry.handlers.workflow_completed import WorkflowCompletedTelemetryHandler
from syntara.workflows.audit.execution_completed import WorkflowCompletedEvent
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, WorkflowTerminalStatus


class TestWorkflowCompletedTelemetryHandler:
    """Tests for the side-effect telemetry handler."""

    @patch("syntara.telemetry.handlers.workflow_completed.get_telemetry_registry")
    def test_emits_segment_event(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-test-123"
        mock_get_registry.return_value = registry

        execution_id = uuid4()
        request_id = uuid4()
        domain_event = WorkflowCompletedEvent(
            execution_id=execution_id,
            workflow_id=uuid4(),
            status=WorkflowTerminalStatus.COMPLETED,
            duration_ms=5000,
            node_count=3,
            error_count=0,
            request_id=request_id,
        )

        result = WorkflowCompletedTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_called_once()
        event = registry.send_event.call_args[0][0]
        assert isinstance(event, WorkflowExecutionCompletedEvent)
        assert event.workflow_execution_id == str(execution_id)
        assert event.status == WorkflowTerminalStatus.COMPLETED
        assert event.duration_ms == 5000
        assert event.node_count == 3
        assert event.error_count == 0
        assert event.error_type is None
        assert event.entitlement_id == "ent-test-123"
        assert event.request_id == request_id

    @patch("syntara.telemetry.handlers.workflow_completed.get_telemetry_registry")
    def test_emits_failed_event_with_error_type(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-456"
        mock_get_registry.return_value = registry

        domain_event = WorkflowCompletedEvent(
            execution_id=uuid4(),
            workflow_id=uuid4(),
            status=WorkflowTerminalStatus.FAILED,
            duration_ms=1200,
            node_count=5,
            error_count=2,
            error_type="ActivityExecutionError",
        )

        WorkflowCompletedTelemetryHandler().handle(domain_event)

        event = registry.send_event.call_args[0][0]
        assert event.status == WorkflowTerminalStatus.FAILED
        assert event.error_type == "ActivityExecutionError"
        assert event.error_count == 2

    @patch("syntara.telemetry.handlers.workflow_completed.get_telemetry_registry")
    def test_skips_when_not_initialized(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = False
        mock_get_registry.return_value = registry

        domain_event = WorkflowCompletedEvent(
            execution_id=uuid4(),
            workflow_id=uuid4(),
            status=WorkflowTerminalStatus.COMPLETED,
            duration_ms=100,
            node_count=1,
            error_count=0,
        )

        result = WorkflowCompletedTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_not_called()

    @patch("syntara.telemetry.handlers.workflow_completed.get_telemetry_registry")
    def test_does_not_raise_on_error(self, mock_get_registry: MagicMock) -> None:
        mock_get_registry.side_effect = RuntimeError("boom")

        domain_event = WorkflowCompletedEvent(
            execution_id=uuid4(),
            workflow_id=uuid4(),
            status=WorkflowTerminalStatus.COMPLETED,
            duration_ms=100,
            node_count=1,
            error_count=0,
        )

        result = WorkflowCompletedTelemetryHandler().handle(domain_event)
        assert result is None

    @patch("syntara.telemetry.handlers.workflow_completed.get_telemetry_registry")
    def test_none_request_id_passes_none(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-789"
        mock_get_registry.return_value = registry

        domain_event = WorkflowCompletedEvent(
            execution_id=uuid4(),
            workflow_id=uuid4(),
            status=WorkflowTerminalStatus.COMPLETED,
            duration_ms=100,
            node_count=0,
            error_count=0,
        )

        WorkflowCompletedTelemetryHandler().handle(domain_event)

        event = registry.send_event.call_args[0][0]
        assert event.request_id is None

    @patch("syntara.telemetry.handlers.workflow_completed.get_telemetry_registry")
    def test_passes_trigger_type_and_interface_through(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-iface"
        mock_get_registry.return_value = registry

        domain_event = WorkflowCompletedEvent(
            execution_id=uuid4(),
            workflow_id=uuid4(),
            status=WorkflowTerminalStatus.COMPLETED,
            duration_ms=3000,
            node_count=2,
            error_count=0,
            trigger_type=ActivityName.SCHEDULED_TRIGGER,
            interface="api",
        )

        WorkflowCompletedTelemetryHandler().handle(domain_event)

        event = registry.send_event.call_args[0][0]
        assert event.trigger_type == ActivityName.SCHEDULED_TRIGGER
        assert event.interface == "api"

    @patch("syntara.telemetry.handlers.workflow_completed.get_telemetry_registry")
    def test_handles_none_trigger_type_and_interface(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-none"
        mock_get_registry.return_value = registry

        domain_event = WorkflowCompletedEvent(
            execution_id=uuid4(),
            workflow_id=uuid4(),
            status=WorkflowTerminalStatus.COMPLETED,
            duration_ms=100,
            node_count=1,
            error_count=0,
        )

        WorkflowCompletedTelemetryHandler().handle(domain_event)

        event = registry.send_event.call_args[0][0]
        assert event.trigger_type is None
        assert event.interface is None
