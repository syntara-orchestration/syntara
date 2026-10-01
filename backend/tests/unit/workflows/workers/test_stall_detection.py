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
    return ActivityExecution(
        id=uuid4(),
        execution_id=uuid4(),
        activity_name="test_activity",
        node_type=NodeType.HTTP_REQUEST,
        temporal_activity_id=f"act-{uuid4()}",
        status=status,
        expected_duration=expected_duration,
        started_at=started_at,
        stall_alert_at=stall_alert_at,
    )


def _make_session_factory(activities: list[ActivityExecution]) -> MagicMock:
    """Create a mock session factory that returns activities from query.

    Filters activities to match the SQL WHERE clause:
    - status == RUNNING
    - expected_duration IS NOT NULL
    - started_at IS NOT NULL
    - stall_alert_at IS NULL
    """
    # Filter activities to match SQL WHERE clause
    filtered = [
        a
        for a in activities
        if a.status == ActivityStatus.RUNNING
        and a.expected_duration is not None
        and a.started_at is not None
        and a.stall_alert_at is None
    ]

    mock_result = MagicMock()
    mock_result.all.return_value = filtered

    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
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
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)
        activity = _make_activity(
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=started_at,
        )

        session_factory = _make_session_factory([activity])

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
        ):
            mock_recorder = MagicMock()
            mock_get_recorder.return_value = mock_recorder

            await detect_stalled_activities(session_factory)

            # Verify the activity was claimed (stall_alert_at and updated_at were set)
            assert activity.stall_alert_at is not None
            assert activity.updated_at is not None

            # Verify audit event was dispatched
            mock_dispatch.assert_called_once()

            # Verify metric was recorded
            mock_recorder.record.assert_called_once()

    @pytest.mark.asyncio
    async def test_activity_below_threshold_ignored(
        self,
    ) -> None:
        """Activity that has not exceeded expected duration should be ignored."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=30)  # Started 30s ago
        activity = _make_activity(
            status=ActivityStatus.RUNNING,
            expected_duration=120,  # Expects 120s, so not stalled yet
            started_at=started_at,
        )

        session_factory = _make_session_factory([activity])

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
        ):
            await detect_stalled_activities(session_factory)

            # Verify the activity was not claimed
            assert activity.stall_alert_at is None

            # Verify no audit event or metric
            mock_dispatch.assert_not_called()
            mock_get_recorder.return_value.record.assert_not_called()

    @pytest.mark.asyncio
    async def test_null_expected_duration_ignored(
        self,
    ) -> None:
        """Activity with NULL expected_duration should be ignored."""
        activity = _make_activity(
            status=ActivityStatus.RUNNING,
            expected_duration=None,  # NULL expected duration
            started_at=datetime.now(UTC) - timedelta(hours=2),
        )

        session_factory = _make_session_factory([activity])

        with patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch:
            await detect_stalled_activities(session_factory)
            mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_null_started_at_ignored(
        self,
    ) -> None:
        """Activity with NULL started_at should be ignored."""
        activity = _make_activity(
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=None,  # NULL started_at
        )

        session_factory = _make_session_factory([activity])

        with patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch:
            await detect_stalled_activities(session_factory)
            mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_running_activity_ignored(
        self,
    ) -> None:
        """Non-running activities should be ignored."""
        activities = [
            _make_activity(
                status=status,
                expected_duration=60,
                started_at=datetime.now(UTC) - timedelta(seconds=120),
            )
            for status in [
                ActivityStatus.PENDING,
                ActivityStatus.COMPLETED,
                ActivityStatus.FAILED,
                ActivityStatus.CANCELLED,
            ]
        ]

        session_factory = _make_session_factory(activities)

        with patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch:
            await detect_stalled_activities(session_factory)
            mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_existing_stall_alert_ignored(
        self,
    ) -> None:
        """Activity with existing stall_alert_at should be ignored (deduplication)."""
        activity = _make_activity(
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=datetime.now(UTC) - timedelta(seconds=120),
            stall_alert_at=datetime.now(UTC) - timedelta(seconds=60),  # Already marked as stalled
        )

        session_factory = _make_session_factory([activity])

        with patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch:
            await detect_stalled_activities(session_factory)
            mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_eligible_activities_processed_independently(
        self,
    ) -> None:
        """Multiple stalled activities should each be claimed and processed."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)

        # Create 3 stalled activities
        activities = [
            _make_activity(
                status=ActivityStatus.RUNNING,
                expected_duration=60,
                started_at=started_at,
            )
            for _ in range(3)
        ]

        session_factory = _make_session_factory(activities)

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_get_recorder,
        ):
            mock_recorder = MagicMock()
            mock_get_recorder.return_value = mock_recorder

            await detect_stalled_activities(session_factory)

            # Verify all 3 were claimed
            for activity in activities:
                assert activity.stall_alert_at is not None

            # Verify 3 audit events dispatched
            assert mock_dispatch.call_count == 3

            # Verify 3 metrics recorded
            assert mock_recorder.record.call_count == 3

    @pytest.mark.asyncio
    async def test_audit_failure_does_not_stop_batch(
        self,
    ) -> None:
        """Audit dispatch failure should not prevent remaining stalls from being processed."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)

        # Create 3 stalled activities
        activities = [
            _make_activity(
                status=ActivityStatus.RUNNING,
                expected_duration=60,
                started_at=started_at,
            )
            for _ in range(3)
        ]

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

            # All 3 should still have been claimed
            for activity in activities:
                assert activity.stall_alert_at is not None

            # 3 audit dispatches attempted
            assert mock_dispatch.call_count == 3

            # Only 2 metrics (first and third, second failed audit and telemetry)
            assert mock_recorder.record.call_count == 2

    @pytest.mark.asyncio
    async def test_telemetry_failure_does_not_stop_batch(
        self,
    ) -> None:
        """Telemetry recording failure should not prevent remaining stalls from being processed."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)

        # Create 2 stalled activities
        activities = [
            _make_activity(
                status=ActivityStatus.RUNNING,
                expected_duration=60,
                started_at=started_at,
            )
            for _ in range(2)
        ]

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

            # Both should still have been claimed
            for activity in activities:
                assert activity.stall_alert_at is not None

            # 2 audit events dispatched
            assert mock_dispatch.call_count == 2

            # 2 telemetry attempts (first failed, second succeeded)
            assert mock_recorder.record.call_count == 2


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
