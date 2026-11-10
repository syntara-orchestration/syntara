"""Tests for the non-blocking Temporal client warmup during startup.

The warmup itself (``_warm_temporal_client``) is tested directly; startup
launches it via ``asyncio.create_task`` so a slow Temporal server cannot
delay pod readiness, and ``_lifespan_shutdown`` cancels a still-pending
warmup instead of waiting for it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from syntara.api.main import _lifespan_shutdown, _warm_temporal_client

if TYPE_CHECKING:
    from typing import Any


class TestWarmTemporalClient:
    """Tests for the _warm_temporal_client helper."""

    async def test_logs_warmed_when_client_available(self) -> None:
        """A successful connect logs the warmed outcome."""
        with (
            patch(
                "syntara.api.main.get_shared_temporal_client",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch("syntara.api.main.logger") as mock_logger,
        ):
            await _warm_temporal_client()

        mock_logger.info.assert_called_once_with("temporal_client_warmed")
        mock_logger.warning.assert_not_called()

    async def test_logs_skipped_when_client_unavailable(self) -> None:
        """An unavailable server logs the skipped outcome without raising."""
        with (
            patch(
                "syntara.api.main.get_shared_temporal_client",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("syntara.api.main.logger") as mock_logger,
        ):
            await _warm_temporal_client()

        mock_logger.warning.assert_called_once_with(
            "temporal_client_warmup_skipped", reason="server unavailable at startup"
        )
        mock_logger.info.assert_not_called()

    async def test_warmup_task_does_not_block_its_spawner(self) -> None:
        """A hanging connect must not block the caller that spawned the warmup.

        Startup launches the warmup with ``asyncio.create_task`` and does
        not await it; this pins the contract that the warmup may take up to
        the connect timeout while its spawner proceeds immediately.
        """
        connect_started = asyncio.Event()
        release_connect = asyncio.Event()

        async def _hang_connect() -> None:
            connect_started.set()
            await release_connect.wait()

        with patch(
            "syntara.api.main.get_shared_temporal_client",
            new=_hang_connect,
        ):
            warmup_task = asyncio.create_task(_warm_temporal_client())
            # The spawner proceeded: the warmup is running but unfinished.
            await asyncio.wait_for(connect_started.wait(), timeout=1.0)
            assert not warmup_task.done()
            release_connect.set()
            await asyncio.wait_for(warmup_task, timeout=1.0)


def _make_shutdown_resources(**overrides: object) -> dict[str, Any]:
    """Build a minimal resources dict accepted by _lifespan_shutdown."""

    def _worker() -> MagicMock:
        worker = MagicMock()
        worker.stop = AsyncMock()
        return worker

    async def _async_noop() -> None:
        return None

    rate_limit_redis = MagicMock()
    rate_limit_redis.disconnect = AsyncMock(side_effect=_async_noop)
    runtime_settings = MagicMock()
    runtime_settings.stop_watching = AsyncMock(side_effect=_async_noop)
    authz_evaluator = MagicMock()
    authz_evaluator.stop = AsyncMock(side_effect=_async_noop)

    resources: dict[str, Any] = {
        "schedule_reconciliation_worker": _worker(),
        "multipart_cleanup_worker": _worker(),
        "queue_depth_poller": _worker(),
        "session_cleanup_worker": _worker(),
        "metrics_cleanup_worker": _worker(),
        "completion_poller": _worker(),
        "periodic_collector": _worker(),
        "lifecycle_manager": MagicMock(),
        "rate_limit_redis": rate_limit_redis,
        "runtime_settings": runtime_settings,
        "authz_evaluator": authz_evaluator,
    }
    resources.update(overrides)
    return resources


def _patch_shutdown_side_effects() -> list[Any]:
    """Patches for the shutdown steps not under test."""
    engine = MagicMock()
    engine.dispose = AsyncMock()
    return [
        patch("syntara.api.main.stop_audit_subsystems", new_callable=AsyncMock),
        patch("syntara.api.main.flush_telemetry"),
        patch("syntara.api.main.engine", engine),
        patch("syntara.api.main._get_lock_file_path", return_value=Path("/nonexistent/lock")),
    ]


class TestLifespanShutdownWarmup:
    """Tests for warmup cleanup during _lifespan_shutdown."""

    async def test_cancels_pending_warmup_without_waiting(self) -> None:
        """Shutdown cancels a still-running warmup rather than awaiting it.

        The warmup's connect wait can outlive shutdown (up to the connect
        timeout); shutdown must return promptly after cancelling it.
        """
        hang = asyncio.Event()

        async def _hanging_warmup() -> None:
            await hang.wait()

        warmup_task = asyncio.create_task(_hanging_warmup())
        resources = _make_shutdown_resources(temporal_warmup_task=warmup_task)

        patches = _patch_shutdown_side_effects()
        for p in patches:
            p.start()
        try:
            await asyncio.wait_for(_lifespan_shutdown(resources), timeout=1.0)
        finally:
            for p in patches:
                p.stop()

        assert warmup_task.cancelled()
        hang.set()

    async def test_completed_warmup_is_left_alone(self) -> None:
        """A warmup that already finished needs no cancellation."""

        async def _finished_warmup() -> None:
            return None

        warmup_task = asyncio.create_task(_finished_warmup())
        await warmup_task
        resources = _make_shutdown_resources(temporal_warmup_task=warmup_task)

        patches = _patch_shutdown_side_effects()
        for p in patches:
            p.start()
        try:
            await asyncio.wait_for(_lifespan_shutdown(resources), timeout=1.0)
        finally:
            for p in patches:
                p.stop()

        assert warmup_task.done()
        assert not warmup_task.cancelled()

    async def test_missing_warmup_key_is_tolerated(self) -> None:
        """Resources built without a warmup entry (older callers) still shut down."""
        resources = _make_shutdown_resources()

        patches = _patch_shutdown_side_effects()
        for p in patches:
            p.start()
        try:
            await asyncio.wait_for(_lifespan_shutdown(resources), timeout=1.0)
        finally:
            for p in patches:
                p.stop()
