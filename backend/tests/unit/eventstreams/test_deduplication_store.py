"""Isolated repository boundaries; database behavior is covered separately."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.core.deduplication import (
    ClaimLost,
    DeliveryCapacityCheck,
    DeliveryClaim,
    DeliveryExpectation,
    DeliveryState,
    FrozenDeliveryBinding,
    RevisionChanged,
    StorageBackpressure,
    TemporalAcceptance,
    TerminalDelivery,
    input_fingerprint,
)
from syntara.eventstreams.core.processing import CONTENT_INSPECTION_PENDING, CONTENT_VALIDATED
from syntara.eventstreams.core.results import EventDecodeFailure, EventFailureCode
from syntara.eventstreams.core.scheduling_metadata import EVENT_DELIVERY_METADATA_KEY
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.services import deduplication_store
from syntara.eventstreams.services.deduplication_store import EventDeliveryStore
from syntara.workflows.models.execution import Execution
from tests.unit.eventstreams.test_delivery_identity import identity

NOW = datetime(2026, 10, 19, tzinfo=UTC)
PRINCIPAL = UUID(int=10)


def delivery() -> EventDelivery:
    """Construct ledger evidence without a database factory or session."""
    value = identity()
    return EventDelivery(
        **value.model_dump(exclude={"record"}),
        identity_digest=value.digest,
        record_identity=value.record,
        transport=value.record.transport,
        execution_identity=value.execution_id,
        temporal_workflow_id=value.temporal_workflow_id,
        claim_token=uuid4(),
        owner_worker_id="worker",
        lease_until=NOW + timedelta(seconds=60),
        next_attempt_at=NOW,
    )


def binding() -> FrozenDeliveryBinding:
    """Frozen reference context contains no message contents."""
    return FrozenDeliveryBinding(
        workflow_version_id=UUID(int=7),
        configuration_revision=1,
        runtime_credential_id=UUID(int=8),
        connection_revision="revision-1",
        execution_principal_id=PRINCIPAL,
        enabled_by=UUID(int=9),
        received_at=NOW,
        prepared_at=NOW,
        input_fingerprint=input_fingerprint({"value": 1}, {}),
    )


def store(session: AsyncSession | None = None) -> EventDeliveryStore:
    """Inject all nonlocal requirements into the isolated repository."""
    return EventDeliveryStore(
        MagicMock(spec=AsyncSession) if session is None else session,
        execution_principal_id=PRINCIPAL,
    )


def inspection_lifecycle() -> tuple[EventSubscription, EventSubscriptionSource]:
    value = identity()
    subscription = EventSubscription(
        id=value.subscription_id,
        workflow_id=value.workflow_id,
        project_id=UUID(int=6),
        trigger_node_id="incoming",
        published_version_id=UUID(int=7),
        active_source_generation=1,
        configuration_revision=2,
        created_by=PRINCIPAL,
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


async def test_inspection_marker_is_allowed_behind_admission_holds_and_survives_lease_expiry(monkeypatch) -> None:
    subscription, source = inspection_lifecycle()
    subscription.paused = True
    row = delivery()
    row.last_error_code = CONTENT_INSPECTION_PENDING
    row.lease_until = NOW - timedelta(seconds=1)
    row.next_attempt_at = datetime.max.replace(tzinfo=UTC)
    repository = store()
    monkeypatch.setattr(deduplication_store, "lock_source_lifecycle", AsyncMock(return_value=(subscription, source)))
    monkeypatch.setattr(repository, "_delivery", AsyncMock(return_value=row))
    monkeypatch.setattr(repository, "_now", AsyncMock(return_value=NOW))
    monkeypatch.setattr(repository, "_recovery_held", AsyncMock(side_effect=AssertionError("new admission")))
    previous = row.claim_token

    async def takeover(current, owner) -> DeliveryClaim:
        assert current.next_attempt_at == NOW
        current.claim_token = uuid4()
        current.owner_worker_id = owner
        current.lease_until = NOW + timedelta(seconds=60)
        return repository._claim(current)

    async def change(_claim, **values: object) -> EventDelivery:
        for name, value in values.items():
            setattr(row, name, value)
        return row

    monkeypatch.setattr(repository, "_takeover", takeover)
    monkeypatch.setattr(repository, "_change", change)
    result = await repository.acquire_inspection(
        row.delivery_identity(),
        DeliveryExpectation(published_version_id=UUID(int=7), configuration_revision=2),
        "new-worker",
    )
    assert isinstance(result, DeliveryClaim)
    assert result.token != previous
    assert row.last_error_code == CONTENT_INSPECTION_PENDING
    assert row.next_attempt_at == datetime.max.replace(tzinfo=UTC)
    assert source.delivery_evidence_revision == 1


@pytest.mark.parametrize("invalid", ["token", "owner", "expired", "permanent", "frozen"])
async def test_inspection_finish_cannot_clear_stale_or_replaced_evidence(monkeypatch, invalid) -> None:
    row = delivery()
    row.last_error_code = CONTENT_INSPECTION_PENDING
    claim = EventDeliveryStore._claim(row)
    if invalid == "token":
        row.claim_token = uuid4()
    elif invalid == "owner":
        row.owner_worker_id = "new-worker"
    elif invalid == "expired":
        row.lease_until = NOW
    elif invalid == "permanent":
        row.last_error_code = EventFailureCode.invalid_json.value
    else:
        row.frozen_binding = binding()
    repository = store()
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=row))
    monkeypatch.setattr(repository, "_now", AsyncMock(return_value=NOW))
    defer = AsyncMock()
    monkeypatch.setattr(repository, "defer", defer)
    assert isinstance(await repository.finish_inspection(claim, None), ClaimLost)
    defer.assert_not_awaited()


@pytest.mark.parametrize(
    ("failure", "keep_pending", "expected_code"),
    [
        (None, False, CONTENT_VALIDATED),
        (None, True, CONTENT_INSPECTION_PENDING),
        (EventDecodeFailure(code=EventFailureCode.invalid_json), False, EventFailureCode.invalid_json.value),
        (EventDecodeFailure(code=EventFailureCode.invalid_json), True, EventFailureCode.invalid_json.value),
    ],
)
async def test_inspection_finish_retains_unresolved_safe_evidence_and_changes_revision(
    monkeypatch, failure, keep_pending, expected_code
) -> None:
    row = delivery()
    row.last_error_code = CONTENT_INSPECTION_PENDING
    _, source = inspection_lifecycle()
    session = MagicMock(spec=AsyncSession)
    session.get.return_value = source
    repository = store(session)
    monkeypatch.setattr(repository, "_current", AsyncMock(return_value=row))
    monkeypatch.setattr(repository, "_now", AsyncMock(return_value=NOW))
    defer = AsyncMock(return_value=None)
    monkeypatch.setattr(repository, "defer", defer)
    claim = repository._claim(row)
    assert await repository.finish_inspection(claim, failure, keep_pending=keep_pending) is None
    defer.assert_awaited_once_with(
        claim,
        next_attempt_at=datetime.max.replace(tzinfo=UTC) if failure is not None else NOW,
        error_code=expected_code,
    )
    assert source.delivery_evidence_revision == 1
    assert row.state == DeliveryState.IN_PROGRESS


async def test_freeze_validates_pending_inspection_with_prepared_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    row = delivery()
    row.last_error_code = CONTENT_INSPECTION_PENDING
    frozen = binding()
    subscription, source = inspection_lifecycle()
    subscription.desired_enabled = True
    subscription.configuration_revision = frozen.configuration_revision
    subscription.runtime_credential_id = frozen.runtime_credential_id
    subscription.enabled_by = frozen.enabled_by
    value = row.delivery_identity()
    execution = Execution(
        id=value.execution_id,
        workflow_id=value.workflow_id,
        workflow_version_id=frozen.workflow_version_id,
        temporal_workflow_id=value.temporal_workflow_id,
        project_id=subscription.project_id,
        trigger_node_id=subscription.trigger_node_id,
        created_by=PRINCIPAL,
        input_data={"value": 1},
    )
    session = MagicMock(spec=AsyncSession)
    session.get.side_effect = [subscription, source, None]
    repository = store(session)
    monkeypatch.setattr(repository, "_current", AsyncMock(return_value=row))
    monkeypatch.setattr(repository, "_recovery_held", AsyncMock(return_value=False))
    change = AsyncMock(
        return_value=row.model_copy(
            update={
                "frozen_binding": frozen,
                "execution_id": execution.id,
                "last_error_code": CONTENT_VALIDATED,
            }
        )
    )
    monkeypatch.setattr(repository, "_change", change)
    claim = repository._claim(row)

    result = await repository.freeze(claim, frozen, execution)

    assert isinstance(result, DeliveryClaim)
    assert result.binding == frozen
    change.assert_awaited_once_with(
        claim,
        frozen_binding=frozen,
        execution_id=execution.id,
        last_error_code=CONTENT_VALIDATED,
    )
    session.add.assert_called_once_with(execution)
    session.flush.assert_awaited_once()
    assert row.state == DeliveryState.IN_PROGRESS


async def test_inspection_storage_refusal_does_not_insert_a_production_stub(monkeypatch) -> None:
    subscription, source = inspection_lifecycle()
    session = MagicMock(spec=AsyncSession)
    repository = store(session)
    monkeypatch.setattr(deduplication_store, "lock_source_lifecycle", AsyncMock(return_value=(subscription, source)))
    monkeypatch.setattr(repository, "_delivery", AsyncMock(return_value=None))
    repository.capacity_check = MagicMock(spec=DeliveryCapacityCheck)
    repository.capacity_check.permits_new_delivery.return_value = False
    assert isinstance(
        await repository.acquire_inspection(
            identity(), DeliveryExpectation(published_version_id=UUID(int=7), configuration_revision=2), "worker"
        ),
        StorageBackpressure,
    )
    session.execute.assert_not_awaited()


async def test_inspection_rejects_changed_schema_revision_before_delivery_access(monkeypatch) -> None:
    subscription, source = inspection_lifecycle()
    repository = store()
    monkeypatch.setattr(deduplication_store, "lock_source_lifecycle", AsyncMock(return_value=(subscription, source)))
    read = AsyncMock()
    monkeypatch.setattr(repository, "_delivery", read)
    result = await repository.acquire_inspection(
        identity(), DeliveryExpectation(published_version_id=UUID(int=7), configuration_revision=1), "worker"
    )
    assert isinstance(result, RevisionChanged)
    read.assert_not_awaited()


@pytest.mark.parametrize("invalid", ["token", "owner", "expired", "terminal"])
async def test_stale_capabilities_cannot_renew(invalid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A supplied claim cannot override authoritative ownership or database time."""
    row = delivery()
    claim = EventDeliveryStore._claim(row)
    if invalid == "token":
        row.claim_token = uuid4()
    elif invalid == "owner":
        row.owner_worker_id = "another-worker"
    elif invalid == "expired":
        row.lease_until = NOW
    else:
        row.state = DeliveryState.REJECTED
    repository = store()
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=row))
    monkeypatch.setattr(repository, "_now", AsyncMock(return_value=NOW))
    change = AsyncMock()
    monkeypatch.setattr(repository, "_change", change)
    assert isinstance(await repository.renew(claim), ClaimLost)
    change.assert_not_awaited()


async def test_stale_claim_returns_lost_before_attempt_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Expired tokens receive ClaimLost even when the row has no frozen Execution."""
    row = delivery()
    claim = EventDeliveryStore._claim(row)
    row.claim_token = uuid4()
    repository = store()
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=row))
    assert isinstance(await repository.record_start_attempt(claim), ClaimLost)
    acceptance = TemporalAcceptance(
        execution_id=claim.identity.execution_id,
        temporal_workflow_id=claim.identity.temporal_workflow_id,
        temporal_run_id="run",
        input_fingerprint="a" * 64,
    )
    assert isinstance(await repository.record_acceptance(claim, acceptance), ClaimLost)


@pytest.mark.parametrize("lease_until", [None, NOW - timedelta(microseconds=1), NOW])
@pytest.mark.parametrize("prepared", [False, True])
async def test_expired_finalization_stops_before_validation_or_execution_lock(
    lease_until: datetime | None,
    monkeypatch: pytest.MonkeyPatch,
    *,
    prepared: bool,
) -> None:
    """Expired unresolved claims are lost even when acceptance evidence is invalid."""
    row = delivery()
    if prepared:
        row.frozen_binding = binding()
        row.execution_id = row.execution_identity
        row.attempt_count = 1
        row.first_start_attempt_at = NOW
    claim = EventDeliveryStore._claim(row)
    row.lease_until = lease_until
    session = MagicMock(spec=AsyncSession)
    repository = store(session)
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=row))
    monkeypatch.setattr(repository, "_now", AsyncMock(return_value=NOW))
    acceptance = TemporalAcceptance(
        execution_id=claim.identity.execution_id,
        temporal_workflow_id=claim.identity.temporal_workflow_id,
        temporal_run_id="run",
        input_fingerprint=binding().input_fingerprint if prepared else "a" * 64,
    )
    assert isinstance(await repository.finalize_scheduled(claim, acceptance), ClaimLost)
    session.exec.assert_not_awaited()
    session.execute.assert_not_awaited()


async def test_scheduled_finalization_retry_returns_evidence_after_lease_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An idempotent terminal read needs the same token but no live processing lease."""
    row = delivery()
    row.frozen_binding = binding()
    row.attempt_count = 1
    row.first_start_attempt_at = NOW
    row.state = DeliveryState.SCHEDULED
    row.temporal_run_id = "run"
    row.execution_confirmed_at = NOW
    row.resolved_at = NOW
    claim = EventDeliveryStore._claim(row)
    row.lease_until = NOW - timedelta(seconds=1)
    session = MagicMock(spec=AsyncSession)
    repository = store(session)
    monkeypatch.setattr(repository, "_locked", AsyncMock(return_value=row))
    now = AsyncMock(return_value=NOW)
    monkeypatch.setattr(repository, "_now", now)
    acceptance = TemporalAcceptance(
        execution_id=claim.identity.execution_id,
        temporal_workflow_id=claim.identity.temporal_workflow_id,
        temporal_run_id="run",
        input_fingerprint=binding().input_fingerprint,
    )
    result = await repository.finalize_scheduled(claim, acceptance)
    assert isinstance(result, TerminalDelivery)
    assert result.execution_id == claim.identity.execution_id
    assert result.temporal_run_id == "run"
    assert result.execution_confirmed_at == NOW
    now.assert_not_awaited()
    session.exec.assert_not_awaited()
    session.execute.assert_not_awaited()


@pytest.mark.parametrize("attempt_id", [None, UUID(int=42)])
async def test_attempt_metadata_preserves_prior_evidence(
    monkeypatch: pytest.MonkeyPatch, attempt_id: UUID | None
) -> None:
    row = delivery()
    row.frozen_binding = binding()
    row.execution_id = row.execution_identity
    row.attempt_count = 2
    row.first_start_attempt_at = NOW
    row.start_retry_deadline = NOW + timedelta(hours=23)
    claim = EventDeliveryStore._claim(row)
    prior_id = str(UUID(int=41))
    execution = Execution(
        execution_metadata={
            "event": {"frozen": True},
            EVENT_DELIVERY_METADATA_KEY: {
                "start_attempt_id": prior_id,
                "scheduling_failure_count": 2,
                "scheduling_state": "prepared",
            },
        }
    )
    session = MagicMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=execution)
    session.flush = AsyncMock()
    repository = store(session)
    monkeypatch.setattr(repository, "_current", AsyncMock(return_value=row))

    async def change(_claim: DeliveryClaim, **_values: object) -> EventDelivery:
        row.attempt_count += 1
        return row

    monkeypatch.setattr(repository, "_change", change)
    result = await repository.record_start_attempt(claim, attempt_id=attempt_id)
    assert isinstance(result, DeliveryClaim)
    assert result.attempt_count == 3
    assert execution.execution_metadata is not None
    metadata = execution.execution_metadata[EVENT_DELIVERY_METADATA_KEY]
    assert metadata["start_attempt_id"] == (prior_id if attempt_id is None else str(attempt_id))
    assert metadata["attempt_count"] == 3
    assert metadata["scheduling_failure_count"] == 2
    assert metadata["scheduling_state"] == "prepared"
    assert execution.execution_metadata["event"] == {"frozen": True}


async def test_no_trigger_resolution_cannot_overwrite_preparation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prepared work remains unresolved rather than being converted into rejection."""
    row = delivery()
    row.frozen_binding = binding()
    repository = store()
    monkeypatch.setattr(repository, "_current", AsyncMock(return_value=row))
    claim = EventDeliveryStore._claim(row)
    with pytest.raises(ValueError, match="Prepared or ambiguous"):
        await repository.finalize_without_execution(claim, DeliveryState.REJECTED)


def test_recovery_uses_frozen_principal_after_worker_configuration_change() -> None:
    """Existing work remains valid under its original principal and deterministic IDs."""
    value = identity()
    frozen = binding()
    execution = Execution(
        id=value.execution_id,
        workflow_id=value.workflow_id,
        workflow_version_id=frozen.workflow_version_id,
        temporal_workflow_id=value.temporal_workflow_id,
        project_id=UUID(int=6),
        created_by=PRINCIPAL,
        input_data={"value": 1},
    )
    repository = EventDeliveryStore(MagicMock(spec=AsyncSession), execution_principal_id=UUID(int=99))
    repository._validate_execution(value, frozen, execution)


@pytest.mark.parametrize("failure", [False, TimeoutError(), OSError()])
async def test_capacity_uncertainty_blocks_new_writes(failure: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """Storage pressure or an unavailable capacity port cannot create a claim."""
    value = identity()
    subscription = EventSubscription(
        id=value.subscription_id,
        workflow_id=value.workflow_id,
        project_id=UUID(int=6),
        trigger_node_id="incoming",
        published_version_id=UUID(int=7),
        active_source_generation=1,
        configuration_revision=1,
        created_by=PRINCIPAL,
    )
    source = EventSubscriptionSource(
        id=value.source_id,
        subscription_id=value.subscription_id,
        generation=1,
        deployment_id=value.deployment_id,
        integration_identity=value.integration_identity,
        integration_id=value.integration_identity,
        transport="kafka",
        configuration=KafkaSourceConfiguration(topic="orders", group_id="syntara.test"),
    )
    session = MagicMock(spec=AsyncSession)
    capacity = AsyncMock(spec=DeliveryCapacityCheck)
    if isinstance(failure, Exception):
        capacity.permits_new_delivery.side_effect = failure
    else:
        capacity.permits_new_delivery.return_value = failure
    repository = EventDeliveryStore(session, capacity_check=capacity, execution_principal_id=PRINCIPAL)
    monkeypatch.setattr(deduplication_store, "lock_source_lifecycle", AsyncMock(return_value=(subscription, source)))
    monkeypatch.setattr(repository, "_delivery", AsyncMock(return_value=None))
    result = await repository.acquire(
        value,
        DeliveryExpectation(published_version_id=UUID(int=7), configuration_revision=1),
        "worker",
    )
    assert isinstance(result, StorageBackpressure)
    session.execute.assert_not_awaited()


@pytest.mark.parametrize("limit", [0, -1, 101, True, 1.5])
async def test_due_selection_requires_a_bounded_integer(limit: int) -> None:
    """Unbounded or nonintegral recovery requests do not issue SQL."""
    repository = store()
    with pytest.raises(ValueError, match="batch size"):
        await repository.claim_due("worker", limit=limit)


@pytest.mark.parametrize("error_code", ["payload detail", "secret=value", "", "a" * 101])
async def test_retry_metadata_accepts_only_bounded_safe_codes(error_code: str) -> None:
    """Arbitrary exception bodies cannot enter retry metadata."""
    repository = store()
    claim = EventDeliveryStore._claim(delivery())
    with pytest.raises(ValueError, match="sanitized"):
        await repository.defer(claim, next_attempt_at=NOW, error_code=error_code)
