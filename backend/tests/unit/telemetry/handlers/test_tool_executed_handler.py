"""Unit tests for ToolExecutedTelemetryHandler."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from syntara.telemetry.events.tool_execution import ToolExecutedEvent, ToolExecutionEvent
from syntara.telemetry.handlers.tool_executed import ToolExecutedTelemetryHandler
from syntara.tool_manager.models.tool_execution import ToolExecutionStatus


class TestToolExecutedTelemetryHandler:
    """Tests for the ToolExecutedTelemetryHandler."""

    @patch("syntara.telemetry.handlers.tool_executed.get_telemetry_registry")
    def test_emits_event_with_correct_fields(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-test-789"
        mock_get_registry.return_value = registry

        exec_id = uuid4()
        domain_event = ToolExecutedEvent(
            namespaced_name="mcp::get_greeting",
            status=ToolExecutionStatus.SUCCESS,
            duration_ms=142,
            execution_id=exec_id,
        )
        result = ToolExecutedTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_called_once()
        event = registry.send_event.call_args[0][0]
        assert isinstance(event, ToolExecutionEvent)
        assert event.namespaced_name == "mcp::get_greeting"
        assert event.status == ToolExecutionStatus.SUCCESS
        assert event.duration_ms == 142
        assert event.workflow_execution_id == exec_id
        assert event.entitlement_id == "ent-test-789"

    @patch("syntara.telemetry.handlers.tool_executed.get_telemetry_registry")
    def test_emits_event_without_execution_id(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-test"
        mock_get_registry.return_value = registry

        domain_event = ToolExecutedEvent(
            namespaced_name="mcp::tool",
            status=ToolExecutionStatus.ERROR,
            duration_ms=50,
        )
        result = ToolExecutedTelemetryHandler().handle(domain_event)

        assert result is None
        event = registry.send_event.call_args[0][0]
        assert event.workflow_execution_id is None

    @patch("syntara.telemetry.handlers.tool_executed.get_telemetry_registry")
    def test_skips_when_not_initialized(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = False
        mock_get_registry.return_value = registry

        domain_event = ToolExecutedEvent(
            namespaced_name="mcp::tool",
            status=ToolExecutionStatus.SUCCESS,
            duration_ms=100,
        )
        result = ToolExecutedTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_not_called()

    @patch("syntara.telemetry.handlers.tool_executed.get_telemetry_registry")
    def test_does_not_raise_on_exception(self, mock_get_registry: MagicMock) -> None:
        mock_get_registry.side_effect = RuntimeError("boom")

        domain_event = ToolExecutedEvent(
            namespaced_name="mcp::tool",
            status=ToolExecutionStatus.TIMEOUT,
            duration_ms=30000,
        )
        result = ToolExecutedTelemetryHandler().handle(domain_event)
        assert result is None
