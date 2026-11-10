"""Read-only retained group checks, including inactive sources and batch reuse."""

import asyncio
from base64 import urlsafe_b64encode
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from aiokafka.client import ConnectionGroup
from aiokafka.protocol.commit import OffsetFetchRequest, OffsetFetchResponse_v3
from aiokafka.protocol.metadata import MetadataResponse_v5
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.adapters import kafka_retention_verifier as module
from syntara.eventstreams.adapters.kafka_identity import MetadataResponseV10, SourceMetadataRequest
from syntara.eventstreams.adapters.kafka_initial_position import KafkaPartitionInitialPosition
from syntara.eventstreams.adapters.kafka_record_identity import KafkaRecordIdentity
from syntara.eventstreams.core.connection import ResolvedKafkaConnection
from syntara.eventstreams.core.deduplication import CommittedPositionUnavailableError, DeliveryIdentity
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.integrations.lib.kafka_client import KafkaPolicyClient
from tests.unit.eventstreams.test_deduplication_store import binding
from tests.unit.eventstreams.test_subscription_snapshot import _source, _subscription

TOPIC_ID = UUID(int=1)


def context(monkeypatch):
    """Use real persisted value shapes and mock only database and broker I/O."""
    subscription = _subscription(desired_enabled=False, paused=True, retired=True)
    source = _source(subscription)
    source.configuration = source.configuration.model_copy(
        update={"cluster_id": "cluster-A", "topic_id": urlsafe_b64encode(TOPIC_ID.bytes).decode().rstrip("=")}
    )
    identity = DeliveryIdentity(
        deployment_id=source.deployment_id,
        integration_identity=source.integration_identity,
        source_id=source.id,
        source_generation=source.generation,
        workflow_id=subscription.workflow_id,
        subscription_id=subscription.id,
        record=KafkaRecordIdentity(topic=source.configuration.topic, partition=0, offset=41),
    )
    delivery = EventDelivery(
        **identity.model_dump(exclude={"record"}),
        identity_digest=identity.digest,
        record_identity=identity.record,
        transport="kafka",
        execution_identity=identity.execution_id,
        temporal_workflow_id=identity.temporal_workflow_id,
    )
    session = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    position = KafkaPartitionInitialPosition(source_id=source.id, partition=0)
    rows = {
        EventSubscriptionSource: source,
        EventSubscription: subscription,
        EventDelivery: delivery,
        KafkaPartitionInitialPosition: position,
    }
    session.get = AsyncMock(side_effect=lambda model, _key: rows.get(model))
    connection = ResolvedKafkaConnection(bootstrap_servers=["broker:9093"], security_protocol="PLAINTEXT")
    resolve = AsyncMock(return_value=connection)
    verifier = module.KafkaRetentionVerifier(
        MagicMock(return_value=session), resolve, deployment_id=source.deployment_id
    )
    verifier._deliveries.has_content_gate = AsyncMock(return_value=False)
    client = MagicMock(spec=KafkaPolicyClient)
    client.bootstrap = AsyncMock()
    client.close = AsyncMock()
    client.get_random_node.return_value = 1
    client.coordinator_lookup = AsyncMock(return_value=1)
    metadata = MetadataResponseV10(
        throttle_time_ms=0,
        brokers=[],
        cluster_id="cluster-A",
        controller_id=1,
        topics=[(0, source.configuration.topic, TOPIC_ID, False, [(0, 0, 1, 0, [1], [1], [], {})], 0, {})],
        cluster_authorized_operations=0,
        tags={},
    )
    offset = OffsetFetchResponse_v3(0, [(source.configuration.topic, [(0, 42, "", 0)])], 0)
    client.send = AsyncMock(
        side_effect=lambda _node, request, **_kwargs: metadata if isinstance(request, SourceMetadataRequest) else offset
    )
    construct = MagicMock(return_value=client)
    monkeypatch.setattr(module, "KafkaPolicyClient", construct)
    return SimpleNamespace(
        verifier=verifier,
        client=client,
        construct=construct,
        identity=identity,
        source=source,
        subscription=subscription,
        delivery=delivery,
        session=session,
        resolve=resolve,
        metadata=metadata,
        offset=offset,
        position=position,
    )


async def test_inactive_source_reads_only_metadata_and_group_offsets(monkeypatch):
    ctx = context(monkeypatch)
    assert await ctx.verifier.is_committed_beyond(ctx.identity)
    ctx.session.begin.return_value.__aexit__.assert_awaited()
    ctx.resolve.assert_awaited_once()
    ctx.client.coordinator_lookup.assert_awaited_once_with(0, ctx.source.configuration.group_id)
    requests = [call.args[1] for call in ctx.client.send.await_args_list]
    assert [type(request) for request in requests] == [SourceMetadataRequest, OffsetFetchRequest]
    fields = requests[1].prepare({9: (1, 3)}).to_object()
    assert fields["consumer_group"] == ctx.source.configuration.group_id
    assert fields["topics"] == [{"topic": ctx.source.configuration.topic, "partitions": [0]}]
    assert ctx.client.send.await_args.kwargs["group"] == ConnectionGroup.COORDINATION
    ctx.client.close.assert_awaited_once()


async def test_batch_reuses_connection_but_reads_fresh_offsets(monkeypatch):
    ctx = context(monkeypatch)
    async with ctx.verifier.batch():
        assert await ctx.verifier.is_committed_beyond(ctx.identity)
        assert await ctx.verifier.is_committed_beyond(ctx.identity)
        assert ctx.client.send.await_count == 3
        ctx.client.close.assert_not_awaited()
    ctx.client.close.assert_awaited_once()
    assert await ctx.verifier.is_committed_beyond(ctx.identity)
    assert ctx.client.send.await_count == 5
    assert ctx.client.close.await_count == 2


async def test_recovery_revision_rechecks_source_identity(monkeypatch):
    ctx = context(monkeypatch)
    async with ctx.verifier.batch():
        assert await ctx.verifier.is_committed_beyond(ctx.identity)
        ctx.source.delivery_evidence_revision += 2
        ctx.offset.topics = [(ctx.source.configuration.topic, [(0, -1, "", 0)])]
        assert not await ctx.verifier.is_committed_beyond(ctx.identity)
        assert ctx.client.send.await_count == 4


@pytest.mark.parametrize("field", ["cluster_id", "topic_id"])
async def test_missing_saved_identity_is_not_invented_from_current_metadata(monkeypatch, field):
    ctx = context(monkeypatch)
    ctx.source.configuration = ctx.source.configuration.model_copy(update={field: None})
    with pytest.raises(CommittedPositionUnavailableError):
        await ctx.verifier.is_committed_beyond(ctx.identity)
    ctx.client.coordinator_lookup.assert_not_awaited()


async def test_unsupported_topic_identifiers_do_not_add_a_new_broker_requirement(monkeypatch):
    ctx = context(monkeypatch)
    ctx.source.configuration = ctx.source.configuration.model_copy(update={"topic_id": None})
    metadata = MetadataResponse_v5(
        throttle_time_ms=0,
        brokers=[],
        cluster_id="cluster-A",
        controller_id=1,
        topics=[(0, ctx.source.configuration.topic, False, [(0, 0, 1, [1], [1], [])])],
    )
    ctx.client.send.side_effect = (
        lambda _node, request, **_kwargs: metadata if isinstance(request, SourceMetadataRequest) else ctx.offset
    )
    assert await ctx.verifier.is_committed_beyond(ctx.identity)


@pytest.mark.parametrize("field", ["cluster_id", "topic_id"])
async def test_recreated_source_never_supplies_offset_proof(monkeypatch, field):
    ctx = context(monkeypatch)
    ctx.source.configuration = ctx.source.configuration.model_copy(update={field: "different-incarnation"})
    with pytest.raises(CommittedPositionUnavailableError):
        await ctx.verifier.is_committed_beyond(ctx.identity)
    ctx.client.coordinator_lookup.assert_not_awaited()
    assert ctx.client.send.await_count == 1
    ctx.client.close.assert_awaited_once()


@pytest.mark.parametrize(("offset", "error", "top_error"), [(-1, 0, 0), (41, 0, 0), (42, 29, 0), (42, 0, 15)])
async def test_missing_unadvanced_or_failed_commits_keep_evidence(monkeypatch, offset, error, top_error):
    ctx = context(monkeypatch)
    ctx.offset.topics = [(ctx.source.configuration.topic, [(0, offset, "", error)])]
    ctx.offset.error_code = top_error
    assert not await ctx.verifier.is_committed_beyond(ctx.identity)


async def test_foreign_deployment_does_not_open_a_session(monkeypatch):
    ctx = context(monkeypatch)
    foreign = ctx.identity.model_copy(update={"deployment_id": uuid4()})
    assert not await ctx.verifier.is_committed_beyond(foreign)
    ctx.verifier._sessions.assert_not_called()
    ctx.construct.assert_not_called()


async def test_content_gate_blocks_even_a_verified_group(monkeypatch):
    ctx = context(monkeypatch)
    ctx.verifier._deliveries.has_content_gate.return_value = True
    assert not await ctx.verifier.is_committed_beyond(ctx.identity)
    ctx.construct.assert_not_called()


@pytest.mark.parametrize("field", ["gap_detected_at", "recovery_token"])
async def test_unresolved_position_evidence_blocks_cleanup(monkeypatch, field):
    ctx = context(monkeypatch)
    if field == "recovery_token":
        ctx.position.recovery_token = uuid4()
    else:
        ctx.position.gap_detected_at = ctx.position.initialized_at
    assert not await ctx.verifier.is_committed_beyond(ctx.identity)
    ctx.construct.assert_not_called()


async def test_frozen_credential_is_used_after_source_replacement(monkeypatch):
    ctx = context(monkeypatch)
    ctx.delivery.frozen_binding = binding()
    assert ctx.delivery.frozen_binding.runtime_credential_id != ctx.subscription.runtime_credential_id
    assert await ctx.verifier.is_committed_beyond(ctx.identity)
    assert ctx.resolve.await_args.args[0].runtime_credential_id == ctx.delivery.frozen_binding.runtime_credential_id


async def test_cancelled_bootstrap_closes_its_client(monkeypatch):
    ctx = context(monkeypatch)
    entered = asyncio.Event()

    async def block() -> None:
        entered.set()
        await asyncio.Event().wait()

    ctx.client.bootstrap.side_effect = block
    task = asyncio.create_task(ctx.verifier.is_committed_beyond(ctx.identity))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    ctx.client.close.assert_awaited_once()
    assert ctx.verifier._probe is None


async def test_connection_failure_does_not_expose_secret_contents(monkeypatch):
    ctx = context(monkeypatch)
    ctx.client.bootstrap.side_effect = OSError("PRIVATE connection contents")
    async with ctx.verifier.batch():
        with pytest.raises(CommittedPositionUnavailableError) as failure:
            await ctx.verifier.is_committed_beyond(ctx.identity)
        assert "PRIVATE" not in str(failure.value)


@pytest.mark.parametrize("missing_position", [False, True])
async def test_verified_offsets_do_not_require_initialization_history(monkeypatch, missing_position):
    ctx = context(monkeypatch)
    ctx.position.initial_metadata_missing = True
    if missing_position:
        original_get = ctx.session.get.side_effect
        ctx.session.get.side_effect = lambda model, key: (
            None if model is KafkaPartitionInitialPosition else original_get(model, key)
        )
    assert await ctx.verifier.is_committed_beyond(ctx.identity)
