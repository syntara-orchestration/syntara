"""Unit tests for node execution telemetry via emit_activities + Audit dispatcher."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.telemetry.events.workflow_emitters import emit_activities
from syntara.telemetry.handlers.node_execution import NodeExecutedTelemetryHandler
from syntara.workflows.audit.node_execution import NodeExecutedEvent
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus

EXECUTION_ID = uuid4()
NODE_DEF: dict[str, object] = {"id": "script-1", "type": "script", "name": "Test Script"}
NODE_DEFINITIONS_MAP: dict[str, dict[str, object]] = {"script-1": NODE_DEF}


def _make_activity(
    name: str,
    status: ActivityStatus,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    node_type: str = "script",
) -> ActivityExecution:
    return ActivityExecution(
        execution_id=EXECUTION_ID,
        activity_name=name,
        node_type=node_type,
        temporal_activity_id=f"temporal-{name}",
        status=status,
        started_at=started_at,
        completed_at=completed_at,
    )


class TestEmitActivityTelemetry:
    """Tests for node execution telemetry emitted via emit_activities."""

    def setup_method(self) -> None:
        AuditEventDispatcher.register({NodeExecutedEvent: NodeExecutedTelemetryHandler()})

    @patch("syntara.telemetry.handlers.node_execution.get_telemetry_registry")
    def test_emits_for_completed_activity(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = ""
        mock_get_registry.return_value = registry

        activity = _make_activity("script-1", ActivityStatus.COMPLETED)
        old_values: dict[str, object] = {"status": ActivityStatus.PENDING}

        emit_activities(
            execution_id=EXECUTION_ID,
            activity_definitions_map=NODE_DEFINITIONS_MAP,
            updated_activities=[(activity, old_values)],
        )

        registry.send_event.assert_called_once()
        event = registry.send_event.call_args[0][0]
        assert event.workflow_execution_id == str(EXECUTION_ID)
        assert event.node_type == "script"
        assert event.status == "completed"
        assert event.duration_ms is None
        assert event.error_type is None

    @patch("syntara.telemetry.handlers.node_execution.get_telemetry_registry")
    def test_computes_duration_from_timestamps(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = ""
        mock_get_registry.return_value = registry

        start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = start + timedelta(seconds=5, milliseconds=500)
        activity = _make_activity("script-1", ActivityStatus.COMPLETED, started_at=start, completed_at=end)
        old_values: dict[str, object] = {"status": ActivityStatus.RUNNING}

        emit_activities(
            execution_id=EXECUTION_ID,
            activity_definitions_map=NODE_DEFINITIONS_MAP,
            updated_activities=[(activity, old_values)],
        )

        event = registry.send_event.call_args[0][0]
        assert event.duration_ms == 5500

    @patch("syntara.telemetry.handlers.node_execution.get_telemetry_registry")
    def test_emits_for_failed_activity_with_error_type(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = ""
        mock_get_registry.return_value = registry

        activity = _make_activity("script-1", ActivityStatus.FAILED)
        old_values: dict[str, object] = {"status": ActivityStatus.RUNNING}

        emit_activities(
            execution_id=EXECUTION_ID,
            activity_definitions_map=NODE_DEFINITIONS_MAP,
            updated_activities=[(activity, old_values)],
        )

        event = registry.send_event.call_args[0][0]
        assert event.status == "failed"
        assert event.error_type == "ActivityExecutionError"

    @patch("syntara.telemetry.handlers.node_execution.get_telemetry_registry")
    def test_emits_for_skipped_activity(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = ""
        mock_get_registry.return_value = registry

        activity = _make_activity("script-1", ActivityStatus.SKIPPED)
        old_values: dict[str, object] = {"status": ActivityStatus.PENDING}

        emit_activities(
            execution_id=EXECUTION_ID,
            activity_definitions_map=NODE_DEFINITIONS_MAP,
            updated_activities=[(activity, old_values)],
        )

        event = registry.send_event.call_args[0][0]
        assert event.status == "skipped"

    @patch("syntara.telemetry.handlers.node_execution.get_telemetry_registry")
    def test_skips_non_terminal_status(self, mock_get_registry: MagicMock) -> None:
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = ""
        mock_get_registry.return_value = registry

        activity = _make_activity("script-1", ActivityStatus.RUNNING)
        old_values: dict[str, object] = {"status": ActivityStatus.PENDING}

        emit_activities(
            execution_id=EXECUTION_ID,
            activity_definitions_map=NODE_DEFINITIONS_MAP,
            updated_activities=[(activity, old_values)],
        )

        registry.send_event.assert_not_called()

    @patch("syntara.telemetry.handlers.node_execution.get_telemetry_registry")
    def test_skips_already_terminal_old_status(self, mock_get_registry: MagicMock) -> None:
        """Avoid duplicate telemetry when re-syncing an already-terminal activity."""
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = ""
        mock_get_registry.return_value = registry

        activity = _make_activity("script-1", ActivityStatus.COMPLETED)
        old_values: dict[str, object] = {"status": ActivityStatus.COMPLETED}

        emit_activities(
            execution_id=EXECUTION_ID,
            activity_definitions_map=NODE_DEFINITIONS_MAP,
            updated_activities=[(activity, old_values)],
        )

        registry.send_event.assert_not_called()

    @patch("syntara.telemetry.handlers.node_execution.get_telemetry_registry")
    def test_fire_and_forget_on_error(self, mock_get_registry: MagicMock) -> None:
        """Telemetry errors should not propagate."""
        registry = MagicMock()
        registry.is_initialized.return_value = True
        registry.entitlement_id = ""
        registry.send_event.side_effect = RuntimeError("Segment down")
        mock_get_registry.return_value = registry

        activity = _make_activity("script-1", ActivityStatus.COMPLETED)
        old_values: dict[str, object] = {"status": ActivityStatus.PENDING}

        emit_activities(
            execution_id=EXECUTION_ID,
            activity_definitions_map=NODE_DEFINITIONS_MAP,
            updated_activities=[(activity, old_values)],
        )
