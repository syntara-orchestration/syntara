"""Kafka partition consumer transport adapter.

Wraps ``AIOKafkaConsumer`` with assignment-epoch tracking and typed
position reads.  All ownership-sensitive operations require the caller's
expected epoch and reject on stale or revoked assignments.  Errors are
sanitized before leaving this module; credentials never appear in
exception messages.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from typing import TYPE_CHECKING

import structlog
from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.abc import ConsumerRebalanceListener
from aiokafka.coordinator.assignors.roundrobin import RoundRobinPartitionAssignor
from aiokafka.errors import KafkaError, KafkaTimeoutError
from aiokafka.structs import OffsetAndMetadata

from syntara.eventstreams.core.consumer import CommittedPositionResult, RebalanceCallback
from syntara.eventstreams.exceptions import (
    ConsumerNotRunningError,
    KafkaTransportError,
    OwnershipRevokedError,
    StaleEpochError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Iterable

    from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
    from syntara.eventstreams.core.connection import ResolvedKafkaConnection

logger = structlog.stdlib.get_logger(__name__)

_CREDENTIAL_SCRUB = re.compile(
    r"(password|username|credential|secret|sasl)[=:\s]+\S+",
    re.IGNORECASE,
)


def _sanitize(message: str) -> str:
    """Remove credential fragments from an error message."""
    return _CREDENTIAL_SCRUB.sub(r"\1=***", message)


class _RebalanceListener(ConsumerRebalanceListener):
    """Delegate rebalance events to bound callables without accessing private state."""

    def __init__(
        self,
        on_revoked: Callable[[set[TopicPartition]], Coroutine[None, None, None]],
        on_assigned: Callable[[set[TopicPartition]], Coroutine[None, None, None]],
    ) -> None:
        """Accept revoked/assigned handlers."""
        self._on_revoked = on_revoked
        self._on_assigned = on_assigned

    async def on_partitions_revoked(self, revoked: set[TopicPartition]) -> None:
        """Forward revocation to the adapter handler."""
        await self._on_revoked(revoked)

    async def on_partitions_assigned(self, assigned: set[TopicPartition]) -> None:
        """Forward assignment to the adapter handler."""
        await self._on_assigned(assigned)


class KafkaPartitionConsumer:
    """Epoch-aware Kafka consumer for a single topic and consumer group.

    Constructed with resolved connection parameters and a source
    configuration.  Client construction uses the story-mandated settings:
    ``RoundRobinPartitionAssignor``, ``enable_auto_commit=False``,
    ``isolation_level="read_committed"``, ``auto_offset_reset="none"``.
    """

    def __init__(
        self,
        connection: ResolvedKafkaConnection,
        source_config: KafkaSourceConfiguration,
        *,
        rebalance_callback: RebalanceCallback | None = None,
        client_id: str | None = None,
    ) -> None:
        """Accept resolved connection and source configuration."""
        self._connection = connection
        self._source_config = source_config
        self._rebalance_callback = rebalance_callback
        self._client_id = client_id

        self._consumer: AIOKafkaConsumer | None = None
        self._assignment: frozenset[int] = frozenset()
        self._epoch: int = 0
        self._running: bool = False

    @property
    def assignment(self) -> frozenset[int]:
        """Return currently assigned partition numbers."""
        return self._assignment

    @property
    def epoch(self) -> int:
        """Return current assignment epoch."""
        return self._epoch

    @property
    def is_running(self) -> bool:
        """Return whether the consumer is started and not yet stopped."""
        return self._running

    @property
    def topic(self) -> str:
        """Return the subscribed topic."""
        return self._source_config.topic

    @property
    def group_id(self) -> str:
        """Return the consumer group identifier."""
        return self._source_config.group_id

    async def start(self) -> None:
        """Construct the ``AIOKafkaConsumer``, start it, and subscribe."""
        if self._running:
            return

        consumer = AIOKafkaConsumer(
            bootstrap_servers=list(self._connection.bootstrap_servers),
            client_id=self._client_id or f"syntara-event-{self._source_config.group_id}",
            group_id=self._source_config.group_id,
            security_protocol=self._connection.security_protocol,
            sasl_mechanism=self._connection.sasl_mechanism,
            sasl_plain_username=self._connection.sasl_plain_username,
            sasl_plain_password=self._connection.sasl_plain_password,
            ssl_context=self._connection.ssl_context,
            enable_auto_commit=False,
            auto_offset_reset="none",
            isolation_level="read_committed",
            partition_assignment_strategy=(RoundRobinPartitionAssignor,),
        )

        try:
            await consumer.start()
        except KafkaError as exc:
            with contextlib.suppress(KafkaError):
                await consumer.stop()
            raise KafkaTransportError(_sanitize(str(exc))) from exc

        self._consumer = consumer
        self._running = True

        listener = _RebalanceListener(
            on_revoked=self._handle_partitions_revoked,
            on_assigned=self._handle_partitions_assigned,
        )
        consumer.subscribe([self._source_config.topic], listener=listener)

    async def stop(self) -> None:
        """Stop the consumer and release resources.

        Raises ``KafkaTransportError`` if the client fails to shut down.
        The client reference is cleared regardless so a failed stop does
        not leave a stale handle.  Safe to call when already stopped.
        """
        self._running = False
        consumer = self._consumer
        if consumer is None:
            self._assignment = frozenset()
            return
        try:
            await consumer.stop()
        except KafkaError as exc:
            raise KafkaTransportError(_sanitize(str(exc))) from None
        finally:
            self._consumer = None
            self._assignment = frozenset()

    async def seek(self, partition: int, offset: int, *, expected_epoch: int) -> None:
        """Seek a partition to an offset; reject stale epochs."""
        consumer = self._require_running()
        self._check_epoch(expected_epoch)
        self._check_ownership(partition)
        try:
            consumer.seek(self._tp(partition), offset)
        except KafkaError as exc:
            raise KafkaTransportError(_sanitize(str(exc))) from exc

    async def commit(self, offsets: dict[int, int], *, expected_epoch: int) -> None:
        """Commit explicit partition-to-next-offset map.

        Does not substitute fetched positions or commit all returned records.
        """
        consumer = self._require_running()
        self._check_epoch(expected_epoch)
        for partition in offsets:
            self._check_ownership(partition)

        offset_map = {self._tp(p): OffsetAndMetadata(o, "") for p, o in offsets.items()}
        try:
            await consumer.commit(offset_map)
        except KafkaError as exc:
            raise KafkaTransportError(_sanitize(str(exc))) from exc

    async def committed(
        self,
        partitions: Iterable[int],
        *,
        timeout_ms: int = 5000,
    ) -> dict[int, CommittedPositionResult]:
        """Read committed offsets with typed verification status.

        aiokafka returns ``None`` both for a genuine no-commit (-1) and for
        ``UnknownTopicOrPartitionError``.  For assigned partitions the
        topic/partition is known to exist, so ``None`` means ``ABSENT``.
        For unassigned partitions the cause is ambiguous: ``UNCERTAIN``.
        """
        consumer = self._require_running()
        results: dict[int, CommittedPositionResult] = {}
        for partition in partitions:
            tp = self._tp(partition)
            try:
                offset_and_meta = await asyncio.wait_for(
                    consumer.committed(tp),
                    timeout=timeout_ms / 1000,
                )
                if offset_and_meta is None:
                    if partition in self._assignment:
                        results[partition] = CommittedPositionResult.absent(partition)
                    else:
                        results[partition] = CommittedPositionResult.uncertain(
                            partition, "no committed offset or unknown partition"
                        )
                else:
                    results[partition] = CommittedPositionResult.verified(partition, offset_and_meta)
            except (TimeoutError, KafkaTimeoutError):
                results[partition] = CommittedPositionResult.unavailable(partition, "timeout")
            except KafkaError as exc:
                results[partition] = CommittedPositionResult.unavailable(partition, _sanitize(str(exc)))
        return results

    async def end_offsets(
        self,
        partitions: Iterable[int],
        *,
        timeout_ms: int = 5000,
    ) -> dict[int, CommittedPositionResult]:
        """Read the ``read_committed`` visible-end boundary for initialization.

        Missing partitions in the response or ``-1`` (unknown offset) are
        reported as ``UNCERTAIN``.
        """
        consumer = self._require_running()
        partition_list = list(partitions)
        tps = [self._tp(p) for p in partition_list]
        try:
            raw = await asyncio.wait_for(
                consumer.end_offsets(tps),
                timeout=timeout_ms / 1000,
            )
        except (TimeoutError, KafkaTimeoutError):
            return {tp.partition: CommittedPositionResult.unavailable(tp.partition, "timeout") for tp in tps}
        except KafkaError as exc:
            msg = _sanitize(str(exc))
            return {tp.partition: CommittedPositionResult.unavailable(tp.partition, msg) for tp in tps}

        results: dict[int, CommittedPositionResult] = {}
        returned_partitions = {tp.partition for tp in raw}
        for p in partition_list:
            if p not in returned_partitions:
                results[p] = CommittedPositionResult.uncertain(p, "partition missing from end_offsets response")
                continue
            offset = raw[self._tp(p)]
            if offset < 0:
                results[p] = CommittedPositionResult.uncertain(p, "unknown offset boundary")
            else:
                results[p] = CommittedPositionResult.verified(p, offset)
        return results

    async def pause(self, partitions: Iterable[int], *, expected_epoch: int) -> None:
        """Pause fetching from partitions without dropping group membership."""
        consumer = self._require_running()
        self._check_epoch(expected_epoch)
        partition_list = list(partitions)
        for p in partition_list:
            self._check_ownership(p)
        consumer.pause(*[self._tp(p) for p in partition_list])

    async def resume(self, partitions: Iterable[int], *, expected_epoch: int) -> None:
        """Resume fetching from previously paused partitions."""
        consumer = self._require_running()
        self._check_epoch(expected_epoch)
        partition_list = list(partitions)
        for p in partition_list:
            self._check_ownership(p)
        consumer.resume(*[self._tp(p) for p in partition_list])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_running(self) -> AIOKafkaConsumer:
        if not self._running or self._consumer is None:
            raise ConsumerNotRunningError
        return self._consumer

    def _check_epoch(self, expected_epoch: int) -> None:
        if expected_epoch != self._epoch:
            raise StaleEpochError(expected=expected_epoch, current=self._epoch)

    def _check_ownership(self, partition: int) -> None:
        if partition not in self._assignment:
            raise OwnershipRevokedError(partition)

    def _tp(self, partition: int) -> TopicPartition:
        return TopicPartition(self._source_config.topic, partition)

    async def _handle_partitions_revoked(self, revoked: set[TopicPartition]) -> None:
        revoked_partitions = frozenset(tp.partition for tp in revoked)
        if not revoked_partitions:
            return

        epoch = self._epoch
        try:
            if self._rebalance_callback is not None:
                await self._rebalance_callback.on_partitions_revoked(revoked_partitions, epoch)
        finally:
            self._assignment -= revoked_partitions
            self._epoch += 1
            logger.debug(
                "Partitions revoked",
                topic=self.topic,
                revoked=sorted(revoked_partitions),
                epoch=self._epoch,
            )

    async def _handle_partitions_assigned(self, assigned: set[TopicPartition]) -> None:
        assigned_partitions = frozenset(tp.partition for tp in assigned)
        self._assignment = assigned_partitions
        epoch = self._epoch

        logger.debug(
            "Partitions assigned",
            topic=self.topic,
            assigned=sorted(assigned_partitions),
            epoch=epoch,
        )

        if self._rebalance_callback is not None:
            await self._rebalance_callback.on_partitions_assigned(assigned_partitions, epoch)
