"""Unit tests for the schedule reconciliation worker.

Tests the diff-based reconciliation callback that creates missing
Temporal Schedules and deletes orphans.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.workflows.workers.schedule_reconciliation import (
    _extract_expected_schedules,
    reconcile_scheduled_triggers,
)

_PATCH_SVC = "syntara.workflows.workers.schedule_reconciliation.ScheduledTriggerService"


def _make_triggers(
    scheduled_triggers: list[dict[str, Any]] | None = None,
    other_triggers: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build a triggers array with optional scheduled triggers."""
    triggers: list[dict[str, Any]] = []
    for t in scheduled_triggers or []:
        triggers.append(
            {
                "id": t["id"],
                "type": "scheduled_trigger",
                "parameters": t.get("parameters", {"interval": "1h"}),
            }
        )
    triggers.extend(other_triggers or [])
    return triggers


def _session_ctx(rows: list[tuple[str, list[dict[str, Any]]]]) -> MagicMock:
    """Async session context manager that returns the given query rows."""
    mock_result = MagicMock()
    mock_result.all.return_value = rows

    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(return_value=mock_result)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _make_session_factory(rows: list[tuple[str, list[dict[str, Any]]]]) -> MagicMock:
    """Create a mock session factory that returns the given (workflow_id, triggers) rows.

    ``async_sessionmaker()`` is a *sync* call that returns an async context
    manager, so we use ``MagicMock`` (not ``AsyncMock``) for the factory
    and attach ``__aenter__``/``__aexit__`` to its return value.
    """
    return MagicMock(return_value=_session_ctx(rows))


class TestExtractExpectedSchedules:
    """Tests for the _extract_expected_schedules helper."""

    def test_empty_rows(self) -> None:
        lookup = _extract_expected_schedules([])
        assert lookup == {}

    def test_extracts_scheduled_triggers(self) -> None:
        wf_id = str(uuid4())
        triggers = _make_triggers(scheduled_triggers=[{"id": "t1"}, {"id": "t2"}])
        lookup = _extract_expected_schedules([(wf_id, triggers)])

        assert len(lookup) == 2
        assert f"orchestrator-sched-{wf_id}-t1" in lookup
        assert f"orchestrator-sched-{wf_id}-t2" in lookup

    def test_ignores_non_scheduled_triggers(self) -> None:
        wf_id = str(uuid4())
        triggers = [{"id": "m1", "type": "manual_trigger", "parameters": {}}]
        lookup = _extract_expected_schedules([(wf_id, triggers)])
        assert lookup == {}

    def test_skips_triggers_without_id(self) -> None:
        wf_id = str(uuid4())
        triggers = [{"type": "scheduled_trigger", "parameters": {"interval": "1h"}}]
        lookup = _extract_expected_schedules([(wf_id, triggers)])
        assert lookup == {}


class TestReconcileScheduledTriggers:
    """Tests for the reconcile_scheduled_triggers callback."""

    @pytest.mark.asyncio
    async def test_steady_state_no_mutations(self) -> None:
        """When expected == actual, no creates or deletes happen."""
        wf_id = str(uuid4())
        triggers = _make_triggers(scheduled_triggers=[{"id": "t1"}])
        session_factory = _make_session_factory([(wf_id, triggers)])

        expected_schedule_id = f"orchestrator-sched-{wf_id}-t1"

        with patch(_PATCH_SVC) as mock_svc_cls:
            mock_svc = mock_svc_cls.return_value
            mock_svc.get_client = AsyncMock(return_value=MagicMock())
            mock_svc.list_all_schedules = AsyncMock(return_value={expected_schedule_id})
            mock_svc.create_schedule = AsyncMock()
            mock_svc_cls.delete_schedule = AsyncMock()

            await reconcile_scheduled_triggers(session_factory)

            mock_svc.create_schedule.assert_not_called()
            mock_svc_cls.delete_schedule.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_missing_schedules(self) -> None:
        """Missing schedules (expected - actual) should be created."""
        wf_id = str(uuid4())
        triggers = _make_triggers(scheduled_triggers=[{"id": "t1"}, {"id": "t2"}])
        session_factory = _make_session_factory([(wf_id, triggers)])

        with patch(_PATCH_SVC) as mock_svc_cls:
            mock_svc = mock_svc_cls.return_value
            mock_svc.get_client = AsyncMock(return_value=MagicMock())
            mock_svc.list_all_schedules = AsyncMock(return_value=set())
            mock_svc.create_schedule = AsyncMock(return_value="id")
            mock_svc_cls.delete_schedule = AsyncMock()

            await reconcile_scheduled_triggers(session_factory)

            assert mock_svc.create_schedule.call_count == 2

    @pytest.mark.asyncio
    async def test_deletes_orphan_schedules(self) -> None:
        """Orphan schedules (actual - expected) should be deleted."""
        session_factory = _make_session_factory([])
        orphan_id = "orchestrator-sched-dead-workflow-trigger_1"

        with patch(_PATCH_SVC) as mock_svc_cls:
            mock_client = MagicMock()
            mock_svc = mock_svc_cls.return_value
            mock_svc.get_client = AsyncMock(return_value=mock_client)
            mock_svc.list_all_schedules = AsyncMock(return_value={orphan_id})
            mock_svc_cls.delete_schedule = AsyncMock(return_value=True)

            await reconcile_scheduled_triggers(session_factory)

            mock_svc_cls.delete_schedule.assert_called_once_with(mock_client, orphan_id)

    @pytest.mark.asyncio
    async def test_mixed_creates_and_deletes(self) -> None:
        """Should create missing and delete orphans in the same cycle."""
        wf_id = str(uuid4())
        triggers = _make_triggers(scheduled_triggers=[{"id": "t1"}])
        session_factory = _make_session_factory([(wf_id, triggers)])

        expected_id = f"orchestrator-sched-{wf_id}-t1"
        stale_id = f"orchestrator-sched-{wf_id}-old_trigger"
        orphan_id = "orchestrator-sched-dead-wf-orphan"

        with patch(_PATCH_SVC) as mock_svc_cls:
            mock_client = MagicMock()
            mock_svc = mock_svc_cls.return_value
            mock_svc.get_client = AsyncMock(return_value=mock_client)
            mock_svc.list_all_schedules = AsyncMock(return_value={stale_id, orphan_id})
            mock_svc.create_schedule = AsyncMock(return_value=expected_id)
            mock_svc_cls.delete_schedule = AsyncMock(return_value=True)

            await reconcile_scheduled_triggers(session_factory)

            mock_svc.create_schedule.assert_called_once()
            call_args = mock_svc.create_schedule.call_args
            assert call_args[0][0] == wf_id
            assert call_args[0][1] == "t1"

            delete_calls = mock_svc_cls.delete_schedule.call_args_list
            deleted_ids = {call[0][1] for call in delete_calls}
            assert stale_id in deleted_ids
            assert orphan_id in deleted_ids

    @pytest.mark.asyncio
    async def test_temporal_unavailable_skips_gracefully(self) -> None:
        """When Temporal is unavailable, should log and return without error."""
        wf_id = str(uuid4())
        triggers = _make_triggers(scheduled_triggers=[{"id": "t1"}])
        session_factory = _make_session_factory([(wf_id, triggers)])

        with patch(_PATCH_SVC) as mock_svc_cls:
            mock_svc = mock_svc_cls.return_value
            mock_svc.get_client = AsyncMock(return_value=None)

            await reconcile_scheduled_triggers(session_factory)

            mock_svc.get_client.assert_called_once()

    @pytest.mark.asyncio
    async def test_client_timeout_skips_without_waiting_on_hang(self) -> None:
        """A hung Temporal client must not stall the reconciliation cycle."""
        wf_id = str(uuid4())
        triggers = _make_triggers(scheduled_triggers=[{"id": "t1"}])
        session_factory = _make_session_factory([(wf_id, triggers)])

        async def _hang() -> MagicMock:
            await asyncio.Event().wait()
            return MagicMock()

        with (
            patch(_PATCH_SVC) as mock_svc_cls,
            patch(
                "syntara.workflows.workers.schedule_reconciliation._RECONCILE_TEMPORAL_TIMEOUT_SECONDS",
                0.05,
            ),
        ):
            mock_svc = mock_svc_cls.return_value
            mock_svc.get_client = _hang
            mock_svc.list_all_schedules = AsyncMock()

            await reconcile_scheduled_triggers(session_factory)

            mock_svc.list_all_schedules.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_timeout_skips_without_waiting_on_hang(self) -> None:
        """A hung schedule list must not stall the reconciliation cycle."""
        wf_id = str(uuid4())
        triggers = _make_triggers(scheduled_triggers=[{"id": "t1"}])
        session_factory = _make_session_factory([(wf_id, triggers)])

        async def _hang_list(_client: MagicMock) -> set[str]:
            await asyncio.Event().wait()
            return set()

        with (
            patch(_PATCH_SVC) as mock_svc_cls,
            patch(
                "syntara.workflows.workers.schedule_reconciliation._RECONCILE_TEMPORAL_TIMEOUT_SECONDS",
                0.05,
            ),
        ):
            mock_svc = mock_svc_cls.return_value
            mock_svc.get_client = AsyncMock(return_value=MagicMock())
            mock_svc.list_all_schedules = _hang_list
            mock_svc.create_schedule = AsyncMock()
            mock_svc_cls.delete_schedule = AsyncMock()

            await asyncio.wait_for(reconcile_scheduled_triggers(session_factory), timeout=1.0)

            mock_svc.create_schedule.assert_not_called()
            mock_svc_cls.delete_schedule.assert_not_called()

    @pytest.mark.asyncio
    async def test_mutate_timeout_skips_without_waiting_on_hang(self) -> None:
        """A hung create/delete gather must not stall the reconciliation cycle."""
        session_factory = _make_session_factory([])
        orphan_id = "orchestrator-sched-dead-workflow-trigger_1"

        async def _hang_delete(_client: MagicMock, _schedule_id: str) -> bool:
            await asyncio.Event().wait()
            return True

        with (
            patch(_PATCH_SVC) as mock_svc_cls,
            patch(
                "syntara.workflows.workers.schedule_reconciliation._RECONCILE_TEMPORAL_TIMEOUT_SECONDS",
                0.05,
            ),
        ):
            mock_client = MagicMock()
            mock_svc = mock_svc_cls.return_value
            mock_svc.get_client = AsyncMock(return_value=mock_client)
            mock_svc.list_all_schedules = AsyncMock(return_value={orphan_id})
            mock_svc_cls.delete_schedule = _hang_delete

            await asyncio.wait_for(reconcile_scheduled_triggers(session_factory), timeout=1.0)

    @pytest.mark.asyncio
    async def test_does_not_delete_schedule_republished_during_list(self) -> None:
        """Expected IDs are loaded after list so a republish during connect/list is kept."""
        wf_id = str(uuid4())
        triggers = _make_triggers(scheduled_triggers=[{"id": "t1"}])
        expected_id = f"orchestrator-sched-{wf_id}-t1"
        order: list[str] = []

        async def _list(_client: MagicMock) -> set[str]:
            order.append("list")
            return {expected_id}

        def _factory() -> MagicMock:
            order.append("db")
            return _session_ctx([(wf_id, triggers)])

        session_factory = MagicMock(side_effect=_factory)

        with patch(_PATCH_SVC) as mock_svc_cls:
            mock_client = MagicMock()
            mock_svc = mock_svc_cls.return_value
            mock_svc.get_client = AsyncMock(return_value=mock_client)
            mock_svc.list_all_schedules = _list
            mock_svc.create_schedule = AsyncMock()
            mock_svc_cls.delete_schedule = AsyncMock()

            await reconcile_scheduled_triggers(session_factory)

            assert order == ["list", "db"]
            mock_svc_cls.delete_schedule.assert_not_called()
            mock_svc.create_schedule.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_published_workflows_checks_orphans_only(self) -> None:
        """With no published workflows, should still clean up orphans."""
        session_factory = _make_session_factory([])
        orphan_id = "orchestrator-sched-old-wf-old-trigger"

        with patch(_PATCH_SVC) as mock_svc_cls:
            mock_client = MagicMock()
            mock_svc = mock_svc_cls.return_value
            mock_svc.get_client = AsyncMock(return_value=mock_client)
            mock_svc.list_all_schedules = AsyncMock(return_value={orphan_id})
            mock_svc_cls.delete_schedule = AsyncMock(return_value=True)

            await reconcile_scheduled_triggers(session_factory)

            mock_svc_cls.delete_schedule.assert_called_once_with(mock_client, orphan_id)

    @pytest.mark.asyncio
    async def test_create_error_does_not_block_others(self) -> None:
        """A failure creating one schedule should not prevent others from being created."""
        wf_id = str(uuid4())
        triggers = _make_triggers(scheduled_triggers=[{"id": "t1"}, {"id": "t2"}])
        session_factory = _make_session_factory([(wf_id, triggers)])

        call_count = 0

        async def _create_side_effect(*args: str, **kwargs: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                msg = "Temporal error"
                raise RuntimeError(msg)
            return "created"

        with patch(_PATCH_SVC) as mock_svc_cls:
            mock_svc = mock_svc_cls.return_value
            mock_svc.get_client = AsyncMock(return_value=MagicMock())
            mock_svc.list_all_schedules = AsyncMock(return_value=set())
            mock_svc.create_schedule = AsyncMock(side_effect=_create_side_effect)
            mock_svc_cls.delete_schedule = AsyncMock()

            await reconcile_scheduled_triggers(session_factory)

            assert mock_svc.create_schedule.call_count == 2

    @pytest.mark.asyncio
    async def test_delete_error_does_not_block_others(self) -> None:
        """A failure deleting one schedule should not prevent others from being deleted."""
        session_factory = _make_session_factory([])
        orphan_a = "orchestrator-sched-dead-wf-a"
        orphan_b = "orchestrator-sched-dead-wf-b"

        call_count = 0

        async def _delete_side_effect(_client: MagicMock, _schedule_id: str) -> bool:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                msg = "Temporal error"
                raise RuntimeError(msg)
            return True

        with patch(_PATCH_SVC) as mock_svc_cls:
            mock_client = MagicMock()
            mock_svc = mock_svc_cls.return_value
            mock_svc.get_client = AsyncMock(return_value=mock_client)
            mock_svc.list_all_schedules = AsyncMock(return_value={orphan_a, orphan_b})
            mock_svc_cls.delete_schedule = AsyncMock(side_effect=_delete_side_effect)

            await reconcile_scheduled_triggers(session_factory)

            assert mock_svc_cls.delete_schedule.call_count == 2

    @pytest.mark.asyncio
    async def test_none_session_factory_returns_early(self) -> None:
        """Should return immediately if session_factory is None."""
        await reconcile_scheduled_triggers(None)


class TestGetScheduleReconciliationWorker:
    """Tests for the get_schedule_reconciliation_worker factory."""

    def test_creates_worker_with_correct_config(self) -> None:
        """Should create a PeriodicWorker with the expected name, interval, and coordinate flag."""
        from syntara.workflows.workers.schedule_reconciliation import (
            get_schedule_reconciliation_worker,
        )

        # Clear the lru_cache to ensure a fresh call
        get_schedule_reconciliation_worker.cache_clear()

        worker = get_schedule_reconciliation_worker()

        assert worker._name == "schedule-reconciliation"
        assert worker._interval_seconds == 60.0
        assert worker._coordinate is True
        assert worker._callback is reconcile_scheduled_triggers

        # Clean up cache for other tests
        get_schedule_reconciliation_worker.cache_clear()
