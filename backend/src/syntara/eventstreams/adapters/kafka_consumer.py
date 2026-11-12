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
from typing import TYPE_CHECKING, Any, cast

import structlog
from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.abc import ConsumerRebalanceListener
from aiokafka.client import ConnectionGroup
from aiokafka.coordinator.assignors.roundrobin import RoundRobinPartitionAssignor
from aiokafka.errors import (
    IncompatibleBrokerVersion,
    KafkaError,
    KafkaTimeoutError,
    OffsetOutOfRangeError,
    UnknownTopicOrPartitionError,
    UnsupportedVersionError,
)
from aiokafka.protocol.fetch import FetchRequest_v0, FetchResponse_v0
from aiokafka.structs import OffsetAndMetadata

from syntara.core.config.base import get_settings
from syntara.eventstreams.adapters.kafka_identity import SourceMetadataRequest, decode_source_identity
from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata, KafkaTimestampType
from syntara.eventstreams.core.consumer import (
    MAX_POSITION_OFFSET,
    CommittedPositionResult,
    IdentityObservation,
    IdentityStatus,
    PartitionSetObservation,
    PartitionSetStatus,
    RebalanceCallback,
    SourceIdentityObservation,
)
from syntara.eventstreams.core.envelope import RawEvent, RawEventHeader
from syntara.eventstreams.exceptions import (
    ConsumerNotRunningError,
    KafkaSourceIdentityError,
    KafkaTransportError,
    OwnershipRevokedError,
    StaleEpochError,
)
from syntara.integrations.lib.kafka_client import KafkaPolicyClient

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Iterable, Iterator

    from aiokafka.cluster import ClusterMetadata
    from aiokafka.protocol.api import Request, Response

    from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
    from syntara.eventstreams.core.connection import ResolvedKafkaConnection
    from syntara.eventstreams.core.source_metadata import EventSourceMetadata

logger = structlog.stdlib.get_logger(__name__)

_CREDENTIAL_SCRUB = re.compile(
    r"(password|username|credential|secret|sasl)[=:\s]+\S+",
    re.IGNORECASE,
)


def _sanitize(message: str) -> str:
    """Remove credential fragments from an error message."""
    return _CREDENTIAL_SCRUB.sub(r"\1=***", message)


class _ResetAwareKafkaClient(KafkaPolicyClient):
    """Observe offset errors before aiokafka silently applies its earliest fallback."""

    def __init__(
        self,
        *,
        topic: str,
        assignment_epoch: Callable[[], int],
        on_reset: Callable[[int, int], None],
        on_metadata_changed: Callable[[], None] | None = None,
        on_topic_missing: Callable[[], None] | None = None,
        **kwargs: object,
    ) -> None:
        """Keep reset signals scoped to this consumer and its assignment epoch."""
        super().__init__(**kwargs)
        self._reset_topic = topic
        self._assignment_epoch = assignment_epoch
        self._on_reset = on_reset
        self._on_metadata_changed = on_metadata_changed
        self._on_topic_missing = on_topic_missing

    async def _metadata_update(self, cluster_metadata: ClusterMetadata, topics: Iterable[str] | None) -> bool:
        """Require source verification when the SDK refreshes topic/broker metadata."""
        if self._on_metadata_changed is not None:
            self._on_metadata_changed()
        return await super()._metadata_update(cluster_metadata, topics)

    async def send(
        self, node_id: int | str, request: Request[Any], *, group: ConnectionGroup = ConnectionGroup.DEFAULT
    ) -> Response | None:
        """Preserve the response while reporting affected partitions to the adapter."""
        epoch = self._assignment_epoch()
        response = await super().send(node_id, request, group=group)
        if response is not None and request.API_KEY == FetchRequest_v0.API_KEY:
            # Every installed FetchResponse version starts each partition tuple
            # with partition/error_code. Remaining fields differ by version.
            for topic, partitions in cast("FetchResponse_v0", response).topics or ():
                if topic != self._reset_topic:
                    continue
                for partition in partitions:
                    if partition[1] == OffsetOutOfRangeError.errno:
                        self._on_reset(partition[0], epoch)
                    elif (
                        partition[1] == UnknownTopicOrPartitionError.errno
                        and epoch == self._assignment_epoch()
                        and self._on_topic_missing is not None
                    ):
                        self._on_topic_missing()
        return response


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
    ``isolation_level="read_committed"``, ``auto_offset_reset="earliest"``.
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
        self._stop_task: asyncio.Task[None] | None = None
        self._position_operations: set[int] = set()
        self._offset_resets: set[int] = set()
        self._metadata_revision = 0
        self._verified_metadata_revision = 0
        self._last_source_identity: SourceIdentityObservation | None = None
        self._topic_missing = False
        self._identity_lock = asyncio.Lock()

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

    def set_rebalance_callback(self, callback: RebalanceCallback) -> None:
        """Bind a runner before startup without exposing the underlying client."""
        if self._running:
            msg = "Rebalance callbacks must be bound before startup"
            raise ValueError(msg)
        self._rebalance_callback = callback

    def _note_offset_reset(self, partition: int, epoch: int) -> None:
        if epoch == self._epoch and partition in self._assignment:
            self._offset_resets.add(partition)

    def _check_offset_resets(self, partitions: Iterable[int]) -> None:
        if self._offset_resets.intersection(partitions):
            msg = "Kafka offset reset requires position reconciliation"
            raise KafkaTransportError(msg)

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
        if self._consumer is not None:
            msg = "Consumer shutdown is incomplete; retry stop before starting"
            raise KafkaTransportError(msg)

        settings = get_settings()
        connection_options: dict[str, Any] = {  # aiokafka's untyped constructor boundary
            "bootstrap_servers": list(self._connection.bootstrap_servers),
            "client_id": self._client_id or f"syntara-event-{self._source_config.group_id}",
            "security_protocol": self._connection.security_protocol,
            "sasl_mechanism": self._connection.sasl_mechanism,
            "sasl_plain_username": (
                self._connection.sasl_plain_username.get_secret_value()
                if self._connection.sasl_plain_username is not None
                else None
            ),
            "sasl_plain_password": (
                self._connection.sasl_plain_password.get_secret_value()
                if self._connection.sasl_plain_password is not None
                else None
            ),
            "ssl_context": self._connection.ssl_context,
        }
        consumer = AIOKafkaConsumer(
            **connection_options,
            group_id=self._source_config.group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            isolation_level="read_committed",
            partition_assignment_strategy=(RoundRobinPartitionAssignor,),
            max_poll_records=settings.event_fetch_max_records,
            fetch_max_bytes=settings.event_queue_max_bytes,
            max_partition_fetch_bytes=settings.event_queue_max_bytes,
        )
        # aiokafka 0.14 has no public client/factory injection. Its constructor
        # has not opened sockets or started tasks yet. Replace the internal
        # client before startup so coordinator and metadata paths use policy too.
        consumer._client = _ResetAwareKafkaClient(  # noqa: SLF001 - aiokafka has no client injection API
            **connection_options,
            topic=self.topic,
            assignment_epoch=lambda: self._epoch,
            on_reset=self._note_offset_reset,
            on_metadata_changed=self._metadata_changed,
            on_topic_missing=self._note_topic_missing,
        )

        # Startup can be cancelled by a deadline or shutdown; retain ownership
        # so the runner's cleanup can close a partially started client.
        self._consumer = consumer
        try:
            await consumer.start()
        except KafkaError as exc:
            with contextlib.suppress(KafkaTransportError):
                await self.stop()
            raise KafkaTransportError(_sanitize(str(exc))) from exc

        self._running = True

        listener = _RebalanceListener(
            on_revoked=self._handle_partitions_revoked,
            on_assigned=self._handle_partitions_assigned,
        )
        consumer.subscribe([self._source_config.topic], listener=listener)

    async def fetch(
        self,
        partitions: Iterable[int],
        context: EventSourceMetadata,
        *,
        expected_epoch: int,
        max_records: int,
        timeout_ms: int,
    ) -> dict[int, list[RawEvent]]:
        """Fetch only requested owned partitions; returned positions never authorize commits.

        Kafka may return an oversized batch despite byte limits. The runner
        bounds its retained queues and seeks unqueued records back while owned.
        No callback lock is held across getmany().
        """
        if max_records <= 0 or timeout_ms <= 0:
            msg = "Fetch limits must be positive"
            raise ValueError(msg)
        consumer = self._require_running()
        self._check_epoch(expected_epoch)
        requested = tuple(dict.fromkeys(partitions))
        for partition in requested:
            self._check_ownership(partition)
        self._check_offset_resets(requested)
        await self._verify_metadata_identity(expected_epoch)
        if not requested:
            consumer.pause(*(self._tp(partition) for partition in self._assignment))
        try:
            batches = await consumer.getmany(
                *(self._tp(partition) for partition in requested),
                timeout_ms=timeout_ms,
                max_records=max_records,
            )
        except KafkaError as exc:
            raise KafkaTransportError(_sanitize(str(exc))) from None
        self._require_running()
        self._check_epoch(expected_epoch)
        self._check_offset_resets(requested)
        await self._verify_metadata_identity(expected_epoch)
        result: dict[int, list[RawEvent]] = {}
        for tp, records in batches.items():
            self._check_ownership(tp.partition)
            if tp.topic != self.topic or tp.partition not in requested:
                msg = "Unexpected partition in fetch response"
                raise KafkaTransportError(msg)
            result[tp.partition] = [
                RawEvent(
                    value=record.value,
                    key=record.key,
                    headers=tuple(RawEventHeader(name=name, value=value) for name, value in record.headers),
                    source_metadata=KafkaSourceMetadata(
                        **context.model_dump(),
                        topic=tp.topic,
                        partition=tp.partition,
                        offset=str(record.offset),
                        timestamp_ms=record.timestamp,
                        timestamp_type=(
                            KafkaTimestampType.create_time
                            if record.timestamp_type == 0
                            else KafkaTimestampType.log_append_time
                            if record.timestamp_type == 1
                            else None
                        ),
                    ),
                )
                for record in records
            ]
        return result

    async def stop(self) -> None:
        """Stop the consumer and release resources.

        Raises ``KafkaTransportError`` if the client fails to shut down.
        Retain the client after a failed/cancelled close so stop can retry.
        Safe to call when already stopped.
        Revoke callbacks can drain using their current ownership/epoch until
        the stop call exits; final cleanup then invalidates that epoch.
        """
        consumer = self._consumer
        if consumer is None:
            return
        if self._stop_task is None:
            self._stop_task = asyncio.create_task(consumer.stop())
            self._stop_task.add_done_callback(self._stop_settled)
        try:
            await asyncio.shield(self._stop_task)
        except KafkaError as exc:
            raise KafkaTransportError(_sanitize(str(exc))) from None
        else:
            self._consumer = None
            self._stop_task = None
        finally:
            if self._running:
                self._epoch += 1
            self._running = False
            self._assignment = frozenset()
            self._offset_resets.clear()

    @staticmethod
    def _stop_settled(task: asyncio.Task[None]) -> None:
        if not task.cancelled():
            task.exception()

    async def seek(self, partition: int, offset: int, *, expected_epoch: int) -> None:
        """Seek a partition to an offset; reject stale epochs."""
        consumer = self._require_running()
        self._check_epoch(expected_epoch)
        self._check_ownership(partition)
        try:
            consumer.seek(self._tp(partition), offset)
        except KafkaError as exc:
            raise KafkaTransportError(_sanitize(str(exc))) from exc
        self._offset_resets.discard(partition)

    async def commit(self, offsets: dict[int, int], *, expected_epoch: int) -> None:
        """Commit explicit partition-to-next-offset map.

        Does not substitute fetched positions or commit all returned records.
        """
        consumer = self._require_running()
        self._check_epoch(expected_epoch)
        for partition in offsets:
            self._check_ownership(partition)
        self._check_offset_resets(offsets)
        await self._verify_metadata_identity(expected_epoch)

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
        """Observe cluster/topic IDs and the complete exact-topic partition set.

        Uses the consumer's authenticated client for one bounded, version-
        negotiated Metadata request. The request cannot create topics. Status
        is independent per identifier: unsupported protocol, unknown topic,
        unavailable lookup and uncertain/missing evidence are distinct.
        Partition membership is independently verified, even without topic-ID
        support. It comes from fresh metadata, never assignment or fetched data.

        Epoch checks before/after I/O reject a superseded assignment, including
        stop/restart. A caller must still use current ownership and the same
        expected epoch for any subsequent seek/commit. This method neither
        compares saved IDs nor decides initialization or gap-recovery policy.
        """
        consumer = self._require_observation_epoch(expected_epoch, timeout_ms)
        metadata_revision = self._metadata_revision
        try:
            async with asyncio.timeout(timeout_ms / 1000):
                # aiokafka has no public consumer API for cluster/topic UUIDs.
                # Keep authenticated metadata transport access inside this adapter.
                # The installed-client compatibility test guards this private boundary.
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
                partitions=PartitionSetObservation(
                    status=PartitionSetStatus.UNAVAILABLE, error="topic is unknown to broker"
                ),
            )
        except KafkaError:
            result = self._identity_failure(expected_epoch, IdentityStatus.UNAVAILABLE, "metadata lookup failed")
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            result = self._identity_failure(expected_epoch, IdentityStatus.UNCERTAIN, "invalid metadata response")
        self._require_observation_epoch(expected_epoch, timeout_ms)
        if result.topic_id.status == IdentityStatus.UNKNOWN_TOPIC:
            self._note_topic_missing()
        self._remember_source_identity(result, metadata_revision)
        return result

    def _metadata_changed(self) -> None:
        self._metadata_revision += 1

    def _note_topic_missing(self) -> None:
        self._topic_missing |= (
            self._last_source_identity is not None or self._source_config.initial_partition_ids is not None
        )
        self._metadata_changed()

    def _remember_source_identity(self, observation: SourceIdentityObservation, revision: int) -> None:
        previous = self._last_source_identity
        if self._topic_missing and (previous is None or previous.topic_id.status != IdentityStatus.VERIFIED):
            msg = "Suspected Kafka topic recreation requires source replacement"
            raise KafkaSourceIdentityError(msg)
        for name in ("cluster_id", "topic_id"):
            current = getattr(observation, name)
            saved = getattr(previous, name) if previous is not None else None
            if current.status not in {IdentityStatus.VERIFIED, IdentityStatus.UNSUPPORTED}:
                return
            if (
                saved is not None
                and saved.status == IdentityStatus.VERIFIED
                and current.status == IdentityStatus.VERIFIED
                and current.value != saved.value
            ):
                msg = "Kafka source identity changed; source replacement is required"
                raise KafkaSourceIdentityError(msg)
            if (
                saved is not None
                and saved.status == IdentityStatus.VERIFIED
                and current.status != IdentityStatus.VERIFIED
            ):
                return
        if observation.partitions.status != PartitionSetStatus.VERIFIED:
            return
        self._last_source_identity = observation
        self._topic_missing = False
        self._verified_metadata_revision = revision

    async def _verify_metadata_identity(self, expected_epoch: int) -> None:
        if self._verified_metadata_revision == self._metadata_revision:
            return
        async with self._identity_lock:
            if self._verified_metadata_revision != self._metadata_revision:
                await self.observe_source_identity(expected_epoch=expected_epoch)
                if self._verified_metadata_revision != self._metadata_revision:
                    msg = "Kafka source identity requires position reconciliation"
                    raise KafkaTransportError(msg)
        self._check_epoch(expected_epoch)

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
            topic=self.topic,
            assignment_epoch=epoch,
            cluster_id=evidence,
            topic_id=evidence,
            partitions=PartitionSetObservation(
                status=PartitionSetStatus.UNCERTAIN
                if status == IdentityStatus.UNCERTAIN
                else PartitionSetStatus.UNAVAILABLE,
                error=error,
            ),
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
            self._offset_resets.difference_update(revoked_partitions)
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
        self._offset_resets.intersection_update(assigned_partitions)
        epoch = self._epoch

        logger.debug(
            "Partitions assigned",
            topic=self.topic,
            assigned=sorted(assigned_partitions),
            epoch=epoch,
        )

        if self._rebalance_callback is not None:
            await self._rebalance_callback.on_partitions_assigned(assigned_partitions, epoch)
