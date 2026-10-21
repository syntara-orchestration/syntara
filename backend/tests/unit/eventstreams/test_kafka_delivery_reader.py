"""Partition evidence and cleanup verification through isolated database/broker ports."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.adapters.kafka_committed_position import KafkaCommittedPositionVerifier
from syntara.eventstreams.adapters.kafka_consumer import KafkaPartitionConsumer
from syntara.eventstreams.adapters.kafka_delivery_reader import KafkaDeliveryReader
from syntara.eventstreams.adapters.kafka_record_identity import KafkaRecordIdentity
from syntara.eventstreams.core.consumer import CommittedPositionResult
from syntara.eventstreams.core.deduplication import (
    CleanupCandidate,
    CommittedPositionUnavailableError,
    DeliveryIdentity,
)
from syntara.eventstreams.core.processing import CONTENT_INSPECTION_PENDING
from syntara.eventstreams.core.results import EventFailureCode
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.delivery_retention_service import EventDeliveryRetentionService
from tests.unit.eventstreams.test_connection_provider import connection_context
from tests.unit.eventstreams.test_delivery_retention import session_factory
from tests.unit.eventstreams.test_record_processing_service import retained


def context() -> tuple[SubscriptionSnapshot, DeliveryIdentity, MagicMock, MagicMock, KafkaCommittedPositionVerifier]:
    snapshot = connection_context().snapshot
    identity = DeliveryIdentity(
        deployment_id=snapshot.deployment_id,
        integration_identity=snapshot.integration_identity,
        source_id=snapshot.source_id,
        source_generation=snapshot.source_generation,
        workflow_id=snapshot.workflow_id,
        subscription_id=snapshot.subscription_id,
        record=KafkaRecordIdentity(topic=snapshot.configuration.topic, partition=0, offset=41),
    )
    client = MagicMock(spec=KafkaPartitionConsumer)
    client.topic, client.group_id = snapshot.configuration.topic, snapshot.configuration.group_id
    client.epoch, client.assignment = 7, frozenset({0})
    client.committed.return_value = {0: CommittedPositionResult.verified(0, 42)}
    reader = MagicMock(spec=KafkaDeliveryReader)
    reader.has_content_gate.return_value = False
    verifier = KafkaCommittedPositionVerifier(client, snapshot, reader)
    return snapshot, identity, client, reader, verifier


async def test_pending_query_uses_numeric_offsets_and_bounded_source_partition_scope() -> None:
    snapshot, identity, _, _, _ = context()
    session = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    session.exec.return_value = MagicMock()
    session.exec.return_value.one_or_none.return_value = retained(identity)
    reader = KafkaDeliveryReader(lambda: session)
    assert await reader.first_pending(snapshot, 0) == identity
    statement = session.exec.call_args.args[0].compile(
        dialect=postgresql.dialect(),  # type: ignore[no-untyped-call]
        compile_kwargs={"literal_binds": True},
    )
    sql = str(statement)
    assert "AS BIGINT" in sql
    assert "LIMIT 1" in sql
    assert "event_deliveries.source_id" in sql
    assert "event_deliveries.source_generation" in sql
    assert "record_identity ->> 'partition'" in sql
    assert "rejected" in sql
    assert "invalid_json" in sql


@pytest.mark.parametrize("gated", [False, True])
async def test_content_gate_query_covers_retained_source_errors_across_generations(gated) -> None:
    snapshot, _, _, _, _ = context()
    session = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    session.exec.return_value = MagicMock()
    session.exec.return_value.first.return_value = "retained-error" if gated else None
    reader = KafkaDeliveryReader(lambda: session)
    assert await reader.has_content_gate(snapshot, 0) is gated
    query = session.exec.call_args.args[0]
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    statement = query.compile(dialect=dialect, compile_kwargs={"literal_binds": True})
    sql = str(statement)
    assert "event_deliveries.source_id =" in sql
    assert snapshot.source_id in query.compile(dialect=dialect).params.values()
    assert "event_deliveries.transport = 'kafka'" in sql
    assert "record_identity ->> 'partition'" in sql
    assert " = 0" in sql
    assert "event_deliveries.state = 'rejected'" in sql
    assert all(f"'{code.value}'" in sql for code in EventFailureCode)
    assert f"'{CONTENT_INSPECTION_PENDING}'" in sql
    assert "LIMIT 1" in sql
    # Republish/restart must not hide errors from an older retained generation.
    assert "source_generation" not in sql


@pytest.mark.parametrize(
    "position",
    [
        CommittedPositionResult.absent(0),
        CommittedPositionResult.unavailable(0, "timeout"),
        CommittedPositionResult.uncertain(0, "unknown"),
        CommittedPositionResult.verified(0, 41),
        CommittedPositionResult.verified(1, 42),
    ],
)
async def test_cleanup_requires_verified_progress_beyond_the_exact_record(position) -> None:
    _, identity, client, _, verifier = context()
    client.committed.return_value = {0: position}
    assert not await verifier.is_committed_beyond(identity)


async def test_verified_progress_is_bound_to_source_and_ownership_epoch() -> None:
    _, identity, client, _, verifier = context()
    assert await verifier.is_committed_beyond(identity)
    client.committed.assert_awaited_once_with([0], expected_epoch=7)
    assert not await verifier.is_committed_beyond(identity.model_copy(update={"source_id": uuid4()}))

    async def lose_ownership(*_args: object, **_kwargs: object) -> dict[int, CommittedPositionResult]:
        client.epoch = 8
        return {0: CommittedPositionResult.verified(0, 100)}

    client.committed.side_effect = lose_ownership
    assert not await verifier.is_committed_beyond(identity)
    client.assignment = frozenset()
    client.committed.reset_mock()
    assert not await verifier.is_committed_beyond(identity)
    client.committed.assert_not_awaited()


@pytest.mark.parametrize("failure", [SQLAlchemyError("unavailable"), TimeoutError(), OSError()])
async def test_unavailable_gate_evidence_cannot_authorize_cleanup(failure) -> None:
    _, identity, client, reader, verifier = context()
    reader.has_content_gate.side_effect = failure
    with pytest.raises(CommittedPositionUnavailableError):
        await verifier.is_committed_beyond(identity)
    client.committed.assert_not_awaited()


@pytest.mark.parametrize("gated", [False, True])
async def test_retention_composes_authoritative_reader_and_content_gate(monkeypatch, gated) -> None:
    _, identity, client, reader, verifier = context()
    reader.has_content_gate.return_value = gated
    factory, sessions = session_factory()
    retention = EventDeliveryRetentionService(factory, verifier=verifier, retention_seconds=3600)
    candidate = CleanupCandidate(identity=identity, resolved_at=datetime.now(UTC), evidence_revision=1)
    monkeypatch.setattr(retention, "_candidate", AsyncMock(return_value=candidate))
    assert await retention.cleanup_one(identity) is not gated
    if gated:
        assert len(sessions) == 1
        client.committed.assert_not_awaited()
        sessions[0].delete.assert_not_awaited()
    else:
        sessions[-1].delete.assert_awaited_once()
