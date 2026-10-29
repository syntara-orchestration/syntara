"""Authoritative Kafka committed-position verification for delivery retention."""

from sqlalchemy.exc import SQLAlchemyError

from syntara.eventstreams.adapters.kafka_delivery_reader import KafkaDeliveryReader
from syntara.eventstreams.adapters.kafka_position_control import AssignedPartitionClient
from syntara.eventstreams.adapters.kafka_record_identity import KafkaRecordIdentity
from syntara.eventstreams.core.consumer import PositionStatus
from syntara.eventstreams.core.deduplication import CommittedPositionUnavailableError, DeliveryIdentity
from syntara.eventstreams.exceptions import (
    ConsumerNotRunningError,
    KafkaTransportError,
    OwnershipRevokedError,
    StaleEpochError,
)
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot


class KafkaCommittedPositionVerifier:
    """Bind verified progress to one immutable source and its persisted group."""

    def __init__(
        self, client: AssignedPartitionClient, snapshot: SubscriptionSnapshot, deliveries: KafkaDeliveryReader
    ) -> None:
        """Receive the same transport/source used by the single-subscription runner."""
        self._client = client
        self._snapshot = snapshot
        self._deliveries = deliveries

    async def is_committed_beyond(self, identity: DeliveryIdentity) -> bool:
        """Never substitute fetched positions, absent commits, or another source's group."""
        snapshot = self._snapshot
        record = identity.record
        if (
            not isinstance(record, KafkaRecordIdentity)
            or identity.source_id != snapshot.source_id
            or identity.source_generation != snapshot.source_generation
            or identity.subscription_id != snapshot.subscription_id
            or identity.workflow_id != snapshot.workflow_id
            or identity.deployment_id != snapshot.deployment_id
            or identity.integration_identity != snapshot.integration_identity
            or self._client.topic != snapshot.configuration.topic
            or self._client.group_id != snapshot.configuration.group_id
            or record.topic != self._client.topic
        ):
            return False
        epoch = self._client.epoch
        if record.partition not in self._client.assignment:
            return False
        try:
            if await self._deliveries.has_content_gate(snapshot, record.partition):
                return False
            positions = await self._client.committed([record.partition], expected_epoch=epoch)
        except (
            ConsumerNotRunningError,
            KafkaTransportError,
            OwnershipRevokedError,
            StaleEpochError,
            OSError,
            TimeoutError,
            SQLAlchemyError,
            ValueError,
        ):
            raise CommittedPositionUnavailableError from None
        position = positions.get(record.partition)
        return (
            self._client.epoch == epoch
            and record.partition in self._client.assignment
            and position is not None
            and position.partition == record.partition
            and position.status == PositionStatus.VERIFIED
            and position.offset is not None
            and position.offset > record.offset
        )
