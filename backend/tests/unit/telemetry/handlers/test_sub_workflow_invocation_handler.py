"""Unit tests for the sub-workflow invocation telemetry handler."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

from syntara.telemetry.events.sub_workflow_invocation import (
    SubWorkflowInvocationEvent,
    SubWorkflowInvocationMode,
)
from syntara.telemetry.handlers.sub_workflow_invocation import SubWorkflowInvocationTelemetryHandler
from syntara.workflows.audit.sub_workflow_invocation import SubWorkflowInvocationCompletedEvent
from syntara.workflows.workflow_engine.models.workflow_definition import WorkflowTerminalStatus


def _domain_event() -> SubWorkflowInvocationCompletedEvent:
    """Build a representative completed invocation event."""
    return SubWorkflowInvocationCompletedEvent(
        parent_execution_id=uuid4(),
        parent_workflow_id=uuid4(),
        parent_workflow_name="Parent",
        parent_node_id="run_child",
        child_execution_id=uuid4(),
        child_workflow_id=uuid4(),
        child_workflow_name="Child",
        status=WorkflowTerminalStatus.COMPLETED,
        invocation_duration_ms=1200,
        child_execution_duration_ms=1000,
        occurred_at=datetime(2026, 11, 24, 10, 0, tzinfo=UTC),
    )


class TestSubWorkflowInvocationTelemetryHandler:
    """Test mapping to Segment and non-fatal behavior."""

    @patch("syntara.telemetry.handlers.sub_workflow_invocation.get_telemetry_registry")
    def test_emits_reference_event_with_anonymized_installation_id(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.anonymous_id = "installation-anon-id"
        registry.entitlement_id = "entitlement-123"
        mock_get_registry.return_value = registry

        result = SubWorkflowInvocationTelemetryHandler().handle(_domain_event())

        assert result is None
        registry.send_event.assert_called_once()
        event = registry.send_event.call_args.args[0]
        assert isinstance(event, SubWorkflowInvocationEvent)
        assert event.invocation_mode == SubWorkflowInvocationMode.REFERENCE
        assert event.installation_anon_id == "installation-anon-id"
        assert event.entitlement_id == "entitlement-123"
        assert event.status == WorkflowTerminalStatus.COMPLETED
        assert event.invocation_duration_ms == 1200
        assert event.child_execution_duration_ms == 1000
        assert "input" not in event.model_dump()
        assert "outputs" not in event.model_dump()

    @patch("syntara.telemetry.handlers.sub_workflow_invocation.get_telemetry_registry")
    def test_skips_when_telemetry_is_disabled(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = False
        mock_get_registry.return_value = registry

        SubWorkflowInvocationTelemetryHandler().handle(_domain_event())

        registry.send_event.assert_not_called()

    @patch("syntara.telemetry.handlers.sub_workflow_invocation.get_telemetry_registry")
    def test_segment_errors_do_not_affect_workflow_execution(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.anonymous_id = "installation-anon-id"
        registry.entitlement_id = ""
        registry.send_event.side_effect = RuntimeError("Segment unavailable")
        mock_get_registry.return_value = registry

        assert SubWorkflowInvocationTelemetryHandler().handle(_domain_event()) is None
