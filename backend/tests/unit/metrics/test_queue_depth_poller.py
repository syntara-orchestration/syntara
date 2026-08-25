"""Unit tests for syntara.metrics.queue_depth_poller."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

from syntara.metrics.queue_depth_poller import (
    _make_poll_callback,
    _query_queue_depth,
    get_queue_depth_poller,
)


class TestQueryQueueDepth:
    """Tests for _query_queue_depth gRPC helper."""

    @pytest.mark.asyncio
    async def test_returns_approximate_backlog_count(self) -> None:
        """Should prefer stats.approximate_backlog_count when available."""
        mock_resp = MagicMock()
        mock_resp.stats.approximate_backlog_count = 42
        mock_resp.task_queue_status = None

        mock_client = MagicMock()
        mock_client.workflow_service.describe_task_queue = AsyncMock(return_value=mock_resp)

        depth = await _query_queue_depth(mock_client, "orchestrator-task-queue", "default")
        assert depth == 42

    @pytest.mark.asyncio
    async def test_falls_back_to_backlog_count_hint(self) -> None:
        """Should use backlog_count_hint when stats is empty."""
        mock_resp = MagicMock()
        mock_resp.stats = None
        mock_resp.task_queue_status.backlog_count_hint = 7

        mock_client = MagicMock()
        mock_client.workflow_service.describe_task_queue = AsyncMock(return_value=mock_resp)

        depth = await _query_queue_depth(mock_client, "orchestrator-task-queue", "default")
        assert depth == 7

    @pytest.mark.asyncio
    async def test_returns_zero_when_empty(self) -> None:
        """Should return 0 when both stats and status report no backlog."""
        mock_resp = MagicMock()
        mock_resp.stats = None
        mock_resp.task_queue_status = None

        mock_client = MagicMock()
        mock_client.workflow_service.describe_task_queue = AsyncMock(return_value=mock_resp)

        depth = await _query_queue_depth(mock_client, "orchestrator-task-queue", "default")
        assert depth == 0


class TestPollCallback:
    """Tests for the poll callback produced by _make_poll_callback.

    The poller delegates connection management to get_shared_client() from
    syntara.core.temporal.client; tests patch that function directly rather
    than the removed Client.connect call.
    """

    @pytest.mark.asyncio
    async def test_records_metric_per_queue_with_task_queue_label(self) -> None:
        """Callback should emit one labeled TEMPORAL_QUEUE_DEPTH record per queue."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.stats.approximate_backlog_count = 5
        mock_resp.task_queue_status = None
        mock_client.workflow_service.describe_task_queue = AsyncMock(return_value=mock_resp)
        mock_client.count_workflows = AsyncMock(return_value=MagicMock(count=0))

        mock_recorder = MagicMock()

        with (
            patch(
                "syntara.metrics.queue_depth_poller.get_shared_client",
                new_callable=AsyncMock,
                return_value=mock_client,
            ),
            patch(
                "syntara.metrics.queue_depth_poller.get_metrics_recorder",
                return_value=mock_recorder,
            ),
        ):
            callback = _make_poll_callback(task_queues=["orchestrator-workflow-queue"])
            await callback(None)

        from syntara.metrics.types import ComponentLabel, MetricType

        depth_calls = [c for c in mock_recorder.record.call_args_list if c.args[0] == MetricType.TEMPORAL_QUEUE_DEPTH]
        assert len(depth_calls) == 1
        assert depth_calls[0] == (
            (MetricType.TEMPORAL_QUEUE_DEPTH, 5.0),
            {"component": ComponentLabel.TEMPORAL_WORKER, "labels": {"task_queue": "orchestrator-workflow-queue"}},
        )

    @pytest.mark.asyncio
    async def test_records_one_metric_per_queue(self) -> None:
        """Callback should emit separate labeled records for each queue polled."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.stats.approximate_backlog_count = 3
        mock_resp.task_queue_status = None
        mock_client.workflow_service.describe_task_queue = AsyncMock(return_value=mock_resp)
        mock_client.count_workflows = AsyncMock(return_value=MagicMock(count=0))

        mock_recorder = MagicMock()
        queues = ["orchestrator-workflow-queue", "orchestrator-background-queue"]

        with (
            patch(
                "syntara.metrics.queue_depth_poller.get_shared_client",
                new_callable=AsyncMock,
                return_value=mock_client,
            ),
            patch(
                "syntara.metrics.queue_depth_poller.get_metrics_recorder",
                return_value=mock_recorder,
            ),
        ):
            callback = _make_poll_callback(task_queues=queues)
            await callback(None)

        from syntara.metrics.types import ComponentLabel, MetricType

        depth_calls = [c for c in mock_recorder.record.call_args_list if c.args[0] == MetricType.TEMPORAL_QUEUE_DEPTH]
        assert len(depth_calls) == 2
        recorded_queues = {c.kwargs["labels"]["task_queue"] for c in depth_calls}
        assert recorded_queues == set(queues)
        for call in depth_calls:
            assert call.args == (MetricType.TEMPORAL_QUEUE_DEPTH, 3.0)
            assert call.kwargs["component"] == ComponentLabel.TEMPORAL_WORKER

    @pytest.mark.asyncio
    async def test_skips_recording_when_client_unavailable(self) -> None:
        """Callback should not record when get_shared_client returns None."""
        mock_recorder = MagicMock()

        with (
            patch(
                "syntara.metrics.queue_depth_poller.get_shared_client",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "syntara.metrics.queue_depth_poller.get_metrics_recorder",
                return_value=mock_recorder,
            ),
        ):
            callback = _make_poll_callback(task_queues=["q"])
            await callback(None)

        mock_recorder.record.assert_not_called()

    @pytest.mark.asyncio
    async def test_continues_remaining_queues_on_rpc_error(self) -> None:
        """An RPCError on one queue should not abort polling of the remaining queues.

        A connection-level error (UNAVAILABLE) also triggers invalidate_client()
        so the next poll cycle will reconnect.
        """
        from temporalio.service import RPCError, RPCStatusCode

        mock_client = MagicMock()

        ok_resp = MagicMock()
        ok_resp.stats.approximate_backlog_count = 7
        ok_resp.task_queue_status = None

        mock_client.workflow_service.describe_task_queue = AsyncMock(
            side_effect=[
                RPCError("unavailable", RPCStatusCode.UNAVAILABLE, b""),
                ok_resp,
            ]
        )
        mock_client.count_workflows = AsyncMock(return_value=MagicMock(count=0))
        mock_recorder = MagicMock()

        with (
            patch(
                "syntara.metrics.queue_depth_poller.get_shared_client",
                new_callable=AsyncMock,
                return_value=mock_client,
            ),
            patch(
                "syntara.metrics.queue_depth_poller.get_metrics_recorder",
                return_value=mock_recorder,
            ),
            patch(
                "syntara.core.temporal.client.invalidate_client",
            ) as mock_invalidate,
        ):
            callback = _make_poll_callback(task_queues=["orchestrator-workflow-queue", "orchestrator-background-queue"])
            await callback(None)

        from syntara.metrics.types import ComponentLabel, MetricType

        # Polling continues: second queue is recorded despite first erroring.
        depth_calls = [c for c in mock_recorder.record.call_args_list if c.args[0] == MetricType.TEMPORAL_QUEUE_DEPTH]
        assert len(depth_calls) == 1
        assert depth_calls[0] == (
            (MetricType.TEMPORAL_QUEUE_DEPTH, 7.0),
            {"component": ComponentLabel.TEMPORAL_WORKER, "labels": {"task_queue": "orchestrator-background-queue"}},
        )
        # Connection error triggers client invalidation so next cycle reconnects.
        mock_invalidate.assert_called_once()


class TestGetQueueDepthPoller:
    """Tests for the get_queue_depth_poller factory."""

    def test_returns_periodic_worker(self) -> None:
        """Factory should return a PeriodicWorker with coordinate=False."""
        from syntara.core.workers.periodic import PeriodicWorker

        poller = get_queue_depth_poller()

        assert isinstance(poller, PeriodicWorker)
        assert poller._coordinate is False
        assert poller._session_factory is None
        assert poller._name == "temporal-queue-depth-poller"

    def test_polls_both_queues_when_queues_differ(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Factory should build a callback that covers both task queues."""
        mock_factory = MagicMock(return_value=AsyncMock())

        with (
            override_settings(
                task_queue="orchestrator-workflow-queue",
                background_task_queue="orchestrator-background-queue",
            ),
            patch("syntara.metrics.queue_depth_poller._make_poll_callback", mock_factory),
        ):
            get_queue_depth_poller()

        assert mock_factory.call_args.kwargs["task_queues"] == [
            "orchestrator-workflow-queue",
            "orchestrator-background-queue",
        ]

    def test_deduplicates_queues_when_both_settings_are_identical(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """When task_queue == background_task_queue, the queue is polled once."""
        mock_factory = MagicMock(return_value=AsyncMock())

        with (
            override_settings(
                task_queue="same-queue",
                background_task_queue="same-queue",
            ),
            patch("syntara.metrics.queue_depth_poller._make_poll_callback", mock_factory),
        ):
            get_queue_depth_poller()

        assert mock_factory.call_args.kwargs["task_queues"] == ["same-queue"]


class TestPeriodicWorkerOptionalSessionFactory:
    """Tests for PeriodicWorker's optional session_factory."""

    def test_raises_when_coordinate_true_and_no_session_factory(self) -> None:
        """coordinate=True without session_factory must raise ValueError."""
        from syntara.core.workers.periodic import PeriodicWorker

        async def noop(_sf: object) -> None:
            pass

        with pytest.raises(ValueError, match="session_factory is required"):
            PeriodicWorker(
                name="bad",
                interval_seconds=1.0,
                callback=noop,
                coordinate=True,
            )

    def test_accepts_none_session_factory_when_uncoordinated(self) -> None:
        """coordinate=False should accept session_factory=None."""
        from syntara.core.workers.periodic import PeriodicWorker

        async def noop(_sf: object) -> None:
            pass

        worker = PeriodicWorker(
            name="ok",
            interval_seconds=1.0,
            callback=noop,
            coordinate=False,
        )
        assert worker._session_factory is None
