"""Unit tests for NodeExecutedTelemetryHandler."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from syntara.telemetry.events.node_execution import NodeExecutionEvent
from syntara.telemetry.handlers.node_execution import NodeExecutedTelemetryHandler
from syntara.workflows.audit.node_execution import NodeExecutedEvent as NodeExecutedDomainEvent
from syntara.workflows.workflow_engine.models.workflow_definition import (
    ActivityTerminalStatus,
    NodeType,
)
from tests.unit.telemetry.conftest import SAMPLE_NODE_DEF


class TestNodeExecutedTelemetryHandler:
    """Tests for the NodeExecutedTelemetryHandler."""

    @patch("syntara.telemetry.handlers.node_execution.get_telemetry_registry")
    def test_emits_event_with_correct_fields(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-test-789"
        mock_get_registry.return_value = registry

        execution_id = uuid4()
        request_id = uuid4()
        domain_event = NodeExecutedDomainEvent(
            execution_id=execution_id,
            node_type=NodeType.SCRIPT,
            node_def=SAMPLE_NODE_DEF,
            status=ActivityTerminalStatus.COMPLETED,
            duration_ms=1500,
            request_id=request_id,
        )
        result = NodeExecutedTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_called_once()
        event = registry.send_event.call_args[0][0]
        assert isinstance(event, NodeExecutionEvent)
        assert event.workflow_execution_id == str(execution_id)
        assert event.node_type == NodeType.SCRIPT
        assert event.status == ActivityTerminalStatus.COMPLETED
        assert event.duration_ms == 1500
        assert event.entitlement_id == "ent-test-789"
        assert event.request_id == request_id

    @patch("syntara.telemetry.handlers.node_execution.get_telemetry_registry")
    def test_emits_failed_event_with_error_type(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = "ent-test"
        mock_get_registry.return_value = registry

        domain_event = NodeExecutedDomainEvent(
            execution_id=uuid4(),
            node_type=NodeType.SCRIPT,
            node_def=SAMPLE_NODE_DEF,
            status=ActivityTerminalStatus.FAILED,
            error_type="ActivityExecutionError",
        )
        result = NodeExecutedTelemetryHandler().handle(domain_event)

        assert result is None
        event = registry.send_event.call_args[0][0]
        assert event.status == ActivityTerminalStatus.FAILED
        assert event.error_type == "ActivityExecutionError"

    @patch("syntara.telemetry.handlers.node_execution.get_telemetry_registry")
    def test_skips_when_not_initialized(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = False
        mock_get_registry.return_value = registry

        domain_event = NodeExecutedDomainEvent(
            execution_id=uuid4(),
            node_type=NodeType.SCRIPT,
            node_def=SAMPLE_NODE_DEF,
            status=ActivityTerminalStatus.COMPLETED,
        )
        result = NodeExecutedTelemetryHandler().handle(domain_event)

        assert result is None
        registry.send_event.assert_not_called()

    @patch("syntara.telemetry.handlers.node_execution.get_telemetry_registry")
    def test_does_not_raise_on_exception(self, mock_get_registry: MagicMock) -> None:
        mock_get_registry.side_effect = RuntimeError("boom")

        domain_event = NodeExecutedDomainEvent(
            execution_id=uuid4(),
            node_type=NodeType.SCRIPT,
            node_def=SAMPLE_NODE_DEF,
            status=ActivityTerminalStatus.COMPLETED,
        )
        result = NodeExecutedTelemetryHandler().handle(domain_event)
        assert result is None
