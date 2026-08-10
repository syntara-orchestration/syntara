"""Unit tests for audit system lifecycle management.

Tests cover:
- Audit outbox worker initialization and startup
- Worker shutdown and event draining
- Thread-safe state transitions
- Idempotent start/stop operations
- Worker restart after shutdown
"""

import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.audit.lifecycle import (
    AuditLifecycleState,
    start_audit_outbox_worker,
    stop_audit_outbox_worker,
)

# ------------------------------------------------------------------ #
# Helper Functions
# ------------------------------------------------------------------ #


def _reset_lifecycle_state() -> None:
    """Reset module-level lifecycle state to STOPPED (for test isolation)."""
    import syntara.audit.lifecycle as lifecycle_module

    with lifecycle_module._state_lock:
        lifecycle_module._state = AuditLifecycleState.STOPPED


# ------------------------------------------------------------------ #
# Start Tests
# ------------------------------------------------------------------ #


class TestStartAuditOutboxWorker:
    """Test start_audit_outbox_worker function."""

    def setup_method(self) -> None:
        """Reset lifecycle state before each test."""
        _reset_lifecycle_state()

    def test_starts_outbox_worker(self) -> None:
        """Test that start initializes and starts the outbox worker."""
        mock_worker = MagicMock()

        with patch("syntara.audit.lifecycle.get_outbox_worker", return_value=mock_worker):
            start_audit_outbox_worker()

        mock_worker.start.assert_called_once()

    def test_sets_running_state(self) -> None:
        """Test that start transitions state to RUNNING."""
        mock_worker = MagicMock()

        with patch("syntara.audit.lifecycle.get_outbox_worker", return_value=mock_worker):
            start_audit_outbox_worker()

        import syntara.audit.lifecycle as lifecycle_module

        assert lifecycle_module._state == AuditLifecycleState.RUNNING

    def test_idempotent_when_already_running(self) -> None:
        """Test that calling start when already running is a no-op."""
        mock_worker = MagicMock()

        with patch("syntara.audit.lifecycle.get_outbox_worker", return_value=mock_worker):
            # First call starts the worker
            start_audit_outbox_worker()
            mock_worker.start.assert_called_once()

            # Second call should not start again
            start_audit_outbox_worker()
            mock_worker.start.assert_called_once()  # Still only called once

    def test_logs_already_running(self) -> None:
        """Test that calling start when running logs a debug message."""
        mock_worker = MagicMock()

        with (
            patch("syntara.audit.lifecycle.get_outbox_worker", return_value=mock_worker),
            patch("syntara.audit.lifecycle.logger") as mock_logger,
        ):
            # First call
            start_audit_outbox_worker()

            # Second call should log
            start_audit_outbox_worker()

            mock_logger.debug.assert_called_with("audit.components.already_running", state=AuditLifecycleState.RUNNING)

    def test_thread_safe_concurrent_calls(self) -> None:
        """Test that concurrent start calls are thread-safe (only one starts worker)."""
        mock_worker = MagicMock()
        barrier = threading.Barrier(2)

        def concurrent_start() -> None:
            barrier.wait()  # Synchronize threads
            start_audit_outbox_worker()

        with patch("syntara.audit.lifecycle.get_outbox_worker", return_value=mock_worker):
            thread1 = threading.Thread(target=concurrent_start)
            thread2 = threading.Thread(target=concurrent_start)

            thread1.start()
            thread2.start()

            thread1.join()
            thread2.join()

        # Worker should only be started once despite concurrent calls
        mock_worker.start.assert_called_once()


# ------------------------------------------------------------------ #
# Stop Tests
# ------------------------------------------------------------------ #


class TestStopAuditOutboxWorker:
    """Test stop_audit_outbox_worker function."""

    def setup_method(self) -> None:
        """Reset lifecycle state before each test."""
        _reset_lifecycle_state()

    @pytest.mark.asyncio
    async def test_drains_and_stops_worker(self) -> None:
        """Test that stop drains in-flight events and stops the worker."""
        mock_worker = AsyncMock()

        # Start first so we have RUNNING state
        with patch("syntara.audit.lifecycle.get_outbox_worker", return_value=mock_worker):
            start_audit_outbox_worker()

            await stop_audit_outbox_worker()

        mock_worker.drain.assert_called_once()
        mock_worker.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_sets_stopped_state(self) -> None:
        """Test that stop transitions state to STOPPED."""
        mock_worker = AsyncMock()

        with patch("syntara.audit.lifecycle.get_outbox_worker", return_value=mock_worker):
            start_audit_outbox_worker()

            await stop_audit_outbox_worker()

        import syntara.audit.lifecycle as lifecycle_module

        assert lifecycle_module._state == AuditLifecycleState.STOPPED

    @pytest.mark.asyncio
    async def test_idempotent_when_already_stopped(self) -> None:
        """Test that calling stop when already stopped is a no-op."""
        mock_worker = AsyncMock()

        with patch("syntara.audit.lifecycle.get_outbox_worker", return_value=mock_worker):
            # First call stops the worker (even though it was never started)
            await stop_audit_outbox_worker()

            # Drain and stop should not be called (worker was never running)
            mock_worker.drain.assert_not_called()
            mock_worker.stop.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_already_stopped(self) -> None:
        """Test that calling stop when stopped logs a debug message."""
        mock_worker = AsyncMock()

        with (
            patch("syntara.audit.lifecycle.get_outbox_worker", return_value=mock_worker),
            patch("syntara.audit.lifecycle.logger") as mock_logger,
        ):
            # Call stop when already stopped
            await stop_audit_outbox_worker()

            mock_logger.debug.assert_called_with("audit.components.already_stopped", state=AuditLifecycleState.STOPPED)

    @pytest.mark.asyncio
    async def test_handles_none_worker(self) -> None:
        """Test that stop handles None worker gracefully (no-op)."""
        mock_worker = MagicMock()

        with patch("syntara.audit.lifecycle.get_outbox_worker", return_value=mock_worker):
            start_audit_outbox_worker()

        # Now patch to return None for stop
        with patch("syntara.audit.lifecycle.get_outbox_worker", return_value=None):
            # Should not raise when worker is None
            await stop_audit_outbox_worker()

        # Verify state is STOPPED
        import syntara.audit.lifecycle as lifecycle_module

        assert lifecycle_module._state == AuditLifecycleState.STOPPED

    @pytest.mark.asyncio
    async def test_drain_before_stop(self) -> None:
        """Test that drain is called before stop (ensures in-flight events complete)."""
        mock_worker = AsyncMock()
        call_order = []

        async def track_drain() -> None:
            call_order.append("drain")

        async def track_stop() -> None:
            call_order.append("stop")

        mock_worker.drain = AsyncMock(side_effect=track_drain)
        mock_worker.stop = AsyncMock(side_effect=track_stop)

        with patch("syntara.audit.lifecycle.get_outbox_worker", return_value=mock_worker):
            start_audit_outbox_worker()
            await stop_audit_outbox_worker()

        assert call_order == ["drain", "stop"]


# ------------------------------------------------------------------ #
# Restart Tests
# ------------------------------------------------------------------ #


class TestRestartAuditOutboxWorker:
    """Test restarting the audit system after shutdown."""

    def setup_method(self) -> None:
        """Reset lifecycle state before each test."""
        _reset_lifecycle_state()

    @pytest.mark.asyncio
    async def test_can_restart_after_stop(self) -> None:
        """Test that worker can be restarted after being stopped."""
        mock_worker = AsyncMock()

        with patch("syntara.audit.lifecycle.get_outbox_worker", return_value=mock_worker):
            # Start -> Stop -> Start cycle
            start_audit_outbox_worker()
            assert mock_worker.start.call_count == 1

            await stop_audit_outbox_worker()
            assert mock_worker.drain.call_count == 1
            assert mock_worker.stop.call_count == 1

            # Restart should work
            start_audit_outbox_worker()
            assert mock_worker.start.call_count == 2

    @pytest.mark.asyncio
    async def test_multiple_start_stop_cycles(self) -> None:
        """Test multiple start/stop cycles work correctly."""
        mock_worker = AsyncMock()

        with patch("syntara.audit.lifecycle.get_outbox_worker", return_value=mock_worker):
            for i in range(3):
                start_audit_outbox_worker()
                assert mock_worker.start.call_count == i + 1

                await stop_audit_outbox_worker()
                assert mock_worker.drain.call_count == i + 1
                assert mock_worker.stop.call_count == i + 1

                import syntara.audit.lifecycle as lifecycle_module

                assert lifecycle_module._state == AuditLifecycleState.STOPPED


# ------------------------------------------------------------------ #
# Thread Safety Tests
# ------------------------------------------------------------------ #


class TestThreadSafety:
    """Test thread safety of lifecycle operations."""

    def setup_method(self) -> None:
        """Reset lifecycle state before each test."""
        _reset_lifecycle_state()

    def test_state_transitions_are_atomic(self) -> None:
        """Test that state transitions under lock prevent race conditions."""
        mock_worker = MagicMock()

        with patch("syntara.audit.lifecycle.get_outbox_worker", return_value=mock_worker):
            # Rapidly call start from multiple threads
            threads = [threading.Thread(target=start_audit_outbox_worker) for _ in range(10)]

            for thread in threads:
                thread.start()

            for thread in threads:
                thread.join()

        # Despite 10 concurrent calls, worker should only start once
        mock_worker.start.assert_called_once()

        import syntara.audit.lifecycle as lifecycle_module

        assert lifecycle_module._state == AuditLifecycleState.RUNNING

    @pytest.mark.asyncio
    async def test_stop_waits_for_lock(self) -> None:
        """Test that stop waits for lock even if start holds it."""
        mock_worker = AsyncMock()

        with patch("syntara.audit.lifecycle.get_outbox_worker", return_value=mock_worker):
            # Start the worker
            start_audit_outbox_worker()

            # Stop should acquire lock and complete
            await stop_audit_outbox_worker()

            import syntara.audit.lifecycle as lifecycle_module

            assert lifecycle_module._state == AuditLifecycleState.STOPPED


# ------------------------------------------------------------------ #
# Integration with Worker Tests
# ------------------------------------------------------------------ #


class TestWorkerIntegration:
    """Test integration with AuditOutboxWorker."""

    def setup_method(self) -> None:
        """Reset lifecycle state before each test."""
        _reset_lifecycle_state()

    def test_get_outbox_worker_called_on_start(self) -> None:
        """Test that get_outbox_worker is called to retrieve worker instance."""
        mock_worker = MagicMock()

        with patch("syntara.audit.lifecycle.get_outbox_worker", return_value=mock_worker) as mock_get:
            start_audit_outbox_worker()

            mock_get.assert_called_once()
            mock_worker.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_outbox_worker_called_on_stop(self) -> None:
        """Test that get_outbox_worker is called during shutdown."""
        mock_worker = AsyncMock()

        with (
            patch("syntara.audit.lifecycle.get_outbox_worker", return_value=mock_worker) as mock_get,
        ):
            start_audit_outbox_worker()
            await stop_audit_outbox_worker()

            # get_outbox_worker called twice: once for start, once for stop
            assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_stop_safe_when_worker_is_none(self) -> None:
        """Test that stop gracefully handles None worker (started with worker, stopped with None)."""
        mock_worker = MagicMock()

        with patch("syntara.audit.lifecycle.get_outbox_worker", return_value=mock_worker):
            start_audit_outbox_worker()

        # Worker becomes None during stop (edge case: worker uninitialized during shutdown)
        with patch("syntara.audit.lifecycle.get_outbox_worker", return_value=None):
            # Should not raise
            await stop_audit_outbox_worker()

        import syntara.audit.lifecycle as lifecycle_module

        # State should still transition to STOPPED
        assert lifecycle_module._state == AuditLifecycleState.STOPPED
