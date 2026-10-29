"""Authoritative reconciliation, bounded startup, isolation, and idle readiness."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from syntara.core.constants import EventSchedulingDefaults, EventWorkerDefaults
from syntara.eventstreams.adapters.kafka_consumer import KafkaPartitionConsumer
from syntara.eventstreams.adapters.kafka_record_runner import KafkaRecordRunner
from syntara.eventstreams.consumer_service import EventWorkerManager, placement_targets
from syntara.eventstreams.core.runtime import (
    RuntimeFailureCode,
    RuntimeRevision,
    RuntimeState,
    SubscriptionRuntimeStatus,
)
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.subscription_reader import EventSubscriptionReader
from syntara.eventstreams.services.worker_resources import EventWorkerResources
from tests.helpers.eventstream_runtime import IsolatedSubscriptionRunner
from tests.helpers.eventstream_worker import IsolatedPlacementPool, IsolatedPlacementService
from tests.unit.eventstreams.test_connection_provider import connection_context
from tests.unit.eventstreams.test_kafka_consumer import _connection, _mock_consumer


async def eventually(predicate) -> None:
    """Wait for a lifecycle observation without arbitrary wall-clock sleeps."""
    async with asyncio.timeout(2):
        while not predicate():  # noqa: ASYNC110 - bounded polling of several independent lifecycle observations
            await asyncio.sleep(0)


@pytest_asyncio.fixture
async def manager_context(monkeypatch):
    monkeypatch.setattr(EventWorkerDefaults, "STARTUP_CONCURRENCY", 2)
    snapshot = connection_context().snapshot
    reader = AsyncMock(spec=EventSubscriptionReader)
    reader.read.return_value = [snapshot]
    reader.recovery_holds.return_value = set()
    pool = IsolatedPlacementPool(snapshot.deployment_id, [snapshot.subscription_id])
    pool.candidates = lambda: (binding.subscription_id for binding in reader.read.return_value)
    placement = IsolatedPlacementService(pool, worker_id=UUID(int=1))
    resources = EventWorkerResources()
    runners, trace = [], []

    def construct(binding) -> IsolatedSubscriptionRunner:
        assert pool.leases[binding.subscription_id].owner == placement.worker
        pool.trace.append(("construct", binding.subscription_id))
        runner = IsolatedSubscriptionRunner(binding, trace)
        runners.append(runner)
        return runner

    factory = AsyncMock(side_effect=construct)
    manager = EventWorkerManager(reader, factory, placement, resources)
    yield SimpleNamespace(
        manager=manager,
        reader=reader,
        factory=factory,
        runners=runners,
        snapshot=snapshot,
        trace=trace,
        pool=pool,
        placement=placement,
        resources=resources,
    )
    for runner in runners:
        runner.stop_error = None
        if runner.start_release is not None:
            runner.start_release.set()
    await manager.stop()


async def test_readiness_waits_for_authoritative_read_without_waiting_for_broker(manager_context):
    context = manager_context
    read_entered, read_release = asyncio.Event(), asyncio.Event()
    broker_release = asyncio.Event()

    async def read() -> list[SubscriptionSnapshot]:
        read_entered.set()
        await read_release.wait()
        return [context.snapshot]

    async def construct(binding) -> IsolatedSubscriptionRunner:
        runner = IsolatedSubscriptionRunner(binding, context.trace)
        runner.start_release = broker_release
        context.runners.append(runner)
        return runner

    context.reader.read.side_effect = read
    context.factory.side_effect = construct
    task = asyncio.create_task(context.manager.start())
    await read_entered.wait()
    assert not context.manager.ready
    context.factory.assert_not_awaited()
    read_release.set()
    await task
    assert context.manager.ready
    await eventually(lambda: bool(context.runners))
    assert not context.runners[0].started


async def test_enabled_empty_worker_is_ready_and_idle(manager_context):
    context = manager_context
    context.reader.read.return_value = []
    await context.manager.start()
    assert context.manager.ready
    assert not context.manager.subscription_ids
    context.factory.assert_not_awaited()


async def test_overlapping_starts_share_one_worker_pool_and_loop(manager_context):
    context = manager_context
    read_entered, read_release, second_entered = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def read() -> list[SubscriptionSnapshot]:
        read_entered.set()
        await read_release.wait()
        return []

    async def start_again() -> None:
        second_entered.set()
        await context.manager.start()

    context.reader.read.side_effect = read
    existing_tasks = asyncio.all_tasks()
    first = asyncio.create_task(context.manager.start())
    await read_entered.wait()
    workers = tuple(context.manager._workers)
    second = asyncio.create_task(start_again())
    await second_entered.wait()
    assert not second.done()
    assert tuple(context.manager._workers) == workers
    read_release.set()
    await asyncio.gather(first, second)
    assert context.manager.ready
    assert tuple(context.manager._workers) == workers
    assert len(workers) == EventWorkerDefaults.STARTUP_CONCURRENCY
    context.reader.read.assert_awaited_once()
    await context.manager.stop()
    assert all(task.done() for task in workers)
    assert context.manager.reconciliation_task.done()
    assert not {
        task for task in asyncio.all_tasks() - existing_tasks if task.get_name().startswith("event-subscription-")
    }


@pytest.mark.parametrize("timeout_in_factory", [False, True])
async def test_startup_timeouts_preserve_backoff_and_open_circuit(manager_context, monkeypatch, timeout_in_factory):
    context = manager_context
    monkeypatch.setattr(EventWorkerDefaults, "STARTUP_TIMEOUT_SECONDS", 0.01)
    now = datetime.now(UTC)
    monkeypatch.setattr("syntara.eventstreams.services.subscription_supervisor._utc_now", lambda: now)
    blocked = asyncio.Event()

    async def construct(binding) -> IsolatedSubscriptionRunner:
        if timeout_in_factory:
            await blocked.wait()
        runner = IsolatedSubscriptionRunner(binding, context.trace)
        runner.start_release = blocked
        context.runners.append(runner)
        return runner

    context.factory.side_effect = construct
    await context.manager.start()
    await eventually(lambda: bool(context.manager.subscription_ids))
    supervisor = context.manager._supervisors[context.snapshot.subscription_id]
    for attempt in range(1, EventSchedulingDefaults.IMMEDIATE_ATTEMPTS + 1):
        await eventually(
            lambda attempt=attempt: supervisor.status.failure_count == attempt and not context.manager._busy
        )
        status = supervisor.status
        assert status.reason == RuntimeFailureCode.CONNECTION_UNAVAILABLE.value
        assert status.state == (
            RuntimeState.BLOCKED if attempt == EventSchedulingDefaults.IMMEDIATE_ATTEMPTS else RuntimeState.BACKOFF
        )
        assert status.retry_at > now
        assert all(runner.stopped for runner in context.runners)
        await context.manager.reconcile()
        await eventually(lambda: not context.manager._pending and not context.manager._busy)
        assert context.factory.await_count == attempt
        if attempt < EventSchedulingDefaults.IMMEDIATE_ATTEMPTS:
            now = status.retry_at + timedelta(seconds=1)
            await context.manager.reconcile()
    assert supervisor.status.circuit_open
    assert context.manager._supervisors[context.snapshot.subscription_id] is supervisor


@pytest.mark.parametrize("shutdown", [False, True])
async def test_partial_kafka_start_is_closed_on_timeout_or_shutdown(manager_context, monkeypatch, shutdown):
    context = manager_context
    monkeypatch.setattr(EventWorkerDefaults, "STARTUP_TIMEOUT_SECONDS", 30 if shutdown else 0.01)
    now = datetime.now(UTC)
    monkeypatch.setattr("syntara.eventstreams.services.subscription_supervisor._utc_now", lambda: now)
    blocked = asyncio.Event()
    clients, runners = [], []
    sessions = MagicMock()

    def client(**_kwargs: object) -> AsyncMock:
        assert all(previous.stop.await_count == 1 for previous in clients)
        consumer = _mock_consumer()
        consumer.start.side_effect = blocked.wait
        clients.append(consumer)
        return consumer

    def construct(binding) -> KafkaRecordRunner:
        runner = KafkaRecordRunner(
            binding,
            KafkaPartitionConsumer(_connection(), binding.configuration),
            sessions,
            MagicMock(),
            MagicMock(),
            owner_worker_id="worker",
        )
        runners.append(runner)
        return runner

    monkeypatch.setattr("syntara.eventstreams.adapters.kafka_consumer.AIOKafkaConsumer", client)
    context.factory.side_effect = construct
    await context.manager.start()
    await eventually(lambda: bool(clients) and clients[0].start.await_count == 1)
    supervisor = context.manager._supervisors[context.snapshot.subscription_id]
    if shutdown:
        await context.manager.stop()
        assert supervisor.status.failure_count == 0
        assert len(clients) == 1
    else:
        for attempt in range(1, 3):
            await eventually(
                lambda attempt=attempt: supervisor.status.failure_count == attempt and not context.manager._busy
            )
            assert clients[-1].stop.await_count == 1
            if attempt == 1:
                now = supervisor.status.retry_at + timedelta(seconds=1)
                await context.manager.reconcile()
        assert len(clients) == 2
        await context.manager.stop()
    for consumer in clients:
        consumer.stop.assert_awaited_once()
        consumer.subscribe.assert_not_called()
        consumer.commit.assert_not_awaited()
    assert all(runner.status.state == RuntimeState.STOPPED for runner in runners)
    sessions.assert_not_called()


async def test_repeated_and_hinted_reads_keep_one_client(manager_context):
    context = manager_context
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    await asyncio.gather(*(context.manager.reconcile() for _ in range(5)))
    for _ in range(10):
        context.manager.request_reconcile()
    await eventually(lambda: context.reader.read.await_count >= 7)
    assert len(context.runners) == 1
    assert context.factory.await_count == 1
    assert context.manager.subscription_ids == {context.snapshot.subscription_id}


async def test_periodic_reconciliation_uses_jitter(manager_context, monkeypatch):
    context = manager_context
    delays = []

    def jitter(lower, upper) -> int:
        delays.append((lower, upper))
        return 1

    monkeypatch.setattr(EventWorkerDefaults, "RECONCILE_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr("syntara.eventstreams.consumer_service.random.uniform", jitter)
    await context.manager.start()
    await eventually(lambda: context.reader.read.await_count >= 2)
    assert delays[0] == (0.9, 1.1)
    assert len(context.runners) == 1


async def test_blocked_start_does_not_block_healthy_subscription(manager_context):
    context = manager_context
    healthy = context.snapshot.model_copy(update={"subscription_id": uuid4()})
    context.reader.read.return_value = [context.snapshot, healthy]
    blocked = asyncio.Event()

    def construct(binding) -> IsolatedSubscriptionRunner:
        runner = IsolatedSubscriptionRunner(binding, context.trace)
        if binding == context.snapshot:
            runner.start_release = blocked
        context.runners.append(runner)
        return runner

    context.factory.side_effect = construct
    await context.manager.start()
    await eventually(lambda: any(runner.started for runner in context.runners))
    assert next(r for r in context.runners if r.snapshot == healthy).started
    assert not next(r for r in context.runners if r.snapshot == context.snapshot).started
    assert context.manager.ready


async def test_startup_tasks_remain_bounded_under_repeated_reconciliation(manager_context):
    context = manager_context
    context.reader.read.return_value = [
        context.snapshot.model_copy(update={"subscription_id": uuid4()}) for _ in range(10)
    ]
    release = asyncio.Event()

    def construct(binding) -> IsolatedSubscriptionRunner:
        runner = IsolatedSubscriptionRunner(binding, context.trace)
        runner.start_release = release
        context.runners.append(runner)
        return runner

    context.factory.side_effect = construct
    await context.manager.start()
    await eventually(lambda: len(context.runners) == 2)
    await context.manager.reconcile()
    assert len(context.runners) == 2
    assert len(context.manager._workers) == 2
    release.set()
    await eventually(lambda: len(context.runners) == 10 and all(r.started for r in context.runners))
    assert context.factory.await_count == 10


async def test_one_subscription_failure_is_isolated(manager_context):
    context = manager_context
    bad = context.snapshot.model_copy(update={"subscription_id": uuid4()})
    context.reader.read.return_value = [bad, context.snapshot]

    def construct(binding) -> IsolatedSubscriptionRunner:
        if binding == bad:
            msg = "isolated configuration failure"
            raise ValueError(msg)
        runner = IsolatedSubscriptionRunner(binding, context.trace)
        context.runners.append(runner)
        return runner

    context.factory.side_effect = construct
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    assert context.manager.ready
    assert len(context.manager.subscription_ids) == 2


async def test_inactive_binding_stops_client_and_resume_constructs_one_replacement(manager_context):
    context = manager_context
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    context.reader.read.return_value = []
    await context.manager.reconcile()
    await eventually(lambda: not context.manager.subscription_ids)
    assert context.runners[0].stopped
    context.reader.read.return_value = [context.snapshot]
    await context.manager.reconcile()
    await eventually(lambda: len(context.runners) == 2 and context.runners[1].started)
    assert context.runners[0].snapshot.configuration == context.runners[1].snapshot.configuration


@pytest_asyncio.fixture
async def retiring_context(manager_context, monkeypatch):
    context = manager_context
    scheduled = []
    loop = asyncio.get_running_loop()
    call_later = loop.call_later

    def schedule(delay, callback, *args: object, **kwargs: object) -> asyncio.TimerHandle:
        handle: asyncio.TimerHandle = call_later(delay, callback, *args, **kwargs)
        if callback == context.manager._retry_retirement:
            scheduled.append((delay, callback, args, handle))
        return handle

    monkeypatch.setattr(loop, "call_later", schedule)
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    runner = context.runners[0]
    runner.stop_error = OSError("close unavailable")
    key = context.snapshot.subscription_id
    supervisor = context.manager._supervisors[key]
    stop = AsyncMock(wraps=supervisor.stop)
    monkeypatch.setattr(supervisor, "stop", stop)
    context.reader.read.return_value = []
    await context.manager.reconcile()
    await eventually(lambda: key in context.manager._retirement_retries and not context.manager._busy)
    return SimpleNamespace(
        context=context, key=key, supervisor=supervisor, scheduled=scheduled, runner=runner, stop=stop
    )


@pytest.mark.parametrize("next_state", ["inactive", "resumed"])
async def test_incomplete_retirement_keeps_one_delayed_retry(retiring_context, next_state):
    context, key = retiring_context.context, retiring_context.key
    assert retiring_context.supervisor.status.state == RuntimeState.DRAINING
    assert key in context.manager._retiring
    assert context.manager._pending[key] is None
    assert len(retiring_context.scheduled) == 1
    delay, retry, args, handle = retiring_context.scheduled[0]
    assert 0 < delay <= EventSchedulingDefaults.TRANSIENT_PROBE_SECONDS
    calls = retiring_context.stop.await_count
    if next_state == "resumed":
        context.reader.read.return_value = [context.snapshot]
    await context.manager.reconcile()
    await asyncio.sleep(0)
    assert context.manager._retirement_retries[key] is handle
    assert len(retiring_context.scheduled) == 1
    assert retiring_context.stop.await_count == calls
    context.factory.assert_awaited_once()
    retiring_context.runner.stop_error = None
    handle.cancel()
    retry(*args)
    await eventually(lambda: key not in context.manager._retiring and not context.manager._busy)
    assert key not in context.manager._retirement_retries
    assert retiring_context.runner.stopped
    if next_state == "resumed":
        await eventually(lambda: len(context.runners) == 2 and context.runners[1].started)
        assert context.factory.await_count == 2
    else:
        context.factory.assert_awaited_once()


async def test_shutdown_cancels_delayed_retirement_and_rejects_stale_callback(retiring_context):
    context = retiring_context.context
    _, retry, args, handle = retiring_context.scheduled[0]
    retiring_context.runner.stop_error = None
    context.manager.close_reconciliation()
    assert handle.cancelled()
    retry(*args)
    assert not context.manager._retirement_retries
    assert not context.manager._pending
    await context.manager.stop()
    assert retiring_context.runner.stopped
    context.factory.assert_awaited_once()


async def test_database_failure_closes_shared_gate_without_new_starts(manager_context):
    context = manager_context
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    context.reader.read.side_effect = OSError("database unavailable")
    context.manager.request_reconcile()
    await eventually(lambda: context.reader.read.await_count >= 2)
    assert not context.resources.gate.resolution_open(context.snapshot)
    assert not context.placement.authority(context.snapshot.subscription_id).is_current()
    assert context.snapshot.subscription_id in context.manager.owned_subscription_ids
    assert context.factory.await_count == 1


async def test_publication_revision_replaces_only_the_existing_runner(manager_context):
    context = manager_context
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    supervisor = context.manager._supervisors[context.snapshot.subscription_id]
    replacement = context.snapshot.model_copy(update={"published_version_id": uuid4()})
    context.reader.read.return_value = [replacement]
    await context.manager.reconcile()
    await eventually(lambda: len(context.runners) == 2 and context.runners[1].started)
    assert context.manager._supervisors[context.snapshot.subscription_id] is supervisor
    assert context.trace.index(("stop", RuntimeRevision.from_snapshot(context.snapshot))) < context.trace.index(
        ("start", RuntimeRevision.from_snapshot(replacement))
    )


async def test_initial_database_failure_does_not_report_ready(manager_context):
    context = manager_context
    context.reader.read.side_effect = OSError("database unavailable")
    await context.manager.start()
    assert not context.manager.ready
    context.reader.read.side_effect = None
    context.reader.read.return_value = []
    await context.manager._membership._heartbeat()
    context.manager.request_reconcile()
    await eventually(lambda: context.manager.ready)


async def test_shutdown_discards_queued_starts_and_hints(manager_context):
    context = manager_context
    context.reader.read.return_value = [
        context.snapshot.model_copy(update={"subscription_id": uuid4()}) for _ in range(10)
    ]
    release = asyncio.Event()

    def construct(binding) -> IsolatedSubscriptionRunner:
        runner = IsolatedSubscriptionRunner(binding, context.trace)
        runner.start_release = release
        context.runners.append(runner)
        return runner

    context.factory.side_effect = construct
    await context.manager.start()
    await eventually(lambda: len(context.runners) == 2)
    context.manager.close_reconciliation()
    await context.manager.stop()
    calls = context.reader.read.await_count
    context.manager.request_reconcile()
    await context.manager.reconcile()
    assert not context.manager.ready
    assert context.reader.read.await_count == calls
    assert context.factory.await_count == 2
    assert all(runner.stopped for runner in context.runners)


@pytest.mark.parametrize(
    ("subscriptions", "replicas", "expected"),
    [(0, 3, [0, 0, 0]), (1, 3, [1, 0, 0]), (5, 3, [2, 2, 1]), (6, 3, [2, 2, 2]), (3, 1, [3]), (3, 0, [])],
)
def test_count_targets_are_deterministic_and_include_zero(subscriptions, replicas, expected):
    workers = [UUID(int=index + 1) for index in range(replicas)]
    targets = placement_targets(subscriptions, reversed(workers))
    assert list(targets.values()) == expected
    assert list(targets) == workers
    if replicas:
        assert sum(targets.values()) == subscriptions


async def test_zero_target_is_ready_without_claiming_or_starting(manager_context):
    context = manager_context
    other = IsolatedPlacementService(context.pool, worker_id=UUID(int=0))
    await other.heartbeat_worker(other.worker, draining=False)
    await context.manager.start()
    assert context.manager.ready
    assert not context.manager.owned_subscription_ids
    assert not context.placement.claim_limits
    context.factory.assert_not_awaited()


async def test_missing_self_membership_closes_shared_gate_without_new_claims(manager_context, monkeypatch):
    context = manager_context
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    monkeypatch.setattr(context.placement, "list_live_workers", AsyncMock(return_value=[]))
    with pytest.raises(RuntimeError, match="absent from authoritative live membership"):
        await context.manager.reconcile()
    assert not context.manager.ready
    assert not context.resources.scheduling_open
    assert not context.resources.gate.cache_trusted()
    assert not context.placement.authority(context.snapshot.subscription_id).is_current()
    assert context.placement.claim_limits == [1]
    context.factory.assert_awaited_once()


async def test_client_construction_follows_committed_claim(manager_context):
    context = manager_context
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    key = context.snapshot.subscription_id
    assert context.pool.trace.index(("heartbeat", context.placement.worker.worker_id)) < context.pool.trace.index(
        ("claim_commit", key)
    )
    assert context.pool.trace.index(("claim_commit", key)) < context.pool.trace.index(("construct", key))


async def test_uncertain_claim_is_reconciled_before_any_start(manager_context):
    context = manager_context
    context.placement.claim_error = True
    await context.manager.start()
    context.factory.assert_not_awaited()
    assert not context.manager.ready
    key = context.snapshot.subscription_id
    assert key in context.placement.pending_reconciliation
    assert context.manager.owned_subscription_ids == {key}
    assert key in context.manager._retiring
    assert context.manager._pending[key] is None
    assert context.manager._work_ready.is_set()
    assert not context.manager._selected
    assert not context.manager.subscription_ids
    await context.manager._fill_deficit(1)
    assert context.placement.claim_limits == [1]
    context.factory.assert_not_awaited()
    context.placement.claim_error = False
    await context.manager._membership._heartbeat()
    await eventually(lambda: ("release", key) in context.pool.trace)
    await context.manager.reconcile()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    assert (
        context.pool.trace.index(("reconcile", key))
        < context.pool.trace.index(("release", key))
        < context.pool.trace.index(("claim_commit", key))
        < context.pool.trace.index(("construct", key))
    )
    assert context.placement.claim_limits == [1, 1]


async def test_connection_failure_retains_lease_and_independent_backoff(manager_context):
    context = manager_context
    context.factory.side_effect = OSError("broker unavailable")
    await context.manager.start()
    key = context.snapshot.subscription_id
    await eventually(lambda: key in context.manager._supervisors and not context.manager._busy)
    supervisor = context.manager._supervisors[key]
    assert supervisor.status.state == RuntimeState.BACKOFF
    lease = context.pool.leases[key]
    await context.manager._membership.renew_owned()
    assert context.pool.leases[key].owner == lease.owner
    assert context.pool.leases[key].expires_at >= lease.expires_at
    assert ("release", key) not in context.pool.trace
    assert context.placement.claim_limits == [1]


async def test_membership_change_moves_only_excess_owned_consumers(manager_context):
    context = manager_context
    bindings = [context.snapshot.model_copy(update={"subscription_id": UUID(int=index)}) for index in (10, 20, 30)]
    context.reader.read.return_value = bindings
    await context.manager.start()
    await eventually(lambda: len(context.runners) == 3 and all(r.started for r in context.runners))
    stable = {runner.snapshot.subscription_id: runner for runner in context.runners}
    second_placement = IsolatedPlacementService(context.pool, worker_id=UUID(int=2))
    second_runners = []

    def construct(binding) -> IsolatedSubscriptionRunner:
        runner = IsolatedSubscriptionRunner(binding, [])
        second_runners.append(runner)
        return runner

    second = EventWorkerManager(
        context.reader, AsyncMock(side_effect=construct), second_placement, EventWorkerResources()
    )
    try:
        await second.start()
        assert second.ready
        assert not second_runners  # Unexpired placements are never stolen to meet target.
        await context.manager.reconcile()
        await eventually(lambda: UUID(int=30) not in context.manager.owned_subscription_ids)
        await second.reconcile()
        await eventually(lambda: len(second_runners) == 1 and second_runners[0].started)
        await context.manager.reconcile()
        await second.reconcile()
        assert context.manager.owned_subscription_ids == {UUID(int=10), UUID(int=20)}
        assert second.owned_subscription_ids == {UUID(int=30)}
        assert all(not stable[key].stopped and stable[key].start_calls == 1 for key in (UUID(int=10), UUID(int=20)))
        assert stable[UUID(int=30)].stopped
    finally:
        await second.stop()


async def test_rejected_renewal_closes_delayed_start_and_drains(manager_context):
    context = manager_context
    release = asyncio.Event()

    def construct(binding) -> IsolatedSubscriptionRunner:
        runner = IsolatedSubscriptionRunner(binding, context.trace)
        runner.start_release = release
        context.runners.append(runner)
        return runner

    context.factory.side_effect = construct
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].start_entered.is_set())
    context.reader.read.return_value = []
    context.placement.reject_renewal = True
    await context.manager._membership.renew_owned()
    assert not context.runners[0].accepting
    await eventually(lambda: context.runners[0].stopped)
    assert not context.runners[0].open_calls
    context.factory.assert_awaited_once()


async def test_uncertain_renewal_cannot_reopen_before_old_consumer_stops(manager_context):
    context = manager_context
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    runner = context.runners[0]
    runner.drain_release = asyncio.Event()
    context.placement.renew_error = True
    key = context.snapshot.subscription_id
    try:
        await context.manager._membership.renew_owned()
        assert not runner.accepting
        await eventually(lambda: runner.drain_entered.is_set())
        await context.manager.reconcile()
        assert key in context.placement.pending_reconciliation
        assert not context.placement.authority(key).is_current()
        context.factory.assert_awaited_once()
        assert ("release", key) not in context.pool.trace
    finally:
        context.placement.renew_error = False
        runner.drain_release.set()
    await context.manager._membership._heartbeat()
    await eventually(lambda: len(context.runners) == 2 and context.runners[1].started)
    assert runner.stopped
    starts = [index for index, event in enumerate(context.pool.trace) if event == ("construct", key)]
    assert context.pool.trace.index(("release", key)) < starts[1]


async def test_cancelled_draining_request_is_not_repeated_by_stop(manager_context, monkeypatch):
    context = manager_context
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)

    async def blocked_heartbeat() -> None:
        await asyncio.Event().wait()

    heartbeat = AsyncMock(side_effect=blocked_heartbeat)
    monkeypatch.setattr(context.manager._membership, "_heartbeat", heartbeat)
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.01):
            await context.manager.begin_shutdown()
    assert heartbeat.await_count == 1
    assert context.manager._membership._draining
    assert not context.resources.accepting
    await context.manager.stop()
    assert heartbeat.await_count == 1
    assert context.runners[0].stopped
    assert context.manager.membership_task.done()


async def test_shutdown_renews_through_drain_and_releases_after_stop(manager_context):
    context = manager_context
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    runner = context.runners[0]
    runner.drain_release = asyncio.Event()
    task = asyncio.create_task(context.manager.stop())
    try:
        await runner.drain_entered.wait()
        assert not context.resources.accepting
        assert context.pool.members[context.placement.worker.worker_id].draining
        key = context.snapshot.subscription_id
        assert ("release", key) not in context.pool.trace
        await context.manager._membership.renew_owned()
        assert ("renew", key) in context.pool.trace
        assert not context.manager.membership_task.done()
    finally:
        runner.drain_release.set()
        await task
    assert runner.stopped
    assert ("release", key) in context.pool.trace
    assert context.manager.membership_task.done()


async def test_release_failure_leaves_database_lease_to_expire(manager_context):
    context = manager_context
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    context.placement.release_error = True
    key = context.snapshot.subscription_id
    await context.manager.stop()
    assert context.runners[0].stopped
    assert context.pool.leases[key].owner == context.placement.worker
    assert key not in context.manager.owned_subscription_ids
    assert context.pool.trace.count(("release", key)) == 1
    assert context.manager.membership_task.done()


async def test_held_source_starts_one_owned_transport_with_record_intake_closed(manager_context):
    context = manager_context
    context.reader.recovery_holds.return_value = {context.snapshot.source_id}
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    assert context.manager.ready
    assert context.manager.owned_subscription_ids == {context.snapshot.subscription_id}
    assert context.resources.gate.transport_open(context.snapshot)
    assert not context.resources.gate.admission_open(context.snapshot)
    assert not context.resources.gate.resolution_open(context.snapshot)
    await context.manager.reconcile()
    context.factory.assert_awaited_once()
    context.reader.recovery_holds.return_value = set()
    await context.manager.reconcile()
    assert context.resources.gate.admission_open(context.snapshot)
    context.factory.assert_awaited_once()


async def test_uncertain_lease_does_not_rearm_reconciliation_while_consumer_drains(manager_context):
    context = manager_context
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    runner = context.runners[0]
    runner.drain_release = asyncio.Event()
    key = context.snapshot.subscription_id
    context.placement.authority(key).invalidate()
    context.placement._pending.add(key)
    try:
        await context.manager.reconcile()
        assert not context.manager._hint.is_set()
        await runner.drain_entered.wait()
        before = context.reader.read.await_count
        for _ in range(3):
            await context.manager.reconcile()
            assert key in context.placement.pending_reconciliation
            assert not context.manager._hint.is_set()
        assert context.reader.read.await_count == before + 3
        assert not context.placement.authority(key).is_current()
        context.factory.assert_awaited_once()
        assert ("release", key) not in context.pool.trace
    finally:
        runner.drain_release.set()


async def test_cancelled_shutdown_retains_and_fences_slow_drain_children(manager_context, monkeypatch):
    context = manager_context
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    key = context.snapshot.subscription_id
    supervisor = context.manager._supervisors[key]
    stop = supervisor.stop
    entered, cancelled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def delayed_stop() -> SubscriptionRuntimeStatus:
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.set()
            await release.wait()
        status: SubscriptionRuntimeStatus = await stop()
        return status

    monkeypatch.setattr(supervisor, "stop", delayed_stop)
    monkeypatch.setattr(EventWorkerDefaults, "HINT_TIMEOUT_SECONDS", 0.02)
    task = asyncio.create_task(context.manager.stop())
    try:
        await entered.wait()
        task.cancel()
        await cancelled.wait()
        assert not context.manager.membership_task.done()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert context.manager.membership_task.done()
        assert context.manager._drain_tasks
        assert context.pool.leases[key].owner == context.placement.worker
        assert ("release", key) not in context.pool.trace
    finally:
        release.set()
        if not task.done():
            await task
        await eventually(lambda: not context.manager._drain_tasks)
    assert context.runners[0].stopped
    assert ("release", key) not in context.pool.trace


async def test_consumer_registration_fences_startup_before_factory_runs(manager_context):
    from syntara.eventstreams.services.runtime_control_service import EventRuntimeControlService

    context = manager_context
    controls = AsyncMock(spec=EventRuntimeControlService)
    controls.register.return_value = False
    context.manager._controls = controls
    await context.manager.start()
    await eventually(lambda: controls.register.await_count > 0)
    context.factory.assert_not_awaited()
    controls.acknowledge.assert_not_awaited()


async def test_consumer_acknowledges_pause_only_after_verified_stop(manager_context):
    from syntara.eventstreams.services.runtime_control_service import EventRuntimeControlService

    context = manager_context
    controls = AsyncMock(spec=EventRuntimeControlService)
    controls.register.return_value = True
    context.manager._controls = controls
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    context.reader.read.return_value = []
    await context.manager.reconcile()
    await eventually(lambda: context.runners[0].stopped)
    await eventually(
        lambda: any(call.args[1].state == RuntimeState.STOPPED for call in controls.acknowledge.await_args_list)
    )
    assert controls.register.await_count == 1
    assert controls.register.call_args.args[0] == context.snapshot
    assert controls.register.call_args.args[1].owner == context.placement.worker


async def test_source_replacement_acknowledges_old_runtime_before_registering_new_placement(manager_context):
    from syntara.eventstreams.services.runtime_control_service import EventRuntimeControlService

    context = manager_context
    controls = AsyncMock(spec=EventRuntimeControlService)
    events = []

    async def register(snapshot: SubscriptionSnapshot, _lease) -> bool:
        events.append(("register", snapshot.source_id))
        return True

    async def acknowledge(snapshot: SubscriptionSnapshot, status: SubscriptionRuntimeStatus, *, lease=None) -> None:
        if status.state == RuntimeState.STOPPED:
            events.append(("stopped", snapshot.source_id))

    controls.register.side_effect = register
    controls.acknowledge.side_effect = acknowledge
    context.manager._controls = controls
    await context.manager.start()
    await eventually(lambda: bool(context.runners) and context.runners[0].started)
    replacement = context.snapshot.model_copy(
        update={"source_id": uuid4(), "source_generation": 2, "configuration_revision": 2}
    )
    context.reader.read.return_value = [replacement]
    await context.manager.reconcile()
    await eventually(lambda: len(context.runners) == 2 and context.runners[1].started)
    assert context.runners[0].stopped
    assert context.runners[1].snapshot.source_id == replacement.source_id
    assert events.index(("stopped", context.snapshot.source_id)) < events.index(("register", replacement.source_id))
