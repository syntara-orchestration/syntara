"""Unit tests for WorkflowExecutionErrorTelemetryHandler."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from syntara.telemetry.events.workflow_error import TimedOutComponent, WorkflowErrorEvent
from syntara.telemetry.handlers.workflow_execution_error import WorkflowExecutionErrorTelemetryHandler
from syntara.workflows.audit.execution_error import WorkflowExecutionErrorEvent

EXECUTION_ID = uuid4()
WORKFLOW_ID = uuid4()
REQUEST_ID = uuid4()


class TestWorkflowExecutionErrorTelemetryHandler:
    """Tests for the WorkflowExecutionErrorTelemetryHandler."""

    @patch("syntara.telemetry.handlers.workflow_execution_error.get_telemetry_registry")
    def test_emits_activity_timeout(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-123"
        mock_get_registry.return_value = registry

        domain_event = WorkflowExecutionErrorEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            timed_out_component=TimedOutComponent.ACTIVITY,
            configured_timeout_seconds=30.0,
            elapsed_time_ms=30500,
            activity_id="script-1",
            request_id=REQUEST_ID,
        )
        result = WorkflowExecutionErrorTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_called_once()
        event = registry.send_event.call_args[0][0]
        assert isinstance(event, WorkflowErrorEvent)
        assert event.workflow_execution_id == str(EXECUTION_ID)
        assert event.timed_out_component == TimedOutComponent.ACTIVITY
        assert event.configured_timeout_seconds == 30.0
        assert event.elapsed_time_ms == 30500
        assert event.activity_id == "script-1"
        assert event.request_id == REQUEST_ID
        assert event.entitlement_id == "ent-123"
        assert event.retry_count == 0

    @patch("syntara.telemetry.handlers.workflow_execution_error.get_telemetry_registry")
    def test_emits_workflow_timeout(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-456"
        mock_get_registry.return_value = registry

        domain_event = WorkflowExecutionErrorEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            timed_out_component=TimedOutComponent.WORKFLOW,
            configured_timeout_seconds=3600.0,
            elapsed_time_ms=3600000,
            error_type="WorkflowTimedOut",
        )
        result = WorkflowExecutionErrorTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_called_once()
        event = registry.send_event.call_args[0][0]
        assert isinstance(event, WorkflowErrorEvent)
        assert event.workflow_execution_id == str(EXECUTION_ID)
        assert event.timed_out_component == TimedOutComponent.WORKFLOW
        assert event.configured_timeout_seconds == 3600.0
        assert event.elapsed_time_ms == 3600000
        assert event.activity_id is None
        assert event.request_id is None
        assert event.error_type == "WorkflowTimedOut"

    @patch("syntara.telemetry.handlers.workflow_execution_error.get_telemetry_registry")
    def test_emits_retry_with_reason(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-789"
        mock_get_registry.return_value = registry

        domain_event = WorkflowExecutionErrorEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            timed_out_component=TimedOutComponent.ACTIVITY,
            configured_timeout_seconds=30.0,
            elapsed_time_ms=0,
            activity_id="http-1",
            retry_count=2,
            error_type="ConnectionError",
            retry_reason="Connection refused",
        )
        result = WorkflowExecutionErrorTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_called_once()
        event = registry.send_event.call_args[0][0]
        assert event.retry_count == 2
        assert event.error_type == "ConnectionError"
        assert event.retry_reason == "Connection refused"

    @patch("syntara.telemetry.handlers.workflow_execution_error.get_telemetry_registry")
    def test_skips_when_not_initialized(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = False
        mock_get_registry.return_value = registry

        domain_event = WorkflowExecutionErrorEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            timed_out_component=TimedOutComponent.ACTIVITY,
            configured_timeout_seconds=30.0,
            elapsed_time_ms=30000,
        )
        result = WorkflowExecutionErrorTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_not_called()

    @patch("syntara.telemetry.handlers.workflow_execution_error.get_telemetry_registry")
    def test_does_not_raise_on_exception(self, mock_get_registry: MagicMock) -> None:
        mock_get_registry.side_effect = RuntimeError("boom")

        domain_event = WorkflowExecutionErrorEvent(
            execution_id=EXECUTION_ID,
            workflow_id=WORKFLOW_ID,
            timed_out_component=TimedOutComponent.ACTIVITY,
            configured_timeout_seconds=30.0,
            elapsed_time_ms=30000,
        )
        result = WorkflowExecutionErrorTelemetryHandler().handle(domain_event)
        assert result is None
