"""Unit tests for the periodic metrics cleanup worker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from orchestrator_test_sdk.e2e import async_poll_for
from prometheus_client import CollectorRegistry

from syntara.metrics.cleanup import cleanup_stale_metrics, get_metrics_cleanup_worker
from syntara.metrics.recorder import MetricsRecorder
from syntara.metrics.types import MetricType

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager


def _mock_session_factory() -> MagicMock:
    """Create a mock async_sessionmaker."""
    session = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


# =============================================================================
# cleanup_stale_metrics callback
# =============================================================================


class TestCleanupStaleMetrics:
    """Tests for the cleanup_stale_metrics callback function."""

    @pytest.mark.asyncio
    async def test_removes_expired_records(self) -> None:
        """Expired records are evicted from the store."""
        recorder = MetricsRecorder(
            retention_seconds=60,
            prometheus_registry=CollectorRegistry(),
        )
        recorder.record(MetricType.LLM_DURATION, 100.0, unit="ms")

        record = next(iter(recorder.query()))
        record.created_at = datetime.now(UTC) - timedelta(hours=1)

        with patch("syntara.metrics.cleanup.get_metrics_recorder", return_value=recorder):
            await cleanup_stale_metrics(_mock_session_factory())

        assert recorder.store.count() == 0

    @pytest.mark.asyncio
    async def test_keeps_fresh_records(self) -> None:
        """Records within the retention window are preserved."""
        recorder = MetricsRecorder(
            retention_seconds=3600,
            prometheus_registry=CollectorRegistry(),
        )
        recorder.record(MetricType.LLM_DURATION, 100.0, unit="ms")
        recorder.record(MetricType.CACHE_HIT, 1.0)

        with patch("syntara.metrics.cleanup.get_metrics_recorder", return_value=recorder):
            await cleanup_stale_metrics(_mock_session_factory())

        assert recorder.store.count() == 2

    @pytest.mark.asyncio
    async def test_mixed_expired_and_fresh(self) -> None:
        """Only expired records are removed; fresh ones stay."""
        recorder = MetricsRecorder(
            retention_seconds=60,
            prometheus_registry=CollectorRegistry(),
        )
        recorder.record(MetricType.LLM_DURATION, 100.0, unit="ms")
        recorder.record(MetricType.CACHE_HIT, 1.0)

        records = list(recorder.query())
        records[0].created_at = datetime.now(UTC) - timedelta(hours=1)

        with patch("syntara.metrics.cleanup.get_metrics_recorder", return_value=recorder):
            await cleanup_stale_metrics(_mock_session_factory())

        assert recorder.store.count() == 1
        remaining = next(iter(recorder.query()))
        assert remaining.metric_type == MetricType.CACHE_HIT

    @pytest.mark.asyncio
    async def test_noop_on_empty_store(self) -> None:
        """Cleanup on an empty store completes without error."""
        recorder = MetricsRecorder(
            retention_seconds=3600,
            prometheus_registry=CollectorRegistry(),
        )

        with patch("syntara.metrics.cleanup.get_metrics_recorder", return_value=recorder):
            await cleanup_stale_metrics(_mock_session_factory())

        assert recorder.store.count() == 0


# =============================================================================
# get_metrics_cleanup_worker factory
# =============================================================================


class TestGetMetricsCleanupWorker:
    """Tests for the get_metrics_cleanup_worker factory function."""

    def test_returns_periodic_worker(self, override_settings: Callable[..., AbstractContextManager[object]]) -> None:
        """Factory returns a PeriodicWorker with correct configuration."""
        from syntara.core.workers.periodic import PeriodicWorker

        with (
            override_settings(metrics_cleanup_interval_seconds=1800.0),
            patch("syntara.metrics.cleanup.AsyncSessionLocal", new_callable=MagicMock),
        ):
            worker = get_metrics_cleanup_worker()

        assert isinstance(worker, PeriodicWorker)

    def test_uses_configured_interval(self, override_settings: Callable[..., AbstractContextManager[object]]) -> None:
        """Worker interval comes from settings."""
        with (
            override_settings(metrics_cleanup_interval_seconds=900.0),
            patch("syntara.metrics.cleanup.AsyncSessionLocal", new_callable=MagicMock),
        ):
            worker = get_metrics_cleanup_worker()

        assert worker._interval_seconds == 900.0

    def test_coordinate_is_false(self, override_settings: Callable[..., AbstractContextManager[object]]) -> None:
        """Cleanup runs per-process (no advisory lock coordination)."""
        with (
            override_settings(metrics_cleanup_interval_seconds=3600.0),
            patch("syntara.metrics.cleanup.AsyncSessionLocal", new_callable=MagicMock),
        ):
            worker = get_metrics_cleanup_worker()

        assert worker._coordinate is False


# =============================================================================
# Integration: PeriodicWorker lifecycle with cleanup callback
# =============================================================================


class TestCleanupWorkerIntegration:
    """End-to-end test: PeriodicWorker invokes cleanup_stale_metrics on schedule."""

    @pytest.mark.asyncio
    async def test_worker_invokes_cleanup_periodically(self) -> None:
        """The worker calls the cleanup callback at least once."""
        recorder = MetricsRecorder(
            retention_seconds=1,
            prometheus_registry=CollectorRegistry(),
        )
        recorder.record(MetricType.LLM_DURATION, 100.0, unit="ms")
        record = next(iter(recorder.query()))
        record.created_at = datetime.now(UTC) - timedelta(seconds=10)

        with patch("syntara.metrics.cleanup.get_metrics_recorder", return_value=recorder):
            from syntara.core.workers.periodic import PeriodicWorker

            worker = PeriodicWorker(
                name="test-metrics-cleanup",
                interval_seconds=0.01,
                session_factory=_mock_session_factory(),
                callback=cleanup_stale_metrics,
                coordinate=False,
            )
            worker.start()
            await async_poll_for(lambda: recorder.store.count() == 0, description="stale metrics to be cleaned up")
            await worker.stop()
