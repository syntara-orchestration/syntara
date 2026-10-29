"""Placement behavior at isolated database boundaries, not live contention guarantees."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.exceptions import SafeValueError
from syntara.eventstreams.core.placement import PlacementLost, PlacementUncertainError, WorkerIdentity
from syntara.eventstreams.models.consumer_worker import EventConsumerWorker
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.services.placement_service import SubscriptionPlacementService
from syntara.eventstreams.services.subscription_supervisor import SubscriptionSupervisor
from syntara.workflows.models.workflow import Workflow
from tests.helpers.eventstream_runtime import IsolatedSubscriptionRunner
from tests.unit.eventstreams.test_connection_provider import connection_context
from tests.unit.eventstreams.test_placement import NOW, placement_lease

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from syntara.eventstreams.core.placement import SubscriptionPlacementLease


class ScriptedSessions:
    """Fresh mock sessions with explicit transaction acknowledgement and row results."""

    def __init__(self) -> None:
        """Keep a separate session script for every provider operation."""
        self.plans: deque[tuple[deque[object], deque[object], BaseException | None]] = deque()
        self.sessions: list[MagicMock] = []
        self.events: list[str] = []
        self.statements: list[object] = []
        self.before_commit: Callable[[], object] = MagicMock()

    def plan(self, reads, *, writes=(), commit_error=None):
        self.plans.append((deque(reads), deque(writes), commit_error))

    def __call__(self) -> MagicMock:
        """Construct an isolated session with observable commit and close boundaries."""
        reads, writes, commit_error = self.plans.popleft()
        session = MagicMock(spec=AsyncSession)
        self.sessions.append(session)
        session.__aenter__.return_value = session
        session.__aexit__.side_effect = lambda *_args: self.events.append("close")
        transaction = MagicMock()
        transaction.__aenter__ = AsyncMock(side_effect=lambda: self.events.append("begin"))

        async def finish(error, *_args: object) -> bool:
            if error is not None:
                self.events.append("rollback")
                return False
            self.before_commit()
            self.events.append("commit")
            if commit_error is not None:
                raise commit_error
            return False

        transaction.__aexit__ = AsyncMock(side_effect=finish)
        session.begin.return_value = transaction

        async def query(statement) -> MagicMock:
            self.statements.append(statement)
            value = reads.popleft()
            result = MagicMock()
            result.one.return_value = value
            result.one_or_none.return_value = value
            result.all.return_value = value
            return result

        async def mutate(statement) -> MagicMock:
            self.statements.append(statement)
            result = MagicMock()
            result.scalar_one_or_none.return_value = writes.popleft()
            return result

        session.exec.side_effect = query
        session.execute.side_effect = mutate
        return session


def sql(statement):
    return str(statement.compile(dialect=postgresql.dialect()))


@pytest.fixture
def context():
    snapshot = connection_context().snapshot
    worker = WorkerIdentity(deployment_id=snapshot.deployment_id)
    member = EventConsumerWorker(
        worker_id=worker.worker_id, deployment_id=worker.deployment_id, heartbeat_until=NOW + timedelta(seconds=120)
    )
    subscription = EventSubscription(
        id=snapshot.subscription_id,
        workflow_id=snapshot.workflow_id,
        project_id=snapshot.project_id,
        trigger_node_id=snapshot.trigger_node_id,
        published_version_id=snapshot.published_version_id,
        active_source_generation=snapshot.source_generation,
        configuration_revision=snapshot.configuration_revision,
        enabled_by=snapshot.enabled_by,
        created_by=uuid4(),
        updated_by=uuid4(),
        updated_at=NOW,
    )
    source = EventSubscriptionSource(
        id=snapshot.source_id,
        subscription_id=snapshot.subscription_id,
        deployment_id=snapshot.deployment_id,
        generation=snapshot.source_generation,
        integration_identity=snapshot.integration_identity,
        transport=snapshot.transport,
        configuration=snapshot.configuration,
    )
    workflow = Workflow(
        id=snapshot.workflow_id,
        project_id=snapshot.project_id,
        name="placement",
        created_by=uuid4(),
        published_version_id=snapshot.published_version_id,
        is_enabled=True,
    )
    database = ScriptedSessions()
    service = SubscriptionPlacementService(database, worker)
    return SimpleNamespace(
        snapshot=snapshot,
        worker=worker,
        member=member,
        subscription=subscription,
        source=source,
        workflow=workflow,
        database=database,
        service=service,
        authority=service.authority(subscription.id),
        lease=placement_lease(worker, subscription.id),
    )


def plan_claim(context, **kwargs: object) -> None:
    context.database.plan(
        [
            context.worker.deployment_id,
            context.member,
            NOW,
            [(context.workflow, context.subscription.id)],
            context.subscription,
            context.source,
            NOW,
        ],
        **kwargs,
    )


async def test_bootstrap_uses_persisted_deployment_with_a_fresh_process_uuid():
    database = ScriptedSessions()
    deployment_id = uuid4()
    database.plan([deployment_id])
    database.plan([deployment_id])
    first = await SubscriptionPlacementService.create(database)
    second = await SubscriptionPlacementService.create(database)
    assert first.worker.deployment_id == second.worker.deployment_id == deployment_id
    assert first.worker.worker_id != second.worker.worker_id
    assert database.events == ["begin", "commit", "close", "begin", "commit", "close"]


async def test_claim_requires_confirmed_commit_and_preserves_metadata(context):
    original = context.subscription.model_dump(exclude={"assigned_worker_id", "assignment_lease_until"})

    def before_commit() -> None:
        assert not context.authority.is_current()

    context.database.before_commit = before_commit
    plan_claim(context)
    leases = await context.service.claim_subscriptions(context.worker, limit=1)
    assert leases == [context.authority.lease]
    assert context.authority.is_current()
    assert context.database.events == ["begin", "commit", "close"]
    assert context.subscription.model_dump(exclude={"assigned_worker_id", "assignment_lease_until"}) == original
    statements = [sql(statement) for statement in context.database.statements]
    locks = [statement for statement in statements if "FOR UPDATE" in statement]
    assert "event_consumer_workers" in locks[0]
    assert "FOR UPDATE OF workflows SKIP LOCKED" in locks[1]
    assert "FROM event_subscriptions" in locks[2]
    assert locks[2].endswith("FOR UPDATE SKIP LOCKED")
    assert "FROM event_subscription_sources" in locks[3]
    assert locks[3].endswith("FOR UPDATE SKIP LOCKED")


@pytest.mark.parametrize("failure", [SQLAlchemyError("lost acknowledgement"), asyncio.CancelledError()])
async def test_uncertain_claim_cannot_start_or_reclaim_before_fresh_reconciliation(context, failure):
    plan_claim(context, commit_error=failure)
    with pytest.raises(
        asyncio.CancelledError if isinstance(failure, asyncio.CancelledError) else PlacementUncertainError
    ):
        await context.service.claim_subscriptions(context.worker, limit=1)
    assert not context.authority.is_current()
    assert not context.authority.reserve_local(object())
    assert context.subscription.id in context.service._pending
    # Model an acknowledgement lost after server commit. Only a new confirmed
    # transaction may return this row as usable authority.
    context.database.plan([context.worker.deployment_id, context.member, NOW, context.subscription, NOW])
    result = await context.service.reconcile_placement(context.subscription.id)
    assert result == context.authority.lease
    assert context.authority.is_current()
    assert len(context.database.sessions) == 2
    assert context.database.sessions[0] is not context.database.sessions[1]
    assert context.subscription.id not in context.service._pending


async def test_uncertain_claim_reconciliation_can_confirm_no_ownership(context):
    plan_claim(context, commit_error=SQLAlchemyError())
    with pytest.raises(PlacementUncertainError):
        await context.service.claim_subscriptions(context.worker, limit=1)
    context.subscription.assigned_worker_id = uuid4()
    context.database.plan([context.worker.deployment_id, context.member, NOW, context.subscription, NOW])
    assert isinstance(await context.service.reconcile_placement(context.subscription.id), PlacementLost)
    assert not context.authority.is_current()


async def test_slow_confirmed_claim_exposes_unusable_ownership_for_reconciliation(context, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(context.service, "_clock", lambda: clock[0])
    monkeypatch.setattr(context.authority, "_clock", lambda: clock[0])

    def late_commit() -> None:
        clock[0] = 100.0

    context.database.before_commit = late_commit
    plan_claim(context)
    assert await context.service.claim_subscriptions(context.worker, limit=1) == []
    assert not context.authority.is_current()
    assert context.subscription.id in context.service.pending_reconciliation
    context.database.plan([context.worker.deployment_id, context.member, NOW, context.subscription, NOW])
    assert not isinstance(await context.service.reconcile_placement(context.subscription.id), PlacementLost)
    assert context.authority.is_current()
    assert context.service.pending_reconciliation == frozenset()


@pytest.mark.parametrize(
    ("row", "field", "value"),
    [
        ("workflow", "is_enabled", False),
        ("workflow", "published_version_id", None),
        ("subscription", "paused", True),
        ("subscription", "retired", True),
        ("subscription", "desired_enabled", False),
        ("source", "retired_at", NOW),
        ("source", "deployment_id", uuid4()),
        ("member", "heartbeat_until", NOW),
    ],
)
async def test_claim_rechecks_lifecycle_publication_deployment_and_member_after_locks(context, row, field, value):
    # Member liveness must be valid on the first lookup and expired by the time
    # lifecycle locks are acquired. Other stale candidates fail their recheck.
    plan_claim(context)
    if row == "member":
        context.database.plans.clear()
        context.database.plan(
            [
                context.worker.deployment_id,
                context.member,
                NOW - timedelta(seconds=1),
                [(context.workflow, context.subscription.id)],
                context.subscription,
                context.source,
                NOW,
            ]
        )
    setattr(getattr(context, row), field, value)
    assert await context.service.claim_subscriptions(context.worker, limit=1) == []
    assert context.subscription.assigned_worker_id is None
    assert not context.authority.is_current()


async def test_expired_local_runner_must_stop_before_claiming_same_subscription(context):
    context.authority.confirm(context.lease, request_started=time.monotonic())
    old = object()
    assert context.authority.reserve_local(old)
    context.authority.invalidate()
    plan_claim(context)
    assert await context.service.claim_subscriptions(context.worker, limit=1) == []
    assert context.authority.local_in_use
    assert context.subscription.assigned_worker_id is None
    context.authority.local_stopped(old)
    plan_claim(context)
    assert len(await context.service.claim_subscriptions(context.worker, limit=1)) == 1


async def test_claim_cannot_steal_an_unexpired_subscription(context):
    owner = uuid4()
    context.subscription.assigned_worker_id = owner
    context.subscription.assignment_lease_until = NOW + timedelta(seconds=1)
    plan_claim(context)
    assert await context.service.claim_subscriptions(context.worker, limit=1) == []
    assert context.subscription.assigned_worker_id == owner
    assert context.subscription.assignment_lease_until == NOW + timedelta(seconds=1)


@pytest.mark.parametrize("draining", [False, True])
async def test_conditional_renewal_checks_owner_and_expiry_without_metadata_mutations(context, draining):
    context.member.draining = draining
    context.authority.confirm(context.lease, request_started=time.monotonic())
    context.database.plan(
        [context.worker.deployment_id, context.member, NOW, context.subscription.id, NOW],
        writes=[NOW + timedelta(seconds=60)],
    )
    renewed = await context.service.renew_placement(context.lease)
    assert renewed == context.authority.lease
    statement = context.database.statements[-1]
    compiled = sql(statement)
    assert "assigned_worker_id =" in compiled
    assert "assignment_lease_until > clock_timestamp()" in compiled
    assert "deployment_id =" in compiled
    assert compiled.split(" SET ")[1].split(" WHERE ")[0] == "assignment_lease_until=%(assignment_lease_until)s"
    assert context.authority.is_current()


async def test_expired_or_transferred_renewal_is_lost_and_cannot_revive_authority(context):
    context.authority.confirm(context.lease, request_started=time.monotonic())
    context.database.plan(
        [context.worker.deployment_id, context.member, NOW, context.subscription.id, NOW], writes=[None]
    )
    assert isinstance(await context.service.renew_placement(context.lease), PlacementLost)
    assert not context.authority.is_current()


async def test_failed_renewal_requires_reconciliation_even_if_last_lease_has_time_left(context):
    context.authority.confirm(context.lease, request_started=time.monotonic())
    context.database.plan(
        [context.worker.deployment_id, context.member, NOW, context.subscription.id, NOW],
        writes=[NOW + timedelta(seconds=60)],
        commit_error=SQLAlchemyError(),
    )
    with pytest.raises(PlacementUncertainError):
        await context.service.renew_placement(context.lease)
    assert not context.authority.is_current()
    assert isinstance(await context.service.renew_placement(context.lease), PlacementLost)
    assert len(context.database.sessions) == 1


async def test_release_requires_confirmed_local_stop_and_cannot_clear_another_owner(context):
    context.authority.confirm(context.lease, request_started=time.monotonic())
    old = object()
    context.authority.reserve_local(old)
    assert not await context.service.release_placement(context.lease)
    assert context.database.sessions == []
    context.authority.local_stopped(old)
    context.database.plan([context.worker.deployment_id], writes=[None])  # Another process has taken over.
    assert not await context.service.release_placement(context.lease)
    statement = sql(context.database.statements[-1])
    assert "assigned_worker_id =" in statement
    assert "deployment_id =" in statement
    assert "configuration_revision" not in statement.split(" WHERE ")[0]
    assert "updated_by" not in statement.split(" WHERE ")[0]


async def test_release_is_confirmed_before_success_and_stale_same_owner_release_is_ignored(context):
    later = placement_lease(context.worker, context.subscription.id, seconds=120)
    context.authority.confirm(later, request_started=time.monotonic())
    assert not await context.service.release_placement(context.lease)
    assert context.authority.is_current()
    assert context.database.sessions == []
    context.database.plan([context.worker.deployment_id], writes=[context.subscription.id])
    assert await context.service.release_placement(later)
    assert not context.authority.is_current()
    assert context.database.events[-2:] == ["commit", "close"]


async def test_uncertain_release_never_reports_success_or_allows_start(context):
    context.authority.confirm(context.lease, request_started=time.monotonic())
    context.database.plan(
        [context.worker.deployment_id], writes=[context.subscription.id], commit_error=SQLAlchemyError()
    )
    with pytest.raises(PlacementUncertainError):
        await context.service.release_placement(context.lease)
    assert not context.authority.is_current()
    assert context.subscription.id in context.service.pending_reconciliation
    assert not await context.service.release_placement(context.lease)


async def test_owner_and_deployment_mismatch_never_reach_database(context):
    context.authority.confirm(context.lease, request_started=time.monotonic())
    other = WorkerIdentity(deployment_id=uuid4())
    foreign = placement_lease(other, context.subscription.id)
    with pytest.raises(SafeValueError, match="different worker"):
        await context.service.renew_placement(foreign)
    assert not await context.service.release_placement(foreign)
    assert context.authority.is_current()
    with pytest.raises(SafeValueError, match="different worker"):
        await context.service.claim_subscriptions(other, limit=1)
    context.database.plan([uuid4()])
    with pytest.raises(SafeValueError, match="persisted deployment"):
        await context.service.list_live_workers()


async def test_heartbeat_registers_draining_membership_and_listing_filters_live_workers(context):
    context.database.plan([context.worker.deployment_id, NOW, context.member, NOW], writes=[None])
    membership = await context.service.heartbeat_worker(context.worker, draining=True)
    assert membership.draining
    assert membership.heartbeat_until == NOW + timedelta(seconds=60)
    assert context.database.events[-2:] == ["commit", "close"]
    context.database.plan([context.worker.deployment_id, []])
    assert await context.service.list_live_workers() == []
    statement = sql(context.database.statements[-1])
    assert "draining IS false" in statement
    assert "heartbeat_until > clock_timestamp()" in statement
    assert "deployment_id =" in statement
    sessions = len(context.database.sessions)
    assert await context.service.claim_subscriptions(context.worker, limit=1) == []
    assert len(context.database.sessions) == sessions


async def test_uncertain_draining_heartbeat_still_blocks_new_local_claims(context):
    context.database.plan(
        [context.worker.deployment_id, NOW, context.member, NOW], writes=[None], commit_error=SQLAlchemyError()
    )
    with pytest.raises(PlacementUncertainError):
        await context.service.heartbeat_worker(context.worker, draining=True)
    assert await context.service.claim_subscriptions(context.worker, limit=1) == []
    assert len(context.database.sessions) == 1


async def test_late_periodic_heartbeat_cannot_undo_draining(context):
    context.database.plan([context.worker.deployment_id, NOW, context.member, NOW], writes=[None])
    assert (await context.service.heartbeat_worker(context.worker, draining=True)).draining
    context.database.plan([context.worker.deployment_id, NOW, context.member, NOW], writes=[None])
    assert (await context.service.heartbeat_worker(context.worker, draining=False)).draining
    assert context.member.draining
    assert await context.service.claim_subscriptions(context.worker, limit=1) == []


async def test_stale_renewal_cannot_change_a_later_local_lease(context, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(context.authority, "_clock", lambda: clock[0])
    later = placement_lease(context.worker, context.subscription.id, seconds=120)
    context.authority.confirm(later, request_started=0.0)
    clock[0] = 100.0
    assert await context.service.renew_placement(context.lease) is later
    assert context.authority.lease is later
    assert context.authority.is_current()
    assert context.database.sessions == []
    clock[0] = 120.0
    assert not context.authority.is_current()


@pytest.mark.parametrize("state", ["expired", "uncertain"])
async def test_stale_renewal_returns_loss_only_when_current_authority_is_invalid(context, monkeypatch, state):
    clock = [0.0]
    monkeypatch.setattr(context.authority, "_clock", lambda: clock[0])
    later = placement_lease(context.worker, context.subscription.id, seconds=120)
    context.authority.confirm(later, request_started=0.0)
    if state == "expired":
        clock[0] = 120.0
    else:
        context.service.distrust()
    result = await context.service.renew_placement(context.lease)
    assert isinstance(result, PlacementLost)
    assert not context.authority.is_current()
    assert context.subscription.id in context.service.pending_reconciliation
    assert context.database.sessions == []


@pytest.mark.parametrize(("returned_id", "removed"), [(None, 0), ("worker", 1)])
async def test_stale_pruning_retains_membership_with_unexpired_dependent_leases(context, returned_id, removed):
    context.member.heartbeat_until = NOW - timedelta(seconds=1)
    context.database.plan(
        [context.worker.deployment_id, [context.member]],
        writes=[context.worker.worker_id if returned_id else None],
    )
    assert await context.service.prune_stale_workers(limit=1) == removed
    statement = sql(context.database.statements[-1])
    assert "NOT (EXISTS" in statement
    assert "assignment_lease_until > clock_timestamp()" in statement
    assert "assigned_worker_id =" in statement


@pytest.mark.parametrize("limit", [0, -1, 101])
async def test_claim_and_prune_are_bounded_before_io(context, limit):
    with pytest.raises(SafeValueError, match="batch"):
        await context.service.claim_subscriptions(context.worker, limit=limit)
    with pytest.raises(SafeValueError, match="batch"):
        await context.service.prune_stale_workers(limit=limit)
    assert context.database.sessions == []


async def test_renewal_can_commit_while_supervisor_factory_waits_for_network(context):
    plan_claim(context)
    lease = (await context.service.claim_subscriptions(context.worker, limit=1))[0]
    entered, release = asyncio.Event(), asyncio.Event()

    async def factory(snapshot) -> IsolatedSubscriptionRunner:
        assert context.database.events[-1] == "close"
        entered.set()
        await release.wait()
        return IsolatedSubscriptionRunner(snapshot, [])

    supervisor = SubscriptionSupervisor(context.snapshot.subscription_id, factory, placement=context.authority)
    starting = asyncio.create_task(supervisor.apply(context.snapshot))
    await entered.wait()
    try:
        context.database.plan(
            [context.worker.deployment_id, context.member, NOW, context.subscription.id, NOW],
            writes=[NOW + timedelta(seconds=60)],
        )
        renewed = await asyncio.wait_for(context.service.renew_placement(lease), timeout=1)
        assert renewed == context.authority.lease
        assert context.authority.local_in_use
        assert context.database.events[-1] == "close"
        assert not starting.done()
    finally:
        release.set()
        await starting
        await supervisor.stop()


async def test_competing_local_mutations_serialize_without_sharing_sessions(context):
    plan_claim(context)
    context.database.plan([context.worker.deployment_id, NOW, context.member, NOW], writes=[None])
    entered, release = asyncio.Event(), asyncio.Event()
    original = context.service._claim_locked

    async def hold(
        session: AsyncSession, workflow: Workflow, subscription_id: UUID, member: EventConsumerWorker
    ) -> SubscriptionPlacementLease | None:
        result = await original(session, workflow, subscription_id, member)
        entered.set()
        await release.wait()
        return cast("SubscriptionPlacementLease | None", result)

    context.service._claim_locked = hold
    claiming = asyncio.create_task(context.service.claim_subscriptions(context.worker, limit=1))
    await entered.wait()
    heartbeat = asyncio.create_task(context.service.heartbeat_worker(context.worker, draining=True))
    await asyncio.sleep(0)
    assert len(context.database.sessions) == 1
    release.set()
    await asyncio.gather(claiming, heartbeat)
    assert len(context.database.sessions) == 2
    assert context.database.events == ["begin", "commit", "close", "begin", "commit", "close"]
