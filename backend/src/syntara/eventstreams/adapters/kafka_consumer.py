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
from aiokafka.errors import (
    IncompatibleBrokerVersion,
    KafkaError,
    KafkaTimeoutError,
    UnknownTopicOrPartitionError,
    UnsupportedVersionError,
)
from aiokafka.structs import OffsetAndMetadata

from syntara.eventstreams.adapters.kafka_identity import SourceMetadataRequest, decode_source_identity
from syntara.eventstreams.core.consumer import (
    MAX_POSITION_OFFSET,
    CommittedPositionResult,
    IdentityObservation,
    IdentityStatus,
    RebalanceCallback,
    SourceIdentityObservation,
)
from syntara.eventstreams.exceptions import (
    ConsumerNotRunningError,
    KafkaTransportError,
    OwnershipRevokedError,
    StaleEpochError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Iterable, Iterator

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
        self._position_operations: set[int] = set()

    @property
    def assignment(self) -> frozenset[int]:
        """Return currently assigned partition numbers."""
        return self._assignment

    @property
    def epoch(self) -> int:
        """Return the opaque epoch, advanced on assignment, revocation and stop."""
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

    @contextlib.contextmanager
    def position_operation(self, partition: int, *, expected_epoch: int) -> Iterator[bool]:
        """Keep finite position changes exclusive across services sharing this client."""
        self._require_running()
        self._check_epoch(expected_epoch)
        self._check_ownership(partition)
        if partition in self._position_operations:
            yield False
            return
        self._position_operations.add(partition)
        try:
            yield True
        finally:
            self._position_operations.remove(partition)

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
        if self._running:
            self._epoch += 1
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
        expected_epoch: int | None = None,
    ) -> dict[int, CommittedPositionResult]:
        """Read committed offsets with typed verification status.

        aiokafka returns ``None`` both for a genuine no-commit (-1) and for
        ``UnknownTopicOrPartitionError``.  For assigned partitions the
        topic/partition is known to exist, so ``None`` means ``ABSENT``.
        For unassigned partitions the cause is ambiguous: ``UNCERTAIN``.
        Each partition read has a bounded timeout. Initialization/recovery must
        pass expected_epoch so a rebalance during I/O invalidates the results;
        omitting it is only suitable for diagnostics, not recovery decisions.
        """
        consumer = self._require_observation_epoch(expected_epoch, timeout_ms)
        results: dict[int, CommittedPositionResult] = {}
        for partition in partitions:
            if expected_epoch is not None:
                self._check_epoch(expected_epoch)
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
                    results[partition] = self._position_result(partition, offset_and_meta)
            except (TimeoutError, KafkaTimeoutError):
                results[partition] = CommittedPositionResult.unavailable(partition, "timeout")
            except KafkaError:
                results[partition] = CommittedPositionResult.unavailable(partition, "committed position lookup failed")
        self._require_observation_epoch(expected_epoch, timeout_ms)
        return results

    async def beginning_offsets(
        self,
        partitions: Iterable[int],
        *,
        expected_epoch: int,
        timeout_ms: int = 5000,
    ) -> dict[int, CommittedPositionResult]:
        """Observe earliest retained offsets without changing consumer positions.

        One timeout bounds the complete batch. Missing/invalid offsets and
        unknown partitions are uncertain; broker failures/timeouts are
        unavailable. Offsets are verified only in the non-negative int64 range.
        The expected epoch is checked before and after I/O, including failures.
        Reads do not establish ownership or authorize processing/commits.
        """
        return await self._read_boundary(
            partitions, expected_epoch=expected_epoch, timeout_ms=timeout_ms, beginning=True
        )

    async def end_offsets(
        self,
        partitions: Iterable[int],
        *,
        timeout_ms: int = 5000,
        expected_epoch: int | None = None,
    ) -> dict[int, CommittedPositionResult]:
        """Observe the read_committed visible-end boundary without resetting.

        Initialization/recovery callers must supply expected_epoch, retain that
        same epoch across observations, and use it for ownership-checked writes.
        Omitting it preserves diagnostic reads without assignment guarantees.
        """
        return await self._read_boundary(
            partitions, expected_epoch=expected_epoch, timeout_ms=timeout_ms, beginning=False
        )

    async def observe_source_identity(
        self,
        *,
        expected_epoch: int,
        timeout_ms: int = 5000,
    ) -> SourceIdentityObservation:
        """Observe cluster and exact-topic IDs; never infer an identity match.

        Uses the consumer's authenticated client for one bounded, version-
        negotiated Metadata request. The request cannot create topics. Status
        is independent per identifier: unsupported protocol, unknown topic,
        unavailable lookup and uncertain/missing evidence are distinct.

        Epoch checks before/after I/O reject a superseded assignment, including
        stop/restart. A caller must still use current ownership and the same
        expected epoch for any subsequent seek/commit. This method neither
        compares saved IDs nor decides initialization or gap-recovery policy.
        """
        consumer = self._require_observation_epoch(expected_epoch, timeout_ms)
        try:
            async with asyncio.timeout(timeout_ms / 1000):
                # aiokafka has no public consumer API for cluster/topic UUIDs.
                # Keep access to its authenticated transport inside this adapter.
                client = consumer._client  # noqa: SLF001 -- authenticated transport boundary, no public metadata-ID API
                node_id = client.get_random_node()
                if node_id is None:
                    result = self._identity_failure(
                        expected_epoch, IdentityStatus.UNAVAILABLE, "no metadata broker available"
                    )
                else:
                    response = await client.send(node_id, SourceMetadataRequest(self.topic))
                    result = decode_source_identity(response, topic=self.topic, epoch=expected_epoch)
        except (TimeoutError, KafkaTimeoutError):
            result = self._identity_failure(expected_epoch, IdentityStatus.UNAVAILABLE, "metadata lookup timed out")
        except (UnsupportedVersionError, IncompatibleBrokerVersion, NotImplementedError):
            result = self._identity_failure(expected_epoch, IdentityStatus.UNSUPPORTED, "metadata protocol unsupported")
        except UnknownTopicOrPartitionError:
            result = SourceIdentityObservation(
                topic=self.topic,
                assignment_epoch=expected_epoch,
                cluster_id=IdentityObservation(status=IdentityStatus.UNAVAILABLE, error="metadata lookup failed"),
                topic_id=IdentityObservation(status=IdentityStatus.UNKNOWN_TOPIC, error="topic is unknown to broker"),
            )
        except KafkaError:
            result = self._identity_failure(expected_epoch, IdentityStatus.UNAVAILABLE, "metadata lookup failed")
        except (AttributeError, KeyError, TypeError, ValueError):
            result = self._identity_failure(expected_epoch, IdentityStatus.UNCERTAIN, "invalid metadata response")
        self._require_observation_epoch(expected_epoch, timeout_ms)
        return result

    async def _read_boundary(
        self,
        partitions: Iterable[int],
        *,
        expected_epoch: int | None,
        timeout_ms: int,
        beginning: bool,
    ) -> dict[int, CommittedPositionResult]:
        consumer = self._require_observation_epoch(expected_epoch, timeout_ms)
        tps = [self._tp(p) for p in dict.fromkeys(partitions)]
        if not tps:
            return {}
        try:
            if beginning:
                raw = await asyncio.wait_for(consumer.beginning_offsets(tps), timeout=timeout_ms / 1000)
            else:
                raw = await asyncio.wait_for(consumer.end_offsets(tps), timeout=timeout_ms / 1000)
            results = {tp.partition: self._position_result(tp.partition, raw.get(tp)) for tp in tps}
        except UnknownTopicOrPartitionError:
            results = {
                tp.partition: CommittedPositionResult.uncertain(tp.partition, "unknown topic or partition")
                for tp in tps
            }
        except (TimeoutError, KafkaTimeoutError):
            results = {tp.partition: CommittedPositionResult.unavailable(tp.partition, "timeout") for tp in tps}
        except KafkaError:
            results = {
                tp.partition: CommittedPositionResult.unavailable(tp.partition, "offset lookup failed") for tp in tps
            }
        except (AttributeError, TypeError, ValueError):
            results = {
                tp.partition: CommittedPositionResult.uncertain(tp.partition, "invalid offset response") for tp in tps
            }
        self._require_observation_epoch(expected_epoch, timeout_ms)
        return results

    @staticmethod
    def _position_result(partition: int, offset: object) -> CommittedPositionResult:
        if type(offset) is not int or not 0 <= offset <= MAX_POSITION_OFFSET:
            return CommittedPositionResult.uncertain(partition, "offset missing or outside non-negative int64 range")
        return CommittedPositionResult.verified(partition, offset)

    def _require_observation_epoch(self, expected_epoch: int | None, timeout_ms: int) -> AIOKafkaConsumer:
        if type(timeout_ms) is not int or timeout_ms <= 0:
            msg = "timeout_ms must be positive"
            raise ValueError(msg)
        if expected_epoch is not None:
            self._check_epoch(expected_epoch)
        return self._require_running()

    def _identity_failure(self, epoch: int, status: IdentityStatus, error: str) -> SourceIdentityObservation:
        evidence = IdentityObservation(status=status, error=error)
        return SourceIdentityObservation(
            topic=self.topic, assignment_epoch=epoch, cluster_id=evidence, topic_id=evidence
        )

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
        self._epoch += 1
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
