"""Kafka position services with isolated PostgreSQL and broker/Temporal test clients."""

import asyncio
import importlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.constants import FieldLimits
from syntara.eventstreams.adapters import kafka_position_store
from syntara.eventstreams.adapters.kafka_consumer import KafkaPartitionConsumer
from syntara.eventstreams.adapters.kafka_initial_position import (
    InitializationKind,
    KafkaPartitionInitialPosition,
    PositionRequest,
    PositionStatus,
    RecoveryPolicy,
    RecoveryReplacementRequest,
    RecoveryRequest,
)
from syntara.eventstreams.adapters.kafka_initial_position_service import KafkaInitialPositionService
from syntara.eventstreams.adapters.kafka_position_control import (
    DrainEvidence,
    PartitionRecoveryControl,
    RecoveryCacheCoordination,
)
from syntara.eventstreams.adapters.kafka_position_store import KafkaInitialPositionStore
from syntara.eventstreams.core.consumer import (
    CommittedPositionResult,
    IdentityObservation,
    IdentityStatus,
    PartitionSetObservation,
    PartitionSetStatus,
    SourceIdentityObservation,
)
from syntara.eventstreams.core.deduplication import (
    CleanupCandidate,
    DeliveryClaim,
    DeliveryIdentity,
    DeliveryState,
    RecoveryReservation,
    RevisionChanged,
    TemporalAcceptance,
    TerminalDelivery,
)
from syntara.eventstreams.core.handler import ResolvedDelivery
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.recovery_hold import EventDeliveryRecoveryHold
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.services.admission_service import EventAdmissionService
from syntara.eventstreams.services.delivery_retention_service import (
    EventDeliveryRetentionService,
    release_recovery_locked,
)
from tests.integration.eventstreams.conftest import DeliveryContext


@dataclass
class Scenario:
    """Real store with controlled broker observations and assignment-local control."""

    context: DeliveryContext
    commits: dict[int, int] = field(default_factory=dict)
    beginnings: dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0})
    ends: dict[int, int] = field(default_factory=lambda: {0: 100, 1: 120})
    client: MagicMock = field(default_factory=lambda: MagicMock(spec=KafkaPartitionConsumer))
    admission: MagicMock = field(default_factory=lambda: MagicMock(spec=EventAdmissionService))
    control: MagicMock = field(default_factory=lambda: MagicMock(spec=PartitionRecoveryControl))
    cache_coordination: MagicMock = field(default_factory=lambda: MagicMock(spec=RecoveryCacheCoordination))

    def __post_init__(self) -> None:
        """Bind controlled broker observations to the real persisted source."""
        self.client.topic = self.context.snapshot.configuration.topic
        self.client.group_id = self.context.snapshot.configuration.group_id
        self.client.epoch = 7
        self.client.assignment = frozenset({0, 1})
        self.client._position_operations = set()
        self.client.position_operation.side_effect = lambda partition, *, expected_epoch: (
            KafkaPartitionConsumer.position_operation(self.client, partition, expected_epoch=expected_epoch)
        )
        self.client.committed.side_effect = self.committed
        self.client.beginning_offsets.side_effect = self.beginning
        self.client.end_offsets.side_effect = self.end
        self.client.commit.side_effect = self.commit
        self.client.observe_source_identity.return_value = SourceIdentityObservation(
            topic=self.client.topic,
            assignment_epoch=7,
            cluster_id=IdentityObservation(status=IdentityStatus.VERIFIED, value="cluster-A"),
            topic_id=IdentityObservation(status=IdentityStatus.VERIFIED, value="topic-A"),
            partitions=PartitionSetObservation(status=PartitionSetStatus.VERIFIED, partition_ids=(0, 1)),
        )
        self.control.close_and_drain.return_value = DrainEvidence(
            quiescent=True, retained_evidence_complete=True, permanent_content_error=False
        )
        self.control.is_fenced.return_value = True
        self.cache_coordination.is_coordinated.return_value = True

    @property
    def store(self) -> KafkaInitialPositionStore:
        return KafkaInitialPositionStore(self.context.session_factory)

    @property
    def service(self) -> KafkaInitialPositionService:
        return KafkaInitialPositionService(
            self.store, self.client, self.admission, self.control, cache_coordination=self.cache_coordination
        )

    def request(self, partition: int = 0) -> PositionRequest:
        snapshot = self.context.snapshot
        return PositionRequest(
            source_id=snapshot.source_id,
            source_generation=snapshot.source_generation,
            configuration_revision=snapshot.configuration_revision,
            partition=partition,
            assignment_epoch=7,
        )

    def recovery(
        self,
        *,
        policy: RecoveryPolicy = RecoveryPolicy.RETAINED_BEGINNING,
        acknowledge: bool = False,
        allow_disposition: bool = False,
    ) -> RecoveryRequest:
        return RecoveryRequest(
            **self.request().model_dump(),
            expected_recovery_revision=0,
            policy=policy,
            reason="offset_expired",
            acknowledge_duplicate_risk=acknowledge,
            allow_unscheduled_disposition=allow_disposition,
        )

    async def committed(self, partitions: list[int], **_kwargs: object) -> dict[int, CommittedPositionResult]:
        return {
            p: CommittedPositionResult.verified(p, self.commits[p])
            if p in self.commits
            else CommittedPositionResult.absent(p)
            for p in partitions
        }

    async def beginning(self, partitions: list[int], **_kwargs: object) -> dict[int, CommittedPositionResult]:
        return {p: CommittedPositionResult.verified(p, self.beginnings[p]) for p in partitions}

    async def end(self, partitions: list[int], **_kwargs: object) -> dict[int, CommittedPositionResult]:
        return {p: CommittedPositionResult.verified(p, self.ends[p]) for p in partitions}

    async def commit(self, offsets: dict[int, int], **_kwargs: object) -> None:
        self.commits.update(offsets)

    async def gap(self) -> None:
        assert (await self.service.initialize(self.request())).status == PositionStatus.READY
        self.commits.clear()
        assert (await self.service.initialize(self.request())).status == PositionStatus.RECOVERY_GAP


async def test_first_winning_boundary_is_unique_and_reused_after_interruption(
    delivery_context: DeliveryContext,
) -> None:
    scenario = Scenario(delivery_context)
    request = scenario.request()
    observation = scenario.client.observe_source_identity.return_value
    await scenario.store.capture_initial_partitions(request, observation)
    first = await scenario.store.choose_initial(
        request, observation, 100, initialization_kind=InitializationKind.FIRST_ACTIVATION
    )
    winner = await scenario.store.choose_initial(
        request, observation, 150, initialization_kind=InitializationKind.FIRST_ACTIVATION
    )
    assert first.initial_next_offset == winner.initial_next_offset == 100
    scenario.ends[0] = 200
    result = await scenario.service.initialize(request)
    assert result.status == PositionStatus.READY
    assert result.next_offset == 100
    async with delivery_context.session_factory() as session:
        positions = (
            await session.exec(
                select(KafkaPartitionInitialPosition).where(
                    col(KafkaPartitionInitialPosition.source_id) == request.source_id
                )
            )
        ).all()
        assert len(positions) == 1
        assert positions[0].initial_commit_confirmed_at is not None


async def test_normal_resume_preserves_first_boundary_and_new_partitions_initialize_independently(
    delivery_context: DeliveryContext,
) -> None:
    scenario = Scenario(delivery_context)
    assert (await scenario.service.initialize(scenario.request())).next_offset == 100
    scenario.commits[0] = 175
    scenario.ends[0] = 200
    assert (await scenario.service.initialize(scenario.request())).next_offset == 175
    assert (await scenario.service.initialize(scenario.request(1))).next_offset == 120
    first = await scenario.store.read(scenario.request())
    second = await scenario.store.read(scenario.request(1))
    assert first.position is not None
    assert second.position is not None
    assert first.position.initial_next_offset == 100
    assert second.position.initial_next_offset == 120


async def test_confirmed_recovery_before_first_boundary_allows_normal_resume(delivery_context: DeliveryContext) -> None:
    scenario = Scenario(delivery_context)
    await scenario.gap()
    scenario.beginnings[0] = 20
    recovered = await scenario.service.recover(scenario.recovery(), owner_worker_id="recovery")
    assert recovered.status == PositionStatus.READY
    assert recovered.next_offset == 20
    context = await scenario.store.read(scenario.request())
    assert context.position is not None
    assert context.position.initial_next_offset == 100
    assert context.position.recovery_boundary == 20
    assert context.position.recovery_reason == "offset_expired"
    assert not context.recovery_held
    assert (await scenario.service.initialize(scenario.request())).status == PositionStatus.READY


async def test_interrupted_confirmation_keeps_hold_and_reconciles_recorded_boundary(
    delivery_context: DeliveryContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = Scenario(delivery_context)
    await scenario.gap()
    store = scenario.store
    service = KafkaInitialPositionService(
        store, scenario.client, scenario.admission, scenario.control, cache_coordination=scenario.cache_coordination
    )
    confirm = store.confirm_recovery

    async def unavailable(*_args: object) -> None:
        raise SQLAlchemyError

    monkeypatch.setattr(store, "confirm_recovery", unavailable)
    value = scenario.recovery(policy=RecoveryPolicy.CURRENT_END)
    assert (await service.recover(value, owner_worker_id="recovery")).status == PositionStatus.BLOCKED
    pending = await store.read(scenario.request())
    assert pending.recovery_held
    assert pending.position is not None
    assert pending.position.pending_boundary == 100
    assert pending.position.recovery_confirmed_at is None
    scenario.ends[0] = 200
    monkeypatch.setattr(store, "confirm_recovery", confirm)
    assert (await service.recover(value, owner_worker_id="recovery")).next_offset == 100
    assert scenario.client.commit.await_count == 2  # initial activation plus one recovery commit
    assert not (await store.read(scenario.request())).recovery_held


async def test_recovery_hold_closes_new_admission_until_confirmation(delivery_context: DeliveryContext) -> None:
    scenario = Scenario(delivery_context)
    await scenario.gap()
    pending = await scenario.store.begin_recovery(scenario.recovery())
    assert pending.recovery_token is not None
    async with delivery_context.session_factory() as session, session.begin():
        result = await delivery_context.store(session).acquire(
            delivery_context.identity(101), delivery_context.expectation(), "late-worker"
        )
        assert isinstance(result, RevisionChanged)
    async with delivery_context.session_factory() as session:
        hold = await session.get(EventDeliveryRecoveryHold, pending.recovery_token)
        assert hold is not None
        assert hold.released_at is None


async def test_recovery_serializes_with_cleanup_and_preserves_needed_evidence(
    delivery_context: DeliveryContext,
) -> None:
    scenario = Scenario(delivery_context)
    await scenario.gap()
    # Ordinary terminal evidence, not a permanent-content rejection.
    claim = await delivery_context.claim(50)
    async with delivery_context.session_factory() as session, session.begin():
        result = await delivery_context.store(session).finalize_without_execution(claim, DeliveryState.FILTERED)
        assert isinstance(result, TerminalDelivery)
        await session.execute(
            update(EventDelivery)
            .where(col(EventDelivery.identity_digest) == claim.identity.digest)
            .values(resolved_at=datetime.now(UTC) - timedelta(hours=2))
        )

    class InterleavingVerifier:
        async def is_committed_beyond(self, _identity: object) -> bool:
            await scenario.store.begin_recovery(scenario.recovery())
            return True

    retention = EventDeliveryRetentionService(
        delivery_context.session_factory, verifier=InterleavingVerifier(), retention_seconds=3600
    )
    assert not await retention.cleanup_one(claim.identity)
    async with delivery_context.session_factory() as session:
        assert await session.get(EventDelivery, claim.identity.digest) is not None


async def test_expired_prepared_claim_stays_unresolved_when_temporal_repair_is_ambiguous(
    delivery_context: DeliveryContext,
) -> None:
    from syntara.eventstreams.core.handler import BlockedDelivery, SchedulingFailureCode

    scenario = Scenario(delivery_context)
    await scenario.gap()
    prepared = await delivery_context.claim(50, prepare=True)
    async with delivery_context.session_factory() as session, session.begin():
        await delivery_context.store(session).record_start_attempt(prepared)
    await delivery_context.expire(prepared)
    scenario.admission.recover_claim.return_value = BlockedDelivery(error_code=SchedulingFailureCode.TEMPORAL_NOT_FOUND)
    result = await scenario.service.recover(scenario.recovery(), owner_worker_id="recovery")
    assert result.reason == "ambiguous_start_unresolved"
    scenario.admission.recover_claim.assert_awaited_once()
    async with delivery_context.session_factory() as session:
        pending = await session.get(EventDelivery, prepared.identity.digest)
        assert pending is not None
        assert pending.state == DeliveryState.IN_PROGRESS
        assert pending.attempt_count == 1
        assert pending.frozen_binding == prepared.binding
    assert (await scenario.store.read(scenario.request())).recovery_held


async def test_concurrent_initializers_share_one_winning_boundary(delivery_context: DeliveryContext) -> None:
    scenario = Scenario(delivery_context)
    observation = scenario.client.observe_source_identity.return_value
    await scenario.store.capture_initial_partitions(scenario.request(), observation)
    first, second = await asyncio.gather(
        scenario.store.choose_initial(
            scenario.request(), observation, 80, initialization_kind=InitializationKind.FIRST_ACTIVATION
        ),
        scenario.store.choose_initial(
            scenario.request(), observation, 90, initialization_kind=InitializationKind.FIRST_ACTIVATION
        ),
    )
    assert first.initial_next_offset == second.initial_next_offset
    assert first.initial_next_offset in {80, 90}
    assert (await scenario.service.initialize(scenario.request())).next_offset == first.initial_next_offset


@pytest.mark.parametrize(
    "column",
    [
        "initial_next_offset",
        "recovery_boundary",
        "pending_boundary",
        "recovery_revision",
        "observed_group_next_offset",
        "superseded_recovery_boundary",
        "superseded_recovery_revision",
    ],
)
@pytest.mark.parametrize("invalid", [-1, 2**63])
async def test_database_rejects_negative_or_overflowing_offsets_and_revisions(
    delivery_context: DeliveryContext, column: str, invalid: int
) -> None:
    scenario = Scenario(delivery_context)
    assert (await scenario.service.initialize(scenario.request())).status == PositionStatus.READY
    with pytest.raises(DBAPIError):
        async with delivery_context.session_factory() as session, session.begin():
            await session.execute(
                update(KafkaPartitionInitialPosition)
                .where(col(KafkaPartitionInitialPosition.source_id) == scenario.request().source_id)
                .values(**{column: invalid})
            )


async def test_downgrade_refuses_retained_initialization_or_recovery_metadata(
    delivery_context: DeliveryContext,
) -> None:
    scenario = Scenario(delivery_context)
    assert (await scenario.service.initialize(scenario.request())).status == PositionStatus.READY
    migration = importlib.import_module(
        "syntara.core.database.migrations.versions.e73fc325e2a3_add_kafka_partition_initial_positions"
    )

    def downgrade(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()

    with pytest.raises(RuntimeError, match="Unsafe downgrade"):
        async with delivery_context.session_factory() as session, session.begin():
            connection = await session.connection()
            await connection.run_sync(downgrade)


async def test_recovery_repairs_prepared_delivery_before_changing_group_position(
    delivery_context: DeliveryContext,
) -> None:
    scenario = Scenario(delivery_context)
    await scenario.gap()
    prepared = await delivery_context.claim(50, prepare=True)
    await delivery_context.expire(prepared)

    async def accepted(claim: DeliveryClaim) -> ResolvedDelivery:
        assert claim.binding is not None
        async with delivery_context.session_factory() as session, session.begin():
            attempted = await delivery_context.store(session).record_start_attempt(claim)
            assert isinstance(attempted, DeliveryClaim)
        acceptance = TemporalAcceptance(
            execution_id=claim.identity.execution_id,
            temporal_workflow_id=claim.identity.temporal_workflow_id,
            temporal_run_id="verified-run",
            input_fingerprint=claim.binding.input_fingerprint,
        )
        async with delivery_context.session_factory() as session, session.begin():
            terminal = await delivery_context.store(session).finalize_scheduled(attempted, acceptance)
            assert isinstance(terminal, TerminalDelivery)
        return ResolvedDelivery(terminal=terminal)

    scenario.admission.recover_claim.side_effect = accepted
    result = await scenario.service.recover(scenario.recovery(), owner_worker_id="recovery")
    assert result.status == PositionStatus.READY
    scenario.admission.recover_claim.assert_awaited_once()
    async with delivery_context.session_factory() as session:
        scheduled = await session.get(EventDelivery, prepared.identity.digest)
        assert scheduled is not None
        assert scheduled.state == DeliveryState.SCHEDULED
        assert scheduled.execution_confirmed_at is not None
        assert scheduled.temporal_run_id == "verified-run"


async def test_required_acknowledgement_preserves_selected_boundary_at_current_revision(
    delivery_context: DeliveryContext,
) -> None:
    scenario = Scenario(delivery_context)
    await scenario.gap()
    scenario.control.close_and_drain.return_value = DrainEvidence(
        quiescent=True, retained_evidence_complete=False, permanent_content_error=False
    )
    original = scenario.recovery()
    blocked = await scenario.service.recover(original, owner_worker_id="recovery")
    assert blocked.reason == "duplicate_risk_acknowledgement_required"
    pending = await scenario.store.read(scenario.request())
    assert pending.position is not None
    assert pending.position.pending_boundary == 0
    assert pending.position.recovery_revision == 1
    assert pending.recovery_held
    scenario.ends[0] = 200
    acknowledged = original.model_copy(update={"expected_recovery_revision": 1, "acknowledge_duplicate_risk": True})
    assert (await scenario.service.recover(acknowledged, owner_worker_id="recovery")).status == PositionStatus.READY
    confirmed = await scenario.store.read(scenario.request())
    assert confirmed.position is not None
    assert confirmed.position.recovery_revision == 2
    assert confirmed.position.recovery_boundary == 0
    assert confirmed.position.duplicate_risk_acknowledged
    assert not confirmed.recovery_held
    assert (
        await scenario.service.recover(original, owner_worker_id="stale-request")
    ).status == PositionStatus.REVISION_CHANGED


@pytest.mark.parametrize("offset", [20, 150, 2**53 + 1, 2**63 - 2])
async def test_retained_beginning_fences_unprepared_claim_without_discarding_redelivery(
    delivery_context: DeliveryContext, offset: int
) -> None:
    scenario = Scenario(delivery_context)
    await scenario.gap()
    scenario.beginnings[0] = 20
    scenario.ends[0] = max(200, offset + 1)
    original = await delivery_context.claim(offset)
    await delivery_context.expire(original)
    recovered = await scenario.service.recover(scenario.recovery(), owner_worker_id="recovery")
    assert recovered.status == PositionStatus.READY
    assert recovered.next_offset == 20
    async with delivery_context.session_factory() as session:
        pending = await session.get(EventDelivery, original.identity.digest)
        assert pending is not None
        assert pending.state == DeliveryState.IN_PROGRESS
        assert pending.resolved_at is None
        assert pending.claim_token is None
        assert pending.last_error_code == "fenced_by_gap_recovery"
    async with delivery_context.session_factory() as session, session.begin():
        replay = await delivery_context.store(session).acquire(
            original.identity, delivery_context.expectation(), "replay"
        )
        assert isinstance(replay, DeliveryClaim)
        assert replay.token != original.token
        assert replay.binding is None


@pytest.mark.parametrize("allow_disposition", [False, True])
async def test_current_end_disposition_requires_authority_for_proven_unprepared_work(
    delivery_context: DeliveryContext,
    *,
    allow_disposition: bool,
) -> None:
    scenario = Scenario(delivery_context)
    await scenario.gap()
    claim = await delivery_context.claim(50)
    await delivery_context.expire(claim)
    result = await scenario.service.recover(
        scenario.recovery(policy=RecoveryPolicy.CURRENT_END, allow_disposition=allow_disposition),
        owner_worker_id="recovery",
    )
    async with delivery_context.session_factory() as session:
        delivery = await session.get(EventDelivery, claim.identity.digest)
        assert delivery is not None
        if allow_disposition:
            assert result.status == PositionStatus.READY
            assert result.next_offset == 100
            assert delivery.state == DeliveryState.CANCELLED
            assert delivery.last_error_code == "cancelled_by_gap_recovery"
        else:
            assert result.status == PositionStatus.BLOCKED
            assert result.reason == "retirement_authority_required"
            assert result.next_offset is None
            assert delivery.state == DeliveryState.IN_PROGRESS
            assert scenario.commits == {}


@pytest.mark.parametrize("recover", [False, True], ids=["initialization", "recovery"])
async def test_overlapping_position_operations_cannot_rewind_progress_after_ready(
    delivery_context: DeliveryContext, *, recover: bool
) -> None:
    scenario = Scenario(delivery_context)
    if recover:
        await scenario.gap()
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed_commit(offsets: dict[int, int], **kwargs: object) -> None:
        if 0 in offsets:
            entered.set()
            await release.wait()
        await scenario.commit(offsets, **kwargs)

    scenario.client.commit.side_effect = delayed_commit
    first = asyncio.create_task(
        scenario.service.recover(scenario.recovery(), owner_worker_id="first")
        if recover
        else scenario.service.initialize(scenario.request())
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        competing = (
            await scenario.service.recover(scenario.recovery(), owner_worker_id="second")
            if recover
            else await scenario.service.initialize(scenario.request())
        )
        assert competing.status == PositionStatus.BLOCKED
        assert competing.reason == "position_operation_busy"
        # A different partition is not held by this assignment-local gate.
        if not recover:
            assert (await scenario.service.initialize(scenario.request(1))).next_offset == 120
        context = await scenario.store.read(scenario.request())
        assert context.recovery_held == recover
    finally:
        release.set()
        completed = await first
    assert completed.status == PositionStatus.READY
    scenario.ends[0] = 300
    scenario.commits[0] = 250
    commits = scenario.client.commit.await_count
    retried = (
        await scenario.service.recover(scenario.recovery(), owner_worker_id="retry")
        if recover
        else await scenario.service.initialize(scenario.request())
    )
    assert retried.status == PositionStatus.READY
    assert retried.next_offset == scenario.commits[0] == 250
    assert scenario.client.commit.await_count == commits


async def test_drain_interruption_does_not_move_selected_current_end(delivery_context: DeliveryContext) -> None:
    scenario = Scenario(delivery_context)
    await scenario.gap()
    scenario.control.close_and_drain.return_value = DrainEvidence(
        quiescent=False, retained_evidence_complete=True, permanent_content_error=False
    )
    value = scenario.recovery(policy=RecoveryPolicy.CURRENT_END)
    blocked = await scenario.service.recover(value, owner_worker_id="recovery")
    assert blocked.reason == "conflicting_work_not_drained"
    selected = await scenario.store.read(scenario.request())
    assert selected.position is not None
    assert selected.position.pending_boundary == 100
    assert selected.recovery_held
    scenario.ends[0] = 200
    scenario.control.close_and_drain.return_value = DrainEvidence(
        quiescent=True, retained_evidence_complete=True, permanent_content_error=False
    )
    retried = await scenario.service.recover(value, owner_worker_id="recovery")
    assert retried.next_offset == scenario.commits[0] == 100
    assert scenario.control.close_and_drain.call_args.kwargs["boundary"] == 100


async def test_fenced_redelivery_page_cannot_hide_unresolved_prepared_work(delivery_context: DeliveryContext) -> None:
    from syntara.eventstreams.core.handler import BlockedDelivery, SchedulingFailureCode

    scenario = Scenario(delivery_context)
    await scenario.gap()
    # Put the prepared record after a full page in the store's digest ordering.
    offsets = sorted(range(FieldLimits.MAX_ITEMS_PER_PAGE + 3), key=lambda n: delivery_context.identity(n).digest)
    for offset in offsets[:-1]:
        claim = await delivery_context.claim(offset)
        await delivery_context.expire(claim)
    prepared = await delivery_context.claim(offsets[-1], prepare=True)
    await delivery_context.expire(prepared)
    scenario.admission.recover_claim.return_value = BlockedDelivery(error_code=SchedulingFailureCode.TEMPORAL_NOT_FOUND)
    first = await scenario.service.recover(scenario.recovery(), owner_worker_id="recovery")
    assert first.reason == "claims_unresolved"
    scenario.admission.recover_claim.assert_not_awaited()
    second = await scenario.service.recover(scenario.recovery(), owner_worker_id="recovery")
    assert second.reason == "ambiguous_start_unresolved"
    scenario.admission.recover_claim.assert_awaited_once()
    assert scenario.admission.recover_claim.call_args.args[0].identity == prepared.identity
    assert (await scenario.store.read(scenario.request())).recovery_held


@pytest.mark.parametrize("policy", list(RecoveryPolicy))
async def test_missing_initial_metadata_persists_unknown_history_and_can_recover(
    delivery_context: DeliveryContext, policy: RecoveryPolicy
) -> None:
    scenario = Scenario(delivery_context, commits={0: 75}, beginnings={0: 20})
    detected = await scenario.service.initialize(scenario.request())
    assert detected.status == PositionStatus.RECOVERY_GAP
    assert detected.reason == "initial_metadata_missing"
    assert detected.recovery_revision == 0
    scenario.client.seek.assert_not_awaited()
    scenario.client.commit.assert_not_awaited()
    context = await scenario.store.read(scenario.request())
    assert context.position is not None
    assert context.position.initial_metadata_missing
    assert context.position.initial_next_offset is None
    assert context.position.initialized_at is None
    assert context.position.observed_group_next_offset == 75
    assert context.position.authorized_lower_boundary is None
    winner = await scenario.store.choose_initial(
        scenario.request(),
        scenario.client.observe_source_identity.return_value,
        100,
        initialization_kind=InitializationKind.FIRST_ACTIVATION,
    )
    assert winner.initial_next_offset is None
    recovered = await scenario.service.recover(scenario.recovery(policy=policy), owner_worker_id="recovery")
    assert recovered.status == PositionStatus.READY
    assert recovered.next_offset == (20 if policy == RecoveryPolicy.RETAINED_BEGINNING else 100)
    scenario.commits[0], scenario.ends[0] = 150, 200
    assert (await scenario.service.initialize(scenario.request())).next_offset == 150
    saved = await scenario.store.read(scenario.request())
    assert saved.position is not None
    assert saved.position.initial_next_offset is None
    assert saved.position.initial_commit_confirmed_at is None
    assert saved.position.observed_group_next_offset == 75


async def test_missing_metadata_storage_failure_returns_blocked_without_position_changes(
    delivery_context: DeliveryContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = Scenario(delivery_context, commits={0: 75})
    store = scenario.store

    async def unavailable(*_args: object) -> None:
        raise SQLAlchemyError

    monkeypatch.setattr(store, "record_missing_initial", unavailable)
    service = KafkaInitialPositionService(store, scenario.client, scenario.admission, scenario.control)
    blocked = await service.initialize(scenario.request())
    assert blocked.status == PositionStatus.BLOCKED
    assert blocked.reason == "storage_unavailable"
    assert (await store.read(scenario.request())).position is None
    scenario.client.seek.assert_not_awaited()
    scenario.client.commit.assert_not_awaited()


async def test_missing_metadata_recording_and_initialization_keep_the_same_winner(
    delivery_context: DeliveryContext,
) -> None:
    scenario = Scenario(delivery_context)
    await scenario.store.capture_initial_partitions(
        scenario.request(), scenario.client.observe_source_identity.return_value
    )
    missing, initialized = await asyncio.gather(
        scenario.store.record_missing_initial(scenario.request(), 75),
        scenario.store.choose_initial(
            scenario.request(),
            scenario.client.observe_source_identity.return_value,
            100,
            initialization_kind=InitializationKind.FIRST_ACTIVATION,
        ),
    )
    assert missing.initial_next_offset == initialized.initial_next_offset
    assert missing.initial_metadata_missing == initialized.initial_metadata_missing
    if missing.initial_metadata_missing:
        assert missing.initial_next_offset is None
        assert missing.observed_group_next_offset == 75
    else:
        assert missing.initial_next_offset == 100
        assert missing.observed_group_next_offset is None


async def test_sibling_recovery_holds_converge_before_source_admission_reopens(
    delivery_context: DeliveryContext,
) -> None:
    scenario = Scenario(delivery_context)
    await scenario.gap()
    assert (await scenario.service.initialize(scenario.request(1))).status == PositionStatus.READY
    scenario.commits.pop(1)
    assert (await scenario.service.initialize(scenario.request(1))).status == PositionStatus.RECOVERY_GAP
    first = scenario.recovery()
    second = first.model_copy(update={"partition": 1})
    await scenario.store.begin_recovery(first)
    await scenario.store.begin_recovery(second)
    waiting = await scenario.service.recover(first, owner_worker_id="recovery")
    assert waiting.status == PositionStatus.BLOCKED
    assert waiting.reason == "waiting_for_source_recovery"
    context = await scenario.store.read(scenario.request())
    assert context.position is not None
    assert context.position.recovery_confirmed_at is not None
    assert context.recovery_held
    assert (await scenario.service.recover(first, owner_worker_id="recovery")).reason == "waiting_for_source_recovery"
    assert (await scenario.service.recover(second, owner_worker_id="recovery")).status == PositionStatus.READY
    assert (await scenario.service.recover(first, owner_worker_id="recovery")).status == PositionStatus.READY
    assert not (await scenario.store.read(scenario.request())).recovery_held


async def expired_recovery(scenario: Scenario, *, prepared: bool = False) -> DeliveryClaim | None:
    """Leave one frozen decision outside retention, with optional ambiguous work."""
    await scenario.gap()
    claim = await scenario.context.claim(50, prepare=True) if prepared else None
    if claim is not None:
        await scenario.context.expire(claim)
    scenario.control.close_and_drain.return_value = DrainEvidence(
        quiescent=False, retained_evidence_complete=True, permanent_content_error=False
    )
    assert (
        await scenario.service.recover(scenario.recovery(), owner_worker_id="recovery")
    ).status == PositionStatus.BLOCKED
    scenario.beginnings[0], scenario.ends[0] = 20, 200
    scenario.control.close_and_drain.return_value = DrainEvidence(
        quiescent=True, retained_evidence_complete=True, permanent_content_error=False
    )
    return claim


def replacement(
    scenario: Scenario, *, policy: RecoveryPolicy = RecoveryPolicy.RETAINED_BEGINNING
) -> RecoveryReplacementRequest:
    """Name the first pending revision/boundary explicitly."""
    return RecoveryReplacementRequest(
        **scenario.recovery(policy=policy).model_dump(exclude={"expected_recovery_revision"}),
        expected_recovery_revision=1,
        expected_pending_boundary=0,
    )


async def test_expired_recovery_requires_explicit_replacement_and_fences_old_token(
    delivery_context: DeliveryContext,
) -> None:
    scenario = Scenario(delivery_context)
    await expired_recovery(scenario)
    before = await scenario.store.read(scenario.request())
    assert before.position is not None
    old_token = before.position.recovery_token
    assert old_token is not None
    ordinary = await scenario.service.recover(scenario.recovery(), owner_worker_id="recovery")
    assert ordinary.status == PositionStatus.RECOVERY_GAP
    assert ordinary.reason == "out_of_range"
    result = await scenario.service.replace_recovery(replacement(scenario), owner_worker_id="recovery")
    assert result.status == PositionStatus.READY
    assert result.next_offset == scenario.commits[0] == 20
    after = await scenario.store.read(scenario.request())
    assert after.position is not None
    assert after.position.recovery_revision == 2
    assert after.position.superseded_recovery_revision == 1
    assert after.position.superseded_recovery_boundary == 0
    assert after.position.initial_next_offset == 100
    assert not after.recovery_held
    with pytest.raises(kafka_position_store.KafkaPositionError, match="recovery_revision_changed"):
        await scenario.store.stage_recovery(scenario.recovery(), old_token, 0)
    async with delivery_context.session_factory() as session:
        old_hold = await session.get(EventDeliveryRecoveryHold, old_token)
        assert old_hold is not None
        assert old_hold.released_at is not None


async def test_replacement_confirmation_retry_reuses_saved_boundary_without_rewinding_progress(
    delivery_context: DeliveryContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = Scenario(delivery_context)
    await expired_recovery(scenario)
    store = scenario.store
    confirm = store.confirm_recovery

    async def unavailable(*_args: object) -> None:
        raise SQLAlchemyError

    monkeypatch.setattr(store, "confirm_recovery", unavailable)
    service = KafkaInitialPositionService(store, scenario.client, scenario.admission, scenario.control)
    value = replacement(scenario, policy=RecoveryPolicy.CURRENT_END)
    assert (await service.replace_recovery(value, owner_worker_id="recovery")).status == PositionStatus.BLOCKED
    pending = await store.read(scenario.request())
    assert pending.position is not None
    assert pending.position.pending_boundary == 200
    assert pending.recovery_held
    scenario.ends[0] = 300
    monkeypatch.setattr(store, "confirm_recovery", confirm)
    commits = scenario.client.commit.await_count
    assert (await service.replace_recovery(value, owner_worker_id="recovery")).next_offset == 200
    assert scenario.client.commit.await_count == commits
    scenario.commits[0] = 250
    assert (await service.replace_recovery(value, owner_worker_id="recovery")).next_offset == 250
    assert scenario.client.commit.await_count == commits


@pytest.mark.parametrize("gate", ["acknowledgement", "content", "ownership"])
async def test_replacement_cannot_bypass_recovery_gates(delivery_context: DeliveryContext, gate: str) -> None:
    scenario = Scenario(delivery_context)
    await expired_recovery(scenario)
    scenario.client.commit.reset_mock()
    scenario.control.close_and_drain.return_value = DrainEvidence(
        quiescent=True, retained_evidence_complete=gate != "acknowledgement", permanent_content_error=gate == "content"
    )
    if gate == "ownership":

        async def revoked(*_args: object, **_kwargs: object) -> DrainEvidence:
            scenario.client.epoch += 1
            return DrainEvidence(quiescent=True, retained_evidence_complete=True, permanent_content_error=False)

        scenario.control.close_and_drain.side_effect = revoked
    value = replacement(scenario)
    if gate == "content":
        value = value.model_copy(update={"acknowledge_duplicate_risk": True})
    result = await scenario.service.replace_recovery(value, owner_worker_id="recovery")
    assert result.status == (PositionStatus.OWNERSHIP_LOST if gate == "ownership" else PositionStatus.BLOCKED)
    if gate == "content":
        assert result.reason == "permanent_content_error"
    elif gate == "acknowledgement":
        assert result.reason == "duplicate_risk_acknowledgement_required"
    state = await scenario.store.read(scenario.request())
    assert state.recovery_held
    assert state.position is not None
    assert state.position.pending_boundary == 20
    assert state.position.recovery_confirmed_at is None
    scenario.client.commit.assert_not_awaited()


async def test_replacement_preserves_ambiguous_prepared_delivery_and_calls_repair(
    delivery_context: DeliveryContext,
) -> None:
    from syntara.eventstreams.core.handler import BlockedDelivery, SchedulingFailureCode

    scenario = Scenario(delivery_context)
    prepared = await expired_recovery(scenario, prepared=True)
    assert prepared is not None
    scenario.admission.recover_claim.return_value = BlockedDelivery(error_code=SchedulingFailureCode.TEMPORAL_NOT_FOUND)
    scenario.client.commit.reset_mock()
    blocked = await scenario.service.replace_recovery(replacement(scenario), owner_worker_id="recovery")
    assert blocked.reason == "ambiguous_start_unresolved"
    scenario.admission.recover_claim.assert_awaited_once()
    scenario.client.commit.assert_not_awaited()
    async with delivery_context.session_factory() as session:
        delivery = await session.get(EventDelivery, prepared.identity.digest)
        assert delivery is not None
        assert delivery.state == DeliveryState.IN_PROGRESS
        assert delivery.frozen_binding == prepared.binding
    assert (await scenario.store.read(scenario.request())).recovery_held


@pytest.mark.parametrize("stale", ["revision", "boundary"])
async def test_replacement_rejects_stale_request_without_changing_hold(
    delivery_context: DeliveryContext, stale: str
) -> None:
    scenario = Scenario(delivery_context)
    await expired_recovery(scenario)
    before = await scenario.store.read(scenario.request())
    value = replacement(scenario).model_copy(
        update={
            "expected_recovery_revision": 0 if stale == "revision" else 1,
            "expected_pending_boundary": 10 if stale == "boundary" else 0,
        }
    )
    result = await scenario.service.replace_recovery(value, owner_worker_id="recovery")
    assert result.status == PositionStatus.REVISION_CHANGED
    after = await scenario.store.read(scenario.request())
    assert before.position is not None
    assert after.position is not None
    assert before.position.recovery_token == after.position.recovery_token
    assert after.position.recovery_revision == 1
    assert after.position.pending_boundary == 0


async def test_cleanup_cannot_enter_during_replacement_hold_transfer(
    delivery_context: DeliveryContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = Scenario(delivery_context, ends={0: 0, 1: 120})
    assert (await scenario.service.initialize(scenario.request())).status == PositionStatus.READY
    scenario.ends[0] = 100
    claim = await delivery_context.claim(50)
    async with delivery_context.session_factory() as session, session.begin():
        await delivery_context.store(session).finalize_without_execution(claim, DeliveryState.FILTERED)
        await session.execute(
            update(EventDelivery)
            .where(col(EventDelivery.identity_digest) == claim.identity.digest)
            .values(resolved_at=datetime.now(UTC) - timedelta(hours=2))
        )
    await expired_recovery(scenario)
    before = await scenario.store.read(scenario.request())
    assert before.position is not None
    old_token = before.position.recovery_token
    released, proceed, cleanup_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    release = release_recovery_locked

    async def paused_release(
        session: AsyncSession, source: EventSubscriptionSource, reservation: RecoveryReservation
    ) -> bool:
        result = await release(session, source, reservation)
        if reservation.token == old_token:
            released.set()
            await proceed.wait()
        return result

    monkeypatch.setattr(kafka_position_store, "release_recovery_locked", paused_release)
    scenario.control.close_and_drain.return_value = DrainEvidence(
        quiescent=False, retained_evidence_complete=True, permanent_content_error=False
    )
    retention = EventDeliveryRetentionService(
        delivery_context.session_factory, verifier=MagicMock(), retention_seconds=3600
    )
    candidate = retention._candidate

    async def observed_candidate(session: AsyncSession, identity: DeliveryIdentity) -> CleanupCandidate | None:
        cleanup_started.set()
        return await candidate(session, identity)

    monkeypatch.setattr(retention, "_candidate", observed_candidate)
    replacing = asyncio.create_task(
        scenario.service.replace_recovery(replacement(scenario), owner_worker_id="recovery")
    )
    cleaning: asyncio.Task[bool] | None = None
    try:
        await asyncio.wait_for(released.wait(), timeout=5)
        cleaning = asyncio.create_task(retention.cleanup_one(claim.identity))
        await asyncio.wait_for(cleanup_started.wait(), timeout=5)
        assert not cleaning.done()
    finally:
        proceed.set()
        await replacing
    assert cleaning is not None
    assert not await cleaning
    async with delivery_context.session_factory() as session:
        assert await session.get(EventDelivery, claim.identity.digest) is not None
    assert (await scenario.store.read(scenario.request())).recovery_held


@pytest.mark.parametrize("evidence", ["unknown", "replacement"])
async def test_followup_downgrade_preserves_unknown_and_replacement_evidence(
    delivery_context: DeliveryContext, evidence: str
) -> None:
    scenario = Scenario(delivery_context)
    if evidence == "unknown":
        scenario.commits[0] = 75
        assert (await scenario.service.initialize(scenario.request())).status == PositionStatus.RECOVERY_GAP
    else:
        await expired_recovery(scenario)
        assert (
            await scenario.service.replace_recovery(replacement(scenario), owner_worker_id="recovery")
        ).status == PositionStatus.READY
    migration = importlib.import_module(
        "syntara.core.database.migrations.versions.2b07573473d7_preserve_unknown_initial_boundaries_and_"
    )

    def downgrade(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()

    with pytest.raises(RuntimeError, match="Unsafe downgrade"):
        async with delivery_context.session_factory() as session, session.begin():
            connection = await session.connection()
            await connection.run_sync(downgrade)


@pytest.mark.parametrize(
    "values",
    [
        {"initial_next_offset": None},
        {"initialized_at": None},
        {"initial_metadata_missing": True},
    ],
)
async def test_unknown_initial_state_cannot_be_fabricated_by_partial_updates(
    delivery_context: DeliveryContext, values: dict[str, object]
) -> None:
    scenario = Scenario(delivery_context)
    assert (await scenario.service.initialize(scenario.request())).status == PositionStatus.READY
    with pytest.raises(DBAPIError):
        async with delivery_context.session_factory() as session, session.begin():
            await session.execute(
                update(KafkaPartitionInitialPosition)
                .where(col(KafkaPartitionInitialPosition.source_id) == scenario.request().source_id)
                .values(**values)
            )


async def test_followup_migration_preserves_existing_known_boundaries(delivery_context: DeliveryContext) -> None:
    scenario = Scenario(delivery_context)
    assert (await scenario.service.initialize(scenario.request())).status == PositionStatus.READY
    migration = importlib.import_module(
        "syntara.core.database.migrations.versions.2b07573473d7_preserve_unknown_initial_boundaries_and_"
    )
    kinds = importlib.import_module(
        "syntara.core.database.migrations.versions.91f4c2e8a6bd_add_kafka_partition_initialization_kind"
    )

    def roundtrip(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            kinds.downgrade()
            migration.downgrade()
            migration.upgrade()
            kinds.upgrade()

    async with delivery_context.session_factory() as session, session.begin():
        # Simulate a pre-kind row; its real historical boundary must survive unchanged.
        await session.execute(
            update(KafkaPartitionInitialPosition)
            .where(col(KafkaPartitionInitialPosition.source_id) == scenario.request().source_id)
            .values(initialization_kind=None)
        )
        connection = await session.connection()
        await connection.run_sync(roundtrip)
    state = await scenario.store.read(scenario.request())
    assert state.position is not None
    assert state.position.initial_next_offset == 100
    assert state.position.initial_commit_confirmed_at is not None
    assert not state.position.initial_metadata_missing
    assert state.position.observed_group_next_offset is None
    assert state.position.initialization_kind is None


async def test_first_set_exceeds_assignment_and_addition_does_not_complete_first_activation(
    delivery_context: DeliveryContext,
) -> None:
    scenario = Scenario(delivery_context)
    scenario.client.assignment = frozenset({0})
    assert (await scenario.service.initialize(scenario.request())).next_offset == 100
    first = await scenario.store.read(scenario.request())
    assert first.configuration.initial_partition_ids == (0, 1)
    assert first.source_initialized_at is None
    observation = scenario.client.observe_source_identity.return_value
    scenario.client.observe_source_identity.return_value = observation.model_copy(
        update={"partitions": PartitionSetObservation(status=PartitionSetStatus.VERIFIED, partition_ids=(0, 1, 2))}
    )
    scenario.client.assignment = frozenset({0, 2})
    scenario.beginnings[2], scenario.ends[2] = 7, 10
    assert (await scenario.service.initialize(scenario.request(2))).next_offset == 7
    added = await scenario.store.read(scenario.request(2))
    assert added.position is not None
    assert added.position.initialization_kind == InitializationKind.ADDED_PARTITION.value
    assert added.source_initialized_at is None
    assert (await scenario.service.initialize(scenario.request())).status == PositionStatus.READY
    scenario.client.assignment = frozenset({0, 1, 2})
    assert (await scenario.service.initialize(scenario.request(1))).next_offset == 120
    completed = await scenario.store.read(scenario.request())
    assert completed.source_initialized_at is not None
    assert completed.configuration.initial_partition_ids == (0, 1)
    scenario.client.observe_source_identity.return_value = observation.model_copy(
        update={"partitions": PartitionSetObservation(status=PartitionSetStatus.VERIFIED, partition_ids=(0, 1, 2, 3))}
    )
    scenario.client.assignment = frozenset({0, 1, 2, 3})
    scenario.beginnings[3], scenario.ends[3] = 0, 3
    assert (await scenario.service.initialize(scenario.request(3))).next_offset == 0
    after_growth = await scenario.store.read(scenario.request())
    assert after_growth.source_initialized_at == completed.source_initialized_at
    assert after_growth.configuration.initial_partition_ids == (0, 1)


async def test_competing_full_topic_captures_reload_the_first_winning_set(delivery_context: DeliveryContext) -> None:
    scenario = Scenario(delivery_context)
    older = scenario.client.observe_source_identity.return_value
    newer = older.model_copy(
        update={"partitions": PartitionSetObservation(status=PartitionSetStatus.VERIFIED, partition_ids=(0, 1, 2))}
    )
    first, second = await asyncio.gather(
        scenario.store.capture_initial_partitions(scenario.request(), older),
        scenario.store.capture_initial_partitions(scenario.request(), newer),
    )
    assert first.initial_partition_ids == second.initial_partition_ids
    assert first.initial_partition_ids in {(0, 1), (0, 1, 2)}
    saved = await scenario.store.read(scenario.request())
    assert saved.configuration.initial_partition_ids == first.initial_partition_ids
    assert saved.position is None


async def test_capture_survives_crash_before_row_save_and_later_addition_starts_at_zero(
    delivery_context: DeliveryContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = Scenario(delivery_context)
    store = scenario.store
    monkeypatch.setattr(store, "choose_initial", MagicMock(side_effect=SQLAlchemyError("interrupted")))
    service = KafkaInitialPositionService(store, scenario.client, scenario.admission, scenario.control)
    assert (await service.initialize(scenario.request())).status == PositionStatus.BLOCKED
    captured = await store.read(scenario.request())
    assert captured.position is None
    assert captured.configuration.initial_partition_ids == (0, 1)
    observation = scenario.client.observe_source_identity.return_value
    scenario.client.observe_source_identity.return_value = observation.model_copy(
        update={"partitions": PartitionSetObservation(status=PartitionSetStatus.VERIFIED, partition_ids=(0, 1, 2))}
    )
    scenario.client.assignment = frozenset({0, 2})
    scenario.beginnings[2], scenario.ends[2] = 0, 3
    added = await scenario.service.initialize(scenario.request(2))
    assert added.next_offset == 0
    saved = await scenario.store.read(scenario.request(2))
    assert saved.position is not None
    assert saved.position.initial_next_offset == 0
    assert saved.position.initialization_kind == InitializationKind.ADDED_PARTITION.value
    assert saved.configuration.initial_partition_ids == (0, 1)


async def test_legacy_membership_blocks_without_rewriting_real_historical_boundaries(
    delivery_context: DeliveryContext,
) -> None:
    scenario = Scenario(delivery_context)
    assert (await scenario.service.initialize(scenario.request())).next_offset == 100
    async with delivery_context.session_factory() as session, session.begin():
        source = await session.get(EventSubscriptionSource, scenario.request().source_id, with_for_update=True)
        assert source is not None
        source.configuration = source.configuration.model_copy(update={"initial_partition_ids": None})
        await session.execute(
            update(KafkaPartitionInitialPosition)
            .where(col(KafkaPartitionInitialPosition.source_id) == source.id)
            .values(initialization_kind=None)
        )
    scenario.commits[0] = 150
    scenario.ends[0] = 200
    blocked = await scenario.service.initialize(scenario.request())
    assert blocked.status == PositionStatus.RECOVERY_GAP
    assert blocked.reason == "initialization_history_unavailable"
    saved = await scenario.store.read(scenario.request())
    assert saved.configuration.initial_partition_ids is None
    assert saved.position is not None
    assert saved.position.initial_next_offset == 100
    assert saved.position.initialization_kind is None
    scenario.client.commit.reset_mock()
    recovered = await scenario.service.recover(
        scenario.recovery(policy=RecoveryPolicy.CURRENT_END), owner_worker_id="repair"
    )
    assert recovered.next_offset == 200
    resumed = await scenario.store.read(scenario.request())
    assert resumed.configuration.initial_partition_ids is None
    assert resumed.position is not None
    assert resumed.position.initial_next_offset == 100
    assert resumed.position.initialization_kind is None


async def test_kind_migration_refuses_to_erase_classified_boundaries(delivery_context: DeliveryContext) -> None:
    scenario = Scenario(delivery_context)
    await scenario.service.initialize(scenario.request())
    migration = importlib.import_module(
        "syntara.core.database.migrations.versions.91f4c2e8a6bd_add_kafka_partition_initialization_kind"
    )

    def downgrade(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()

    with pytest.raises(RuntimeError, match="Unsafe downgrade"):
        async with delivery_context.session_factory() as session, session.begin():
            connection = await session.connection()
            await connection.run_sync(downgrade)


async def test_invalid_initialization_kind_is_rejected_by_database(delivery_context: DeliveryContext) -> None:
    scenario = Scenario(delivery_context)
    await scenario.service.initialize(scenario.request())
    with pytest.raises(DBAPIError):
        async with delivery_context.session_factory() as session, session.begin():
            await session.execute(
                update(KafkaPartitionInitialPosition)
                .where(col(KafkaPartitionInitialPosition.source_id) == scenario.request().source_id)
                .values(initialization_kind="historical_guess")
            )


async def test_kind_migration_fences_uncaptured_legacy_sources_even_without_position_rows(
    delivery_context: DeliveryContext,
) -> None:
    scenario = Scenario(delivery_context)
    migration = importlib.import_module(
        "syntara.core.database.migrations.versions.91f4c2e8a6bd_add_kafka_partition_initialization_kind"
    )

    def roundtrip(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            migration.upgrade()

    async with delivery_context.session_factory() as session, session.begin():
        connection = await session.connection()
        await connection.run_sync(roundtrip)
    blocked = await scenario.service.initialize(scenario.request())
    assert blocked.status == PositionStatus.BLOCKED
    assert blocked.reason == "initialization_history_unavailable"
    saved = await scenario.store.read(scenario.request())
    assert saved.configuration.initial_partition_ids is None
    assert saved.position is None
    scenario.client.commit.assert_not_awaited()


async def test_backward_recovery_keeps_its_hold_until_external_cache_coordination(
    delivery_context: DeliveryContext,
) -> None:
    scenario = Scenario(delivery_context)
    await scenario.gap()
    scenario.client.commit.reset_mock()
    scenario.cache_coordination.is_coordinated.return_value = False
    blocked = await scenario.service.recover(scenario.recovery(), owner_worker_id="repair")
    assert blocked.reason == "cache_epoch_coordination_required"
    saved = await scenario.store.read(scenario.request())
    assert saved.recovery_held
    assert saved.position is not None
    assert saved.position.pending_boundary == 0
    assert saved.position.recovery_confirmed_at is None
    scenario.client.commit.assert_not_awaited()
