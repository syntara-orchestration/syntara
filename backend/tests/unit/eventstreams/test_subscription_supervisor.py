"""Snapshot convergence, independent failures, and recovery with isolated runners."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio

from syntara.core.config.base import get_settings
from syntara.core.constants import EventSchedulingDefaults
from syntara.core.exceptions import SafeValueError
from syntara.eventstreams.adapters import kafka_record_runner as runner_module
from syntara.eventstreams.adapters.kafka_consumer import KafkaPartitionConsumer
from syntara.eventstreams.adapters.kafka_delivery_reader import KafkaDeliveryReader
from syntara.eventstreams.adapters.kafka_initial_position import PositionResult, PositionStatus
from syntara.eventstreams.adapters.kafka_initial_position_service import KafkaInitialPositionService
from syntara.eventstreams.adapters.kafka_record_runner import KafkaRecordRunner
from syntara.eventstreams.core.handler import ResolvedDelivery
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.core.runtime import (
    RunnerStatus,
    RuntimeFailureCode,
    RuntimeRevision,
    RuntimeState,
    SubscriptionRuntimeError,
)
from syntara.eventstreams.services import recovery_service as recovery_module
from syntara.eventstreams.services import subscription_supervisor as module
from syntara.eventstreams.services.admission_service import EventAdmissionService
from syntara.eventstreams.services.execution_preparation_service import EventExecutionPreparationService
from syntara.eventstreams.services.record_processing_service import EventRecordProcessingService
from syntara.eventstreams.services.recovery_service import EventExecutionRecoveryService
from syntara.eventstreams.services.subscription_supervisor import SubscriptionSupervisor
from syntara.workflows.models.execution import Execution
from tests.helpers.eventstream_runtime import IsolatedSubscriptionRunner
from tests.unit.eventstreams.test_connection_provider import connection_context
from tests.unit.eventstreams.test_execution_preparation_service import preparation_context
from tests.unit.eventstreams.test_record_processing_service import terminal


@pytest_asyncio.fixture
async def harness(monkeypatch):
    snapshot = connection_context().snapshot
    settings = get_settings().model_copy(update={"event_drain_timeout_seconds": 0.02})
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    monkeypatch.setattr(module, "_utc_now", lambda: now[0])
    monkeypatch.setattr(module.random, "uniform", lambda *_args: 1.0)
    trace = []
    runners = []

    def spawn(snapshot) -> IsolatedSubscriptionRunner:
        runner = IsolatedSubscriptionRunner(snapshot, trace)
        runners.append(runner)
        return runner

    factory = AsyncMock(side_effect=spawn)
    supervisor = SubscriptionSupervisor(snapshot.subscription_id, factory)
    supervisors = [supervisor]
    yield SimpleNamespace(
        snapshot=snapshot,
        supervisor=supervisor,
        factory=factory,
        spawn=spawn,
        runners=runners,
        trace=trace,
        now=now,
        supervisors=supervisors,
    )
    for runner in runners:
        runner.stop_error = None
        if runner.drain_release is not None:
            runner.drain_release.set()
        if runner.start_release is not None:
            runner.start_release.set()
    for instance in supervisors:
        await instance.stop()


async def test_repeated_and_overlapping_snapshots_keep_one_runner(harness):
    context = harness
    await asyncio.gather(*(context.supervisor.apply(context.snapshot.model_copy()) for _ in range(10)))
    runner = context.runners[0]
    await runner.run_entered.wait()
    context.factory.assert_awaited_once_with(context.snapshot)
    assert runner.start_calls == 1
    assert runner.stop_calls == 0
    status = context.supervisor.status
    assert status.state == RuntimeState.ACTIVE
    assert status.desired_revision == status.applied_revision == RuntimeRevision.from_snapshot(context.snapshot)


async def test_applied_revision_does_not_hide_runner_initialization(harness, monkeypatch):
    runner = harness.spawn(harness.snapshot)
    original_start = runner.start

    async def start() -> None:
        await original_start()
        runner.observation = RunnerStatus(state=RuntimeState.STARTING)

    monkeypatch.setattr(runner, "start", AsyncMock(side_effect=start))
    harness.factory.side_effect = None
    harness.factory.return_value = runner
    status = await harness.supervisor.apply(harness.snapshot)
    assert status.state == RuntimeState.STARTING
    assert status.applied_revision == status.desired_revision == RuntimeRevision.from_snapshot(harness.snapshot)
    runner.observation = RunnerStatus(state=RuntimeState.ACTIVE)
    assert harness.supervisor.status.state == RuntimeState.ACTIVE
    harness.factory.assert_awaited_once()


@pytest.mark.parametrize("change", [{"paused": True}, {"desired_enabled": False}, {"retired": True}])
async def test_inactive_snapshots_close_admission_and_preserve_source(harness, change):
    context = harness
    await context.supervisor.apply(context.snapshot)
    inactive = context.snapshot.model_copy(update={"configuration_revision": 2, **change})
    status = await context.supervisor.apply(inactive)
    assert status.state == RuntimeState.STOPPED
    assert not status.desired_active
    assert status.applied_revision is None
    assert context.runners[0].stopped
    assert not context.runners[0].accepting
    assert inactive.source_id == context.snapshot.source_id
    assert inactive.configuration == context.snapshot.configuration
    await context.supervisor.apply(inactive)
    context.factory.assert_awaited_once()


@pytest.mark.parametrize("change", [{"paused": True}, {"desired_enabled": False}, {"retired": True}])
async def test_initial_inactive_snapshot_never_constructs_a_client(harness, change):
    status = await harness.supervisor.apply(harness.snapshot.model_copy(update=change))
    assert status.state == RuntimeState.STOPPED
    harness.factory.assert_not_awaited()


async def test_revision_replacement_exposes_desire_while_old_runner_drains(harness):
    context = harness
    await context.supervisor.apply(context.snapshot)
    old = context.runners[0]
    old.drain_release = asyncio.Event()
    replacement = context.snapshot.model_copy(update={"configuration_revision": 2})
    change = asyncio.create_task(context.supervisor.apply(replacement))
    await old.drain_entered.wait()
    status = context.supervisor.status
    assert status.state == RuntimeState.DRAINING
    assert status.desired_revision.configuration_revision == 2
    assert status.applied_revision.configuration_revision == 1
    assert not old.accepting
    assert len(context.runners) == 1
    old.drain_release.set()
    status = await change
    assert status.state == RuntimeState.ACTIVE
    assert status.applied_revision == status.desired_revision
    assert context.trace.index(("stop", RuntimeRevision.from_snapshot(context.snapshot))) < context.trace.index(
        ("start", RuntimeRevision.from_snapshot(replacement))
    )


async def test_publication_change_without_revision_increment_replaces_runner(harness):
    await harness.supervisor.apply(harness.snapshot)
    replacement = harness.snapshot.model_copy(update={"published_version_id": uuid4()})
    await harness.supervisor.apply(replacement)
    assert len(harness.runners) == 2
    assert harness.runners[0].stopped
    assert harness.supervisor.status.applied_revision.published_version_id == replacement.published_version_id
    assert replacement.configuration_revision == harness.snapshot.configuration_revision


async def test_source_replacement_passes_new_binding_without_reusing_old_group(harness):
    await harness.supervisor.apply(harness.snapshot)
    configuration = harness.snapshot.configuration.model_copy(update={"topic": "new-topic", "group_id": "new-group"})
    replacement = harness.snapshot.model_copy(
        update={
            "source_id": uuid4(),
            "source_generation": 2,
            "configuration_revision": 2,
            "configuration": configuration,
        }
    )
    await harness.supervisor.apply(replacement)
    assert harness.runners[0].stopped
    assert harness.runners[1].snapshot == replacement
    assert harness.runners[0].snapshot.configuration != configuration


async def test_resume_passes_unchanged_source_and_group_to_fresh_runner(harness):
    context = harness
    await context.supervisor.apply(context.snapshot)
    paused = context.snapshot.model_copy(update={"paused": True, "configuration_revision": 2})
    await context.supervisor.apply(paused)
    resumed = paused.model_copy(update={"paused": False, "configuration_revision": 3})
    await context.supervisor.apply(resumed)
    assert context.runners[0].stopped
    assert context.runners[1].snapshot == resumed
    assert resumed.source_id == context.snapshot.source_id
    assert resumed.source_generation == context.snapshot.source_generation
    assert resumed.configuration == context.snapshot.configuration
    assert context.supervisor.status.applied_revision.configuration_revision == 3


@pytest.mark.parametrize("position_status", [PositionStatus.READY, PositionStatus.RECOVERY_GAP])
async def test_supervisor_resume_delegates_to_managed_runner_initialization(harness, monkeypatch, position_status):
    snapshot = harness.snapshot
    settings = get_settings().model_copy(update={"event_drain_timeout_seconds": 0.02, "event_fetch_timeout_ms": 1})
    monkeypatch.setattr(runner_module, "get_settings", lambda: settings)
    processing = MagicMock(spec=EventRecordProcessingService)
    processing.admission_eligible.return_value = True
    deliveries = MagicMock(spec=KafkaDeliveryReader)
    deliveries.first_pending.return_value = None
    runners, clients, initialized = [], [], []

    async def factory(binding) -> KafkaRecordRunner:
        client = MagicMock(spec=KafkaPartitionConsumer)
        client.topic, client.group_id = binding.configuration.topic, binding.configuration.group_id
        client.epoch, client.assignment = 9, frozenset({0})
        client.fetch.return_value = {}
        signal = asyncio.Event()
        positions = MagicMock(spec=KafkaInitialPositionService)

        async def initialize(request) -> PositionResult:
            signal.set()
            return PositionResult(
                status=position_status,
                assignment_epoch=request.assignment_epoch,
                next_offset=37 if position_status == PositionStatus.READY else None,
                reason=None if position_status == PositionStatus.READY else "missing_commit",
            )

        positions.initialize.side_effect = initialize
        runner = KafkaRecordRunner(
            binding,
            client,
            MagicMock(),
            MagicMock(spec=EventExecutionPreparationService),
            MagicMock(spec=EventAdmissionService),
            owner_worker_id="supervised",
            processing=processing,
            positions=positions,
            deliveries=deliveries,
        )

        async def start() -> None:
            await runner.on_partitions_assigned(client.assignment, client.epoch)

        client.start.side_effect = start
        runners.append(runner)
        clients.append(client)
        initialized.append(signal)
        return runner

    harness.factory.side_effect = factory
    supervisor = harness.supervisor
    try:
        await supervisor.apply(snapshot)
        await asyncio.wait_for(initialized[0].wait(), timeout=1)
        await supervisor.apply(snapshot.model_copy(update={"paused": True, "configuration_revision": 2}))
        clients[0].stop.assert_awaited_once()
        resumed = snapshot.model_copy(update={"configuration_revision": 3})
        await supervisor.apply(resumed)
        await asyncio.wait_for(initialized[1].wait(), timeout=1)
        assert runners[1].snapshot == resumed
        assert clients[1].group_id == clients[0].group_id
        assert clients[1].topic == clients[0].topic
        assert supervisor.status.state == (
            RuntimeState.ACTIVE if position_status == PositionStatus.READY else RuntimeState.BLOCKED
        )
        if position_status == PositionStatus.RECOVERY_GAP:
            assert supervisor.status.reason == "recovery_gap"
        clients[1].seek.assert_not_awaited()
        clients[1].commit.assert_not_awaited()
        processing.process.assert_not_awaited()
    finally:
        await supervisor.stop()


@pytest.mark.parametrize(("reason", "permanent"), [("recovery_gap", False), ("activity_log_unavailable", True)])
async def test_runner_holds_remain_blocked_without_restart_or_implicit_recovery(harness, reason, permanent):
    await harness.supervisor.apply(harness.snapshot)
    runner = harness.runners[0]
    runner.observation = RunnerStatus(state=RuntimeState.BLOCKED, reason=reason, permanent_content_error=permanent)
    for status in [await harness.supervisor.apply(harness.snapshot), await harness.supervisor.retry()]:
        assert status.state == RuntimeState.BLOCKED
        assert status.reason == reason
        assert status.permanent_content_error is permanent
    harness.factory.assert_awaited_once()
    assert runner.stop_calls == 0


async def test_transient_start_failures_back_off_and_open_a_local_circuit(harness):
    context = harness
    failure = SubscriptionRuntimeError(RuntimeFailureCode.CONNECTION_UNAVAILABLE, transient=True)
    context.factory.side_effect = failure
    for attempt in range(1, EventSchedulingDefaults.IMMEDIATE_ATTEMPTS + 1):
        status = await context.supervisor.apply(context.snapshot)
        assert status.failure_count == attempt
        assert status.retry_at > context.now[0]
        assert status.circuit_open is (attempt == EventSchedulingDefaults.IMMEDIATE_ATTEMPTS)
        await context.supervisor.apply(context.snapshot)
        assert context.factory.await_count == attempt
        if not status.circuit_open:
            context.now[0] = status.retry_at
    assert status.state == RuntimeState.BLOCKED
    assert status.retry_at == context.now[0] + timedelta(seconds=EventSchedulingDefaults.TRANSIENT_PROBE_SECONDS)
    context.now[0] = status.retry_at
    context.factory.side_effect = context.spawn
    assert (await context.supervisor.apply(context.snapshot)).state == RuntimeState.ACTIVE
    assert not context.supervisor.status.circuit_open


async def test_repeated_runtime_crashes_do_not_reset_the_failure_budget(harness):
    context = harness

    def crashing(snapshot) -> IsolatedSubscriptionRunner:
        runner: IsolatedSubscriptionRunner = context.spawn(snapshot)
        runner.run_error = SubscriptionRuntimeError(RuntimeFailureCode.CONNECTION_UNAVAILABLE, transient=True)
        return runner

    context.factory.side_effect = crashing
    for attempt in range(1, EventSchedulingDefaults.IMMEDIATE_ATTEMPTS + 1):
        await context.supervisor.apply(context.snapshot)
        await context.supervisor._task
        status = context.supervisor.status
        assert status.failure_count == attempt
        await context.supervisor.apply(context.snapshot)
        assert context.factory.await_count == attempt
        context.now[0] = status.retry_at
    assert status.circuit_open


async def test_configuration_failure_requires_explicit_retry_without_live_refresh(harness):
    context = harness
    context.factory.side_effect = SafeValueError("PRIVATE credential contents")
    status = await context.supervisor.apply(context.snapshot)
    assert status.state == RuntimeState.BLOCKED
    assert status.reason == "configuration_unavailable"
    assert status.retry_at is None
    assert "PRIVATE" not in status.model_dump_json()
    context.factory.side_effect = context.spawn
    context.now[0] += timedelta(days=1)
    await context.supervisor.apply(context.snapshot)
    context.factory.assert_awaited_once()
    assert (await context.supervisor.retry()).state == RuntimeState.ACTIVE


async def test_one_subscription_failure_does_not_stop_another_supervisor(harness):
    context = harness
    context.factory.side_effect = OSError("PRIVATE connection error")
    assert (await context.supervisor.apply(context.snapshot)).state == RuntimeState.BACKOFF
    healthy_snapshot = context.snapshot.model_copy(update={"subscription_id": uuid4()})
    healthy = SubscriptionSupervisor(healthy_snapshot.subscription_id, AsyncMock(side_effect=context.spawn))
    context.supervisors.append(healthy)
    assert (await healthy.apply(healthy_snapshot)).state == RuntimeState.ACTIVE
    runner = context.runners[0]
    await runner.run_entered.wait()
    await context.supervisor.apply(context.snapshot)
    assert healthy.status.state == RuntimeState.ACTIVE
    assert runner.stop_calls == 0


async def test_drain_deadline_still_stops_old_runner_before_replacement(harness):
    await harness.supervisor.apply(harness.snapshot)
    old = harness.runners[0]
    old.drain_release = asyncio.Event()
    replacement = harness.snapshot.model_copy(update={"configuration_revision": 2})
    status = await asyncio.wait_for(harness.supervisor.apply(replacement), timeout=1)
    assert old.stopped
    assert not old.accepting
    assert status.applied_revision.configuration_revision == 2


async def test_failed_stop_retains_applied_runner_and_prevents_duplicate_clients(harness):
    context = harness
    await context.supervisor.apply(context.snapshot)
    old = context.runners[0]
    old.stop_error = OSError("PRIVATE shutdown error")
    replacement = context.snapshot.model_copy(update={"configuration_revision": 2})
    status = await context.supervisor.apply(replacement)
    assert status.state == RuntimeState.DRAINING
    assert status.reason == "stop_incomplete"
    assert status.applied_revision.configuration_revision == 1
    assert status.desired_revision.configuration_revision == 2
    await context.supervisor.apply(replacement)
    context.factory.assert_awaited_once()
    old.stop_error = None
    assert (await context.supervisor.retry()).applied_revision.configuration_revision == 2
    assert old.stopped


@pytest.mark.parametrize("operation", ["stop", "pause"])
async def test_request_during_startup_closes_client_before_processing(harness, operation):
    runner = harness.spawn(harness.snapshot)
    runner.start_release = asyncio.Event()
    harness.factory.side_effect = None
    harness.factory.return_value = runner
    starting = asyncio.create_task(harness.supervisor.apply(harness.snapshot))
    await runner.start_entered.wait()
    closing = asyncio.create_task(
        harness.supervisor.stop()
        if operation == "stop"
        else harness.supervisor.apply(harness.snapshot.model_copy(update={"paused": True, "configuration_revision": 2}))
    )
    await asyncio.sleep(0)
    runner.start_release.set()
    await starting
    status = await closing
    assert status.state == RuntimeState.STOPPED
    assert runner.stopped
    assert not runner.run_entered.is_set()
    harness.factory.assert_awaited_once()


@pytest.mark.parametrize("stage", ["factory", "runner_start"])
@pytest.mark.parametrize("hook", ["stop", "drain"])
async def test_shutdown_interrupts_startup_without_waiting_for_its_release(harness, stage, hook):
    entered, release = asyncio.Event(), asyncio.Event()

    async def factory(snapshot) -> IsolatedSubscriptionRunner:
        if stage == "factory":
            entered.set()
            await release.wait()
        runner: IsolatedSubscriptionRunner = harness.spawn(snapshot)
        if stage == "runner_start":
            runner.start_entered = entered
            runner.start_release = release
        return runner

    harness.factory.side_effect = factory
    applying = asyncio.create_task(harness.supervisor.apply(harness.snapshot))
    await entered.wait()
    try:
        status = await asyncio.wait_for(getattr(harness.supervisor, hook)(), timeout=0.2)
        assert status.state == RuntimeState.STOPPED
        assert status.applied_revision is None
        await asyncio.wait_for(applying, timeout=0.2)
        assert not release.is_set()
        for runner in harness.runners:
            assert runner.stopped
            assert not runner.run_entered.is_set()
        harness.factory.assert_awaited_once()
    finally:
        release.set()
        await asyncio.gather(applying, return_exceptions=True)


@pytest.mark.parametrize("stage", ["factory", "runner_start"])
@pytest.mark.parametrize("hook", ["stop", "drain"])
async def test_shutdown_deadline_retains_startup_that_delays_cancellation(harness, monkeypatch, stage, hook):
    entered, release = asyncio.Event(), asyncio.Event()
    cancellations = []

    async def delayed() -> None:
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancellations.append(True)
            await release.wait()

    async def factory(snapshot) -> IsolatedSubscriptionRunner:
        runner: IsolatedSubscriptionRunner = harness.spawn(snapshot)
        if stage == "factory":
            await delayed()
        else:
            original_start = runner.start

            async def start() -> None:
                await delayed()
                await original_start()

            monkeypatch.setattr(runner, "start", AsyncMock(side_effect=start))
        return runner

    harness.factory.side_effect = factory
    applying = asyncio.create_task(harness.supervisor.apply(harness.snapshot))
    await entered.wait()
    try:
        for _ in range(2):
            status = await asyncio.wait_for(getattr(harness.supervisor, hook)(), timeout=0.2)
            assert status.state == RuntimeState.DRAINING
            assert status.reason == "stop_incomplete"
            assert status.applied_revision is None
            assert not applying.done()
        assert cancellations == [True]
        harness.factory.assert_awaited_once()
    finally:
        release.set()
        await asyncio.gather(applying, return_exceptions=True)
    assert harness.supervisor.status.state == RuntimeState.STOPPED
    runner = harness.runners[0]
    assert runner.stopped
    assert not runner.accepting
    assert not runner.run_entered.is_set()
    if stage == "factory":
        assert runner.start_calls == 0


@pytest.mark.parametrize("stage", ["factory", "runner_start"])
@pytest.mark.parametrize("change", [{"paused": True}, {"desired_enabled": False}, {"retired": True}])
async def test_inactive_snapshot_interrupts_unfinished_startup(harness, stage, change):
    entered, release = asyncio.Event(), asyncio.Event()

    async def factory(snapshot) -> IsolatedSubscriptionRunner:
        if stage == "factory":
            entered.set()
            await release.wait()
        runner: IsolatedSubscriptionRunner = harness.spawn(snapshot)
        if stage == "runner_start":
            runner.start_entered = entered
            runner.start_release = release
        return runner

    harness.factory.side_effect = factory
    applying = asyncio.create_task(harness.supervisor.apply(harness.snapshot))
    await entered.wait()
    inactive = harness.snapshot.model_copy(update={"configuration_revision": 2, **change})
    try:
        status = await asyncio.wait_for(harness.supervisor.apply(inactive), timeout=0.2)
        assert status.state == RuntimeState.STOPPED
        assert not status.desired_active
        assert not harness.supervisor._closed
        await asyncio.wait_for(applying, timeout=0.2)
        assert not release.is_set()
        harness.factory.assert_awaited_once()
        for runner in harness.runners:
            assert runner.stopped
            assert not runner.run_entered.is_set()
    finally:
        release.set()
        await asyncio.gather(applying, return_exceptions=True)


async def test_pause_deadline_preserves_late_factory_cleanup_without_closing_supervisor(harness):
    entered, release = asyncio.Event(), asyncio.Event()

    async def factory(snapshot) -> IsolatedSubscriptionRunner:
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()
        runner: IsolatedSubscriptionRunner = harness.spawn(snapshot)
        return runner

    harness.factory.side_effect = factory
    applying = asyncio.create_task(harness.supervisor.apply(harness.snapshot))
    await entered.wait()
    paused = harness.snapshot.model_copy(update={"paused": True, "configuration_revision": 2})
    try:
        status = await asyncio.wait_for(harness.supervisor.apply(paused), timeout=0.2)
        assert status.state == RuntimeState.DRAINING
        assert status.reason == "stop_incomplete"
        assert not status.desired_active
        assert not harness.supervisor._closed
        assert not applying.done()
    finally:
        release.set()
        await asyncio.gather(applying, return_exceptions=True)
    assert harness.supervisor.status.state == RuntimeState.STOPPED
    assert harness.runners[0].stopped
    assert harness.runners[0].start_calls == 0
    harness.factory.assert_awaited_once()


async def test_superseded_pause_does_not_start_resumed_runner_under_its_deadline(harness):
    await harness.supervisor.apply(harness.snapshot)
    old = harness.runners[0]
    old.drain_release = asyncio.Event()
    paused = harness.snapshot.model_copy(update={"paused": True, "configuration_revision": 2})
    pausing = asyncio.create_task(harness.supervisor.apply(paused))
    await old.drain_entered.wait()
    entered, release = asyncio.Event(), asyncio.Event()

    async def factory(snapshot) -> IsolatedSubscriptionRunner:
        entered.set()
        await release.wait()
        runner: IsolatedSubscriptionRunner = harness.spawn(snapshot)
        return runner

    harness.factory.side_effect = factory
    resumed = harness.snapshot.model_copy(update={"configuration_revision": 3})
    resuming = asyncio.create_task(harness.supervisor.apply(resumed))
    await asyncio.sleep(0)
    old.drain_release.set()
    try:
        await asyncio.wait_for(entered.wait(), timeout=0.2)
        assert pausing.done()
        assert pausing.result().reason is None
        assert not resuming.done()
    finally:
        release.set()
        await asyncio.gather(pausing, resuming, return_exceptions=True)
    assert harness.supervisor.status.applied_revision.configuration_revision == 3


async def test_caller_cancellation_is_preserved_when_shutdown_also_interrupts_startup(harness):
    runner = harness.spawn(harness.snapshot)
    runner.start_release = asyncio.Event()
    harness.factory.side_effect = None
    harness.factory.return_value = runner
    applying = asyncio.create_task(harness.supervisor.apply(harness.snapshot))
    await runner.start_entered.wait()
    applying.cancel()
    stopping = asyncio.create_task(harness.supervisor.stop())
    try:
        assert (await asyncio.wait_for(stopping, timeout=0.2)).state == RuntimeState.STOPPED
        with pytest.raises(asyncio.CancelledError):
            await applying
        assert runner.stopped
    finally:
        runner.start_release.set()
        await asyncio.gather(applying, stopping, return_exceptions=True)


async def test_cancelled_start_stops_partial_runner(harness):
    runner = harness.spawn(harness.snapshot)
    runner.start_release = asyncio.Event()
    harness.factory.side_effect = None
    harness.factory.return_value = runner
    starting = asyncio.create_task(harness.supervisor.apply(harness.snapshot))
    await runner.start_entered.wait()
    starting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await starting
    assert runner.stopped
    assert harness.supervisor.status.applied_revision is None


async def test_superseded_request_during_drain_never_starts_intermediate_revision(harness):
    context = harness
    await context.supervisor.apply(context.snapshot)
    old = context.runners[0]
    old.drain_release = asyncio.Event()
    second = context.snapshot.model_copy(update={"configuration_revision": 2})
    third = context.snapshot.model_copy(update={"configuration_revision": 3})
    applying_second = asyncio.create_task(context.supervisor.apply(second))
    await old.drain_entered.wait()
    applying_third = asyncio.create_task(context.supervisor.apply(third))
    await asyncio.sleep(0)
    assert context.supervisor.status.desired_revision.configuration_revision == 3
    old.drain_release.set()
    await applying_second
    await applying_third
    assert [revision.configuration_revision for action, revision in context.trace if action == "start"] == [1, 3]


async def test_drain_and_stop_hooks_close_future_starts(harness):
    await harness.supervisor.apply(harness.snapshot)
    assert (await harness.supervisor.drain()).state == RuntimeState.DRAINING
    assert not harness.runners[0].accepting
    await harness.supervisor.apply(harness.snapshot.model_copy(update={"configuration_revision": 2}))
    harness.factory.assert_awaited_once()
    stopped = await harness.supervisor.stop()
    assert stopped.state == RuntimeState.STOPPED
    assert stopped.applied_revision is None
    assert stopped.desired_active
    await harness.supervisor.stop()


async def test_mismatched_subscription_is_rejected_before_changing_desire(harness):
    other = harness.snapshot.model_copy(update={"subscription_id": uuid4()})
    with pytest.raises(ValueError, match="different subscription"):
        await harness.supervisor.apply(other)
    assert harness.supervisor.status.desired_revision is None
    harness.factory.assert_not_awaited()


async def test_factory_returning_wrong_binding_is_stopped_without_start(harness):
    runner = harness.spawn(harness.snapshot.model_copy(update={"configuration_revision": 5}))
    harness.factory.side_effect = None
    harness.factory.return_value = runner
    status = await harness.supervisor.apply(harness.snapshot)
    assert status.state == RuntimeState.BLOCKED
    assert runner.start_calls == 0
    assert runner.stopped


@pytest.mark.parametrize("change", ["paused", "unpublished", "retired", "revision"])
async def test_frozen_work_remains_discoverable_by_consumer_independent_recovery(harness, monkeypatch, change):
    context = preparation_context(monkeypatch)
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    execution = context.rows[Execution]
    frozen = execution.model_dump()
    supervisor = SubscriptionSupervisor(context.snapshot.subscription_id, harness.factory)
    harness.supervisors.append(supervisor)
    await supervisor.apply(context.snapshot)
    updates = {"configuration_revision": context.snapshot.configuration_revision + 1}
    if change == "revision":
        updates.update(published_version_id=uuid4(), runtime_credential_id=uuid4())
    else:
        updates.update(desired_enabled=False)
        if change != "unpublished":
            updates[change] = True
    await supervisor.apply(context.snapshot.model_copy(update=updates))
    if change != "revision":
        assert supervisor.status.state == RuntimeState.STOPPED
    context.store.claim_due.return_value = [prepared.claim]
    monkeypatch.setattr(recovery_module, "EventDeliveryStore", lambda _session: context.store)
    admission = MagicMock(spec=EventAdmissionService)

    async def recover(claim) -> ResolvedDelivery:
        assert context.events[-1] == "commit"
        assert claim.binding == prepared.claim.binding
        assert execution.model_dump() == frozen
        return terminal(claim.identity)

    admission.recover_claim.side_effect = recover
    recovered = await EventExecutionRecoveryService(lambda: context.session, admission).recover_due(
        "recovery", limit=10
    )
    assert isinstance(recovered[0][1], ResolvedDelivery)
    context.store.claim_due.assert_awaited_once_with("recovery", limit=10, prepared_only=True)
    admission.recover_claim.assert_awaited_once_with(prepared.claim)
    assert execution.model_dump() == frozen
    assert context.events.count("freeze") == 1
    assert harness.factory.await_count == (2 if change == "revision" else 1)
