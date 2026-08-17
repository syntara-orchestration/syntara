"""Integration tests for end-to-end workflow telemetry capture.

Validates that the telemetry client registry and handlers
work together to capture and emit workflow and activity telemetry events.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from syntara.telemetry.client import TelemetryClientRegistry
from syntara.telemetry.events.workflow_execution import (
    WorkflowExecutionCompletedEvent,
    WorkflowExecutionStartEvent,
)
from syntara.telemetry.handlers.node_execution import NodeExecutedTelemetryHandler
from syntara.workflows.audit.node_execution import NodeExecutedEvent
from syntara.workflows.workflow_engine.models.workflow_definition import (
    ActivityTerminalStatus,
    NodeType,
    WorkflowTerminalStatus,
)


class TestEndToEndWorkflowTelemetry:
    """Integration test: full telemetry lifecycle from event capture to Segment send."""

    def test_workflow_start_and_complete_events_sent(self) -> None:
        """Verify that a workflow start and completion event are both sent to Segment."""
        registry = TelemetryClientRegistry()
        mock_client = MagicMock()
        registry._client = mock_client
        registry._entitlement_id = "test-install-001"
        registry._anonymous_id = "anon-test-id"

        execution_id = "test-correlation-id"

        registry.send_event(
            WorkflowExecutionStartEvent(
                workflow_execution_id=execution_id,
                entitlement_id=registry.entitlement_id,
            )
        )

        registry.send_event(
            WorkflowExecutionCompletedEvent(
                workflow_execution_id=execution_id,
                status=WorkflowTerminalStatus.COMPLETED,
                duration_ms=1500,
                node_count=3,
                error_count=0,
                entitlement_id=registry.entitlement_id,
            )
        )

        # Verify two track calls were made (start + completed)
        assert mock_client.track.call_count == 2

        # Verify start event
        start_call = mock_client.track.call_args_list[0]
        assert start_call.kwargs["event"] == "workflow_execution_start"
        assert "user_id" not in start_call.kwargs
        assert start_call.kwargs["anonymous_id"] == "anon-test-id"
        assert start_call.kwargs["properties"]["workflow_execution_id"] == execution_id
        assert start_call.kwargs["properties"]["entitlement_id"] == "test-install-001"

        # Verify completed event
        complete_call = mock_client.track.call_args_list[1]
        assert complete_call.kwargs["event"] == "workflow_execution_completed"
        assert complete_call.kwargs["properties"]["status"] == "completed"
        assert complete_call.kwargs["properties"]["duration_ms"] == 1500
        assert complete_call.kwargs["properties"]["node_count"] == 3
        assert complete_call.kwargs["properties"]["error_count"] == 0

    @patch("syntara.telemetry.handlers.node_execution.get_telemetry_registry")
    def test_node_event_sent_via_audit_handler(self, mock_get_registry: MagicMock) -> None:
        """Verify that NodeExecutedTelemetryHandler emits node_execution to Segment."""
        registry = TelemetryClientRegistry()
        mock_client = MagicMock()
        registry._client = mock_client
        registry._entitlement_id = "test-install-001"
        registry._anonymous_id = "anon-test-id"
        mock_get_registry.return_value = registry

        execution_id = uuid4()
        node_def: dict[str, object] = {"id": "http-1", "type": "http_request"}

        handler = NodeExecutedTelemetryHandler()
        handler.handle(
            NodeExecutedEvent(
                execution_id=execution_id,
                node_type=NodeType.HTTP_REQUEST,
                node_def=node_def,
                status=ActivityTerminalStatus.COMPLETED,
            )
        )

        assert mock_client.track.call_count == 1
        call = mock_client.track.call_args
        assert call.kwargs["event"] == "node_execution"
        assert call.kwargs["properties"]["workflow_execution_id"] == str(execution_id)
        assert call.kwargs["properties"]["node_type"] == "http_request"
        assert call.kwargs["properties"]["status"] == "completed"


class TestEntitlementIdPropagation:
    """Integration test: entitlement_id flows from registry to Segment event properties."""

    def test_entitlement_id_in_event_properties(self) -> None:
        """Verify entitlement_id set on registry is included in event properties."""
        registry = TelemetryClientRegistry()
        mock_client = MagicMock()
        registry._client = mock_client
        registry._entitlement_id = "prod-install-xyz"
        registry._anonymous_id = "anon-test-id"

        assert registry.entitlement_id == "prod-install-xyz"

        registry.send_event(
            WorkflowExecutionStartEvent(
                workflow_execution_id="test-id",
                entitlement_id=registry.entitlement_id,
            )
        )

        call = mock_client.track.call_args
        assert "user_id" not in call.kwargs
        assert call.kwargs["anonymous_id"] == "anon-test-id"
        assert call.kwargs["properties"]["entitlement_id"] == "prod-install-xyz"
