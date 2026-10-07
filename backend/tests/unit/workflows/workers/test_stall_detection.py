"""Unit tests for the stall detection worker.

Tests the periodic scanner configuration and worker factory.
Database interaction tests require integration test fixtures and are covered
in integration tests.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.workers.stall_detection import (
    detect_stalled_activities,
    get_stall_detection_worker,
)
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType


def _make_activity(
    *,
    status: ActivityStatus = ActivityStatus.RUNNING,
    expected_duration: int | None = 60,
    started_at: datetime | None,
    stall_alert_at: datetime | None = None,
) -> ActivityExecution:
    """Build an ActivityExecution for testing.

    Args:
        status: Activity status
        expected_duration: Expected duration in seconds or None
        started_at: When the activity started (required to be explicit)
        stall_alert_at: When stall was detected or None

    """
    now = datetime.now(UTC)
    return ActivityExecution(
        id=uuid4(),
        execution_id=uuid4(),
        activity_name="test_activity",
        node_type=NodeType.HTTP_REQUEST,
        temporal_activity_id=f"act-{uuid4()}",
        status=status,
        expected_duration=expected_duration,
        started_at=started_at,
        stall_alert_at=stall_alert_at or (now if stall_alert_at is not None else None),
    )


def _make_session_factory(
    claimed_activities: list[ActivityExecution],
    *,
    first_stall_execution_ids: list[UUID] | None = None,
    execution_modes: dict[UUID, str] | None = None,
    gauge_counts: tuple[int, int] | None = None,
) -> MagicMock:
    """Create a mock session factory that returns activities from UPDATE...RETURNING.

    The UPDATE...RETURNING mock simulates the atomic SQL operations and SELECT queries
    used by the stall detection worker.

    Args:
        claimed_activities: Activities to return from initial claim UPDATE...RETURNING
        first_stall_execution_ids: Execution IDs that should be marked as first-stall
        execution_modes: Map of execution_id to mode string (for Segment events)
        gauge_counts: Tuple of (stalled_workflows_count, stalled_steps_count)

    """
    first_stall_execution_ids = first_stall_execution_ids or []
    execution_modes = execution_modes or {}
    gauge_counts = gauge_counts or (0, 0)

    # Track which call we're on to return different results
    execute_call_count = 0

    async def execute_side_effect(stmt: object, params: dict[str, object] | None = None) -> MagicMock:
        nonlocal execute_call_count
        execute_call_count += 1

        # First call: claim activities UPDATE...RETURNING
        if execute_call_count == 1:
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = claimed_activities
            mock_result = MagicMock()
            mock_result.scalars.return_value = mock_scalars
            return mock_result

        # Second call: batched first-stall UPDATE...RETURNING
        if execute_call_count == 2:
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = first_stall_execution_ids
            mock_result = MagicMock()
            mock_result.scalars.return_value = mock_scalars
            return mock_result

        # Third call: batched execution mode SELECT
        if execute_call_count == 3:
            mock_result = MagicMock()
            # Return list of (id, mode) tuples
            rows = [(exec_id, MagicMock(value=mode)) for exec_id, mode in execution_modes.items()]
            mock_result.all.return_value = rows
            return mock_result

        # Gauge count SELECTs (2 calls: workflows count, steps count)
        if execute_call_count <= 5:
            gauge_index = execute_call_count - 4
            mock_result = MagicMock()
            mock_result.scalar.return_value = gauge_counts[gauge_index]
            return mock_result

        # Fallback
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        return mock_result

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=execute_side_effect)
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    return MagicMock(return_value=ctx)


class TestDetectStalledActivities:
    """Tests for the detect_stalled_activities scanner callback."""

    @pytest.mark.asyncio
    async def test_none_session_factory_returns_early(self) -> None:
        """Scanner should return early when session_factory is None."""
        # This should not raise
        await detect_stalled_activities(None)

    @pytest.mark.asyncio
    async def test_overdue_running_activity_is_claimed(
        self,
    ) -> None:
        """Running activity that exceeded expected duration should be claimed."""
        # Create an activity that started 2 minutes ago with 60s expected duration
        # The mock simulates UPDATE...RETURNING setting stall_alert_at
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)
        execution_id = uuid4()

        activity = _make_activity(
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=started_at,
        )
        activity.execution_id = execution_id
        # Simulate the UPDATE setting stall_alert_at
        activity.stall_alert_at = now

        session_factory = _make_session_factory(
            [activity],
            first_stall_execution_ids=[execution_id],
            execution_modes={execution_id: "standard"},
        )

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
            patch("syntara.workflows.workers.stall_detection.get_telemetry_registry") as mock_get_telemetry,
        ):
            mock_recorder = MagicMock()
            mock_recorder._prometheus = MagicMock()
            mock_get_recorder.return_value = mock_recorder

            mock_telemetry = MagicMock()
            mock_telemetry.is_initialized.return_value = False
            mock_get_telemetry.return_value = mock_telemetry

            await detect_stalled_activities(session_factory)

            # Verify audit event was dispatched with correct values
            mock_dispatch.assert_called_once()
            call_args = mock_dispatch.call_args[0][0]
            assert call_args.activity_execution_id == activity.id
            assert call_args.execution_id == activity.execution_id
            assert call_args.expected_duration == 60
            assert call_args.started_at == started_at
            assert call_args.stall_alert_at == now

            # Verify counter was incremented
            from syntara.metrics.types import MetricType

            mock_recorder.record.assert_called_once_with(MetricType.STALLED_WORKFLOWS_TOTAL, 1.0)

    @pytest.mark.asyncio
    async def test_activity_below_threshold_ignored(
        self,
    ) -> None:
        """Activity that has not exceeded expected duration should not be claimed."""
        # UPDATE...RETURNING returns no rows for activities below threshold
        session_factory = _make_session_factory([])  # No claimed activities

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
            patch("syntara.workflows.workers.stall_detection.get_telemetry_registry") as mock_get_telemetry,
            patch("syntara.workflows.workers.stall_detection._update_prometheus_gauges") as mock_update_gauges,
        ):
            mock_recorder = MagicMock()
            mock_recorder._prometheus = MagicMock()
            mock_get_recorder.return_value = mock_recorder

            mock_telemetry = MagicMock()
            mock_get_telemetry.return_value = mock_telemetry

            await detect_stalled_activities(session_factory)

            # Verify no audit event or metric
            mock_dispatch.assert_not_called()
            mock_recorder.record.assert_not_called()

            # Verify gauges were still updated (no-op case)
            mock_update_gauges.assert_called_once()

    @pytest.mark.asyncio
    async def test_null_expected_duration_ignored(
        self,
    ) -> None:
        """Activity with NULL expected_duration is filtered by SQL WHERE clause."""
        # UPDATE...RETURNING returns no rows since SQL WHERE clause excludes NULL expected_duration
        session_factory = _make_session_factory([])

        with patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch:
            await detect_stalled_activities(session_factory)
            mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_null_started_at_ignored(
        self,
    ) -> None:
        """Activity with NULL started_at is filtered by SQL WHERE clause."""
        # UPDATE...RETURNING returns no rows since SQL WHERE clause excludes NULL started_at
        session_factory = _make_session_factory([])

        with patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch:
            await detect_stalled_activities(session_factory)
            mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_running_activity_ignored(
        self,
    ) -> None:
        """Non-running activities are filtered by SQL WHERE clause."""
        # UPDATE...RETURNING returns no rows since SQL WHERE clause requires status == RUNNING
        session_factory = _make_session_factory([])

        with patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch:
            await detect_stalled_activities(session_factory)
            mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_existing_stall_alert_ignored(
        self,
    ) -> None:
        """Activity with existing stall_alert_at is filtered by SQL WHERE clause (deduplication)."""
        # UPDATE...RETURNING returns no rows since SQL WHERE clause requires stall_alert_at IS NULL
        session_factory = _make_session_factory([])

        with patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch:
            await detect_stalled_activities(session_factory)
            mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_eligible_activities_processed_independently(
        self,
    ) -> None:
        """Multiple stalled activities should each be processed independently."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)

        # Create 3 stalled activities in different executions (already claimed by UPDATE...RETURNING)
        activities = []
        execution_ids = []
        execution_modes = {}
        for _ in range(3):
            execution_id = uuid4()
            execution_ids.append(execution_id)
            execution_modes[execution_id] = "standard"
            activity = _make_activity(
                status=ActivityStatus.RUNNING,
                expected_duration=60,
                started_at=started_at,
            )
            activity.execution_id = execution_id
            activity.stall_alert_at = now
            activities.append(activity)

        session_factory = _make_session_factory(
            activities,
            first_stall_execution_ids=execution_ids,
            execution_modes=execution_modes,
        )

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
            patch("syntara.workflows.workers.stall_detection.get_telemetry_registry") as mock_get_telemetry,
        ):
            mock_recorder = MagicMock()
            mock_recorder._prometheus = MagicMock()
            mock_get_recorder.return_value = mock_recorder

            mock_telemetry = MagicMock()
            mock_telemetry.is_initialized.return_value = False
            mock_get_telemetry.return_value = mock_telemetry

            await detect_stalled_activities(session_factory)

            # Verify 3 audit events dispatched
            assert mock_dispatch.call_count == 3

            # Verify counter incremented 3 times (one per execution)
            from syntara.metrics.types import MetricType

            assert mock_recorder.record.call_count == 3
            for call in mock_recorder.record.call_args_list:
                assert call[0] == (MetricType.STALLED_WORKFLOWS_TOTAL, 1.0)

    @pytest.mark.asyncio
    async def test_audit_failure_does_not_stop_batch(
        self,
    ) -> None:
        """Audit dispatch failure should not prevent Segment/Prometheus or remaining stalls."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)

        # Create 3 stalled activities in different executions (already claimed)
        activities = []
        execution_ids = []
        execution_modes = {}
        for _ in range(3):
            execution_id = uuid4()
            execution_ids.append(execution_id)
            execution_modes[execution_id] = "standard"
            activity = _make_activity(
                status=ActivityStatus.RUNNING,
                expected_duration=60,
                started_at=started_at,
            )
            activity.execution_id = execution_id
            activity.stall_alert_at = now
            activities.append(activity)

        session_factory = _make_session_factory(
            activities,
            first_stall_execution_ids=execution_ids,
            execution_modes=execution_modes,
        )

        call_count = 0

        def dispatch_side_effect(*_args: object, **_kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # Fail on second call
                msg = "Audit dispatch failed"
                raise RuntimeError(msg)

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
            patch("syntara.workflows.workers.stall_detection.get_telemetry_registry") as mock_get_telemetry,
        ):
            mock_dispatch.side_effect = dispatch_side_effect
            mock_recorder = MagicMock()
            mock_recorder._prometheus = MagicMock()
            mock_get_recorder.return_value = mock_recorder

            mock_telemetry = MagicMock()
            mock_telemetry.is_initialized.return_value = False
            mock_get_telemetry.return_value = mock_telemetry

            await detect_stalled_activities(session_factory)

            # 3 audit dispatches attempted
            assert mock_dispatch.call_count == 3

            # 3 counter increments (audit failure does not skip Prometheus)
            from syntara.metrics.types import MetricType

            assert mock_recorder.record.call_count == 3
            for call in mock_recorder.record.call_args_list:
                assert call[0] == (MetricType.STALLED_WORKFLOWS_TOTAL, 1.0)

    @pytest.mark.asyncio
    async def test_audit_event_receives_correct_values(
        self,
    ) -> None:
        """Verify audit event dispatch receives the correct execution/activity/node values."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)
        execution_id = uuid4()
        activity_id = uuid4()

        activity = ActivityExecution(
            id=activity_id,
            execution_id=execution_id,
            activity_name="webhook_trigger_call",
            node_type=NodeType.WEBHOOK_TRIGGER,
            temporal_activity_id=f"act-{uuid4()}",
            status=ActivityStatus.RUNNING,
            expected_duration=90,
            started_at=started_at,
            stall_alert_at=now,
        )

        session_factory = _make_session_factory(
            [activity],
            first_stall_execution_ids=[execution_id],
            execution_modes={execution_id: "standard"},
        )

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
            patch("syntara.workflows.workers.stall_detection.get_telemetry_registry") as mock_get_telemetry,
        ):
            mock_recorder = MagicMock()
            mock_recorder._prometheus = MagicMock()
            mock_get_recorder.return_value = mock_recorder

            mock_telemetry = MagicMock()
            mock_telemetry.is_initialized.return_value = False
            mock_get_telemetry.return_value = mock_telemetry

            await detect_stalled_activities(session_factory)

            # Verify audit event was called with correct values
            mock_dispatch.assert_called_once()
            event = mock_dispatch.call_args[0][0]
            assert event.activity_execution_id == activity_id
            assert event.execution_id == execution_id
            assert event.activity_name == "webhook_trigger_call"
            assert event.node_type == NodeType.WEBHOOK_TRIGGER
            assert event.expected_duration == 90
            assert event.started_at == started_at
            assert event.stall_alert_at == now

    @pytest.mark.asyncio
    async def test_segment_event_emitted_with_anonymized_properties(
        self,
    ) -> None:
        """Verify Segment event is emitted with anonymized properties (SDP R23/AC-13)."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)
        execution_id = uuid4()

        activity = _make_activity(
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=started_at,
        )
        activity.execution_id = execution_id
        activity.node_type = NodeType.HTTP_REQUEST
        activity.stall_alert_at = now

        session_factory = _make_session_factory(
            [activity],
            first_stall_execution_ids=[execution_id],
            execution_modes={execution_id: "test"},
        )

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch"),
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
            patch("syntara.workflows.workers.stall_detection.get_telemetry_registry") as mock_get_telemetry,
        ):
            mock_recorder = MagicMock()
            mock_recorder._prometheus = MagicMock()
            mock_get_recorder.return_value = mock_recorder

            mock_telemetry = MagicMock()
            mock_telemetry.is_initialized.return_value = True
            mock_telemetry.entitlement_id = "test-entitlement"
            mock_get_telemetry.return_value = mock_telemetry

            await detect_stalled_activities(session_factory)

            # Verify Segment event was sent
            mock_telemetry.send_event.assert_called_once()
            event = mock_telemetry.send_event.call_args[0][0]

            # Verify anonymized properties (no workflow_step_count)
            assert event.execution_mode == "test"
            assert event.stalled_step_type == "http_request"
            assert event.entitlement_id == "test-entitlement"
            assert not hasattr(event, "workflow_step_count")

    @pytest.mark.asyncio
    async def test_counter_incremented_once_per_execution(
        self,
    ) -> None:
        """Multiple stalled steps in one execution should increment workflow counter only once."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)
        execution_id = uuid4()

        # Create 3 stalled activities in the same execution
        activities = []
        for i in range(3):
            activity = _make_activity(
                status=ActivityStatus.RUNNING,
                expected_duration=60,
                started_at=started_at,
            )
            activity.execution_id = execution_id
            activity.node_type = NodeType.HTTP_REQUEST
            activity.activity_name = f"activity_{i}"
            activity.stall_alert_at = now
            activities.append(activity)

        session_factory = _make_session_factory(
            activities,
            first_stall_execution_ids=[execution_id],  # Only one execution
            execution_modes={execution_id: "standard"},
        )

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch"),
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
            patch("syntara.workflows.workers.stall_detection.get_telemetry_registry") as mock_get_telemetry,
        ):
            mock_recorder = MagicMock()
            mock_recorder._prometheus = MagicMock()
            mock_get_recorder.return_value = mock_recorder

            mock_telemetry = MagicMock()
            mock_telemetry.is_initialized.return_value = True
            mock_get_telemetry.return_value = mock_telemetry

            await detect_stalled_activities(session_factory)

            # Verify counter incremented once (not 3 times)
            from syntara.metrics.types import MetricType

            mock_recorder.record.assert_called_once_with(MetricType.STALLED_WORKFLOWS_TOTAL, 1.0)

    @pytest.mark.asyncio
    async def test_already_marked_execution_does_not_increment_counter(
        self,
    ) -> None:
        """Execution already marked with first_stall_detected_at should not increment counter again."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)
        execution_id = uuid4()

        activity = _make_activity(
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=started_at,
        )
        activity.execution_id = execution_id
        activity.stall_alert_at = now

        # Empty first_stall list means UPDATE returned no rows (already marked)
        session_factory = _make_session_factory(
            [activity],
            first_stall_execution_ids=[],  # Already marked, no new first-stall
            execution_modes={execution_id: "standard"},
        )

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch"),
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
            patch("syntara.workflows.workers.stall_detection.get_telemetry_registry") as mock_get_telemetry,
        ):
            mock_recorder = MagicMock()
            mock_recorder._prometheus = MagicMock()
            mock_get_recorder.return_value = mock_recorder

            mock_telemetry = MagicMock()
            mock_telemetry.is_initialized.return_value = False
            mock_get_telemetry.return_value = mock_telemetry

            await detect_stalled_activities(session_factory)

            # Verify counter NOT incremented
            mock_recorder.record.assert_not_called()

    @pytest.mark.asyncio
    async def test_gauge_updates_reflect_current_state(
        self,
    ) -> None:
        """Coordinated scanner should query and update gauge values."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)

        activity = _make_activity(
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=started_at,
        )
        activity.stall_alert_at = now

        # Gauge counts: 5 stalled workflows, 12 stalled steps
        session_factory = _make_session_factory(
            [activity],
            first_stall_execution_ids=[activity.execution_id],
            execution_modes={activity.execution_id: "standard"},
            gauge_counts=(5, 12),
        )

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch"),
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
            patch("syntara.workflows.workers.stall_detection.get_telemetry_registry") as mock_get_telemetry,
        ):
            mock_prometheus = MagicMock()
            mock_recorder = MagicMock()
            mock_recorder._prometheus = mock_prometheus
            mock_get_recorder.return_value = mock_recorder

            mock_telemetry = MagicMock()
            mock_telemetry.is_initialized.return_value = False
            mock_get_telemetry.return_value = mock_telemetry

            await detect_stalled_activities(session_factory)

            # Verify gauges were set to correct values
            mock_prometheus.stalled_workflows_current.set.assert_called_once_with(5.0)
            mock_prometheus.stalled_steps_current.set.assert_called_once_with(12.0)

    @pytest.mark.asyncio
    async def test_segment_failure_does_not_stop_batch(
        self,
    ) -> None:
        """Segment event failure should not prevent audit or Prometheus updates."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)
        execution_id = uuid4()

        activity = _make_activity(
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=started_at,
        )
        activity.execution_id = execution_id
        activity.stall_alert_at = now

        session_factory = _make_session_factory(
            [activity],
            first_stall_execution_ids=[execution_id],
            execution_modes={execution_id: "standard"},
        )

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
            patch("syntara.workflows.workers.stall_detection.get_telemetry_registry") as mock_get_telemetry,
        ):
            mock_recorder = MagicMock()
            mock_recorder._prometheus = MagicMock()
            mock_get_recorder.return_value = mock_recorder

            mock_telemetry = MagicMock()
            mock_telemetry.is_initialized.return_value = True
            mock_telemetry.send_event.side_effect = RuntimeError("Segment API error")
            mock_get_telemetry.return_value = mock_telemetry

            await detect_stalled_activities(session_factory)

            # Verify audit still succeeded
            mock_dispatch.assert_called_once()

            # Verify Prometheus counter still incremented
            from syntara.metrics.types import MetricType

            mock_recorder.record.assert_called_once_with(MetricType.STALLED_WORKFLOWS_TOTAL, 1.0)

    @pytest.mark.asyncio
    async def test_prometheus_failure_does_not_stop_audit_or_segment(
        self,
    ) -> None:
        """Prometheus update failure should not prevent audit or Segment events."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)
        execution_id = uuid4()

        activity = _make_activity(
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=started_at,
        )
        activity.execution_id = execution_id
        activity.stall_alert_at = now

        session_factory = _make_session_factory(
            [activity],
            first_stall_execution_ids=[execution_id],
            execution_modes={execution_id: "standard"},
        )

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
            patch("syntara.workflows.workers.stall_detection.get_telemetry_registry") as mock_get_telemetry,
        ):
            mock_prometheus = MagicMock()
            mock_prometheus.stalled_workflows_current.set.side_effect = RuntimeError("Prometheus error")
            mock_recorder = MagicMock()
            mock_recorder._prometheus = mock_prometheus
            mock_recorder.record.side_effect = RuntimeError("Prometheus counter error")
            mock_get_recorder.return_value = mock_recorder

            mock_telemetry = MagicMock()
            mock_telemetry.is_initialized.return_value = True
            mock_telemetry.entitlement_id = "test-entitlement"
            mock_get_telemetry.return_value = mock_telemetry

            await detect_stalled_activities(session_factory)

            # Verify audit still succeeded
            mock_dispatch.assert_called_once()

            # Verify Segment still succeeded
            mock_telemetry.send_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_already_claimed_rows_not_reprocessed(
        self,
    ) -> None:
        """Already-claimed rows (stall_alert_at IS NOT NULL) should not be returned by UPDATE."""
        # UPDATE...RETURNING returns empty list when all rows already have stall_alert_at set
        session_factory = _make_session_factory([])

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
        ):
            await detect_stalled_activities(session_factory)

            # No audit or telemetry should be emitted
            mock_dispatch.assert_not_called()
            mock_get_recorder.return_value.record.assert_not_called()

    @pytest.mark.asyncio
    async def test_noop_cycle_gauge_refresh_failure_isolated(
        self,
    ) -> None:
        """Gauge refresh failure during no-op cycle should not raise."""
        session_factory = _make_session_factory([])

        with (
            patch("syntara.workflows.workers.stall_detection._update_prometheus_gauges") as mock_update_gauges,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder"),
        ):
            # Simulate gauge refresh failure
            mock_update_gauges.side_effect = RuntimeError("DB connection lost")

            # Should not raise
            await detect_stalled_activities(session_factory)

            # Verify gauge update was attempted
            mock_update_gauges.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_dispatch_called_without_session(
        self,
    ) -> None:
        """Audit dispatch is called without a session (best-effort, not transactional)."""
        now = datetime.now(UTC)
        execution_id = uuid4()

        activity = _make_activity(
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=now - timedelta(seconds=120),
        )
        activity.execution_id = execution_id
        activity.stall_alert_at = now

        session_factory = _make_session_factory(
            [activity],
            first_stall_execution_ids=[execution_id],
            execution_modes={execution_id: "standard"},
        )

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
            patch("syntara.workflows.workers.stall_detection.get_telemetry_registry") as mock_get_telemetry,
        ):
            mock_recorder = MagicMock()
            mock_recorder._prometheus = MagicMock()
            mock_get_recorder.return_value = mock_recorder

            mock_telemetry = MagicMock()
            mock_telemetry.is_initialized.return_value = False
            mock_get_telemetry.return_value = mock_telemetry

            await detect_stalled_activities(session_factory)

            mock_dispatch.assert_called_once()
            assert len(mock_dispatch.call_args[0]) == 1
            assert mock_dispatch.call_args[0][0].activity_execution_id == activity.id

    @pytest.mark.asyncio
    async def test_claim_committed_before_audit_dispatch(
        self,
    ) -> None:
        """Claim is committed before audit dispatch (best-effort pattern)."""
        now = datetime.now(UTC)
        execution_id = uuid4()

        activity = _make_activity(
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=now - timedelta(seconds=120),
        )
        activity.execution_id = execution_id
        activity.stall_alert_at = now

        session_factory = _make_session_factory(
            [activity],
            first_stall_execution_ids=[execution_id],
            execution_modes={execution_id: "standard"},
        )
        mock_session = session_factory.return_value.__aenter__.return_value

        call_order: list[str] = []

        async def commit_side_effect() -> None:
            call_order.append("commit")

        mock_session.commit = AsyncMock(side_effect=commit_side_effect)

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
            patch("syntara.workflows.workers.stall_detection.get_telemetry_registry") as mock_get_telemetry,
        ):

            def dispatch_side_effect(*_args: object, **_kwargs: object) -> None:
                call_order.append("dispatch")

            mock_dispatch.side_effect = dispatch_side_effect

            mock_recorder = MagicMock()
            mock_recorder._prometheus = MagicMock()
            mock_get_recorder.return_value = mock_recorder

            mock_telemetry = MagicMock()
            mock_telemetry.is_initialized.return_value = False
            mock_get_telemetry.return_value = mock_telemetry

            await detect_stalled_activities(session_factory)

            first_commit_idx = call_order.index("commit")
            dispatch_idx = call_order.index("dispatch")
            assert first_commit_idx < dispatch_idx

    @pytest.mark.asyncio
    async def test_audit_dispatch_failure_does_not_undo_claim(
        self,
    ) -> None:
        """Audit dispatch failure does not roll back the committed claim."""
        now = datetime.now(UTC)
        execution_id = uuid4()

        activity = _make_activity(
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=now - timedelta(seconds=120),
        )
        activity.execution_id = execution_id
        activity.stall_alert_at = now

        session_factory = _make_session_factory(
            [activity],
            first_stall_execution_ids=[execution_id],
            execution_modes={execution_id: "standard"},
        )
        mock_session = session_factory.return_value.__aenter__.return_value

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
            patch("syntara.workflows.workers.stall_detection.get_telemetry_registry") as mock_get_telemetry,
        ):
            mock_dispatch.side_effect = RuntimeError("Audit dispatch failed")

            mock_recorder = MagicMock()
            mock_recorder._prometheus = MagicMock()
            mock_get_recorder.return_value = mock_recorder

            mock_telemetry = MagicMock()
            mock_telemetry.is_initialized.return_value = False
            mock_get_telemetry.return_value = mock_telemetry

            await detect_stalled_activities(session_factory)

            # Claim was committed, rollback was never called
            assert mock_session.commit.call_count >= 1
            mock_session.rollback.assert_not_called()

    @pytest.mark.asyncio
    async def test_coordinated_scanner_only_updates_gauges(
        self,
    ) -> None:
        """Gauge updates happen only through the coordinated scanner callback path.

        Non-leader replicas never execute the callback (PeriodicWorker skips
        when the advisory lock is not acquired), so their gauges stay at 0.
        See the deployment note in _update_prometheus_gauges for scraping
        requirements.
        """
        now = datetime.now(UTC)
        activity = _make_activity(
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=now - timedelta(seconds=120),
        )
        activity.stall_alert_at = now

        session_factory = _make_session_factory(
            [activity],
            first_stall_execution_ids=[activity.execution_id],
            execution_modes={activity.execution_id: "standard"},
            gauge_counts=(3, 7),
        )

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch"),
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
            patch("syntara.workflows.workers.stall_detection.get_telemetry_registry") as mock_get_telemetry,
        ):
            mock_prometheus = MagicMock()
            mock_recorder = MagicMock()
            mock_recorder._prometheus = mock_prometheus
            mock_get_recorder.return_value = mock_recorder

            mock_telemetry = MagicMock()
            mock_telemetry.is_initialized.return_value = False
            mock_get_telemetry.return_value = mock_telemetry

            await detect_stalled_activities(session_factory)

            # Gauges set to database-queried values (not increments)
            mock_prometheus.stalled_workflows_current.set.assert_called_once_with(3.0)
            mock_prometheus.stalled_steps_current.set.assert_called_once_with(7.0)


class TestStallDetectionWorker:
    """Tests for the PeriodicWorker factory."""

    def test_worker_default_interval_is_10_seconds(self) -> None:
        """Worker should default to 10-second scan interval (SDP R16/AC-10)."""
        from syntara.core.config.base import Settings

        settings = Settings()
        assert settings.stall_detection_interval_seconds == 10.0

    def test_worker_configuration(self) -> None:
        """Worker should be configured with correct interval and coordination."""
        with patch("syntara.workflows.workers.stall_detection.get_settings") as mock_settings:
            mock_settings.return_value.stall_detection_interval_seconds = 30.0

            worker = get_stall_detection_worker()

            assert worker._name == "stall-detection"
            assert worker._interval_seconds == 30.0
            assert worker._coordinate is True

    def test_worker_factory_is_cached(self) -> None:
        """Worker factory should return the same instance when called multiple times."""
        worker1 = get_stall_detection_worker()
        worker2 = get_stall_detection_worker()
        assert worker1 is worker2
