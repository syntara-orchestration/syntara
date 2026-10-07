"""Integration tests for stall detection periodic worker.

Validates scanner query execution, timestamp writes, deduplication,
and concurrency behavior against real PostgreSQL.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.workers.stall_detection import detect_stalled_activities
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User


async def _seed_activity(
    session: AsyncSession,
    user: User,
    *,
    status: ActivityStatus = ActivityStatus.RUNNING,
    expected_duration: int | None = 60,
    started_at: datetime | None = None,
    stall_alert_at: datetime | None = None,
) -> ActivityExecution:
    """Create a test activity execution in the database."""
    # Create parent execution
    execution = Execution(
        id=uuid4(),
        workflow_id=uuid4(),
        workflow_name="test-workflow",
        trigger_type="manual_trigger",
        trigger_id="trigger_1",
        status=ExecutionStatus.RUNNING,
        actor_id=user.id,
    )
    session.add(execution)
    await session.flush()

    # Create activity
    activity = ActivityExecution(
        id=uuid4(),
        execution_id=execution.id,
        activity_name="test_activity",
        node_type=NodeType.HTTP_REQUEST,
        temporal_activity_id=f"act-{uuid4()}",
        status=status,
        expected_duration=expected_duration,
        started_at=started_at,
        stall_alert_at=stall_alert_at,
    )
    session.add(activity)
    await session.commit()
    await session.refresh(activity)
    return activity


@pytest.mark.asyncio
class TestStallDetectionScanner:
    """Integration tests for the stall detection database scanner."""

    async def test_overdue_running_activity_is_claimed(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ) -> None:
        """Scanner selects and claims overdue running activity against real PostgreSQL."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)

        activity = await _seed_activity(
            test_db_session,
            test_user,
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=started_at,
            stall_alert_at=None,
        )

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch"),
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_recorder,
        ):
            mock_recorder.return_value = MagicMock()
            await detect_stalled_activities(test_db_session_factory)

        # Verify claim in database
        # Note: updated_at is NOT set for internal stall bookkeeping
        await test_db_session.refresh(activity)
        assert activity.stall_alert_at is not None
        assert activity.stall_alert_at >= now

    async def test_activity_below_threshold_ignored(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ) -> None:
        """Scanner ignores activities that haven't exceeded expected duration."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=30)  # Started 30s ago

        activity = await _seed_activity(
            test_db_session,
            test_user,
            status=ActivityStatus.RUNNING,
            expected_duration=120,  # Expects 120s, not stalled yet
            started_at=started_at,
            stall_alert_at=None,
        )

        with patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch:
            await detect_stalled_activities(test_db_session_factory)

        # Verify not claimed
        await test_db_session.refresh(activity)
        assert activity.stall_alert_at is None
        mock_dispatch.assert_not_called()

    async def test_null_expected_duration_ignored(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ) -> None:
        """Scanner SQL WHERE clause filters out NULL expected_duration."""
        activity = await _seed_activity(
            test_db_session,
            test_user,
            status=ActivityStatus.RUNNING,
            expected_duration=None,  # NULL
            started_at=datetime.now(UTC) - timedelta(hours=2),
            stall_alert_at=None,
        )

        with patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch:
            await detect_stalled_activities(test_db_session_factory)

        await test_db_session.refresh(activity)
        assert activity.stall_alert_at is None
        mock_dispatch.assert_not_called()

    async def test_null_started_at_ignored(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ) -> None:
        """Scanner SQL WHERE clause filters out NULL started_at."""
        activity = await _seed_activity(
            test_db_session,
            test_user,
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=None,  # NULL
            stall_alert_at=None,
        )

        with patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch:
            await detect_stalled_activities(test_db_session_factory)

        await test_db_session.refresh(activity)
        assert activity.stall_alert_at is None
        mock_dispatch.assert_not_called()

    async def test_non_running_activity_ignored(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ) -> None:
        """Scanner SQL WHERE clause filters by status = RUNNING."""
        for status in [ActivityStatus.PENDING, ActivityStatus.COMPLETED, ActivityStatus.FAILED]:
            await _seed_activity(
                test_db_session,
                test_user,
                status=status,
                expected_duration=60,
                started_at=datetime.now(UTC) - timedelta(seconds=120),
                stall_alert_at=None,
            )

        with patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch:
            await detect_stalled_activities(test_db_session_factory)
            mock_dispatch.assert_not_called()

    async def test_existing_stall_alert_ignored(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ) -> None:
        """Scanner SQL WHERE clause filters out existing stall_alert_at (deduplication)."""
        now = datetime.now(UTC)
        activity = await _seed_activity(
            test_db_session,
            test_user,
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=now - timedelta(seconds=120),
            stall_alert_at=now - timedelta(seconds=60),  # Already marked
        )

        with patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch:
            await detect_stalled_activities(test_db_session_factory)

        # stall_alert_at should remain unchanged (permanent marker)
        await test_db_session.refresh(activity)
        assert activity.stall_alert_at == now - timedelta(seconds=60)
        mock_dispatch.assert_not_called()

    async def test_duplicate_scan_does_not_re_claim(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ) -> None:
        """Running the scanner twice claims an activity only once."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)

        activity = await _seed_activity(
            test_db_session,
            test_user,
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=started_at,
            stall_alert_at=None,
        )

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_recorder,
        ):
            mock_recorder.return_value = MagicMock()

            # First scan claims it
            await detect_stalled_activities(test_db_session_factory)
            await test_db_session.refresh(activity)
            first_stall_alert_at = activity.stall_alert_at
            assert first_stall_alert_at is not None
            assert mock_dispatch.call_count == 1

            # Second scan sees existing stall_alert_at and does NOT claim again
            await detect_stalled_activities(test_db_session_factory)
            await test_db_session.refresh(activity)
            assert activity.stall_alert_at == first_stall_alert_at  # Unchanged
            assert mock_dispatch.call_count == 1  # Still only 1

    async def test_stall_alert_at_is_permanent(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ) -> None:
        """stall_alert_at is never cleared, even if activity later completes.

        This is Bill's approved permanent-marker decision. AAP-92824 Jira text
        references resettable stall state, which conflicts — the Jira ticket
        should be synced with this design decision.
        """
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)

        activity = await _seed_activity(
            test_db_session,
            test_user,
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=started_at,
            stall_alert_at=None,
        )

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch"),
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_recorder,
        ):
            mock_recorder.return_value = MagicMock()
            await detect_stalled_activities(test_db_session_factory)

        await test_db_session.refresh(activity)
        stall_alert_at = activity.stall_alert_at
        assert stall_alert_at is not None

        # Simulate activity completing
        activity.status = ActivityStatus.COMPLETED
        activity.completed_at = datetime.now(UTC)
        test_db_session.add(activity)
        await test_db_session.commit()

        # stall_alert_at remains permanent
        await test_db_session.refresh(activity)
        assert activity.stall_alert_at == stall_alert_at

    async def test_multiple_overdue_activities_all_claimed(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ) -> None:
        """Scanner claims all eligible activities in a single batch."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)

        activities = []
        for _ in range(3):
            activity = await _seed_activity(
                test_db_session,
                test_user,
                status=ActivityStatus.RUNNING,
                expected_duration=60,
                started_at=started_at,
                stall_alert_at=None,
            )
            activities.append(activity)

        with (
            patch("syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch") as mock_dispatch,
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_recorder,
        ):
            mock_recorder.return_value = MagicMock()
            await detect_stalled_activities(test_db_session_factory)

        # All 3 claimed
        for activity in activities:
            await test_db_session.refresh(activity)
            assert activity.stall_alert_at is not None

        # 3 audit events and 3 metrics
        assert mock_dispatch.call_count == 3
        assert mock_recorder.return_value.record.call_count == 3

    async def test_update_returning_yields_mapped_orm_instances(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ) -> None:
        """UPDATE...RETURNING returns mapped ActivityExecution instances with accessible attributes."""
        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)

        # Seed an overdue activity
        activity = await _seed_activity(
            test_db_session,
            test_user,
            status=ActivityStatus.RUNNING,
            expected_duration=60,
            started_at=started_at,
            stall_alert_at=None,
        )

        # Track what audit dispatch receives
        received_event = None

        def capture_event(event: object) -> None:
            nonlocal received_event
            received_event = event

        with (
            patch(
                "syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch",
                side_effect=capture_event,
            ),
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_recorder,
        ):
            mock_recorder.return_value = MagicMock()
            await detect_stalled_activities(test_db_session_factory)

        # Verify audit event received a properly mapped object with all expected fields
        assert received_event is not None
        from syntara.workflows.audit.node_stalled import NodeStalledEvent

        assert isinstance(received_event, NodeStalledEvent)
        assert received_event.activity_execution_id == activity.id
        assert received_event.execution_id == activity.execution_id
        assert received_event.activity_name == "test_activity"
        assert received_event.node_type == NodeType.HTTP_REQUEST
        assert received_event.expected_duration == 60
        assert received_event.started_at == started_at
        assert received_event.stall_alert_at is not None

        # Verify database was updated
        await test_db_session.refresh(activity)
        assert activity.stall_alert_at is not None
        assert activity.stall_alert_at == received_event.stall_alert_at

    async def test_concurrent_scans_claim_each_row_once(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
    ) -> None:
        """Two concurrent scanner invocations claim each row exactly once."""
        import asyncio

        now = datetime.now(UTC)
        started_at = now - timedelta(seconds=120)

        # Seed multiple overdue activities
        activities = []
        for _ in range(5):
            activity = await _seed_activity(
                test_db_session,
                test_user,
                status=ActivityStatus.RUNNING,
                expected_duration=60,
                started_at=started_at,
                stall_alert_at=None,
            )
            activities.append(activity)

        audit_call_count = 0

        def count_dispatch(*_args: object, **_kwargs: object) -> None:
            nonlocal audit_call_count
            audit_call_count += 1

        with (
            patch(
                "syntara.workflows.workers.stall_detection.AuditEventDispatcher.dispatch",
                side_effect=count_dispatch,
            ),
            patch("syntara.workflows.workers.stall_detection.get_metrics_recorder") as mock_recorder,
        ):
            mock_recorder.return_value = MagicMock()

            # Run two scans concurrently
            await asyncio.gather(
                detect_stalled_activities(test_db_session_factory),
                detect_stalled_activities(test_db_session_factory),
            )

        # Verify all activities were claimed, but each exactly once (5 total, not 10)
        for activity in activities:
            await test_db_session.refresh(activity)
            assert activity.stall_alert_at is not None

        # Should have exactly 5 audit dispatches, not 10
        assert audit_call_count == 5
