"""Read-only group progress verification, independent of consumer placement."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from aiokafka.client import ConnectionGroup
from aiokafka.errors import KafkaError
from aiokafka.protocol.api import Response
from aiokafka.protocol.commit import OffsetFetchRequest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.constants import EventDeliveryDefaults
from syntara.core.exceptions import SyntaraError
from syntara.eventstreams.adapters.kafka_delivery_reader import KafkaDeliveryReader
from syntara.eventstreams.adapters.kafka_identity import SourceMetadataRequest, decode_source_identity
from syntara.eventstreams.adapters.kafka_initial_position import KafkaPartitionInitialPosition
from syntara.eventstreams.adapters.kafka_record_identity import KafkaRecordIdentity
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.core.connection import ResolvedKafkaConnection
from syntara.eventstreams.core.consumer import MAX_POSITION_OFFSET, IdentityStatus, PartitionSetStatus
from syntara.eventstreams.core.deduplication import CommittedPositionUnavailableError, DeliveryIdentity
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.integrations.lib.kafka_client import KafkaPolicyClient


@dataclass
class _Probe:
    """At most one protected source client per cleanup batch."""

    snapshot: SubscriptionSnapshot
    evidence_revision: int
    client: KafkaPolicyClient
    partitions: tuple[int, ...] = ()
    coordinator: int | None = None


def _committed_offset(response: Response, topic: str, partition: int) -> int | None:
    """Accept one unambiguous successful Kafka-backed OffsetFetch response."""
    data = response.to_object()
    if data.get("error_code", 0) != 0:
        return None
    topics = data.get("topics")
    if not isinstance(topics, list) or len(topics) != 1:
        return None
    entry = topics[0]
    if not isinstance(entry, dict) or entry.get("topic") != topic:
        return None
    partitions = entry.get("partitions")
    if not isinstance(partitions, list) or len(partitions) != 1:
        return None
    value = partitions[0]
    if not isinstance(value, dict) or value.get("partition") != partition or value.get("error_code") != 0:
        return None
    offset = value.get("offset")
    return offset if type(offset) is int and 0 <= offset <= MAX_POSITION_OFFSET else None


class KafkaRetentionVerifier:
    """Inspect saved groups without joining, seeking, fetching records or committing.

    Reuse at most one source client within a bounded cleanup batch. Source rows,
    content gates and Kafka committed offsets are re-read for each record.
    Recovery's lifecycle locks and the retention service's second check still
    arbitrate deletion. Close the client when the batch ends.
    """

    def __init__(
        self,
        session_factory: Callable[..., AsyncSession],
        resolve_connection: Callable[[SubscriptionSnapshot], Awaitable[ResolvedKafkaConnection]],
        *,
        deployment_id: UUID,
    ) -> None:
        """Inject database access and connection resolution for one deployment."""
        self._sessions = session_factory
        self._resolve_connection = resolve_connection
        self._deployment_id = deployment_id
        self._deliveries = KafkaDeliveryReader(session_factory)
        self._probe: _Probe | None = None
        self._in_batch = False

    @asynccontextmanager
    async def batch(self) -> AsyncIterator[None]:
        """Dispose connections and observations after success, failure or cancellation."""
        if self._in_batch:
            msg = "Cleanup verification batches must not overlap"
            raise RuntimeError(msg)
        self._in_batch = True
        try:
            yield
        finally:
            try:
                await self._close_probe()
            finally:
                self._in_batch = False

    async def _close_probe(self) -> None:
        probe, self._probe = self._probe, None
        if probe is not None:
            try:
                async with asyncio.timeout(EventDeliveryDefaults.CLEANUP_CLOSE_TIMEOUT_SECONDS):
                    await probe.client.close()
            except (TimeoutError, OSError, KafkaError):
                # Failed maintenance teardown cannot turn uncertainty into proof.
                pass

    async def _snapshot(self, identity: DeliveryIdentity) -> tuple[SubscriptionSnapshot, int] | None:
        if identity.deployment_id != self._deployment_id or not isinstance(identity.record, KafkaRecordIdentity):
            return None
        async with self._sessions() as session, session.begin():
            source = await session.get(EventSubscriptionSource, identity.source_id)
            subscription = await session.get(EventSubscription, identity.subscription_id)
            delivery = await session.get(EventDelivery, identity.digest)
            position = await session.get(KafkaPartitionInitialPosition, (identity.source_id, identity.record.partition))
            if (
                source is None
                or subscription is None
                or delivery is None
                or delivery.delivery_identity() != identity
                or (
                    position is not None
                    and (position.gap_detected_at is not None or position.recovery_token is not None)
                )
                or source.subscription_id != identity.subscription_id
                or subscription.workflow_id != identity.workflow_id
                or source.deployment_id != identity.deployment_id
                or source.integration_identity != identity.integration_identity
                or source.generation != identity.source_generation
                or source.transport != "kafka"
                or not isinstance(source.configuration, KafkaSourceConfiguration)
                or source.configuration.topic != identity.record.topic
            ):
                return None
            snapshot = SubscriptionSnapshot.from_models(subscription, source)
            if delivery.frozen_binding is not None:
                # A replaced source can need the original broker credential,
                # rather than the credential now selected by its successor.
                snapshot = snapshot.model_copy(
                    update={"runtime_credential_id": delivery.frozen_binding.runtime_credential_id}
                )
            return snapshot, source.delivery_evidence_revision

    async def _open_probe(self, snapshot: SubscriptionSnapshot, revision: int) -> _Probe:
        await self._close_probe()
        connection = await self._resolve_connection(snapshot)
        client = KafkaPolicyClient(
            bootstrap_servers=list(connection.bootstrap_servers),
            client_id="syntara-delivery-cleanup",
            security_protocol=connection.security_protocol,
            ssl_context=connection.ssl_context,
            sasl_mechanism=connection.sasl_mechanism,
            sasl_plain_username=(
                connection.sasl_plain_username.get_secret_value()
                if connection.sasl_plain_username is not None
                else None
            ),
            sasl_plain_password=(
                connection.sasl_plain_password.get_secret_value()
                if connection.sasl_plain_password is not None
                else None
            ),
            request_timeout_ms=EventDeliveryDefaults.COMMITTED_POSITION_TIMEOUT_SECONDS * 1000,
        )
        probe = _Probe(snapshot, revision, client)
        self._probe = probe  # Retain ownership before any cancellable network call.
        await client.bootstrap()
        node = client.get_random_node()
        if node is None:
            raise CommittedPositionUnavailableError
        response = await client.send(node, SourceMetadataRequest(snapshot.configuration.topic))
        if response is None:
            raise CommittedPositionUnavailableError
        observed = decode_source_identity(response, topic=snapshot.configuration.topic, epoch=0)
        # Keep the existing distinction between unsupported identifiers and
        # uncertain identity. Cleanup must not introduce a newer-broker mandate
        # or populate a previously unknown source identity from current metadata.
        for name in ("cluster_id", "topic_id"):
            evidence = getattr(observed, name)
            saved = getattr(snapshot.configuration, name)
            if saved is None:
                if evidence.status != IdentityStatus.UNSUPPORTED:
                    raise CommittedPositionUnavailableError
            elif evidence.status != IdentityStatus.VERIFIED or evidence.value != saved:
                raise CommittedPositionUnavailableError
        if observed.partitions.status != PartitionSetStatus.VERIFIED or not observed.partitions.partition_ids:
            raise CommittedPositionUnavailableError
        probe.partitions = observed.partitions.partition_ids
        probe.coordinator = await client.coordinator_lookup(0, snapshot.configuration.group_id)
        return probe

    async def is_committed_beyond(self, identity: DeliveryIdentity) -> bool:
        """Retain the row when its offset is missing, failed or its source is unverifiable."""
        if not self._in_batch:
            async with self.batch():
                return await self.is_committed_beyond(identity)
        try:
            current = await self._snapshot(identity)
            if current is None:
                return False
            snapshot, revision = current
            record = identity.record
            return isinstance(record, KafkaRecordIdentity) and await self._verify_partition(snapshot, revision, record)
        except (CommittedPositionUnavailableError, SyntaraError, OSError, KafkaError, ValueError, TypeError, KeyError):
            await self._close_probe()
            raise CommittedPositionUnavailableError from None

    async def _verify_partition(
        self, snapshot: SubscriptionSnapshot, revision: int, record: KafkaRecordIdentity
    ) -> bool:
        if await self._deliveries.has_content_gate(snapshot, record.partition):
            return False
        probe = self._probe
        if probe is None or probe.snapshot != snapshot or probe.evidence_revision != revision:
            probe = await self._open_probe(snapshot, revision)
        if record.partition not in probe.partitions or probe.coordinator is None:
            return False
        response = await probe.client.send(
            probe.coordinator,
            OffsetFetchRequest(snapshot.configuration.group_id, [(record.topic, [record.partition])]),
            group=ConnectionGroup.COORDINATION,
        )
        if response is None:
            raise CommittedPositionUnavailableError
        offset = _committed_offset(response, record.topic, record.partition)
        return offset is not None and offset > record.offset
