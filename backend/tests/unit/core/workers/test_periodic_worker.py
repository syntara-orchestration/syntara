"""Unit tests for PeriodicWorker lifecycle, error resilience, coordination, and cleanup.

Tests are written TDD-first against the PeriodicWorker contract defined in
specs/034-periodic-worker/spec.md and data-model.md.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from orchestrator_test_sdk.e2e import async_poll_for

from syntara.core.workers.periodic import PeriodicWorker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ADVISORY_LOCK_PATH = "syntara.core.workers.periodic._try_advisory_xact_lock"


def _mock_session_factory() -> MagicMock:
    """Create a mock async_sessionmaker that returns an async-context session."""
    session = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


# =============================================================================
# T003: Lifecycle tests
# =============================================================================


class TestPeriodicWorkerLifecycle:
    """Start, stop, idempotent start, restart, no-overlap."""

    @pytest.mark.asyncio
    async def test_start_creates_background_task(self) -> None:
        """start() creates an asyncio task that runs the callback."""
        call_count = 0

        async def counting_cb(_sf: object) -> None:
            nonlocal call_count
            call_count += 1

        worker = PeriodicWorker(
            name="test-start",
            interval_seconds=0.01,
            session_factory=_mock_session_factory(),
            callback=counting_cb,
            coordinate=False,
        )
        worker.start()
        await async_poll_for(lambda: call_count >= 2, description="callback to run at least twice")
        await worker.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self) -> None:
        """stop() cancels the background task and awaits completion."""
        call_count = 0

        async def counting_cb(_sf: object) -> None:
            nonlocal call_count
            call_count += 1

        worker = PeriodicWorker(
            name="test-stop",
            interval_seconds=0.01,
            session_factory=_mock_session_factory(),
            callback=counting_cb,
            coordinate=False,
        )
        worker.start()
        await async_poll_for(lambda: call_count >= 1, description="callback to run at least once")
        await worker.stop()

        count_at_stop = call_count
        await asyncio.sleep(0)
        assert call_count == count_at_stop, "Callback should not run after stop()"

    @pytest.mark.asyncio
    async def test_idempotent_start(self) -> None:
        """Calling start() multiple times creates only one task."""
        call_count = 0

        async def counting_cb(_sf: object) -> None:
            nonlocal call_count
            call_count += 1

        worker = PeriodicWorker(
            name="test-idempotent",
            interval_seconds=0.01,
            session_factory=_mock_session_factory(),
            callback=counting_cb,
            coordinate=False,
        )
        worker.start()
        worker.start()
        worker.start()
        await async_poll_for(lambda: call_count >= 2, description="callback to run at least twice")
        await worker.stop()

        assert call_count < 20, "Too many calls — multiple tasks likely created"

    @pytest.mark.asyncio
    async def test_restart_after_stop(self) -> None:
        """start() after stop() creates a new task."""
        call_count = 0

        async def counting_cb(_sf: object) -> None:
            nonlocal call_count
            call_count += 1

        worker = PeriodicWorker(
            name="test-restart",
            interval_seconds=0.01,
            session_factory=_mock_session_factory(),
            callback=counting_cb,
            coordinate=False,
        )
        worker.start()
        await async_poll_for(lambda: call_count >= 1, description="callback to run at least once")
        await worker.stop()

        count_after_first = call_count

        worker.start()
        await async_poll_for(lambda: call_count > count_after_first, description="callback to run again after restart")
        await worker.stop()

    @pytest.mark.asyncio
    async def test_no_concurrent_callback_overlap(self) -> None:
        """A slow callback blocks the next cycle (no overlap)."""
        running = 0
        max_concurrent = 0

        async def slow_cb(_sf: object) -> None:
            nonlocal running, max_concurrent
            running += 1
            max_concurrent = max(max_concurrent, running)
            await asyncio.sleep(0.03)
            running -= 1

        worker = PeriodicWorker(
            name="test-no-overlap",
            interval_seconds=0.005,
            session_factory=_mock_session_factory(),
            callback=slow_cb,
            coordinate=False,
        )
        worker.start()
        await async_poll_for(lambda: max_concurrent >= 1, timeout=2.0, description="at least one callback to complete")
        await worker.stop()

        assert max_concurrent == 1, f"Expected max 1 concurrent, got {max_concurrent}"


# =============================================================================
# T004: Error resilience + structured logging
# =============================================================================


class TestPeriodicWorkerErrorResilience:
    """Callback exceptions don't kill the loop; lifecycle events are logged."""

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_stop_loop(self) -> None:
        """An exception in the callback is caught; next cycle still runs."""
        call_count = 0

        async def failing_cb(_sf: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                msg = "deliberate test failure"
                raise RuntimeError(msg)

        worker = PeriodicWorker(
            name="test-resilience",
            interval_seconds=0.01,
            session_factory=_mock_session_factory(),
            callback=failing_cb,
            coordinate=False,
        )
        worker.start()
        await async_poll_for(lambda: call_count >= 2, description="loop to continue after error")
        await worker.stop()

    @pytest.mark.asyncio
    async def test_lifecycle_logging_contains_worker_name(self) -> None:
        """Structured log events include the worker name."""

        async def noop_cb(_sf: object) -> None:
            pass

        worker = PeriodicWorker(
            name="log-test-worker",
            interval_seconds=0.01,
            session_factory=_mock_session_factory(),
            callback=noop_cb,
            coordinate=False,
        )

        with patch("syntara.core.workers.periodic.logger") as mock_logger:
            worker.start()
            await async_poll_for(
                lambda: any("periodic_worker_started" in str(c.args) for c in mock_logger.info.call_args_list),
                description="start log event",
            )
            await worker.stop()

        # Check for start and stop log events
        info_calls = mock_logger.info.call_args_list
        start_calls = [call for call in info_calls if "periodic_worker_started" in str(call.args)]
        stop_calls = [call for call in info_calls if "periodic_worker_stopped" in str(call.args)]

        assert len(start_calls) >= 1, f"Expected at least one start log, got: {info_calls}"
        assert len(stop_calls) >= 1, f"Expected at least one stop log, got: {info_calls}"

        # Verify worker name is included in logs
        start_call = start_calls[0]
        stop_call = stop_calls[0]
        assert "log-test-worker" in str(start_call), f"Expected worker name in start log: {start_call}"
        assert "log-test-worker" in str(stop_call), f"Expected worker name in stop log: {stop_call}"

    @pytest.mark.asyncio
    async def test_callback_error_is_logged(self) -> None:
        """When callback raises, the error is logged with worker name."""

        async def failing_cb(_sf: object) -> None:
            msg = "boom"
            raise RuntimeError(msg)

        worker = PeriodicWorker(
            name="error-log-test",
            interval_seconds=0.01,
            session_factory=_mock_session_factory(),
            callback=failing_cb,
            coordinate=False,
        )

        with patch("syntara.core.workers.periodic.logger") as mock_logger:
            worker.start()
            await async_poll_for(
                lambda: any(
                    "periodic_worker_cycle_error" in str(c.args) for c in mock_logger.warning.call_args_list if c.args
                ),
                description="error warning log event",
            )
            await worker.stop()

        # Check if warning was logged with correct worker name
        warning_calls = [
            call
            for call in mock_logger.warning.call_args_list
            if len(call.args) > 0 and "periodic_worker_cycle_error" in str(call.args)
        ]
        assert len(warning_calls) >= 1, (
            f"Expected at least one warning log call, got: {mock_logger.warning.call_args_list}"
        )

        # Verify the warning call includes worker name
        warning_call = warning_calls[0]
        assert "worker_name" in str(warning_call), f"Expected worker_name in warning log: {warning_call}"
        assert "error-log-test" in str(warning_call), (
            f"Expected worker name 'error-log-test' in warning log: {warning_call}"
        )


# =============================================================================
# T005: Coordination tests (mocked advisory locks)
# =============================================================================


class TestPeriodicWorkerCoordination:
    """Advisory lock coordination: acquire/skip/disabled."""

    @pytest.mark.asyncio
    async def test_skips_cycle_when_lock_not_acquired(self) -> None:
        """When advisory lock returns False, callback is not called."""
        call_count = 0

        async def counting_cb(_sf: object) -> None:
            nonlocal call_count
            call_count += 1

        worker = PeriodicWorker(
            name="test-lock-skip",
            interval_seconds=0.01,
            session_factory=_mock_session_factory(),
            callback=counting_cb,
            coordinate=True,
        )

        with patch(ADVISORY_LOCK_PATH, return_value=False) as mock_lock:
            worker.start()
            await async_poll_for(lambda: mock_lock.call_count >= 2, description="lock to be attempted at least twice")
            await worker.stop()

        assert call_count == 0, f"Callback should not run when lock not acquired, got {call_count}"

    @pytest.mark.asyncio
    async def test_runs_callback_when_lock_acquired(self) -> None:
        """When advisory lock returns True, callback is called."""
        call_count = 0

        async def counting_cb(_sf: object) -> None:
            nonlocal call_count
            call_count += 1

        worker = PeriodicWorker(
            name="test-lock-acquired",
            interval_seconds=0.01,
            session_factory=_mock_session_factory(),
            callback=counting_cb,
            coordinate=True,
        )

        with patch(ADVISORY_LOCK_PATH, return_value=True):
            worker.start()
            await async_poll_for(lambda: call_count >= 2, description="callback to run when lock acquired")
            await worker.stop()

    @pytest.mark.asyncio
    async def test_coordinate_false_skips_lock(self) -> None:
        """coordinate=False runs callback without attempting lock."""
        call_count = 0

        async def counting_cb(_sf: object) -> None:
            nonlocal call_count
            call_count += 1

        worker = PeriodicWorker(
            name="test-no-coordinate",
            interval_seconds=0.01,
            session_factory=_mock_session_factory(),
            callback=counting_cb,
            coordinate=False,
        )

        with patch(ADVISORY_LOCK_PATH) as mock_lock:
            worker.start()
            await async_poll_for(lambda: call_count >= 2, description="callback to run without coordination")
            await worker.stop()

        mock_lock.assert_not_called()

    @pytest.mark.asyncio
    async def test_lock_acquisition_failure_skips_cycle(self) -> None:
        """If lock acquisition raises an exception, cycle is skipped gracefully."""
        call_count = 0

        async def counting_cb(_sf: object) -> None:
            nonlocal call_count
            call_count += 1

        worker = PeriodicWorker(
            name="test-lock-failure",
            interval_seconds=0.01,
            session_factory=_mock_session_factory(),
            callback=counting_cb,
            coordinate=True,
        )

        with patch(ADVISORY_LOCK_PATH, side_effect=RuntimeError("db down")) as mock_lock:
            worker.start()
            await async_poll_for(lambda: mock_lock.call_count >= 2, description="lock to be attempted at least twice")
            await worker.stop()

        assert call_count == 0, "Callback should not run when lock acquisition fails"


# =============================================================================
# T006: Cleanup callback tests
# =============================================================================


class TestPeriodicWorkerCleanup:
    """Cleanup callback on stop, including error handling."""

    @pytest.mark.asyncio
    async def test_cleanup_callback_runs_on_stop(self) -> None:
        """Optional cleanup callback is called during stop()."""
        cleanup_called = False
        cb_count = 0

        async def counting_cb(_sf: object) -> None:
            nonlocal cb_count
            cb_count += 1

        async def cleanup() -> None:
            nonlocal cleanup_called
            cleanup_called = True

        worker = PeriodicWorker(
            name="test-cleanup",
            interval_seconds=0.01,
            session_factory=_mock_session_factory(),
            callback=counting_cb,
            cleanup_callback=cleanup,
            coordinate=False,
        )
        worker.start()
        await async_poll_for(lambda: cb_count >= 1, description="worker to run at least once")
        await worker.stop()

        assert cleanup_called, "Cleanup callback should be called on stop()"

    @pytest.mark.asyncio
    async def test_cleanup_error_does_not_prevent_shutdown(self) -> None:
        """Cleanup callback error is logged but stop() completes."""
        cb_count = 0

        async def counting_cb(_sf: object) -> None:
            nonlocal cb_count
            cb_count += 1

        async def failing_cleanup() -> None:
            msg = "cleanup explosion"
            raise RuntimeError(msg)

        worker = PeriodicWorker(
            name="test-cleanup-error",
            interval_seconds=0.01,
            session_factory=_mock_session_factory(),
            callback=counting_cb,
            cleanup_callback=failing_cleanup,
            coordinate=False,
        )
        worker.start()
        await async_poll_for(lambda: cb_count >= 1, description="worker to run at least once")

        # Should not raise
        await worker.stop()

    @pytest.mark.asyncio
    async def test_no_cleanup_callback_is_fine(self) -> None:
        """Worker without cleanup_callback stops cleanly."""
        cb_count = 0

        async def counting_cb(_sf: object) -> None:
            nonlocal cb_count
            cb_count += 1

        worker = PeriodicWorker(
            name="test-no-cleanup",
            interval_seconds=0.01,
            session_factory=_mock_session_factory(),
            callback=counting_cb,
            coordinate=False,
        )
        worker.start()
        await async_poll_for(lambda: cb_count >= 1, description="worker to run at least once")
        await worker.stop()

    @pytest.mark.asyncio
    async def test_stop_without_start_is_noop(self) -> None:
        """Calling stop() without start() should not raise."""

        async def noop_cb(_sf: object) -> None:
            pass

        worker = PeriodicWorker(
            name="test-stop-noop",
            interval_seconds=1.0,
            session_factory=_mock_session_factory(),
            callback=noop_cb,
            coordinate=False,
        )
        await worker.stop()  # Should not raise
