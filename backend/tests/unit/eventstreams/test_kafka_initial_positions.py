"""Isolated position-service sequencing and fail-closed recovery decisions."""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from syntara.core.constants import EventDeliveryDefaults, EventSchedulingDefaults
from syntara.eventstreams.adapters.kafka_consumer import KafkaPartitionConsumer
from syntara.eventstreams.adapters.kafka_initial_position import (
    GapReason,
    KafkaPartitionInitialPosition,
    KafkaPartitionInitialPositionRead,
    PositionRequest,
    PositionResult,
    PositionStatus,
    RecoveryPolicy,
    RecoveryReplacementRequest,
    RecoveryRequest,
)
from syntara.eventstreams.adapters.kafka_initial_position_service import KafkaInitialPositionService
from syntara.eventstreams.adapters.kafka_position_control import (
    DrainEvidence,
    PartitionRecoveryControl,
)
from syntara.eventstreams.adapters.kafka_position_store import (
    KafkaInitialPositionStore,
    KafkaPositionError,
    PositionContext,
)
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.core.consumer import (
    CommittedPositionResult,
    IdentityObservation,
    IdentityStatus,
    SourceIdentityObservation,
)
from syntara.eventstreams.core.deduplication import ClaimLost
from syntara.eventstreams.services.admission_service import EventAdmissionService

NOW = datetime(2026, 10, 21, tzinfo=UTC)


def request(partition: int = 0) -> PositionRequest:
    return PositionRequest(
        source_id=UUID(int=1), source_generation=1, configuration_revision=2, partition=partition, assignment_epoch=7
    )


def row(*, confirmed: bool = True, gap: bool = False, boundary: int = 50) -> KafkaPartitionInitialPosition:
    return KafkaPartitionInitialPosition(
        source_id=UUID(int=1),
        partition=0,
        initial_next_offset=boundary,
        initialized_at=NOW,
        initial_commit_confirmed_at=NOW if confirmed else None,
        gap_detected_at=NOW if gap else None,
        gap_reason=GapReason.MISSING_COMMIT.value if gap else None,
    )


@dataclass
class Harness:
    """Test-only stores/clients isolate orchestration from database and broker I/O."""

    position: KafkaPartitionInitialPosition | None = None
    committed: int | None = None
    beginning: int = 20
    end: int = 100
    held: bool = False
    trace: list[str] = field(default_factory=list)
    client: MagicMock = field(default_factory=lambda: MagicMock(spec=KafkaPartitionConsumer))
    store: MagicMock = field(default_factory=lambda: MagicMock(spec=KafkaInitialPositionStore))
    admission: MagicMock = field(default_factory=lambda: MagicMock(spec=EventAdmissionService))
    control: MagicMock = field(default_factory=lambda: MagicMock(spec=PartitionRecoveryControl))

    def __post_init__(self) -> None:
        """Connect isolated clients to the in-memory test evidence."""
        self.client.topic = "orders"
        self.client.group_id = "syntara.test"
        self.client.epoch = 7
        self.client.assignment = frozenset({0, 1})
        self.client._position_operations = set()
        self.client.position_operation.side_effect = lambda partition, *, expected_epoch: (
            KafkaPartitionConsumer.position_operation(self.client, partition, expected_epoch=expected_epoch)
        )
        self.client.committed.side_effect = self.read_commit
        self.client.beginning_offsets.side_effect = self.read_beginning
        self.client.end_offsets.side_effect = self.read_end
        self.client.commit.side_effect = self.commit
        self.client.seek.side_effect = self.seek
        self.client.observe_source_identity.return_value = SourceIdentityObservation(
            topic="orders",
            assignment_epoch=7,
            cluster_id=IdentityObservation(status=IdentityStatus.VERIFIED, value="cluster"),
            topic_id=IdentityObservation(status=IdentityStatus.VERIFIED, value="topic"),
        )
        self.store.read.side_effect = self.read
        self.store.choose_initial.side_effect = self.choose
        self.store.record_missing_initial.side_effect = self.record_missing_initial
        self.store.confirm_initial.side_effect = self.confirm_initial
        self.store.mark_gap.side_effect = self.mark_gap
        self.store.begin_recovery.side_effect = self.begin_recovery
        self.store.replace_recovery.side_effect = self.replace_recovery
        self.store.select_recovery_boundary.side_effect = self.select_boundary
        self.store.reconcile_claims.return_value = []
        self.store.stage_recovery.side_effect = self.stage
        self.store.confirm_recovery.side_effect = self.confirm_recovery
        self.control.close_and_drain.return_value = DrainEvidence(
            quiescent=True, retained_evidence_complete=True, permanent_content_error=False
        )
        self.control.is_fenced.return_value = True

    @property
    def service(self) -> KafkaInitialPositionService:
        return KafkaInitialPositionService(self.store, self.client, self.admission, self.control)

    async def read(self, _request: PositionRequest) -> PositionContext:
        return PositionContext(
            configuration=KafkaSourceConfiguration(topic="orders", group_id="syntara.test"),
            position=self.position,
            active=True,
            recovery_held=self.held,
        )

    async def read_commit(self, partitions: list[int], **_kwargs: object) -> dict[int, CommittedPositionResult]:
        self.trace.append("verify_commit")
        return {
            p: CommittedPositionResult.absent(p)
            if self.committed is None
            else CommittedPositionResult.verified(p, self.committed)
            for p in partitions
        }

    async def read_beginning(self, partitions: list[int], **_kwargs: object) -> dict[int, CommittedPositionResult]:
        return {p: CommittedPositionResult.verified(p, self.beginning) for p in partitions}

    async def read_end(self, partitions: list[int], **_kwargs: object) -> dict[int, CommittedPositionResult]:
        return {p: CommittedPositionResult.verified(p, self.end) for p in partitions}

    async def choose(
        self, _request: PositionRequest, _observation: SourceIdentityObservation, boundary: int
    ) -> KafkaPartitionInitialPosition:
        self.trace.append("save_initial")
        self.position = row(confirmed=False, boundary=boundary)
        return self.position

    async def record_missing_initial(self, _request: PositionRequest, offset: int) -> KafkaPartitionInitialPosition:
        self.position = KafkaPartitionInitialPosition(
            source_id=UUID(int=1),
            partition=0,
            initial_next_offset=None,
            initialized_at=None,
            initial_metadata_missing=True,
            observed_group_next_offset=offset,
            gap_detected_at=NOW,
            gap_reason=GapReason.INITIAL_METADATA_MISSING.value,
        )
        return self.position

    async def replace_recovery(self, value: RecoveryReplacementRequest, boundary: int) -> KafkaPartitionInitialPosition:
        assert self.position is not None
        assert self.position.pending_boundary == value.expected_pending_boundary
        assert self.position.recovery_revision == value.expected_recovery_revision
        self.position.superseded_recovery_revision = self.position.recovery_revision
        self.position.superseded_recovery_boundary = self.position.pending_boundary
        self.position.recovery_revision += 1
        self.position.recovery_token = UUID(int=43)
        self.position.pending_boundary = boundary
        self.position.pending_policy = value.policy.value
        self.position.pending_reason = value.reason
        self.position.pending_duplicate_risk_acknowledged = value.acknowledge_duplicate_risk
        return self.position

    async def seek(self, partition: int, offset: int, **_kwargs: object) -> None:
        self.trace.append(f"seek:{partition}:{offset}")

    async def commit(self, offsets: dict[int, int], **_kwargs: object) -> None:
        self.trace.append("commit")
        self.committed = next(iter(offsets.values()))

    async def confirm_initial(self, _request: PositionRequest, **_kwargs: object) -> None:
        self.trace.append("confirm_initial")
        assert self.position is not None
        self.position.initial_commit_confirmed_at = NOW

    async def mark_gap(self, _request: PositionRequest, reason: GapReason) -> None:
        if self.position is not None:
            self.position.gap_reason = reason.value
            self.position.gap_detected_at = NOW

    async def begin_recovery(self, value: RecoveryRequest) -> KafkaPartitionInitialPosition:
        self.trace.append("hold_and_close")
        assert self.position is not None
        self.held = True
        if self.position.recovery_token is None:
            self.position.recovery_token = UUID(int=42)
            self.position.recovery_revision += 1
            self.position.pending_policy = value.policy.value
            self.position.pending_reason = value.reason
            self.position.pending_duplicate_risk_acknowledged = value.acknowledge_duplicate_risk
        return self.position

    async def select_boundary(
        self, _request: RecoveryRequest, _token: UUID, boundary: int
    ) -> KafkaPartitionInitialPosition:
        self.trace.append("select_boundary")
        assert self.position is not None
        if self.position.pending_boundary is None:
            self.position.pending_boundary = boundary
        return self.position

    async def stage(self, _request: RecoveryRequest, _token: UUID, boundary: int) -> KafkaPartitionInitialPosition:
        self.trace.append("stage_boundary")
        assert self.position is not None
        assert self.position.pending_boundary == boundary
        return self.position

    async def confirm_recovery(self, value: RecoveryRequest, _token: UUID, boundary: int) -> None:
        self.trace.append("confirm_recovery")
        assert self.position is not None
        self.position.recovery_boundary = boundary
        self.position.recovery_confirmed_at = NOW
        self.position.recovery_policy = value.policy.value
        self.position.recovery_reason = value.reason
        self.position.duplicate_risk_acknowledged = value.acknowledge_duplicate_risk
        self.position.pending_boundary = None
        self.position.recovery_token = None
        self.position.gap_detected_at = None
        self.position.gap_reason = None
        self.held = False


def recovery(
    *, acknowledge: bool = False, policy: RecoveryPolicy = RecoveryPolicy.RETAINED_BEGINNING
) -> RecoveryRequest:
    return RecoveryRequest(
        **request().model_dump(),
        expected_recovery_revision=0,
        policy=policy,
        reason="offset_expired",
        acknowledge_duplicate_risk=acknowledge,
    )


@pytest.mark.parametrize("partition", [0, 1])
async def test_initialization_persists_before_seek_and_confirms_before_permission(partition: int) -> None:
    h = Harness()
    result = await h.service.initialize(request(partition))
    assert result.status == PositionStatus.READY
    assert result.next_offset == 100
    assert (
        h.trace.index("save_initial")
        < h.trace.index(f"seek:{partition}:100")
        < h.trace.index("commit")
        < h.trace.index("confirm_initial")
    )
    assert h.trace[h.trace.index("commit") + 1] == "verify_commit"
    h.client.commit.assert_awaited_once_with({partition: 100}, expected_epoch=7)


async def test_concurrent_initializer_uses_the_saved_winning_boundary() -> None:
    h = Harness()

    async def winner(*_args: object) -> KafkaPartitionInitialPosition:
        h.position = row(confirmed=False, boundary=40)
        return h.position

    h.store.choose_initial.side_effect = winner
    result = await h.service.initialize(request())
    assert result.next_offset == 40
    h.client.commit.assert_awaited_once_with({0: 40}, expected_epoch=7)


async def test_winner_committed_after_first_database_read_is_reloaded_without_a_false_gap() -> None:
    h = Harness()

    async def winning_commit(partitions: list[int], **kwargs: object) -> dict[int, CommittedPositionResult]:
        h.position = row(boundary=40)
        h.committed = 40
        return await h.read_commit(partitions, **kwargs)

    h.client.committed.side_effect = winning_commit
    result = await h.service.initialize(request())
    assert result.status == PositionStatus.READY
    assert result.next_offset == 40
    h.store.mark_gap.assert_not_awaited()
    h.store.choose_initial.assert_not_awaited()
    h.client.commit.assert_not_awaited()


async def test_interrupted_activation_reuses_initial_boundary_after_arrivals() -> None:
    h = Harness(position=row(confirmed=False, boundary=50))
    result = await h.service.initialize(request())
    assert result.status == PositionStatus.READY
    assert result.next_offset == 50
    h.store.choose_initial.assert_not_awaited()
    h.client.commit.assert_awaited_once_with({0: 50}, expected_epoch=7)


async def test_lost_initial_confirmation_response_uses_existing_group_commit() -> None:
    h = Harness()
    h.store.confirm_initial.side_effect = SQLAlchemyError("unavailable")
    assert (await h.service.initialize(request())).status == PositionStatus.BLOCKED
    h.end = 150
    h.store.confirm_initial.side_effect = h.confirm_initial
    result = await h.service.initialize(request())
    assert result.status == PositionStatus.READY
    assert result.next_offset == 100
    assert h.store.choose_initial.await_count == 1
    assert h.client.commit.await_count == 1


async def test_restart_and_republish_use_valid_group_progress_without_rewriting_boundary() -> None:
    h = Harness(position=row(), committed=75)
    result = await h.service.initialize(request())
    assert result.next_offset == 75
    assert h.position is not None
    assert h.position.initial_next_offset == 50
    h.client.commit.assert_not_awaited()
    h.store.choose_initial.assert_not_awaited()
    h.store.confirm_initial.assert_not_awaited()


@pytest.mark.parametrize(
    ("committed", "beginning", "reason"),
    [
        (None, 20, GapReason.MISSING_COMMIT),
        (101, 20, GapReason.OUT_OF_RANGE),
        (40, 20, GapReason.BELOW_AUTHORIZED_BOUNDARY),
        (60, 70, GapReason.OUT_OF_RANGE),
    ],
)
async def test_established_gaps_never_reset_or_reuse_initial_metadata(
    committed: int | None, beginning: int, reason: GapReason
) -> None:
    h = Harness(position=row(), committed=committed, beginning=beginning)
    result = await h.service.initialize(request())
    assert result.status == PositionStatus.RECOVERY_GAP
    assert result.reason == reason.value
    h.store.mark_gap.assert_awaited_once_with(request(), reason)
    h.client.commit.assert_not_awaited()
    h.client.seek.assert_not_awaited()


@pytest.mark.parametrize("established", [False, True])
async def test_uncertain_offsets_never_authorize_commit(*, established: bool) -> None:
    h = Harness(position=row(confirmed=established))
    h.client.committed.return_value = {0: CommittedPositionResult.uncertain(0, "invalid offset")}
    h.client.committed.side_effect = None
    result = await h.service.initialize(request())
    assert result.status == (PositionStatus.RECOVERY_GAP if established else PositionStatus.BLOCKED)
    h.client.commit.assert_not_awaited()


async def test_unavailable_commit_is_a_dependency_block_without_reset() -> None:
    h = Harness(position=row())
    h.client.committed.side_effect = None
    h.client.committed.return_value = {0: CommittedPositionResult.unavailable(0, "timeout")}
    assert (await h.service.initialize(request())).status == PositionStatus.BLOCKED
    h.store.mark_gap.assert_not_awaited()
    h.client.commit.assert_not_awaited()


async def test_source_recreation_blocks_without_changing_positions() -> None:
    h = Harness(position=row(), committed=75)
    h.store.verify_identity.side_effect = KafkaPositionError("source_recreated", PositionStatus.RECOVERY_GAP)
    result = await h.service.initialize(request())
    assert result.status == PositionStatus.RECOVERY_GAP
    h.client.commit.assert_not_awaited()


async def test_recovery_below_first_boundary_becomes_the_effective_lower_bound() -> None:
    h = Harness(position=row(gap=True))
    result = await h.service.recover(recovery(), owner_worker_id="recovery")
    assert result.status == PositionStatus.READY
    assert result.next_offset == 20
    assert h.position is not None
    assert h.position.initial_next_offset == 50
    assert h.position.authorized_lower_boundary == 20
    assert (
        h.trace.index("hold_and_close")
        < h.trace.index("stage_boundary")
        < h.trace.index("commit")
        < h.trace.index("confirm_recovery")
    )
    assert (await h.service.initialize(request())).status == PositionStatus.READY


@pytest.mark.parametrize("acknowledge", [False, True])
async def test_missing_retained_evidence_requires_explicit_duplicate_risk_acknowledgement(*, acknowledge: bool) -> None:
    h = Harness(position=row(gap=True))
    h.control.close_and_drain.return_value = DrainEvidence(
        quiescent=True, retained_evidence_complete=False, permanent_content_error=False
    )
    result = await h.service.recover(recovery(acknowledge=acknowledge), owner_worker_id="recovery")
    assert result.status == (PositionStatus.READY if acknowledge else PositionStatus.BLOCKED)
    if not acknowledge:
        assert result.reason == "duplicate_risk_acknowledgement_required"
        assert h.held
        h.client.commit.assert_not_awaited()


@pytest.mark.parametrize("policy", list(RecoveryPolicy))
async def test_duplicate_acknowledgement_cannot_bypass_permanent_content_gate(policy: RecoveryPolicy) -> None:
    h = Harness(position=row(gap=True))
    h.control.close_and_drain.return_value = DrainEvidence(
        quiescent=True, retained_evidence_complete=False, permanent_content_error=True
    )
    result = await h.service.recover(recovery(acknowledge=True, policy=policy), owner_worker_id="recovery")
    assert result.reason == "permanent_content_error"
    assert h.held
    h.store.reconcile_claims.assert_not_awaited()
    h.client.commit.assert_not_awaited()


async def test_recovery_calls_upstream_ambiguity_repair_and_preserves_unresolved_work() -> None:
    from syntara.eventstreams.services.deduplication_store import EventDeliveryStore
    from tests.unit.eventstreams.test_deduplication_store import delivery

    h = Harness(position=row(gap=True))
    claim = EventDeliveryStore._claim(delivery())
    h.store.reconcile_claims.return_value = [claim]
    h.admission.recover_claim.return_value = ClaimLost()
    result = await h.service.recover(recovery(), owner_worker_id="recovery")
    assert result.reason == "ambiguous_start_unresolved"
    h.admission.recover_claim.assert_awaited_once_with(claim)
    h.store.stage_recovery.assert_not_awaited()
    h.client.commit.assert_not_awaited()
    assert h.held


@pytest.mark.parametrize("phase", ["drain", "commit"])
async def test_ownership_loss_keeps_recovery_unconfirmed(phase: str) -> None:
    h = Harness(position=row(gap=True))

    async def lost_drain(*_args: object, **_kwargs: object) -> DrainEvidence:
        h.client.epoch += 1
        return DrainEvidence(quiescent=True, retained_evidence_complete=True, permanent_content_error=False)

    async def lost_commit(offsets: dict[int, int], **kwargs: object) -> None:
        await h.commit(offsets, **kwargs)
        h.client.epoch += 1

    if phase == "drain":
        h.control.close_and_drain.side_effect = lost_drain
    else:
        h.client.commit.side_effect = lost_commit
    result = await h.service.recover(recovery(), owner_worker_id="recovery")
    assert result.status == PositionStatus.OWNERSHIP_LOST
    h.store.confirm_recovery.assert_not_awaited()
    assert h.held


async def test_interrupted_recovery_confirmation_reconciles_saved_boundary_without_recommitting() -> None:
    h = Harness(position=row(gap=True))
    h.store.confirm_recovery.side_effect = SQLAlchemyError("unavailable")
    assert (
        await h.service.recover(recovery(policy=RecoveryPolicy.CURRENT_END), owner_worker_id="recovery")
    ).status == PositionStatus.BLOCKED
    assert h.position is not None
    assert h.position.pending_boundary == 100
    assert h.held
    h.end = 150
    h.store.confirm_recovery.side_effect = h.confirm_recovery
    result = await h.service.recover(recovery(policy=RecoveryPolicy.CURRENT_END), owner_worker_id="recovery")
    assert result.status == PositionStatus.READY
    assert result.next_offset == 100
    assert h.client.commit.await_count == 1
    # Retrying a confirmed operation follows current progress, never rewinds it.
    h.committed = 125
    assert (
        await h.service.recover(recovery(policy=RecoveryPolicy.CURRENT_END), owner_worker_id="recovery")
    ).next_offset == 125
    assert h.client.commit.await_count == 1


async def test_revision_conflict_stops_before_broker_calls() -> None:
    h = Harness()
    h.store.read.side_effect = KafkaPositionError("source_revision_changed", PositionStatus.REVISION_CHANGED)
    assert (await h.service.initialize(request())).status == PositionStatus.REVISION_CHANGED
    h.client.observe_source_identity.assert_not_awaited()


@pytest.mark.parametrize("invalid", [-1, 2**63, True, "01", "-1"])
def test_api_offsets_reject_invalid_or_lossy_values(invalid: object) -> None:
    with pytest.raises(ValidationError):
        PositionResult.model_validate({"status": "ready", "assignment_epoch": 7, "next_offset": invalid})


def test_api_offsets_serialize_as_decimal_strings_and_preserve_int64_precision() -> None:
    value = PositionResult(status=PositionStatus.READY, assignment_epoch=7, next_offset=2**63 - 1)
    assert value.model_dump(mode="json")["next_offset"] == "9223372036854775807"
    assert PositionResult.model_validate_json(value.model_dump_json()) == value
    assert value.model_json_schema(mode="serialization")["properties"]["next_offset"]["anyOf"][0]["type"] == "string"


def test_metadata_read_schema_serializes_all_boundaries_without_internal_tokens() -> None:
    position = row(boundary=2**63 - 1)
    position.recovery_boundary = 20
    position.recovery_confirmed_at = NOW
    position.recovery_policy = RecoveryPolicy.RETAINED_BEGINNING.value
    position.recovery_reason = "offset_expired"
    position.pending_boundary = 30
    position.recovery_token = UUID(int=42)
    value = KafkaPartitionInitialPositionRead.from_position(position).model_dump(mode="json")
    assert value["initial_next_offset"] == "9223372036854775807"
    assert value["recovery_boundary"] == "20"
    assert value["pending_boundary"] == "30"
    assert "recovery_token" not in value


async def test_expired_saved_initial_boundary_blocks_without_choosing_a_new_end() -> None:
    h = Harness(position=row(confirmed=False, boundary=50), beginning=60)
    result = await h.service.initialize(request())
    assert result.status == PositionStatus.RECOVERY_GAP
    assert result.reason == GapReason.OUT_OF_RANGE.value
    h.store.choose_initial.assert_not_awaited()
    h.client.commit.assert_not_awaited()


async def test_interrupted_recovery_commit_reuses_the_recorded_boundary() -> None:
    h = Harness(position=row(gap=True))
    h.client.commit.side_effect = TimeoutError()
    value = recovery(policy=RecoveryPolicy.CURRENT_END)
    assert (await h.service.recover(value, owner_worker_id="recovery")).status == PositionStatus.BLOCKED
    assert h.position is not None
    assert h.position.pending_boundary == 100
    assert h.held
    h.end = 200
    h.client.commit.side_effect = h.commit
    result = await h.service.recover(value, owner_worker_id="recovery")
    assert result.next_offset == 100
    assert h.client.commit.call_args.args[0] == {0: 100}


@pytest.mark.parametrize("fenced", [False, True])
async def test_failed_drain_or_fence_cannot_reconcile_or_commit(*, fenced: bool) -> None:
    h = Harness(position=row(gap=True))
    h.control.close_and_drain.return_value = DrainEvidence(
        quiescent=not fenced, retained_evidence_complete=True, permanent_content_error=False
    )
    h.control.is_fenced.return_value = fenced
    result = await h.service.recover(recovery(), owner_worker_id="recovery")
    assert result.status == PositionStatus.BLOCKED
    assert result.reason == "conflicting_work_not_drained"
    h.store.reconcile_claims.assert_not_awaited()
    h.client.commit.assert_not_awaited()


@pytest.mark.parametrize("operation", ["drain", "fence"])
async def test_control_timeout_keeps_recovery_blocked_with_its_hold(
    monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    h = Harness(position=row(gap=True))

    async def pending(*_args: object, **_kwargs: object) -> None:
        await asyncio.Event().wait()

    if operation == "drain":
        monkeypatch.setattr(EventSchedulingDefaults, "RPC_TIMEOUT_SECONDS", 0)
        h.control.close_and_drain.side_effect = pending
    else:
        monkeypatch.setattr(EventDeliveryDefaults, "COMMITTED_POSITION_TIMEOUT_SECONDS", 0)
        h.control.is_fenced.side_effect = pending
    result = await h.service.recover(recovery(), owner_worker_id="recovery")
    assert result.status == PositionStatus.BLOCKED
    assert result.recovery_revision is None
    assert h.held
    h.client.commit.assert_not_awaited()


@pytest.mark.parametrize("recover", [False, True], ids=["initialization", "recovery"])
async def test_overlapping_services_cannot_return_ready_while_a_position_commit_is_outstanding(
    *, recover: bool
) -> None:
    h = Harness(position=row(confirmed=recover, gap=recover))
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed_commit(offsets: dict[int, int], **kwargs: object) -> None:
        entered.set()
        await release.wait()
        await h.commit(offsets, **kwargs)

    h.client.commit.side_effect = delayed_commit
    service = h.service
    first = asyncio.create_task(
        service.recover(recovery(), owner_worker_id="first") if recover else service.initialize(request())
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        # A distinct service instance must share the client's position gate.
        competing = (
            await h.service.recover(recovery(), owner_worker_id="second")
            if recover
            else await h.service.initialize(request())
        )
        assert competing.status == PositionStatus.BLOCKED
        assert competing.reason == "position_operation_busy"
        assert h.client.commit.await_count == 1
    finally:
        release.set()
        completed = await first
    assert completed.status == PositionStatus.READY
    h.committed = 75
    assert (await h.service.initialize(request())).next_offset == 75
    assert h.client.commit.await_count == 1


@pytest.mark.parametrize("recover", [False, True], ids=["initialization", "recovery"])
async def test_caller_cancellation_keeps_position_exclusive_until_commit_settles(*, recover: bool) -> None:
    h = Harness(position=row(confirmed=recover, gap=recover))
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed_commit(offsets: dict[int, int], **kwargs: object) -> None:
        entered.set()
        await release.wait()
        await h.commit(offsets, **kwargs)

    h.client.commit.side_effect = delayed_commit
    service = h.service
    caller = asyncio.create_task(
        service.recover(recovery(), owner_worker_id="first") if recover else service.initialize(request())
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert (await h.service.initialize(request())).reason == "position_operation_busy"
        outstanding = tuple(service._operations)
        assert len(outstanding) == 1
    finally:
        release.set()
        await asyncio.gather(*tuple(service._operations))
    h.committed = 75
    assert (await h.service.initialize(request())).next_offset == 75
    assert h.client.commit.await_count == 1


@pytest.mark.parametrize("phase", ["drain", "repair"])
async def test_interruption_before_reconciliation_preserves_first_recovery_selection(phase: str) -> None:
    h = Harness(position=row(gap=True))
    if phase == "drain":
        h.control.close_and_drain.return_value = DrainEvidence(
            quiescent=False, retained_evidence_complete=True, permanent_content_error=False
        )
    else:
        h.store.reconcile_claims.return_value = [MagicMock()]
        h.admission.recover_claim.return_value = ClaimLost()
    value = recovery(policy=RecoveryPolicy.CURRENT_END)
    assert (await h.service.recover(value, owner_worker_id="recovery")).status == PositionStatus.BLOCKED
    assert h.position is not None
    assert h.position.pending_boundary == 100
    assert h.held
    h.client.commit.assert_not_awaited()
    h.end = 200
    h.control.close_and_drain.return_value = DrainEvidence(
        quiescent=True, retained_evidence_complete=True, permanent_content_error=False
    )
    h.store.reconcile_claims.return_value = []
    retried = await h.service.recover(value, owner_worker_id="recovery")
    assert retried.next_offset == 100
    assert h.control.close_and_drain.call_args.kwargs["boundary"] == 100


async def test_missing_initial_metadata_is_persisted_before_gap_and_explicitly_recoverable() -> None:
    h = Harness(committed=75)
    detected = await h.service.initialize(request())
    assert detected.status == PositionStatus.RECOVERY_GAP
    assert detected.reason == GapReason.INITIAL_METADATA_MISSING
    assert detected.recovery_revision == 0
    h.store.record_missing_initial.assert_awaited_once_with(request(), 75)
    assert h.position is not None
    assert h.position.initial_next_offset is None
    assert h.position.authorized_lower_boundary is None
    h.client.commit.assert_not_awaited()
    recovered = await h.service.recover(recovery(), owner_worker_id="recovery")
    assert recovered.status == PositionStatus.READY
    assert recovered.next_offset == 20
    assert h.position.initial_next_offset is None
    assert h.position.observed_group_next_offset == 75
    assert h.position.authorized_lower_boundary == 20


async def test_missing_metadata_persistence_failure_cannot_report_a_durable_gap() -> None:
    h = Harness(committed=75)
    h.store.record_missing_initial.side_effect = SQLAlchemyError("unavailable")
    blocked = await h.service.initialize(request())
    assert blocked.status == PositionStatus.BLOCKED
    assert blocked.reason == "storage_unavailable"
    h.client.commit.assert_not_awaited()
    h.client.seek.assert_not_awaited()


async def test_missing_metadata_recording_preserves_a_concurrent_initializer() -> None:
    h = Harness(committed=75)

    async def winner(*_args: object) -> KafkaPartitionInitialPosition:
        h.position = row(boundary=50)
        return h.position

    h.store.record_missing_initial.side_effect = winner
    assert (await h.service.initialize(request())).next_offset == 75
    assert h.position is not None
    assert h.position.initial_next_offset == 50
    assert not h.position.initial_metadata_missing
    h.client.commit.assert_not_awaited()


@pytest.mark.parametrize("expired", [False, True])
async def test_replacement_is_explicit_and_only_for_an_expired_pending_boundary(*, expired: bool) -> None:
    h = Harness(position=row(gap=True))
    h.control.close_and_drain.return_value = DrainEvidence(
        quiescent=False, retained_evidence_complete=True, permanent_content_error=False
    )
    assert (await h.service.recover(recovery(), owner_worker_id="recovery")).status == PositionStatus.BLOCKED
    h.beginning = 30 if expired else 20
    h.control.close_and_drain.return_value = DrainEvidence(
        quiescent=True, retained_evidence_complete=True, permanent_content_error=False
    )
    value = RecoveryReplacementRequest(
        **recovery().model_dump(exclude={"expected_recovery_revision"}),
        expected_recovery_revision=1,
        expected_pending_boundary=20,
    )
    replaced = await h.service.replace_recovery(value, owner_worker_id="recovery")
    if expired:
        assert replaced.status == PositionStatus.READY
        assert replaced.next_offset == 30
        h.store.replace_recovery.assert_awaited_once_with(value, 30)
    else:
        assert replaced.status == PositionStatus.BLOCKED
        assert replaced.reason == "recovery_boundary_not_expired"
        h.store.replace_recovery.assert_not_awaited()


def test_unknown_initial_and_replacement_evidence_serialize_losslessly() -> None:
    position = KafkaPartitionInitialPosition(
        source_id=UUID(int=1),
        partition=0,
        initial_next_offset=None,
        initialized_at=None,
        initial_metadata_missing=True,
        observed_group_next_offset=2**63 - 1,
        gap_detected_at=NOW,
        gap_reason=GapReason.INITIAL_METADATA_MISSING.value,
        recovery_revision=2,
        superseded_recovery_revision=1,
        superseded_recovery_boundary=2**53 + 1,
    )
    data = KafkaPartitionInitialPositionRead.from_position(position).model_dump(mode="json")
    assert data["initial_next_offset"] is None
    assert data["initialized_at"] is None
    assert data["observed_group_next_offset"] == "9223372036854775807"
    assert data["superseded_recovery_boundary"] == "9007199254740993"
