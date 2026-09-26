"""Process-owned asynchronous draining for ExecutionTargets and Clusters."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from execution_plane.models.cluster import ClusterStatus
from execution_plane.models.execution_target import TargetStatus

if TYPE_CHECKING:
    import uuid

    from execution_plane.cluster.cluster_store import ClusterStore
    from execution_plane.execution_target.execution_target_store import ExecutionTargetStore
    from execution_plane.work_store import WorkStore


logger = structlog.stdlib.get_logger(__name__)


class DrainMonitor:
    """Own, recover, supervise, and shut down all drain tasks in one process."""

    def __init__(
        self,
        target_store: ExecutionTargetStore,
        cluster_store: ClusterStore,
        work_store: WorkStore,
        poll_interval: float = 1.0,
        monitor_interval: float = 1.0,
    ) -> None:
        """Create a monitor using the long-lived persistence stores."""
        self._target_store = target_store
        self._cluster_store = cluster_store
        self._work_store = work_store
        self._poll_interval = poll_interval
        self._monitor_interval = monitor_interval
        self._tasks: dict[uuid.UUID, asyncio.Task[None]] = {}
        self._monitor_task: asyncio.Task[None] | None = None
        self._started = False

    async def start(self) -> None:
        """Recover persisted draining resources and start their monitor tasks."""
        if self._started:
            return
        self._started = True
        try:
            await self._scan_draining()
            self._monitor_task = asyncio.create_task(self._monitor_loop(), name="ep-drain-monitor")
        except Exception:
            self._started = False
            raise

    def _schedule_target(self, target_id: uuid.UUID, updated_by: uuid.UUID) -> None:
        """Schedule an individual target drain if one is not already running."""
        task = self._tasks.get(target_id)
        if task is not None and not task.done():
            return
        self._tasks[target_id] = asyncio.create_task(self._drain_target(target_id, updated_by))

    async def _schedule_cluster(self, cluster_id: uuid.UUID, updated_by: uuid.UUID) -> None:
        """Schedule Cluster draining and coordinate its target finalizations."""
        task = self._tasks.get(cluster_id)
        if task is not None and not task.done():
            return
        targets = await self._target_store.list(cluster_id=cluster_id)
        for target in targets:
            target_task = self._tasks.get(target.id)
            if target_task is not None and not target_task.done():
                target_task.cancel()
                await asyncio.gather(target_task, return_exceptions=True)
        self._tasks[cluster_id] = asyncio.create_task(self._drain_cluster(cluster_id, updated_by))

    async def wait_for_idle(self) -> None:
        """Wait for currently scheduled drain tasks, primarily for controlled shutdown/tests."""
        tasks = list(self._tasks.values())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self) -> None:
        """Cancel and await every task before stores are disposed."""
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            await asyncio.gather(self._monitor_task, return_exceptions=True)
            self._monitor_task = None
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._started = False

    async def _monitor_loop(self) -> None:
        """Poll persisted drain state so API requests are observed by the worker."""
        while True:
            await asyncio.sleep(self._monitor_interval)
            try:
                await self._scan_draining()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Drain monitor scan failed")

    async def _scan_draining(self) -> None:
        """Schedule workers for all persisted draining resources."""
        clusters = await self._cluster_store.list(status=ClusterStatus.DRAINING)
        cluster_ids = {cluster.id for cluster in clusters}
        for cluster in clusters:
            await self._schedule_cluster(cluster.id, cluster.updated_by)
        targets = await self._target_store.list(status=TargetStatus.DRAINING)
        for target in targets:
            if target.cluster_id not in cluster_ids:
                self._schedule_target(target.id, target.updated_by)

    async def _drain_target(self, target_id: uuid.UUID, updated_by: uuid.UUID) -> None:
        try:
            await self._wait_until_drained(target_id)
            if await self._target_store.get(target_id) is not None:
                await self._target_store.finalize_delete(target_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            try:
                await self._target_store.mark_failed(target_id, updated_by)
            except Exception:  # noqa: BLE001
                return

    async def _drain_cluster(self, cluster_id: uuid.UUID, updated_by: uuid.UUID) -> None:
        try:
            targets = await self._target_store.list(cluster_id=cluster_id)
            for target in targets:
                await self._wait_until_drained(target.id)
                if await self._target_store.get(target.id) is not None:
                    await self._target_store.finalize_delete(target.id)
            await self._cluster_store.finalize_delete(cluster_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            try:
                await self._cluster_store.mark_drain_failed(cluster_id, "cluster drain failed", updated_by)
            except Exception:  # noqa: BLE001
                return

    async def _wait_until_drained(self, target_id: uuid.UUID) -> None:
        while not await self._work_store.is_target_drained(target_id):  # noqa: ASYNC110
            await asyncio.sleep(self._poll_interval)
