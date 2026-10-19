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
    DeliveryExpectation,
    DeliveryState,
    FrozenDeliveryBinding,
    StorageBackpressure,
    TemporalAcceptance,
    input_fingerprint,
)
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
