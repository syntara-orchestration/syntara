"""Real repository branches with isolated SQL sessions and upstream clients."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.adapters import kafka_position_store
from syntara.eventstreams.adapters.kafka_initial_position import (
    GapReason,
    InitializationKind,
    PositionRequest,
    PositionStatus,
    RecoveryPolicy,
    RecoveryReplacementRequest,
    RecoveryRequest,
)
from syntara.eventstreams.adapters.kafka_position_store import KafkaInitialPositionStore, KafkaPositionError
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.core.consumer import (
    IdentityObservation,
    IdentityStatus,
    PartitionSetObservation,
    PartitionSetStatus,
    SourceIdentityObservation,
)
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from tests.helpers.eventstream_sessions import session_factory
from tests.unit.eventstreams.test_delivery_identity import identity
from tests.unit.eventstreams.test_kafka_initial_positions import NOW, row


def lifecycle() -> tuple[EventSubscription, EventSubscriptionSource]:
    value = identity()
    subscription = EventSubscription(
        id=value.subscription_id,
        workflow_id=value.workflow_id,
        project_id=UUID(int=6),
        trigger_node_id="incoming",
        published_version_id=UUID(int=7),
        active_source_generation=1,
        configuration_revision=2,
        created_by=UUID(int=90),
    )
    source = EventSubscriptionSource(
        id=value.source_id,
        subscription_id=value.subscription_id,
        deployment_id=value.deployment_id,
        integration_identity=value.integration_identity,
        integration_id=value.integration_identity,
        generation=1,
        transport="kafka",
        configuration=KafkaSourceConfiguration(topic="orders", group_id="syntara.test"),
    )
    return subscription, source


def position_request() -> PositionRequest:
    return PositionRequest(
        source_id=identity().source_id, source_generation=1, configuration_revision=2, partition=2, assignment_epoch=7
    )


def observation(*, cluster: str = "cluster-A", topic: str = "topic-A") -> SourceIdentityObservation:
    return SourceIdentityObservation(
        topic="orders",
        assignment_epoch=7,
        cluster_id=IdentityObservation(status=IdentityStatus.VERIFIED, value=cluster),
        topic_id=IdentityObservation(status=IdentityStatus.VERIFIED, value=topic),
        partitions=PartitionSetObservation(status=PartitionSetStatus.VERIFIED, partition_ids=(0, 1, 2)),
    )


def test_verified_source_identifiers_are_populated_once_and_never_replaced() -> None:
    _, source = lifecycle()
    KafkaInitialPositionStore._identity(source, observation())
    assert source.configuration.cluster_id == "cluster-A"
    assert source.configuration.topic_id == "topic-A"
    KafkaInitialPositionStore._identity(source, observation())
    for changed in (observation(cluster="other-cluster"), observation(topic="other-topic")):
        with pytest.raises(KafkaPositionError, match="source_recreated"):
            KafkaInitialPositionStore._identity(source, changed)
    assert source.configuration.cluster_id == "cluster-A"
    assert source.configuration.topic_id == "topic-A"


@pytest.mark.parametrize(
    "status",
    [IdentityStatus.UNSUPPORTED, IdentityStatus.UNAVAILABLE, IdentityStatus.UNCERTAIN, IdentityStatus.UNKNOWN_TOPIC],
)
def test_known_source_identity_cannot_be_replaced_by_missing_evidence(status: IdentityStatus) -> None:
    _, source = lifecycle()
    KafkaInitialPositionStore._identity(source, observation())
    missing = observation().model_copy(update={"topic_id": IdentityObservation(status=status)})
    with pytest.raises(KafkaPositionError, match="source_identity_unavailable"):
        KafkaInitialPositionStore._identity(source, missing)


async def test_source_revision_is_checked_before_position_or_delivery_access(monkeypatch: pytest.MonkeyPatch) -> None:
    subscription, source = lifecycle()
    subscription.configuration_revision += 1
    session = MagicMock(spec=AsyncSession)
    monkeypatch.setattr(kafka_position_store, "lock_source_lifecycle", AsyncMock(return_value=(subscription, source)))
    with pytest.raises(KafkaPositionError) as failure:
        await KafkaInitialPositionStore._locked(session, position_request())
    assert failure.value.status == PositionStatus.REVISION_CHANGED
    session.get.assert_not_awaited()


async def test_stale_recovery_revision_cannot_register_a_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    session.get.return_value = None
    repository = KafkaInitialPositionStore(MagicMock(return_value=session))
    subscription, source = lifecycle()
    position = row(gap=True)
    position.recovery_revision = 3
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=(subscription, source, position)))
    value = RecoveryRequest(
        **position_request().model_dump(),
        expected_recovery_revision=2,
        policy=RecoveryPolicy.CURRENT_END,
        reason="offset_expired",
    )
    with pytest.raises(KafkaPositionError, match="recovery_revision_changed"):
        await repository.begin_recovery(value)
    assert position.recovery_token is None


@pytest.mark.parametrize("stale", ["token", "revision", "policy", "reason"])
async def test_confirmation_rejects_stale_partition_fences(monkeypatch, stale) -> None:
    session = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    repository = KafkaInitialPositionStore(MagicMock(return_value=session))
    subscription, source = lifecycle()
    position = row(gap=True)
    token = UUID(int=42)
    position.recovery_token = token
    position.recovery_revision = 1
    position.pending_boundary = 20
    position.pending_policy = "retained_beginning"
    position.pending_reason = "missing_commit"
    request = RecoveryRequest(
        **position_request().model_dump(),
        expected_recovery_revision=3 if stale == "revision" else 0,
        policy="current_end" if stale == "policy" else "retained_beginning",
        reason="out_of_range" if stale == "reason" else "missing_commit",
    )
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=(subscription, source, position)))
    with pytest.raises(KafkaPositionError, match="recovery_revision_changed"):
        await repository.confirm_recovery(request, UUID(int=43) if stale == "token" else token, 20)
    assert position.recovery_token == token
    assert position.pending_boundary == 20
    assert position.recovery_confirmed_at is None


async def test_recovery_selection_reloads_first_winner(monkeypatch: pytest.MonkeyPatch) -> None:
    factory, _ = session_factory()
    repository = KafkaInitialPositionStore(factory)
    subscription, source = lifecycle()
    position = row(gap=True)
    position.recovery_revision = 1
    position.recovery_token = UUID(int=42)
    position.pending_policy = RecoveryPolicy.CURRENT_END.value
    position.pending_reason = "offset_expired"
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=(subscription, source, position)))
    value = RecoveryRequest(
        **position_request().model_dump(),
        expected_recovery_revision=0,
        policy=RecoveryPolicy.CURRENT_END,
        reason="offset_expired",
    )
    first = await repository.select_recovery_boundary(value, UUID(int=42), 100)
    winner = await repository.select_recovery_boundary(value, UUID(int=42), 200)
    assert first.pending_boundary == winner.pending_boundary == 100


@pytest.mark.parametrize("stale", ["revision", "boundary"])
async def test_stale_replacement_cannot_transfer_holds(stale: str, monkeypatch: pytest.MonkeyPatch) -> None:
    factory, _ = session_factory()
    repository = KafkaInitialPositionStore(factory)
    subscription, source = lifecycle()
    position = row(gap=True)
    position.recovery_revision = 1
    position.recovery_token = UUID(int=42)
    position.pending_boundary = 20
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=(subscription, source, position)))
    value = RecoveryReplacementRequest(
        **position_request().model_dump(),
        expected_recovery_revision=0 if stale == "revision" else 1,
        expected_pending_boundary=10 if stale == "boundary" else 20,
        policy=RecoveryPolicy.CURRENT_END,
        reason="retention_advanced",
    )
    with pytest.raises(KafkaPositionError, match="recovery_revision_changed"):
        await repository.replace_recovery(value, 100)
    assert position.recovery_token == UUID(int=42)
    assert position.pending_boundary == 20


def test_superseded_token_cannot_mutate_a_replacement_with_an_adjacent_revision() -> None:
    position = row(gap=True)
    position.recovery_revision = 2
    position.recovery_token = UUID(int=43)
    position.pending_policy = RecoveryPolicy.RETAINED_BEGINNING.value
    position.pending_reason = "offset_expired"
    value = RecoveryRequest(
        **position_request().model_dump(),
        expected_recovery_revision=1,
        policy=RecoveryPolicy.RETAINED_BEGINNING,
        reason="offset_expired",
    )
    with pytest.raises(KafkaPositionError, match="recovery_revision_changed"):
        KafkaInitialPositionStore._pending(position, value, UUID(int=42))


async def test_first_full_topic_capture_is_saved_once_and_later_metadata_cannot_expand_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, _ = session_factory()
    repository = KafkaInitialPositionStore(factory)
    subscription, source = lifecycle()
    subscription.desired_enabled = True
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=(subscription, source, None)))
    monkeypatch.setattr(repository, "_held", AsyncMock(return_value=False))
    history = AsyncMock(return_value=False)
    monkeypatch.setattr(repository, "_has_initialization_history", history)
    first = await repository.capture_initial_partitions(position_request(), observation())
    expanded = observation().model_copy(
        update={"partitions": PartitionSetObservation(status=PartitionSetStatus.VERIFIED, partition_ids=(0, 1, 2, 3))}
    )
    winner = await repository.capture_initial_partitions(position_request(), expanded)
    assert first.initial_partition_ids == (0, 1, 2)
    assert winner.initial_partition_ids == first.initial_partition_ids
    assert source.configuration.initial_partition_ids == first.initial_partition_ids
    history.assert_awaited_once()


async def test_capture_reloads_a_winning_set_that_differs_from_current_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, _ = session_factory()
    repository = KafkaInitialPositionStore(factory)
    subscription, source = lifecycle()
    subscription.desired_enabled = True
    source.configuration = source.configuration.model_copy(update={"initial_partition_ids": (0, 1)})
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=(subscription, source, None)))
    monkeypatch.setattr(repository, "_held", AsyncMock(return_value=False))
    history = AsyncMock()
    monkeypatch.setattr(repository, "_has_initialization_history", history)
    winner = await repository.capture_initial_partitions(position_request(), observation())
    assert winner.initial_partition_ids == (0, 1)
    assert KafkaInitialPositionStore.initialization_kind(winner, 2) == InitializationKind.ADDED_PARTITION
    history.assert_not_awaited()


@pytest.mark.parametrize("retained_row", [False, True])
async def test_missing_first_set_with_historical_evidence_cannot_be_reconstructed(
    monkeypatch: pytest.MonkeyPatch, *, retained_row: bool
) -> None:
    factory, _ = session_factory()
    repository = KafkaInitialPositionStore(factory)
    subscription, source = lifecycle()
    subscription.desired_enabled = True
    position = row(boundary=75) if retained_row else None
    if position is not None:
        position.initialization_kind = None
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=(subscription, source, position)))
    monkeypatch.setattr(repository, "_held", AsyncMock(return_value=False))
    monkeypatch.setattr(repository, "_has_initialization_history", AsyncMock(return_value=True))
    with pytest.raises(KafkaPositionError, match=GapReason.INITIALIZATION_HISTORY_UNAVAILABLE.value):
        await repository.capture_initial_partitions(position_request(), observation())
    assert source.configuration.initial_partition_ids is None
    if position is not None:
        assert position.initial_next_offset == 75
        assert position.initialization_kind is None


@pytest.mark.parametrize("status", [PartitionSetStatus.UNAVAILABLE, PartitionSetStatus.UNCERTAIN])
async def test_capture_requires_verified_complete_topic_membership(
    status: PartitionSetStatus, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory, _ = session_factory()
    repository = KafkaInitialPositionStore(factory)
    subscription, source = lifecycle()
    subscription.desired_enabled = True
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=(subscription, source, None)))
    monkeypatch.setattr(repository, "_held", AsyncMock(return_value=False))
    value = observation().model_copy(update={"partitions": PartitionSetObservation(status=status)})
    with pytest.raises(KafkaPositionError, match="topic_partitions_unavailable"):
        await repository.capture_initial_partitions(position_request(), value)
    assert source.configuration.initial_partition_ids is None


async def test_kind_mismatch_is_rejected_before_boundary_insert(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    repository = KafkaInitialPositionStore(MagicMock(return_value=session))
    subscription, source = lifecycle()
    subscription.desired_enabled = True
    source.configuration = source.configuration.model_copy(update={"initial_partition_ids": (0, 1, 2)})
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=(subscription, source, None)))
    monkeypatch.setattr(repository, "_held", AsyncMock(return_value=False))
    with pytest.raises(KafkaPositionError, match="initialization_kind_changed"):
        await repository.choose_initial(
            position_request(), observation(), 0, initialization_kind=InitializationKind.ADDED_PARTITION
        )
    session.execute.assert_not_awaited()


async def test_retained_execution_without_position_refuses_initial_boundary_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    retained = MagicMock()
    retained.first.return_value = identity().execution_id
    session.exec.return_value = retained
    repository = KafkaInitialPositionStore(MagicMock(return_value=session))
    subscription, source = lifecycle()
    subscription.desired_enabled = True
    source.configuration = source.configuration.model_copy(update={"initial_partition_ids": (0, 1)})
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=(subscription, source, None)))
    monkeypatch.setattr(repository, "_held", AsyncMock(return_value=False))
    with pytest.raises(KafkaPositionError, match=GapReason.INITIALIZATION_HISTORY_UNAVAILABLE.value) as failure:
        await repository.choose_initial(
            position_request(), observation(), 0, initialization_kind=InitializationKind.ADDED_PARTITION
        )
    assert failure.value.status == PositionStatus.BLOCKED
    session.exec.assert_awaited_once()
    retained.first.assert_called_once_with()
    session.execute.assert_not_awaited()
    session.flush.assert_not_awaited()


@pytest.mark.parametrize(
    ("partition", "kind"),
    [(0, InitializationKind.ADDED_PARTITION), (2, InitializationKind.FIRST_ACTIVATION)],
)
async def test_kind_membership_mismatch_refuses_initial_confirmation(
    partition: int, kind: InitializationKind, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    repository = KafkaInitialPositionStore(MagicMock(return_value=session))
    subscription, source = lifecycle()
    subscription.desired_enabled = True
    source.configuration = source.configuration.model_copy(update={"initial_partition_ids": (0, 1)})
    position = row(confirmed=False, boundary=50)
    position.partition = partition
    position.initialization_kind = kind.value
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=(subscription, source, position)))
    monkeypatch.setattr(repository, "_held", AsyncMock(return_value=False))
    with pytest.raises(KafkaPositionError, match=GapReason.INITIALIZATION_HISTORY_UNAVAILABLE.value) as failure:
        await repository.confirm_initial(position_request().model_copy(update={"partition": partition}), boundary=50)
    assert failure.value.status == PositionStatus.RECOVERY_GAP
    assert position.initial_commit_confirmed_at is None
    assert position.initial_next_offset == 50
    assert source.initialized_at is None
    session.exec.assert_not_awaited()
    session.flush.assert_not_awaited()


async def test_source_initialization_waits_for_all_first_members_and_survives_an_addition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    result = MagicMock()
    result.one.return_value = NOW
    result.all.return_value = [0]
    session.exec.return_value = result
    repository = KafkaInitialPositionStore(MagicMock(return_value=session))
    subscription, source = lifecycle()
    subscription.desired_enabled = True
    source.configuration = source.configuration.model_copy(update={"initial_partition_ids": (0, 1)})
    first = row(confirmed=False)
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=(subscription, source, first)))
    monkeypatch.setattr(repository, "_held", AsyncMock(return_value=False))
    await repository.confirm_initial(position_request().model_copy(update={"partition": 0}), boundary=50)
    assert first.initial_commit_confirmed_at == NOW
    assert source.initialized_at is None
    second = row(confirmed=False)
    second.partition = 1
    result.all.return_value = [0, 1]
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=(subscription, source, second)))
    await repository.confirm_initial(position_request().model_copy(update={"partition": 1}), boundary=50)
    assert source.initialized_at == NOW
    added = row(confirmed=False, boundary=7)
    added.partition = 2
    added.initialization_kind = InitializationKind.ADDED_PARTITION.value
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=(subscription, source, added)))
    await repository.confirm_initial(position_request(), boundary=7)
    assert added.initial_commit_confirmed_at == NOW
    assert source.initialized_at == NOW
