"""Unit tests for the stall detection worker.

Tests the periodic scanner configuration and worker factory.
Database interaction tests require integration test fixtures and are covered
in integration tests.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

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


def _make_session_factory(claimed_activities: list[ActivityExecution]) -> MagicMock:
    """Create a mock session factory that returns activities from UPDATE...RETURNING.

    The UPDATE...RETURNING mock simulates the atomic SQL operation that claims
    stalled activities and returns only those that were successfully updated.

    Args:
        claimed_activities: Activities to return from UPDATE...RETURNING (already claimed)

    """
    # Mock the result of UPDATE...RETURNING
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = claimed_activities

    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

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
        activity = _make_activity(
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=started_at,
        )
        # Simulate the UPDATE setting stall_alert_at
        activity.stall_alert_at = now
        activity.updated_at = now

        session_factory = _make_session_factory([activity])

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
        ):
            mock_recorder = MagicMock()
            mock_get_recorder.return_value = mock_recorder

            await detect_stalled_activities(session_factory)

            # Verify audit event was dispatched with correct values
            mock_dispatch.assert_called_once()
            call_args = mock_dispatch.call_args[0][0]
            assert call_args.activity_execution_id == activity.id
            assert call_args.execution_id == activity.execution_id
            assert call_args.expected_duration == 60
            assert call_args.started_at == started_at
            assert call_args.stall_alert_at == now

            # Verify metric was recorded
            mock_recorder.record.assert_called_once()

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
        ):
            await detect_stalled_activities(session_factory)

            # Verify no audit event or metric
            mock_dispatch.assert_not_called()
            mock_get_recorder.return_value.record.assert_not_called()

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

        # Create 3 stalled activities (already claimed by UPDATE...RETURNING)
        activities = []
        for _ in range(3):
            activity = _make_activity(
                status=ActivityStatus.RUNNING,
                expected_duration=60,
                started_at=started_at,
            )
            activity.stall_alert_at = now
            activity.updated_at = now
            activities.append(activity)

        session_factory = _make_session_factory(activities)

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
        ):
            mock_recorder = MagicMock()
            mock_get_recorder.return_value = mock_recorder

            await detect_stalled_activities(session_factory)

            # Verify 3 audit events dispatched
            assert mock_dispatch.call_count == 3

            # Verify 3 metrics recorded
            assert mock_recorder.record.call_count == 3

    @pytest.mark.asyncio
    async def test_audit_failure_does_not_stop_batch(
        self,
    ) -> None:
        """Audit dispatch failure should not prevent telemetry or remaining stalls."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)

        # Create 3 stalled activities (already claimed)
        activities = []
        for _ in range(3):
            activity = _make_activity(
                status=ActivityStatus.RUNNING,
                expected_duration=60,
                started_at=started_at,
            )
            activity.stall_alert_at = now
            activity.updated_at = now
            activities.append(activity)

        session_factory = _make_session_factory(activities)

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
        ):
            mock_dispatch.side_effect = dispatch_side_effect
            mock_recorder = MagicMock()
            mock_get_recorder.return_value = mock_recorder

            await detect_stalled_activities(session_factory)

            # 3 audit dispatches attempted
            assert mock_dispatch.call_count == 3

            # 3 telemetry attempts (audit failure does not skip telemetry)
            assert mock_recorder.record.call_count == 3

    @pytest.mark.asyncio
    async def test_telemetry_failure_does_not_stop_batch(
        self,
    ) -> None:
        """Telemetry recording failure should not prevent remaining stalls from being processed."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)

        # Create 2 stalled activities (already claimed)
        activities = []
        for _ in range(2):
            activity = _make_activity(
                status=ActivityStatus.RUNNING,
                expected_duration=60,
                started_at=started_at,
            )
            activity.stall_alert_at = now
            activity.updated_at = now
            activities.append(activity)

        session_factory = _make_session_factory(activities)

        call_count = 0

        def record_side_effect(*_args: object, **_kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # Fail on first call
                msg = "Telemetry recording failed"
                raise RuntimeError(msg)

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
        ):
            mock_recorder = MagicMock()
            mock_recorder.record.side_effect = record_side_effect
            mock_get_recorder.return_value = mock_recorder

            await detect_stalled_activities(session_factory)

            # 2 audit events dispatched
            assert mock_dispatch.call_count == 2

            # 2 telemetry attempts (first failed, second succeeded)
            assert mock_recorder.record.call_count == 2

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
            updated_at=now,
        )

        session_factory = _make_session_factory([activity])

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
        ):
            mock_get_recorder.return_value = MagicMock()

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
    async def test_telemetry_receives_correct_node_type(
        self,
    ) -> None:
        """Verify telemetry receives the correct node_type label."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)

        activity = _make_activity(
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=started_at,
        )
        activity.node_type = NodeType.AGENTIC
        activity.stall_alert_at = now
        activity.updated_at = now

        session_factory = _make_session_factory([activity])

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch"),
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
        ):
            mock_recorder = MagicMock()
            mock_get_recorder.return_value = mock_recorder

            await detect_stalled_activities(session_factory)

            # Verify telemetry was called with correct node_type label
            mock_recorder.record.assert_called_once()
            call_args = mock_recorder.record.call_args
            assert call_args[1]["labels"]["node_type"] == NodeType.AGENTIC.value

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


class TestStallDetectionWorker:
    """Tests for the PeriodicWorker factory."""

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
