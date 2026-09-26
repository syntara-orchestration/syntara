"""Tests for process-owned drain monitoring."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from execution_plane.drain_monitor import DrainMonitor
from execution_plane.models.cluster import Cluster, ClusterStatus
from execution_plane.models.execution_target import ExecutionTarget, TargetStatus

_DATABASE_UNAVAILABLE = "database unavailable"
_TEMPORARY_FAILURE = "temporary failure"


def _target(*, cluster_id: uuid.UUID | None = None, is_default: bool = False) -> ExecutionTarget:
    now = datetime.now(UTC)
    return ExecutionTarget(
        id=uuid.uuid4(),
        cluster_id=cluster_id or uuid.uuid4(),
        name="target-a",
        backend_type="vanilla_k8s",
        endpoint="https://target.example",
        api_key="secret",
        status=TargetStatus.DRAINING,
        enabled=False,
        is_default=is_default,
        created_by=uuid.uuid4(),
        created_at=now,
        updated_by=uuid.uuid4(),
        updated_at=now,
    )


def _cluster() -> Cluster:
    now = datetime.now(UTC)
    return Cluster(
        id=uuid.uuid4(),
        name="cluster-a",
        endpoint="https://cluster.example",
        api_key="secret",
        status=ClusterStatus.DRAINING,
        enabled=False,
        created_by=uuid.uuid4(),
        created_at=now,
        updated_by=uuid.uuid4(),
        updated_at=now,
    )


class _TargetStore:
    def __init__(self, targets: list[ExecutionTarget]) -> None:
        self.targets = targets
        self.finalized: list[uuid.UUID] = []
        self.failed: list[uuid.UUID] = []

    async def list(self, **_: object) -> list[ExecutionTarget]:
        return self.targets

    async def get(self, target_id: uuid.UUID) -> ExecutionTarget | None:
        return next((target for target in self.targets if target.id == target_id), None)

    async def finalize_delete(self, target_id: uuid.UUID) -> None:
        self.finalized.append(target_id)
        self.targets[:] = [target for target in self.targets if target.id != target_id]

    async def mark_failed(self, target_id: uuid.UUID, _updated_by: uuid.UUID) -> None:
        self.failed.append(target_id)


class _ClusterStore:
    def __init__(self, clusters: list[Cluster]) -> None:
        self.clusters = clusters
        self.finalized: list[uuid.UUID] = []
        self.failed: list[uuid.UUID] = []
        self.recorded_discovery_failures = 0
        self.recorded_drain_failures = 0

    async def list(self, **_: object) -> list[Cluster]:
        return self.clusters

    async def finalize_delete(self, cluster_id: uuid.UUID) -> None:
        self.finalized.append(cluster_id)

    async def record_discovery_state(
        self, cluster_id: uuid.UUID, _status: ClusterStatus, _message: str, _updated_by: uuid.UUID
    ) -> Cluster:
        self.failed.append(cluster_id)
        self.recorded_discovery_failures += 1
        return self.clusters[0]

    async def mark_drain_failed(self, cluster_id: uuid.UUID, _message: str, _updated_by: uuid.UUID) -> Cluster:
        self.failed.append(cluster_id)
        self.recorded_drain_failures += 1
        return self.clusters[0]


class _WorkStore:
    def __init__(self, *, drained: bool) -> None:
        self.drained = drained

    async def is_target_drained(self, _target_id: uuid.UUID) -> bool:
        return self.drained


@pytest.mark.asyncio
async def test_monitor_recovers_and_finalizes_persisted_target_and_cluster_drains() -> None:
    cluster = _cluster()
    targets = [_target(cluster_id=cluster.id, is_default=True)]
    target_id = targets[0].id
    target_store = _TargetStore(targets)
    cluster_store = _ClusterStore([cluster])

    monitor = DrainMonitor(target_store, cluster_store, _WorkStore(drained=True), poll_interval=0)  # type: ignore[arg-type]

    await monitor.start()
    await monitor.wait_for_idle()

    assert target_store.finalized == [target_id]
    assert cluster_store.finalized == [cluster.id]
    await monitor.stop()


@pytest.mark.asyncio
async def test_monitor_stop_cancels_a_waiting_drain_task() -> None:
    target = _target()
    target_store = _TargetStore([target])
    cluster_store = _ClusterStore([])
    gate = asyncio.Event()

    async def is_drained(_target_id: uuid.UUID) -> bool:
        await gate.wait()
        return True

    class WaitingWorkStore:
        async def is_target_drained(self, target_id: uuid.UUID) -> bool:
            return await is_drained(target_id)

    monitor = DrainMonitor(
        target_store,  # type: ignore[arg-type]
        cluster_store,  # type: ignore[arg-type]
        WaitingWorkStore(),  # type: ignore[arg-type]
        poll_interval=0,
        monitor_interval=60,
    )
    await monitor.start()
    await monitor.stop()

    assert target_store.finalized == []


@pytest.mark.asyncio
async def test_monitor_polls_for_newly_persisted_target_drains() -> None:
    target = _target()
    target_store = _TargetStore([])
    cluster_store = _ClusterStore([])
    monitor = DrainMonitor(
        target_store,  # type: ignore[arg-type]
        cluster_store,  # type: ignore[arg-type]
        _WorkStore(drained=True),  # type: ignore[arg-type]
        poll_interval=0,
        monitor_interval=0,
    )

    await monitor.start()
    target_store.targets.append(target)
    for _ in range(100):
        if target.id in target_store.finalized:
            break
        await asyncio.sleep(0)
    await monitor.stop()

    assert target_store.finalized == [target.id]


@pytest.mark.asyncio
async def test_monitor_start_is_idempotent() -> None:
    monitor = DrainMonitor(
        _TargetStore([]),  # type: ignore[arg-type]
        _ClusterStore([]),  # type: ignore[arg-type]
        _WorkStore(drained=True),  # type: ignore[arg-type]
        monitor_interval=60,
    )

    await monitor.start()
    monitor_task = monitor._monitor_task
    await monitor.start()

    assert monitor._monitor_task is monitor_task
    await monitor.stop()


@pytest.mark.asyncio
async def test_monitor_resets_started_state_when_initial_scan_fails() -> None:
    class FailingClusterStore(_ClusterStore):
        async def list(self, **_: object) -> list[Cluster]:
            raise RuntimeError(_DATABASE_UNAVAILABLE)

    monitor = DrainMonitor(
        _TargetStore([]),  # type: ignore[arg-type]
        FailingClusterStore([]),  # type: ignore[arg-type]
        _WorkStore(drained=True),  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await monitor.start()

    assert monitor._started is False


@pytest.mark.asyncio
async def test_monitor_cancels_individual_target_drain_when_cluster_drain_is_scheduled() -> None:
    cluster = _cluster()
    target = _target(cluster_id=cluster.id)
    monitor = DrainMonitor(
        _TargetStore([target]),  # type: ignore[arg-type]
        _ClusterStore([cluster]),  # type: ignore[arg-type]
        _WorkStore(drained=False),  # type: ignore[arg-type]
        monitor_interval=60,
    )

    monitor._schedule_target(target.id, uuid.uuid4())
    target_task = monitor._tasks[target.id]
    await monitor._schedule_cluster(cluster.id, uuid.uuid4())

    assert target_task.cancelled() or target_task.done()
    await monitor.stop()


@pytest.mark.asyncio
async def test_monitor_ignores_duplicate_cluster_schedule() -> None:
    cluster = _cluster()
    monitor = DrainMonitor(
        _TargetStore([]),  # type: ignore[arg-type]
        _ClusterStore([cluster]),  # type: ignore[arg-type]
        _WorkStore(drained=False),  # type: ignore[arg-type]
    )

    await monitor._schedule_cluster(cluster.id, uuid.uuid4())
    first_task = monitor._tasks[cluster.id]
    await monitor._schedule_cluster(cluster.id, uuid.uuid4())

    assert monitor._tasks[cluster.id] is first_task
    await monitor.stop()


@pytest.mark.asyncio
async def test_monitor_ignores_duplicate_target_schedule() -> None:
    target = _target()
    monitor = DrainMonitor(
        _TargetStore([target]),  # type: ignore[arg-type]
        _ClusterStore([]),  # type: ignore[arg-type]
        _WorkStore(drained=False),  # type: ignore[arg-type]
    )

    monitor._schedule_target(target.id, uuid.uuid4())
    first_task = monitor._tasks[target.id]
    monitor._schedule_target(target.id, uuid.uuid4())

    assert monitor._tasks[target.id] is first_task
    await monitor.stop()


@pytest.mark.asyncio
async def test_monitor_logs_and_continues_after_a_scan_failure() -> None:
    monitor = DrainMonitor(
        _TargetStore([]),  # type: ignore[arg-type]
        _ClusterStore([]),  # type: ignore[arg-type]
        _WorkStore(drained=True),  # type: ignore[arg-type]
        monitor_interval=0.001,
    )
    calls = 0

    async def failing_scan() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError(_TEMPORARY_FAILURE)

    await monitor.start()
    monitor._scan_draining = failing_scan  # type: ignore[method-assign]
    await asyncio.sleep(0.01)
    await monitor.stop()

    assert calls > 0


@pytest.mark.asyncio
async def test_monitor_propagates_scan_cancellation() -> None:
    monitor = DrainMonitor(
        _TargetStore([]),  # type: ignore[arg-type]
        _ClusterStore([]),  # type: ignore[arg-type]
        _WorkStore(drained=True),  # type: ignore[arg-type]
        monitor_interval=0,
    )

    async def cancelled_scan() -> None:
        raise asyncio.CancelledError

    monitor._scan_draining = cancelled_scan  # type: ignore[method-assign]
    task = asyncio.create_task(monitor._monitor_loop())

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_monitor_silences_failure_when_target_failure_recording_also_fails() -> None:
    target = _target()

    class FailingTargetStore(_TargetStore):
        async def get(self, _target_id: uuid.UUID) -> ExecutionTarget | None:
            raise RuntimeError(_DATABASE_UNAVAILABLE)

        async def mark_failed(self, _target_id: uuid.UUID, _updated_by: uuid.UUID) -> None:
            raise RuntimeError(_DATABASE_UNAVAILABLE)

    monitor = DrainMonitor(
        FailingTargetStore([target]),  # type: ignore[arg-type]
        _ClusterStore([]),  # type: ignore[arg-type]
        _WorkStore(drained=True),  # type: ignore[arg-type]
    )

    await monitor._drain_target(target.id, uuid.uuid4())


@pytest.mark.asyncio
async def test_monitor_marks_a_target_failed_when_drain_finalization_raises() -> None:
    target = _target()

    class FailingTargetStore(_TargetStore):
        async def get(self, _target_id: uuid.UUID) -> ExecutionTarget | None:
            raise RuntimeError(_DATABASE_UNAVAILABLE)

    target_store = FailingTargetStore([target])
    monitor = DrainMonitor(
        target_store,  # type: ignore[arg-type]
        _ClusterStore([]),  # type: ignore[arg-type]
        _WorkStore(drained=True),  # type: ignore[arg-type]
    )

    await monitor._drain_target(target.id, uuid.uuid4())

    assert target_store.failed == [target.id]


@pytest.mark.asyncio
async def test_monitor_marks_a_cluster_failed_when_cluster_drain_raises() -> None:
    cluster = _cluster()

    class FailingTargetStore(_TargetStore):
        async def list(self, **_: object) -> list[ExecutionTarget]:
            raise RuntimeError(_DATABASE_UNAVAILABLE)

    cluster_store = _ClusterStore([cluster])
    monitor = DrainMonitor(
        FailingTargetStore([]),  # type: ignore[arg-type]
        cluster_store,  # type: ignore[arg-type]
        _WorkStore(drained=True),  # type: ignore[arg-type]
    )

    await monitor._drain_cluster(cluster.id, uuid.uuid4())

    assert cluster_store.failed == [cluster.id]
    assert cluster_store.recorded_discovery_failures == 0
    assert cluster_store.recorded_drain_failures == 1


@pytest.mark.asyncio
async def test_monitor_silences_failure_when_cluster_failure_recording_also_fails() -> None:
    cluster = _cluster()

    class FailingTargetStore(_TargetStore):
        async def list(self, **_: object) -> list[ExecutionTarget]:
            raise RuntimeError(_DATABASE_UNAVAILABLE)

    class FailingClusterStore(_ClusterStore):
        async def mark_drain_failed(self, _cluster_id: uuid.UUID, _message: str, _updated_by: uuid.UUID) -> Cluster:
            raise RuntimeError(_DATABASE_UNAVAILABLE)

    monitor = DrainMonitor(
        FailingTargetStore([]),  # type: ignore[arg-type]
        FailingClusterStore([cluster]),  # type: ignore[arg-type]
        _WorkStore(drained=True),  # type: ignore[arg-type]
    )

    await monitor._drain_cluster(cluster.id, uuid.uuid4())


@pytest.mark.asyncio
async def test_monitor_propagates_cluster_drain_cancellation() -> None:
    cluster = _cluster()
    gate = asyncio.Event()

    class WaitingTargetStore(_TargetStore):
        async def list(self, **_: object) -> list[ExecutionTarget]:
            await gate.wait()
            return []

    monitor = DrainMonitor(
        WaitingTargetStore([]),  # type: ignore[arg-type]
        _ClusterStore([cluster]),  # type: ignore[arg-type]
        _WorkStore(drained=True),  # type: ignore[arg-type]
    )
    task = asyncio.create_task(monitor._drain_cluster(cluster.id, uuid.uuid4()))
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_monitor_polls_until_work_for_a_target_is_drained() -> None:
    target = _target()

    class EventuallyDrainedWorkStore:
        def __init__(self) -> None:
            self.calls = 0

        async def is_target_drained(self, _target_id: uuid.UUID) -> bool:
            self.calls += 1
            return self.calls > 1

    work_store = EventuallyDrainedWorkStore()
    monitor = DrainMonitor(
        _TargetStore([target]),  # type: ignore[arg-type]
        _ClusterStore([]),  # type: ignore[arg-type]
        work_store,  # type: ignore[arg-type]
        poll_interval=0,
    )

    await monitor._wait_until_drained(target.id)

    assert work_store.calls == 2
