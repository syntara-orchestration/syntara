"""Unit tests for _maybe_update_execution_paused_status.

Tests RUNNING↔PAUSED transitions based on activity states.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.workflow_engine.services.activity_sync_service import ActivitySyncService


def _make_activity(status: ActivityStatus, started_at: datetime | None = None) -> Mock:
    a = Mock(spec=ActivityExecution)
    a.status = status
    a.started_at = started_at if started_at is not None else datetime.now(UTC)
    return a


def _make_execution(status: ExecutionStatus) -> Mock:
    e = Mock(spec=Execution)
    e.id = "test-exec-id"
    e.status = status
    e.updated_at = None
    return e


def _make_service() -> ActivitySyncService:
    service = ActivitySyncService(
        temporal_client=Mock(),
        session_factory=Mock(),
    )
    service.activity_publisher = AsyncMock()
    return service


class TestRunningToPaused:
    """RUNNING → PAUSED when all scheduled activities are WAITING."""

    @pytest.mark.asyncio
    async def test_all_waiting_transitions_to_paused(self) -> None:
        execution = _make_execution(ExecutionStatus.RUNNING)
        activities = [_make_activity(ActivityStatus.WAITING), _make_activity(ActivityStatus.WAITING)]
        service = _make_service()

        result = await service._maybe_update_execution_paused_status(execution, activities)

        assert execution.status == ExecutionStatus.PAUSED
        assert result == ExecutionStatus.PAUSED

    @pytest.mark.asyncio
    async def test_running_activity_prevents_pause(self) -> None:
        execution = _make_execution(ExecutionStatus.RUNNING)
        activities = [_make_activity(ActivityStatus.RUNNING), _make_activity(ActivityStatus.WAITING)]
        service = _make_service()

        result = await service._maybe_update_execution_paused_status(execution, activities)

        assert execution.status == ExecutionStatus.RUNNING
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_started_pending_does_not_prevent_pause(self) -> None:
        """A started PENDING activity is transitional — does not block PAUSED."""
        execution = _make_execution(ExecutionStatus.RUNNING)
        activities = [_make_activity(ActivityStatus.PENDING), _make_activity(ActivityStatus.WAITING)]
        service = _make_service()

        result = await service._maybe_update_execution_paused_status(execution, activities)

        assert execution.status == ExecutionStatus.PAUSED
        assert result == ExecutionStatus.PAUSED

    @pytest.mark.asyncio
    async def test_retrying_activity_prevents_pause(self) -> None:
        """RETRYING is active — must not transition to PAUSED."""
        execution = _make_execution(ExecutionStatus.RUNNING)
        activities = [_make_activity(ActivityStatus.RETRYING), _make_activity(ActivityStatus.WAITING)]
        service = _make_service()

        result = await service._maybe_update_execution_paused_status(execution, activities)

        assert execution.status == ExecutionStatus.RUNNING
        assert result is None


class TestPausedToRunning:
    """PAUSED → RUNNING when active activities appear or no WAITING remain."""

    @pytest.mark.asyncio
    async def test_active_activity_resumes(self) -> None:
        execution = _make_execution(ExecutionStatus.PAUSED)
        activities = [_make_activity(ActivityStatus.RUNNING), _make_activity(ActivityStatus.WAITING)]
        service = _make_service()

        result = await service._maybe_update_execution_paused_status(execution, activities)

        assert execution.status == ExecutionStatus.RUNNING
        assert result == ExecutionStatus.RUNNING

    @pytest.mark.asyncio
    async def test_retrying_activity_resumes(self) -> None:
        """RETRYING should also resume from PAUSED."""
        execution = _make_execution(ExecutionStatus.PAUSED)
        activities = [_make_activity(ActivityStatus.RETRYING), _make_activity(ActivityStatus.WAITING)]
        service = _make_service()

        result = await service._maybe_update_execution_paused_status(execution, activities)

        assert execution.status == ExecutionStatus.RUNNING
        assert result == ExecutionStatus.RUNNING

    @pytest.mark.asyncio
    async def test_no_waiting_resumes(self) -> None:
        """PAUSED with only RUNNING (no WAITING) should resume."""
        execution = _make_execution(ExecutionStatus.PAUSED)
        activities = [_make_activity(ActivityStatus.RUNNING)]
        service = _make_service()

        result = await service._maybe_update_execution_paused_status(execution, activities)

        assert execution.status == ExecutionStatus.RUNNING
        assert result == ExecutionStatus.RUNNING


class TestNoTransition:
    """Cases where no status change should occur."""

    @pytest.mark.asyncio
    async def test_terminal_execution_ignored(self) -> None:
        execution = _make_execution(ExecutionStatus.COMPLETED)
        activities = [_make_activity(ActivityStatus.WAITING)]
        service = _make_service()

        result = await service._maybe_update_execution_paused_status(execution, activities)

        assert execution.status == ExecutionStatus.COMPLETED
        assert result is None

    @pytest.mark.asyncio
    async def test_all_terminal_activities_no_transition(self) -> None:
        execution = _make_execution(ExecutionStatus.RUNNING)
        activities = [_make_activity(ActivityStatus.COMPLETED), _make_activity(ActivityStatus.FAILED)]
        service = _make_service()

        result = await service._maybe_update_execution_paused_status(execution, activities)

        assert execution.status == ExecutionStatus.RUNNING
        assert result is None

    @pytest.mark.asyncio
    async def test_pending_placeholder_excluded(self) -> None:
        """PENDING activities are pre-created placeholders, excluded from consideration."""
        execution = _make_execution(ExecutionStatus.RUNNING)
        activities = [_make_activity(ActivityStatus.PENDING)]
        service = _make_service()

        result = await service._maybe_update_execution_paused_status(execution, activities)

        assert execution.status == ExecutionStatus.RUNNING
        assert result is None

    @pytest.mark.asyncio
    async def test_already_paused_all_waiting_no_change(self) -> None:
        """Already PAUSED + all WAITING = no transition needed."""
        execution = _make_execution(ExecutionStatus.PAUSED)
        activities = [_make_activity(ActivityStatus.WAITING)]
        service = _make_service()

        result = await service._maybe_update_execution_paused_status(execution, activities)

        assert execution.status == ExecutionStatus.PAUSED
        assert result is None
