"""Integration tests for adaptive callback and state machine wiring."""

from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.outbox.worker import AuditOutboxWorker


class TestAdaptiveCallback:
    """Test _adaptive_callback integration with state machine and interval mutation."""

    @pytest.mark.asyncio
    async def test_adaptive_callback_updates_interval_and_batch(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Adaptive callback queries backlog, calculates params, processes events, updates interval."""
        worker = AuditOutboxWorker(
            name="test-adaptive",
            interval_seconds=5.0,
            session_factory=test_session_factory,
            write_session_factory=test_session_factory,
            coordinate=False,
        )

        # Mock _get_pending_outbox_count to return a backlog
        with (
            patch.object(worker, "_get_pending_outbox_count", return_value=500),
            patch("syntara.audit.outbox.worker.publish_outbox_events") as mock_publish,
        ):
            # Initial state: base values
            assert worker._interval_seconds == 5.0
            assert worker._adaptive_sm.current_batch_size == 100

            # First cycle: 500 pending → seeds previous count, returns base values
            await worker._adaptive_callback(test_session_factory)

            # Verify publish was called with base batch size
            assert mock_publish.call_count == 1
            call_args = mock_publish.call_args
            assert call_args[0][2] == 100  # batch_size argument

            # Interval should still be base (first cycle seeds)
            assert worker._interval_seconds == 5.0
            assert worker._adaptive_sm.current_batch_size == 100

        # Second cycle: 650 pending → delta=150 → GROWING_MODERATE
        with (
            patch.object(worker, "_get_pending_outbox_count", return_value=650),
            patch("syntara.audit.outbox.worker.publish_outbox_events") as mock_publish,
        ):
            await worker._adaptive_callback(test_session_factory)

            # Should publish with new batch size (130 = 100 * 1.3)
            call_args = mock_publish.call_args
            assert call_args[0][2] == 130  # GROWING_MODERATE batch

            # Interval should speed up (3.5 = 5.0 * 0.7)
            assert worker._interval_seconds == 3.5
            assert worker._adaptive_sm.current_batch_size == 130

    @pytest.mark.asyncio
    async def test_adaptive_callback_skips_on_db_error(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """DB error (None from _get_pending_outbox_count) skips adjustment, preserves params."""
        worker = AuditOutboxWorker(
            name="test-adaptive-error",
            interval_seconds=5.0,
            session_factory=test_session_factory,
            write_session_factory=test_session_factory,
            coordinate=False,
        )

        # Seed the state machine with non-base values
        worker._interval_seconds = 2.0
        worker._adaptive_sm._current_batch_size = 300
        worker._adaptive_sm._previous_pending_count = 1000

        # Mock DB error (returns None)
        with (
            patch.object(worker, "_get_pending_outbox_count", return_value=None),
            patch("syntara.audit.outbox.worker.publish_outbox_events") as mock_publish,
        ):
            await worker._adaptive_callback(test_session_factory)

            # Should NOT call publish (early return on None)
            assert mock_publish.call_count == 0

            # Parameters should be preserved (no adjustment)
            assert worker._interval_seconds == 2.0
            assert worker._adaptive_sm.current_batch_size == 300
            assert worker._adaptive_sm._previous_pending_count == 1000

    @pytest.mark.asyncio
    async def test_adaptive_callback_empty_queue_cooldown(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Empty queue triggers exponential cooldown for interval, resets batch to base."""
        worker = AuditOutboxWorker(
            name="test-adaptive-empty",
            interval_seconds=5.0,
            session_factory=test_session_factory,
            write_session_factory=test_session_factory,
            coordinate=False,
        )

        # Seed with non-base values
        worker._interval_seconds = 2.0
        worker._adaptive_sm._current_interval = 2.0
        worker._adaptive_sm._current_batch_size = 500

        # Empty queue
        with (
            patch.object(worker, "_get_pending_outbox_count", return_value=0),
            patch("syntara.audit.outbox.worker.publish_outbox_events") as mock_publish,
        ):
            await worker._adaptive_callback(test_session_factory)

            # Should publish with base batch size
            call_args = mock_publish.call_args
            assert call_args[0][2] == 100  # Batch reset to base

            # Interval should cooldown (2.0 * 1.3 = 2.6)
            assert worker._interval_seconds == pytest.approx(2.6)
            assert worker._adaptive_sm.current_batch_size == 100

    @pytest.mark.asyncio
    async def test_adaptive_callback_shrinking_backlog(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Shrinking backlog slows down interval and decreases batch size."""
        worker = AuditOutboxWorker(
            name="test-adaptive-shrink",
            interval_seconds=5.0,
            session_factory=test_session_factory,
            write_session_factory=test_session_factory,
            coordinate=False,
        )

        # First cycle: seed with 1000 pending
        worker._adaptive_sm._previous_pending_count = 1000
        worker._adaptive_sm._current_interval = 1.0
        worker._adaptive_sm._current_batch_size = 500
        worker._interval_seconds = 1.0

        # Shrinking: 1000 → 400 (delta = -600 < 0)
        with (
            patch.object(worker, "_get_pending_outbox_count", return_value=400),
            patch("syntara.audit.outbox.worker.publish_outbox_events") as mock_publish,
        ):
            await worker._adaptive_callback(test_session_factory)

            # Should publish with decreased batch (385 = 500 * 0.77)
            call_args = mock_publish.call_args
            assert call_args[0][2] == 385  # SHRINKING batch

            # Interval should slow down (1.3 = 1.0 * 1.3)
            assert worker._interval_seconds == pytest.approx(1.3)
            assert worker._adaptive_sm.current_batch_size == 385

    @pytest.mark.asyncio
    async def test_adaptive_callback_progressive_growth(
        self, test_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Simulate progressive backlog growth across multiple cycles."""
        worker = AuditOutboxWorker(
            name="test-adaptive-progressive",
            interval_seconds=5.0,
            session_factory=test_session_factory,
            write_session_factory=test_session_factory,
            coordinate=False,
        )

        # Cycle 1: 100 pending (first cycle seeds)
        with (
            patch.object(worker, "_get_pending_outbox_count", return_value=100),
            patch("syntara.audit.outbox.worker.publish_outbox_events"),
        ):
            await worker._adaptive_callback(test_session_factory)
            interval_1 = worker._interval_seconds
            batch_1 = worker._adaptive_sm.current_batch_size

        # Cycle 2: Growing moderately (100 → 250, delta=150)
        with (
            patch.object(worker, "_get_pending_outbox_count", return_value=250),
            patch("syntara.audit.outbox.worker.publish_outbox_events"),
        ):
            await worker._adaptive_callback(test_session_factory)
            interval_2 = worker._interval_seconds
            batch_2 = worker._adaptive_sm.current_batch_size

        # Cycle 3: Growing fast (250 → 600, delta=350)
        with (
            patch.object(worker, "_get_pending_outbox_count", return_value=600),
            patch("syntara.audit.outbox.worker.publish_outbox_events"),
        ):
            await worker._adaptive_callback(test_session_factory)
            interval_3 = worker._interval_seconds
            batch_3 = worker._adaptive_sm.current_batch_size

        # Verify progressive adjustment
        assert interval_1 == 5.0  # First cycle returns base
        assert interval_2 < interval_1  # Sped up (GROWING_MODERATE)
        assert interval_3 < interval_2  # Sped up more (GROWING_FAST)

        assert batch_1 == 100  # First cycle returns base
        assert batch_2 > batch_1  # Increased (GROWING_MODERATE)
        assert batch_3 > batch_2  # Increased more (GROWING_FAST)
