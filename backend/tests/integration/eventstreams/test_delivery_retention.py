"""Retained-evidence integration behavior; injected verifiers do not exercise Kafka."""

from __future__ import annotations

import asyncio
import importlib
from base64 import urlsafe_b64encode
from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from aiokafka.protocol.commit import OffsetFetchRequest, OffsetFetchResponse_v3
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, update
from sqlmodel import col, select

from syntara.eventstreams.adapters import kafka_retention_verifier as verifier_module
from syntara.eventstreams.adapters.kafka_identity import MetadataResponseV10, SourceMetadataRequest
from syntara.eventstreams.adapters.kafka_initial_position import KafkaPartitionInitialPosition
from syntara.eventstreams.core.connection import ResolvedKafkaConnection
from syntara.eventstreams.core.deduplication import (
    CommittedPositionUnavailableError,
    DeliveryClaim,
    DeliveryIdentity,
    DeliveryState,
    TerminalDelivery,
)
from syntara.eventstreams.models.control import EventSubscriptionRuntime
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.services.delivery_cache import EventDeliveryTerminalLookup
from syntara.eventstreams.services.delivery_cache_policy import DeliveryEvidencePolicy
from syntara.eventstreams.services.delivery_cleanup_worker import EventDeliveryCleanupWorker
from syntara.eventstreams.services.delivery_retention_service import EventDeliveryRetentionService
from syntara.eventstreams.services.worker_resources import EventWorkerResources
from syntara.workflows.models.execution import Execution
from tests.integration.eventstreams.conftest import finish_partition_recovery, hold_partition_recovery
from tests.integration.eventstreams.test_delivery_store import _acceptance, _attempt

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection
    from sqlalchemy.ext.asyncio import AsyncEngine

    from tests.integration.eventstreams.conftest import DeliveryContext

pytestmark = pytest.mark.integration


class PositionVerifier:
    """Test committed-position evidence; no fetched position is supplied."""

    def __init__(self, next_offset: int | None) -> None:
        """Supply a known committed next offset or explicitly unavailable evidence."""
        self.next_offset = next_offset

    async def is_committed_beyond(self, identity: DeliveryIdentity) -> bool:
        return self.next_offset is not None and self.next_offset > identity.record.offset


async def terminal(context: DeliveryContext, *, offset: int = 0, age: int = 7200) -> DeliveryClaim:
    """Commit a real no-trigger outcome and age it without a wall-clock wait."""
    claim = await context.claim(offset)
    async with context.session_factory() as session, session.begin():
        result = await context.store(session).finalize_without_execution(claim, DeliveryState.REJECTED)
        assert isinstance(result, TerminalDelivery)
        await session.execute(
            update(EventDelivery)
            .where(col(EventDelivery.identity_digest) == claim.identity.digest)
            .values(resolved_at=func.clock_timestamp() - timedelta(seconds=age))
        )
    return claim


@pytest.mark.parametrize(("next_offset", "removed"), [(None, False), (40, False), (41, False), (42, True)])
async def test_cleanup_requires_verified_committed_next_offset(
    delivery_context: DeliveryContext,
    next_offset: int | None,
    *,
    removed: bool,
) -> None:
    context = delivery_context
    claim = await terminal(context, offset=41)
    service = EventDeliveryRetentionService(
        context.session_factory,
        verifier=PositionVerifier(next_offset),
        retention_seconds=3600,
    )
    assert await service.cleanup_one(claim.identity) is removed
    async with context.session_factory() as session, session.begin():
        assert (await session.get(EventDelivery, claim.identity.digest) is None) is removed


@pytest.mark.parametrize(("age", "removed"), [(0, False), (3599, False), (3601, True)])
async def test_retention_is_minimum_from_resolved_at(
    delivery_context: DeliveryContext,
    age: int,
    *,
    removed: bool,
) -> None:
    context = delivery_context
    claim = await terminal(context, age=age)
    service = EventDeliveryRetentionService(
        context.session_factory,
        verifier=PositionVerifier(100),
        retention_seconds=3600,
    )
    assert await service.cleanup_one(claim.identity) is removed


async def test_missing_verifier_retains_old_evidence(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await terminal(context, age=30 * 86400)
    service = EventDeliveryRetentionService(context.session_factory, retention_seconds=3600)
    assert await service.cleanup(limit=100) == 0
    assert not await service.cleanup_one(claim.identity)
    async with context.session_factory() as session, session.begin():
        assert await session.get(EventDelivery, claim.identity.digest) is not None


async def test_unresolved_ambiguous_work_never_expires(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await context.claim(prepare=True)
    async with context.session_factory() as session, session.begin():
        attempted = await context.store(session).record_start_attempt(claim)
        assert isinstance(attempted, DeliveryClaim)
        await session.execute(
            update(EventDelivery)
            .where(col(EventDelivery.identity_digest) == claim.identity.digest)
            .values(
                created_at=func.clock_timestamp() - timedelta(days=30),
                lease_until=func.clock_timestamp() - timedelta(days=20),
            )
        )
    service = EventDeliveryRetentionService(
        context.session_factory,
        verifier=PositionVerifier(100),
        retention_seconds=1,
    )
    assert await service.cleanup(limit=100) == 0
    assert not await service.cleanup_one(claim.identity)
    async with context.session_factory() as session, session.begin():
        row = await session.get(EventDelivery, claim.identity.digest)
        assert row is not None
        assert row.frozen_binding == claim.binding
        assert row.first_start_attempt_at is not None


async def test_multiple_holds_persist_until_each_is_released(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await terminal(context)
    first = await hold_partition_recovery(context, 0)
    second = await hold_partition_recovery(context, 1)
    assert first is not None
    assert second is not None
    assert first != second
    # A fresh instance sees the durable reservation rather than process memory.
    other = EventDeliveryRetentionService(
        context.session_factory,
        verifier=PositionVerifier(100),
        retention_seconds=3600,
    )
    assert not await other.cleanup_one(claim.identity)
    assert await finish_partition_recovery(context, 0, first)
    assert not await other.cleanup_one(claim.identity)
    assert await finish_partition_recovery(context, 1, second)
    assert await other.cleanup_one(claim.identity)


async def test_hold_registration_during_verification_fences_cleanup(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await terminal(context)

    class InterleavingVerifier:
        async def is_committed_beyond(self, _: DeliveryIdentity) -> bool:
            hold = await hold_partition_recovery(context)
            assert hold is not None
            assert await finish_partition_recovery(context, 0, hold)
            return True

    service = EventDeliveryRetentionService(
        context.session_factory,
        verifier=InterleavingVerifier(),
        retention_seconds=3600,
    )
    assert not await service.cleanup_one(claim.identity)
    async with context.session_factory() as session, session.begin():
        source = await session.get(EventSubscriptionSource, context.snapshot.source_id)
        assert source is not None
        assert source.delivery_evidence_revision == 2
        assert await session.get(EventDelivery, claim.identity.digest) is not None
    fresh = EventDeliveryRetentionService(
        context.session_factory,
        verifier=PositionVerifier(100),
        retention_seconds=3600,
    )
    assert await fresh.cleanup_one(claim.identity)


async def test_gap_recorded_during_verification_blocks_cleanup_before_a_token_exists(
    delivery_context: DeliveryContext,
) -> None:
    context = delivery_context
    claim = await terminal(context)

    class InterleavingVerifier:
        async def is_committed_beyond(self, _: DeliveryIdentity) -> bool:
            async with context.session_factory() as session, session.begin():
                now = (await session.exec(select(func.clock_timestamp()))).one()
                session.add(
                    KafkaPartitionInitialPosition(
                        source_id=context.snapshot.source_id,
                        partition=0,
                        initial_next_offset=0,
                        gap_detected_at=now,
                        gap_reason="missing_commit",
                    )
                )
            return True

    service = EventDeliveryRetentionService(
        context.session_factory, verifier=InterleavingVerifier(), retention_seconds=3600
    )
    assert not await service.cleanup_one(claim.identity)
    async with context.session_factory() as session:
        position = await session.get(KafkaPartitionInitialPosition, (context.snapshot.source_id, 0))
        assert position is not None
        assert position.recovery_token is None
        assert position.gap_detected_at is not None
        assert await session.get(EventDelivery, claim.identity.digest) is not None


async def test_cleanup_batch_is_bounded(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    for offset in range(3):
        await terminal(context, offset=offset)
    service = EventDeliveryRetentionService(
        context.session_factory,
        verifier=PositionVerifier(100),
        retention_seconds=3600,
    )
    assert await service.cleanup(limit=2) == 2
    async with context.session_factory() as session, session.begin():
        assert (await session.exec(select(func.count()).select_from(EventDelivery))).one() == 1


async def test_cleanup_moves_past_an_unverifiable_page_and_retries_it_next_sweep(
    delivery_context: DeliveryContext,
) -> None:
    """A full retained page cannot hide later eligible records indefinitely."""
    context = delivery_context
    for offset in range(3):
        await terminal(context, offset=offset)
    async with context.session_factory() as session, session.begin():
        rows = (
            await session.exec(
                select(EventDelivery).order_by(
                    col(EventDelivery.source_id), col(EventDelivery.resolved_at), col(EventDelivery.identity_digest)
                )
            )
        ).all()
        protected = {row.identity_digest for row in rows[:2]}
        later = rows[2].identity_digest

    class TemporarilyUnavailableVerifier:
        async def is_committed_beyond(self, identity: DeliveryIdentity) -> bool:
            if identity.digest in protected:
                raise CommittedPositionUnavailableError
            return True

    service = EventDeliveryRetentionService(
        context.session_factory, verifier=TemporarilyUnavailableVerifier(), retention_seconds=3600
    )
    assert await service.cleanup(limit=2) == 0
    assert service.last_scan_count == 2
    assert await service.cleanup(limit=2) == 1
    async with context.session_factory() as session, session.begin():
        assert await session.get(EventDelivery, later) is None
        for digest in protected:
            assert await session.get(EventDelivery, digest) is not None
    # Exhausting this sweep wraps the cursor. Once verification recovers, the
    # previously protected page remains discoverable and can be deleted safely.
    assert await service.cleanup(limit=2) == 0
    assert service.last_scan_count == 0
    protected.clear()
    assert await service.cleanup(limit=2) == 2


async def test_cleanup_cursor_preserves_rows_with_equal_resolution_times(delivery_context: DeliveryContext) -> None:
    """The identity digest breaks timestamp ties without skipping candidates."""
    context = delivery_context
    for offset in range(3):
        await terminal(context, offset=offset)
    async with context.session_factory() as session, session.begin():
        await session.execute(
            update(EventDelivery).values(resolved_at=func.clock_timestamp() - timedelta(seconds=7200))
        )
    service = EventDeliveryRetentionService(
        context.session_factory, verifier=PositionVerifier(100), retention_seconds=3600
    )
    for _ in range(3):
        assert await service.cleanup(limit=1) == 1
    assert await service.cleanup(limit=1) == 0


async def test_foreign_deployment_is_neither_scanned_nor_verified(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await terminal(context)
    verifier = AsyncMock()
    service = EventDeliveryRetentionService(
        context.session_factory, verifier=verifier, deployment_id=uuid4(), retention_seconds=3600
    )
    assert await service.cleanup(limit=100) == 0
    assert not await service.cleanup_one(claim.identity)
    verifier.is_committed_beyond.assert_not_awaited()


async def test_shutdown_gate_closes_between_verification_and_deletion(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await terminal(context)
    accepting = True

    class ShutdownVerifier:
        async def is_committed_beyond(self, _identity: DeliveryIdentity) -> bool:
            nonlocal accepting
            accepting = False
            return True

    service = EventDeliveryRetentionService(
        context.session_factory, verifier=ShutdownVerifier(), permits_cleanup=lambda: accepting, retention_seconds=3600
    )
    assert not await service.cleanup_one(claim.identity)
    async with context.session_factory() as session:
        assert await session.get(EventDelivery, claim.identity.digest) is not None


@pytest.mark.parametrize("protection", ["partition_recovery", "runtime_content_gate"])
async def test_cleanup_preserves_pending_recovery_and_stopped_content_gates(
    delivery_context: DeliveryContext, protection: str
) -> None:
    context = delivery_context
    claim = await terminal(context)
    if protection == "partition_recovery":
        await hold_partition_recovery(context)
    else:
        async with context.session_factory() as session, session.begin():
            session.add(
                EventSubscriptionRuntime(
                    source_id=context.snapshot.source_id,
                    worker_id="stopped-worker",
                    configuration_revision=context.snapshot.configuration_revision,
                    stopped=True,
                    permanent_content_error=True,
                )
            )
    verifier = AsyncMock()
    verifier.is_committed_beyond.return_value = True
    service = EventDeliveryRetentionService(context.session_factory, verifier=verifier, retention_seconds=3600)
    assert not await service.cleanup_one(claim.identity)
    verifier.is_committed_beyond.assert_not_awaited()


async def test_overlapping_replicas_delete_a_record_at_most_once(delivery_context: DeliveryContext) -> None:
    context = delivery_context
    claim = await terminal(context)
    first = EventDeliveryRetentionService(
        context.session_factory, verifier=PositionVerifier(100), retention_seconds=3600
    )
    second = EventDeliveryRetentionService(
        context.session_factory, verifier=PositionVerifier(100), retention_seconds=3600
    )
    removed = await asyncio.gather(first.cleanup_one(claim.identity), second.cleanup_one(claim.identity))
    assert sum(removed) == 1


async def test_automatic_cleanup_of_retired_source_without_a_consumer(
    delivery_context: DeliveryContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise real cleanup storage and scheduling with read-only broker test doubles."""
    context = delivery_context
    claim = await _attempt(context, await context.claim(offset=41, prepare=True))
    topic_id = UUID(int=1)
    async with context.session_factory() as session, session.begin():
        result = await context.store(session).finalize_scheduled(claim, _acceptance(claim))
        assert isinstance(result, TerminalDelivery)
        await session.execute(
            update(EventDelivery)
            .where(col(EventDelivery.identity_digest) == claim.identity.digest)
            .values(resolved_at=func.clock_timestamp() - timedelta(seconds=7200))
        )
        source = await session.get(EventSubscriptionSource, context.snapshot.source_id)
        assert source is not None
        source.configuration = source.configuration.model_copy(
            update={
                "cluster_id": "cluster-A",
                "topic_id": urlsafe_b64encode(topic_id.bytes).decode().rstrip("="),
                "initial_partition_ids": (0,),
            }
        )
        source.retired_at = (await session.exec(select(func.clock_timestamp()))).one()
        from syntara.eventstreams.models.subscription import EventSubscription

        subscription = await session.get(EventSubscription, context.snapshot.subscription_id)
        assert subscription is not None
        subscription.retired = subscription.paused = True
        subscription.desired_enabled = False
        session.add(
            KafkaPartitionInitialPosition(
                source_id=source.id,
                partition=0,
                initialization_kind="first_activation",
                initial_next_offset=0,
                initial_commit_confirmed_at=source.retired_at,
            )
        )
    topic = context.snapshot.configuration.topic
    metadata = MetadataResponseV10(
        throttle_time_ms=0,
        brokers=[],
        cluster_id="cluster-A",
        controller_id=1,
        topics=[(0, topic, topic_id, False, [(0, 0, 1, 0, [1], [1], [], {})], 0, {})],
        cluster_authorized_operations=0,
        tags={},
    )
    client = MagicMock()
    client.bootstrap = AsyncMock()
    client.get_random_node.return_value = 1
    client.coordinator_lookup = AsyncMock(return_value=1)
    offsets = OffsetFetchResponse_v3(0, [(topic, [(0, 42, "", 0)])], 0)
    client.send = AsyncMock(
        side_effect=lambda _node, request, **_kwargs: metadata
        if isinstance(request, SourceMetadataRequest)
        else offsets
    )
    client.close = AsyncMock()
    monkeypatch.setattr(verifier_module, "KafkaPolicyClient", MagicMock(return_value=client))
    resolve = AsyncMock(
        return_value=ResolvedKafkaConnection(bootstrap_servers=["broker:9093"], security_protocol="PLAINTEXT")
    )
    verifier = verifier_module.KafkaRetentionVerifier(
        context.session_factory, resolve, deployment_id=context.snapshot.deployment_id
    )
    gate = MagicMock()
    gate.scheduling_open = True
    resources = EventWorkerResources(gate)
    retention = EventDeliveryRetentionService(
        context.session_factory,
        verifier=verifier,
        deployment_id=context.snapshot.deployment_id,
        permits_cleanup=lambda: resources.accepting and resources.scheduling_open,
    )
    worker = EventDeliveryCleanupWorker(retention, verifier, resources, idle_seconds=0.01)
    worker.start()
    try:
        async with asyncio.timeout(5):
            while True:
                async with context.session_factory() as session:
                    if await session.get(EventDelivery, claim.identity.digest) is None:
                        assert await session.get(Execution, claim.identity.execution_id) is not None
                        break
                await asyncio.sleep(0.01)
    finally:
        await worker.stop()
    assert client.close.await_count >= 1
    requests = [call.args[1] for call in client.send.await_args_list]
    assert all(isinstance(request, (SourceMetadataRequest, OffsetFetchRequest)) for request in requests)


@pytest.mark.parametrize("age", [0, 7200], ids=["fresh", "expired"])
async def test_invalid_proof_falls_back_to_committed_rejection(delivery_context: DeliveryContext, age: int) -> None:
    """Keep durable rejection evidence usable when cached proof is invalid or unavailable."""
    context = delivery_context
    cache = AsyncMock()
    cache.get.return_value = context.identity().digest
    policy = DeliveryEvidencePolicy(enabled=True, cache_epoch=uuid4(), clock_error_bound_seconds=0.25)
    lookup = EventDeliveryTerminalLookup(context.session_factory, cache=cache, policy=policy)
    assert await lookup.lookup(context.identity()) is None
    await terminal(context, age=age)
    cache.put.side_effect = TimeoutError()
    result = await lookup.lookup(context.identity())
    assert isinstance(result, TerminalDelivery)
    assert result.identity == context.identity()
    assert result.state == DeliveryState.REJECTED
    async with context.session_factory() as session, session.begin():
        row = await session.get(EventDelivery, context.identity().digest)
        assert row is not None
        assert row.state == DeliveryState.REJECTED
    assert cache.get.await_count == 2
    if age == 0:
        cache.put.assert_awaited_once()
    else:
        cache.put.assert_not_awaited()


async def test_downgrade_refuses_retained_evidence(
    delivery_context: DeliveryContext, eventstream_migration_engine: AsyncEngine
) -> None:
    context = delivery_context
    await terminal(context)
    migration = importlib.import_module(
        "syntara.core.database.migrations.versions.673435210536_add_event_deliveries_and_recovery_holds"
    )

    def downgrade(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            current = importlib.import_module(
                "syntara.core.database.migrations.versions.c4a8f17d2e93_use_partition_recovery_fences"
            )
            current.downgrade()
            migration.downgrade()

    with pytest.raises(RuntimeError, match="Unsafe downgrade"):
        async with eventstream_migration_engine.begin() as connection:
            await connection.run_sync(downgrade)
