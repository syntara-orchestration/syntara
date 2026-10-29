"""Independent ownership infrastructure with isolated provider and recovery ports."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from syntara.eventstreams.core.placement import PlacementUncertainError, WorkerMembership
from syntara.eventstreams.services.recovery_worker import EventDeliveryRecoveryWorker
from tests.helpers.eventstream_runtime import IsolatedSubscriptionRunner
from tests.helpers.eventstream_worker import IsolatedPlacementService
from tests.unit.eventstreams import test_consumer_service as consumer_tests
from tests.unit.eventstreams.test_consumer_service import eventually
from tests.unit.eventstreams.test_worker_resources import TrackingSessionFactory

manager_context = consumer_tests.manager_context


async def test_blocked_broker_start_does_not_starve_heartbeat_renewal_or_recovery(manager_context, monkeypatch):
    context = manager_context
    release = asyncio.Event()

    def construct(binding) -> IsolatedSubscriptionRunner:
        runner = IsolatedSubscriptionRunner(binding, context.trace)
        runner.start_release = release
        context.runners.append(runner)
        return runner

    context.factory.side_effect = construct
    context.manager._membership._settings = context.manager._membership._settings.model_copy(
        update={"event_worker_heartbeat_interval_seconds": 0.01}
    )
    store = MagicMock()
    store.claim_due = AsyncMock(return_value=[])
    monkeypatch.setattr("syntara.eventstreams.services.recovery_worker.EventDeliveryStore", lambda _session: store)
    recovery = EventDeliveryRecoveryWorker(
        TrackingSessionFactory(), MagicMock(), resources=context.resources, interval_seconds=0.01
    )
    await context.manager.start()
    recovery.start()
    try:
        await eventually(lambda: bool(context.runners) and context.runners[0].start_entered.is_set())
        await eventually(
            lambda: context.pool.trace.count(("heartbeat", context.placement.worker.worker_id)) > 1
            and ("renew", context.snapshot.subscription_id) in context.pool.trace
            and store.claim_due.await_count > 0
        )
        assert context.manager.ready
        assert not context.runners[0].started
        assert not context.manager.membership_task.done()
    finally:
        await recovery.stop()
        release.set()


async def test_untrusted_lease_is_not_revived_by_renewal(manager_context, monkeypatch):
    context = manager_context
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    key = context.snapshot.subscription_id
    lost = MagicMock()
    monkeypatch.setattr(context.manager._membership, "_lost", lost)
    context.placement.authority(key).invalidate()
    await context.manager._membership.renew_owned()
    lost.assert_called_once_with(key)
    assert not context.placement.authority(key).is_current()
    assert ("renew", key) not in context.pool.trace
    assert not context.runners[0].accepting


async def test_membership_deadline_failure_is_exposed_as_process_infrastructure(manager_context):
    context = manager_context
    membership = context.manager._membership
    membership._settings = membership._settings.model_copy(
        update={"event_worker_liveness_seconds": 0.02, "event_worker_heartbeat_interval_seconds": 10}
    )
    await context.manager.start()
    async with asyncio.timeout(2):
        with pytest.raises(RuntimeError, match="membership deadline"):
            await context.manager.membership_task
    assert not context.manager.ready
    assert not context.resources.gate.scheduling_open
    assert not context.placement.authority(context.snapshot.subscription_id).is_current()


async def test_local_placement_operations_are_serialized_and_bounded(manager_context):
    context = manager_context
    context.reader.read.return_value = []
    await context.manager.start()
    entered, release = asyncio.Event(), asyncio.Event()
    active = peak = calls = 0

    async def operation() -> None:
        nonlocal active, peak, calls
        active += 1
        peak = max(peak, active)
        calls += 1
        entered.set()
        await release.wait()
        active -= 1

    tasks = [asyncio.create_task(context.manager._membership.call(operation)) for _ in range(10)]
    try:
        await entered.wait()
        assert calls == 1
        assert peak == 1
    finally:
        release.set()
        await asyncio.gather(*tasks)
    assert calls == 10
    assert peak == 1


async def test_placement_rechecks_membership_trust_after_waiting_for_lock(manager_context, monkeypatch):
    context = manager_context
    context.reader.read.return_value = []
    membership = context.manager._membership
    clock = [100.0]
    monkeypatch.setattr(membership, "_clock", lambda: clock[0])
    await context.manager.start()
    operation = AsyncMock()
    await membership._operations.acquire()
    task = asyncio.create_task(membership.call(operation))
    try:
        await asyncio.sleep(0)
        clock[0] = membership._deadline
    finally:
        membership._operations.release()
    with pytest.raises(PlacementUncertainError, match="not trusted"):
        await task
    operation.assert_not_awaited()
    assert not context.resources.scheduling_open
    # Fresh authoritative reads and registration remain available for recovery.
    read = AsyncMock(return_value=[])
    assert await membership.call(read, require_trusted=False) == []
    await membership._heartbeat()
    assert membership.trusted


@pytest.mark.parametrize("fail_first", [False, True])
async def test_draining_registration_removes_worker_from_peer_targets(manager_context, monkeypatch, fail_first):
    context = manager_context
    peer = IsolatedPlacementService(context.pool, worker_id=UUID(int=2))
    await peer.heartbeat_worker(peer.worker, draining=False)
    await context.manager.start()
    heartbeat = context.placement.heartbeat_worker
    attempts = []

    async def mark(worker, *, draining) -> WorkerMembership:
        attempts.append(draining)
        if fail_first and len(attempts) == 1:
            msg = "isolated draining write failure"
            raise PlacementUncertainError(msg)
        member: WorkerMembership = await heartbeat(worker, draining=draining)
        return member

    monkeypatch.setattr(context.placement, "heartbeat_worker", mark)
    await context.manager.begin_shutdown()
    assert attempts == ([True, True] if fail_first else [True])
    assert context.pool.members[context.placement.worker.worker_id].draining
    members = await peer.list_live_workers()
    assert consumer_tests.placement_targets(1, (member.worker.worker_id for member in members)) == {
        peer.worker.worker_id: 1
    }
    assert not context.resources.accepting
    assert not context.manager.membership_task.done()


async def test_persistent_draining_write_failure_is_bounded_and_peers_wait_for_expiry(manager_context, monkeypatch):
    context = manager_context
    peer = IsolatedPlacementService(context.pool, worker_id=UUID(int=2))
    await peer.heartbeat_worker(peer.worker, draining=False)
    await context.manager.start()
    msg = "isolated unavailable draining write"
    heartbeat = AsyncMock(side_effect=PlacementUncertainError(msg))
    monkeypatch.setattr(context.placement, "heartbeat_worker", heartbeat)
    with pytest.raises(PlacementUncertainError, match="unavailable draining write"):
        await context.manager.begin_shutdown()
    assert heartbeat.await_count == 2
    assert all(call.kwargs["draining"] for call in heartbeat.await_args_list)
    assert not context.resources.accepting
    assert not context.resources.scheduling_open
    members = await peer.list_live_workers()
    assert len(members) == 2  # No unavailable write can remove a peer-visible row.
    await context.manager.stop()
    assert heartbeat.await_count == 2
    assert context.manager.membership_task.done()
    key = context.placement.worker.worker_id
    context.pool.members[key] = context.pool.members[key].model_copy(
        update={"heartbeat_until": datetime.now(UTC) - timedelta(seconds=1)}
    )
    members = await peer.list_live_workers()
    assert consumer_tests.placement_targets(1, (member.worker.worker_id for member in members)) == {
        peer.worker.worker_id: 1
    }


async def test_failed_required_database_operation_closes_shared_gate(manager_context):
    context = manager_context
    await context.manager.start()

    async def fail() -> None:
        msg = "isolated storage failure"
        raise OSError(msg)

    with pytest.raises(OSError, match="isolated storage failure"):
        await context.manager._membership.call(fail)
    assert not context.resources.gate.scheduling_open
    assert not context.resources.gate.resolution_open(context.snapshot)


async def test_reads_cannot_reopen_gate_while_heartbeat_writes_fail(manager_context):
    context = manager_context
    context.reader.read.return_value = []
    await context.manager.start()
    assert context.manager.ready
    membership = context.manager._membership
    context.placement.heartbeat_error = True
    for _ in range(2):
        with pytest.raises(PlacementUncertainError, match="heartbeat failure"):
            await membership._heartbeat()
        await context.manager.reconcile()
        assert not context.manager.ready
        assert not context.resources.scheduling_open
        assert not context.resources.gate.cache_trusted()
    context.placement.heartbeat_error = False
    await membership._heartbeat()
    assert not context.resources.scheduling_open
    await context.manager.reconcile()
    assert context.manager.ready
    assert context.resources.gate.cache_trusted()


async def test_delayed_heartbeat_does_not_clear_a_newer_failure(manager_context, monkeypatch):
    context = manager_context
    context.reader.read.return_value = []
    await context.manager.start()
    entered, release = asyncio.Event(), asyncio.Event()
    heartbeat = context.placement.heartbeat_worker

    async def delayed(worker, *, draining) -> WorkerMembership:
        entered.set()
        await release.wait()
        member: WorkerMembership = await heartbeat(worker, draining=draining)
        return member

    monkeypatch.setattr(context.placement, "heartbeat_worker", delayed)
    task = asyncio.create_task(context.manager._membership._heartbeat())
    try:
        await entered.wait()
        context.resources.database_failed()
    finally:
        release.set()
        await task
    await context.manager.reconcile()
    assert not context.resources.scheduling_open
    assert not context.manager.ready
    await context.manager._membership._heartbeat()
    await context.manager.reconcile()
    assert context.manager.ready
