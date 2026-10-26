"""Single-subscription Kafka runner; durable services own scheduling decisions."""

import asyncio
import re
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import TypedDict
from uuid import UUID

import structlog
from aiokafka.errors import KafkaError, KafkaTimeoutError
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import get_settings
from syntara.core.constants import EventDeliveryDefaults, EventSchedulingDefaults, EventStreamLimits, FieldLimits
from syntara.eventstreams.adapters.kafka_committed_position import KafkaCommittedPositionVerifier
from syntara.eventstreams.adapters.kafka_consumer import KafkaPartitionConsumer
from syntara.eventstreams.adapters.kafka_delivery_reader import KafkaDeliveryReader
from syntara.eventstreams.adapters.kafka_initial_position import PositionRequest, PositionResult, PositionStatus
from syntara.eventstreams.adapters.kafka_initial_position_service import KafkaInitialPositionService
from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata
from syntara.eventstreams.adapters.kafka_position_control import DrainEvidence
from syntara.eventstreams.adapters.kafka_position_store import KafkaInitialPositionStore
from syntara.eventstreams.adapters.kafka_record_identity import KafkaRecordIdentity
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.core.consumer import MAX_POSITION_OFFSET
from syntara.eventstreams.core.deduplication import DeliveryIdentity, DeliveryState, TerminalDeliveryCache
from syntara.eventstreams.core.envelope import RawEvent
from syntara.eventstreams.core.handler import ResolvedDelivery
from syntara.eventstreams.core.processing import (
    CONTENT_INSPECTION_PENDING,
    HeldRecord,
    InspectedRecord,
    PendingContentFailure,
    RecordProcessingGate,
)
from syntara.eventstreams.core.runtime import RunnerStatus, RuntimeFailureCode, RuntimeState, SubscriptionRuntimeError
from syntara.eventstreams.core.source_metadata import EventSourceMetadata
from syntara.eventstreams.exceptions import (
    ConsumerNotRunningError,
    KafkaTransportError,
    OwnershipRevokedError,
    StaleEpochError,
)
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.admission_service import EventAdmissionService
from syntara.eventstreams.services.delivery_retention_service import EventDeliveryRetentionService
from syntara.eventstreams.services.execution_preparation_service import EventExecutionPreparationService
from syntara.eventstreams.services.record_processing_service import EventRecordProcessingService

logger = structlog.stdlib.get_logger(__name__)
_TRANSPORT_ERRORS = (ConsumerNotRunningError, KafkaTransportError, OwnershipRevokedError, StaleEpochError)


class _ProcessingGuardArguments(TypedDict, total=False):
    admission_guard: Callable[[], bool]


@dataclass
class _Partition:
    partition: int
    epoch: int
    records: deque[RawEvent] = field(default_factory=deque)
    byte_count: int = 0
    task: asyncio.Task[None] | None = None
    ready: bool = False
    eligible: bool = False
    paused: bool = True
    closing: bool = False
    held: HeldRecord | None = None
    resolved_next_offset: int | None = None
    rewind_offset: int | None = None
    reload_required: bool = False
    pending_failure: PendingContentFailure | None = None
    content_gate_unknown: bool = False
    inspection_next_offset: int | None = None
    inspection_end_offset: int | None = None
    fence: UUID | None = None
    reconciled_until: float = 0
    initialization: PositionResult | None = None


def raw_event_size(event: RawEvent) -> int:
    """Count raw value/key/header bytes retained in the application queue."""
    return (
        len(event.value or b"")
        + len(event.key or b"")
        + sum(
            len(header.name.encode("utf-8")) + len(header.value or b"") + EventStreamLimits.HEADER_JSON_OVERHEAD_BYTES
            for header in event.headers
        )
    )


class KafkaRecordRunner:
    """Own assignment-local queues, bounded work, explicit commits, and local fences."""

    def __init__(
        self,
        snapshot: SubscriptionSnapshot,
        client: KafkaPartitionConsumer,
        session_factory: Callable[..., AsyncSession],
        preparation: EventExecutionPreparationService,
        admission: EventAdmissionService,
        *,
        owner_worker_id: str,
        processing: EventRecordProcessingService | None = None,
        positions: KafkaInitialPositionService | None = None,
        deliveries: KafkaDeliveryReader | None = None,
        work_semaphore: asyncio.Semaphore | None = None,
        lookup: TerminalDeliveryCache | None = None,
        gate: RecordProcessingGate | None = None,
    ) -> None:
        """Compose completed services; callers may share a downstream concurrency bound."""
        if not isinstance(snapshot.configuration, KafkaSourceConfiguration) or (
            client.topic != snapshot.configuration.topic or client.group_id != snapshot.configuration.group_id
        ):
            msg = "Runner client must match its immutable Kafka source"
            raise ValueError(msg)
        self.snapshot = snapshot
        self._client = client
        self._owner = owner_worker_id
        self._settings = get_settings()
        self._lookup = lookup
        self._gate = gate
        self._processing = (
            processing
            if processing is not None
            else EventRecordProcessingService(session_factory, preparation, admission, lookup=lookup, gate=gate)
        )
        self._deliveries = deliveries if deliveries is not None else KafkaDeliveryReader(session_factory)
        self._positions = (
            positions
            if positions is not None
            else KafkaInitialPositionService(KafkaInitialPositionStore(session_factory), client, admission, self)
        )
        self.retention = EventDeliveryRetentionService(
            session_factory, verifier=KafkaCommittedPositionVerifier(client, snapshot, self._deliveries)
        )
        self._work = (
            work_semaphore
            if work_semaphore is not None
            else asyncio.Semaphore(self._settings.event_processing_concurrency)
        )
        self._partitions: dict[int, _Partition] = {}
        self._assignment_epoch: int | None = None
        self._commit_lock = asyncio.Lock()
        self._fetch_lock = asyncio.Lock()
        self._stop_lock = asyncio.Lock()
        self._closing = False
        self._started = False
        self._placement_authority: Callable[[], bool] | None = None
        self._placement_enabled = True
        self._stopped = False
        self._drain_deadline: float | None = None
        self._fetching: frozenset[int] = frozenset()
        self._fetch_idle = asyncio.Event()
        self._fetch_idle.set()
        self._client.set_rebalance_callback(self)

    @property
    def queued_records(self) -> int:
        """Include in-flight heads in the subscription record bound."""
        return sum(len(state.records) + int(state.pending_failure is not None) for state in self._partitions.values())

    @property
    def queued_bytes(self) -> int:
        """Include in-flight source bytes in the subscription byte bound."""
        return sum(state.byte_count for state in self._partitions.values())

    @property
    def ready_partitions(self) -> frozenset[int]:
        """Report partial initialization without making client startup mean readiness."""
        return frozenset(state.partition for state in self._partitions.values() if state.ready and self._owned(state))

    def _resolution_open(self) -> bool:
        return self._gate is None or self._gate.resolution_open(self.snapshot) is True

    def _admission_open(self) -> bool:
        return self._placement_open() and (self._gate is None or self._gate.admission_open(self.snapshot) is True)

    def bind_placement(self, permits_admission: Callable[[], bool]) -> None:
        """Hold admission closed throughout supervised factory/client startup."""
        if self._started:
            msg = "Placement must be bound before runner startup"
            raise ValueError(msg)
        self._placement_authority = permits_admission
        self._placement_enabled = False

    def _placement_open(self) -> bool:
        return self._placement_enabled and (self._placement_authority is None or self._placement_authority() is True)

    def open_admission(self) -> bool:
        """Open intake after the supervisor checks a confirmed current lease."""
        if self._closing or self._stopped or self._placement_authority is None or not self._placement_authority():
            return False
        self._placement_enabled = True
        return True

    def _invalidate_gate(self) -> None:
        if self._gate is not None:
            self._gate.dependency_failed(self.snapshot)

    def _cache_admitted(self, state: _Partition) -> bool:
        return (
            self._lookup is not None
            and self._gate is not None
            and self._active(state)
            and state.ready
            and state.eligible
            and state.reconciled_until > asyncio.get_running_loop().time()
            and not state.content_gate_unknown
            and state.pending_failure is None
            and state.held is None
            and self._admission_open()
            and self._resolution_open()
        )

    def _commit_allowed(self, state: _Partition) -> bool:
        # Admission/content gates protect the unresolved head. A later hold or
        # expired admission snapshot cannot invalidate an earlier resolved prefix.
        return (
            self._owned(state)
            and state.ready
            and state.fence is None
            and self._resolution_open()
            and (self._drain_deadline is None or asyncio.get_running_loop().time() < self._drain_deadline)
        )

    @property
    def status(self) -> RunnerStatus:
        """Observe local convergence without granting admission or position authority."""
        if self._stopped:
            return RunnerStatus(state=RuntimeState.STOPPED)
        if self._closing:
            return RunnerStatus(state=RuntimeState.DRAINING)
        if not self._started or self._assignment_epoch != self._client.epoch:
            return RunnerStatus(state=RuntimeState.STARTING)
        states = [state for state in self._partitions.values() if self._owned(state)]
        # A permanent content hold must remain visible even if another partition
        # is only waiting for initialization or a transient dependency.
        states.sort(key=lambda state: (not bool(state.held and state.held.permanent_content_error), state.partition))
        for state in states:
            if state.held is None:
                continue
            reason = state.held.reason
            if reason == "initialization_unresolved" and state.initialization is not None:
                initialization_reason = state.initialization.reason
                if state.initialization.status == PositionStatus.RECOVERY_GAP:
                    reason = "recovery_gap"
                elif initialization_reason is not None and re.fullmatch(r"[a-z][a-z0-9_]{0,99}", initialization_reason):
                    reason = initialization_reason
            return RunnerStatus(
                state=RuntimeState.BLOCKED,
                reason=reason,
                permanent_content_error=state.held.permanent_content_error,
            )
        return RunnerStatus(
            state=RuntimeState.STARTING if any(not state.ready for state in states) else RuntimeState.ACTIVE
        )

    def _owned(self, state: _Partition) -> bool:
        return (
            self._client.epoch == state.epoch
            and state.partition in self._client.assignment
            and self._partitions.get(state.partition) is state
        )

    def _request(self, state: _Partition) -> PositionRequest:
        return PositionRequest(
            source_id=self.snapshot.source_id,
            source_generation=self.snapshot.source_generation,
            configuration_revision=self.snapshot.configuration_revision,
            partition=state.partition,
            assignment_epoch=state.epoch,
        )

    def _identity(self, event: RawEvent) -> DeliveryIdentity:
        metadata = event.source_metadata
        if not isinstance(metadata, KafkaSourceMetadata) or metadata.topic != self._client.topic:
            msg = "Unexpected source event"
            raise ValueError(msg)
        return DeliveryIdentity(
            deployment_id=self.snapshot.deployment_id,
            integration_identity=self.snapshot.integration_identity,
            source_id=self.snapshot.source_id,
            source_generation=self.snapshot.source_generation,
            workflow_id=self.snapshot.workflow_id,
            subscription_id=self.snapshot.subscription_id,
            record=KafkaRecordIdentity(topic=metadata.topic, partition=metadata.partition, offset=metadata.offset),
        )

    def _matches(self, request: PositionRequest, state: _Partition) -> bool:
        expected = self._request(state)
        return all(getattr(request, name) == getattr(expected, name) for name in PositionRequest.model_fields)

    @staticmethod
    def _retry(reason: str) -> HeldRecord:
        return HeldRecord(
            reason=reason,
            retry_at=datetime.now(UTC) + timedelta(seconds=EventSchedulingDefaults.TRANSIENT_PROBE_SECONDS),
        )

    async def start(self) -> None:
        """Start once; partial startup always releases client resources."""
        if self._started or self._closing:
            return
        try:
            await self._client.start()
            self._started = True
        except BaseException as exc:
            await self._client.stop()
            if isinstance(exc, KafkaTransportError):
                cause = exc.__cause__
                raise SubscriptionRuntimeError(
                    RuntimeFailureCode.CONNECTION_UNAVAILABLE,
                    transient=isinstance(cause, KafkaError)
                    and (cause.retriable or isinstance(cause, KafkaTimeoutError)),
                ) from None
            raise

    async def run(self) -> None:
        """Keep membership responsive while partition tasks hold independent backpressure."""
        try:
            await self.start()
            while not self._closing:
                await self._tick()
                await asyncio.sleep(self._settings.event_fetch_timeout_ms / 1000)
        finally:
            await self.stop()

    async def on_partitions_assigned(self, partitions: frozenset[int], epoch: int) -> None:
        """Pause first; initialization and frozen repair run outside the callback."""
        if partitions:
            await self._client.pause(partitions, expected_epoch=epoch)
        for partition in partitions:
            previous = self._partitions.get(partition)
            if previous is None:
                self._partitions[partition] = _Partition(partition=partition, epoch=epoch, closing=self._closing)
                continue
            if previous.epoch == epoch:
                previous.paused = True
                continue
            previous.closing = True
            deadline = asyncio.get_running_loop().time() + self._settings.event_drain_timeout_seconds
            await self._drain_states([previous], deadline, commit=False)
            # Retained assignment keeps its initialized boundary and received
            # queue. An old task cannot mutate this replacement after draining.
            self._partitions[partition] = replace(
                previous,
                epoch=epoch,
                records=deque(previous.records),
                task=None,
                closing=self._closing,
                paused=True,
                reconciled_until=0,
            )
        if epoch == self._client.epoch:
            self._assignment_epoch = epoch

    async def on_partitions_revoked(self, partitions: frozenset[int], epoch: int) -> None:
        """Close admission and bound drain without waiting for the fetch loop."""
        if self._assignment_epoch == epoch:
            self._assignment_epoch = None
        states = [state for p, state in self._partitions.items() if p in partitions and state.epoch == epoch]
        for state in states:
            state.closing = True
        deadline = self._drain_deadline or (
            asyncio.get_running_loop().time() + self._settings.event_drain_timeout_seconds
        )
        await self._drain_states(states, deadline, commit=True)
        await self._flush_pending_content(states, deadline)
        for state in states:
            if self._partitions.get(state.partition) is state:
                del self._partitions[state.partition]

    async def _advance(self, state: _Partition) -> None:
        try:
            async with self._work:
                if not self._active(state):
                    return
                reconcile = (
                    self._gate is None
                    or state.reconciled_until <= asyncio.get_running_loop().time()
                    or not state.ready
                    or state.reload_required
                )
                # Repair precedes initial admission and each bounded refresh.
                # A warmed duplicate needs neither this scan nor an eligibility
                # query; the shared gate can close it immediately between probes.
                if reconcile:
                    if not await self._reconcile_partition(state):
                        return
                elif not await self._prepare_queue(state):
                    return
                if not state.eligible or not self._admission_open() or not self._resolution_open():
                    state.held = self._retry(
                        "admission_closed" if self._resolution_open() else "dependency_unavailable"
                    )
                    return
                await self._process_head(state)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - unexpected failures hold the partition, never reject content
            self._processing_failed(state, exc)
        finally:
            if state.held is not None:
                state.reconciled_until = 0
            if state.held is not None and state.records and self._owned(state) and state.fence is None:
                await self._park(state)

    def _processing_failed(self, state: _Partition, failure: Exception) -> None:
        durable = isinstance(failure, (SQLAlchemyError, OSError, TimeoutError))
        if durable:
            self._invalidate_gate()
        state.held = self._retry("dependency_unavailable" if durable else "processing_unavailable")
        logger.warning(
            "event_record_processing_unavailable", source_id=str(self.snapshot.source_id), partition=state.partition
        )

    async def _reconcile_partition(self, state: _Partition) -> bool:
        if not await self._recover_pending(state) or not await self._prepare_queue(state):
            return False
        if not state.ready:
            position = await self._positions.initialize(self._request(state))
            state.initialization = position
            if position.status != PositionStatus.READY or position.assignment_epoch != state.epoch:
                if position.reason in {
                    "storage_unavailable",
                    "source_identity_unavailable",
                    "source_recreated",
                    "source_revision_changed",
                    "waiting_for_source_recovery",
                    "recovery_hold_unavailable",
                }:
                    self._invalidate_gate()
                state.held = self._retry("initialization_unresolved")
                return False
            state.ready = True
        if self._gate is not None and await self._deliveries.has_content_gate(self.snapshot, state.partition):
            state.held = HeldRecord(reason="activity_log_unavailable", permanent_content_error=True)
            return False
        state.eligible = await self._processing.admission_eligible(self.snapshot)
        state.reconciled_until = asyncio.get_running_loop().time() + EventSchedulingDefaults.TRANSIENT_PROBE_SECONDS
        return True

    async def _prepare_queue(self, state: _Partition) -> bool:
        if state.reload_required:
            # A failed rewind invalidates the local cursor and queued tail.
            # Reload committed progress before admitting anything.
            if state.partition in self._fetching:
                await self._fetch_idle.wait()
            state.records.clear()
            state.byte_count = 0
            state.ready = False
            state.reload_required = False
        if not self._active(state):
            return False
        if state.pending_failure is not None and not state.records:
            await self._hold_pending_content(state)
            return False
        return True

    def _active(self, state: _Partition) -> bool:
        return self._owned(state) and state.fence is None and not state.closing and self._accepting_work()

    def _accepting_work(self) -> bool:
        return not self._closing and not self._stopped and self._placement_open()

    def _processing_guard(self) -> _ProcessingGuardArguments:
        # Keep the guard scoped to this invocation, including injected/shared
        # processing providers. Prepared recovery never requires this guard.
        return {} if self._placement_authority is None else {"admission_guard": self._accepting_work}

    async def _recover_pending(self, state: _Partition) -> bool:
        for _ in range(FieldLimits.MAX_ITEMS_PER_PAGE):
            if not self._active(state):
                return False
            pending = await self._deliveries.first_pending(self.snapshot, state.partition)
            if pending is None:
                return True
            result = await self._processing.process(self.snapshot, pending, None, self._owner)
            if isinstance(result, HeldRecord):
                if result.reason == CONTENT_INSPECTION_PENDING:
                    if await self._inspect_pending_identity(state, pending):
                        continue
                    return False
                state.held = result
                return False
        state.held = self._retry("recovery_batch_pending")
        return False

    async def _process_head(self, state: _Partition) -> None:
        if not state.records or not self._active(state):
            return
        event = state.records[0]
        identity = self._identity(event)
        epoch = state.epoch
        if self._cache_admitted(state):
            result = await self._processing.process(
                self.snapshot, identity, event, self._owner, cache_admitted=True, **self._processing_guard()
            )
        else:
            result = await self._processing.process(
                self.snapshot, identity, event, self._owner, **self._processing_guard()
            )
        if not self._owned(state) or state.epoch != epoch:
            return
        if not state.records or self._identity(state.records[0]) != identity:
            state.held = self._retry("evidence_mismatch")
            return
        if not self._resolution_open():
            state.held = self._retry("dependency_unavailable")
            return
        if not isinstance(result, ResolvedDelivery) or result.terminal.identity != identity:
            state.held = result if isinstance(result, HeldRecord) else self._retry("evidence_mismatch")
        elif result.terminal.state == DeliveryState.REJECTED:
            state.held = HeldRecord(reason="activity_log_unavailable", permanent_content_error=True)
        elif identity.record.offset == MAX_POSITION_OFFSET:
            state.held = HeldRecord(reason="offset_exhausted")
        else:
            # Only this delivered head supplies a candidate next offset.
            # Missing numeric offsets do not represent missing records.
            state.records.popleft()
            state.byte_count -= raw_event_size(event)
            if state.fence is None:
                state.resolved_next_offset = identity.record.offset + 1
            self._note_inspected(state, identity.record.offset)
            state.held = None

    async def _hold_pending_content(self, state: _Partition) -> None:
        pending = state.pending_failure
        if pending is None:
            return
        result = (
            await self._processing.process(self.snapshot, pending.identity, None, self._owner)
            if pending.failure is None
            else await self._processing.hold_content_failure(
                self.snapshot, pending.identity, pending.failure, self._owner, **self._processing_guard()
            )
        )
        await self._apply_pending_result(state, result)

    async def _apply_pending_result(self, state: _Partition, result: ResolvedDelivery | HeldRecord) -> None:
        pending = state.pending_failure
        if pending is None or not self._owned(state):
            return
        if isinstance(result, HeldRecord):
            state.held = self._retry("queue_capacity") if result.reason == "delivery_evidence_unavailable" else result
            if result.permanent_content_error:
                state.pending_failure = None  # The durable content gate now owns recovery.
        elif result.terminal.identity != pending.identity:
            state.held = self._retry("evidence_mismatch")
        elif result.terminal.state == DeliveryState.REJECTED:
            state.held = HeldRecord(reason="activity_log_unavailable", permanent_content_error=True)
        elif pending.identity.record.offset == MAX_POSITION_OFFSET:
            state.held = HeldRecord(reason="offset_exhausted")
        else:
            # This identity was delivered and all earlier heads have finished.
            # Terminal evidence resolves it without retaining its source bytes.
            state.pending_failure = None
            state.held = None
            if state.fence is None:
                state.resolved_next_offset = pending.identity.record.offset + 1
            await self._resume_after_terminal(state, pending.identity.record.offset)

    async def _resume_after_terminal(self, state: _Partition, offset: int) -> None:
        if self._active(state):
            self._note_inspected(state, offset)
            if state.rewind_offset == offset:
                state.rewind_offset = None
            self._request_rewind(state, offset + 1)
            if state.partition not in self._fetching:
                await self._rewind(state)

    @staticmethod
    def _request_rewind(state: _Partition, offset: int) -> None:
        state.rewind_offset = offset if state.rewind_offset is None else min(offset, state.rewind_offset)

    async def _park(self, state: _Partition) -> None:
        """Release blocked queue memory only with a recoverable reading position."""
        offset = self._identity(state.records[0]).record.offset
        self._request_rewind(state, offset)
        await self._pause(state, paused=True)
        if state.partition not in self._fetching:
            await self._rewind(state)
        state.records.clear()
        state.byte_count = 0

    async def _rewind(self, state: _Partition) -> None:
        if state.rewind_offset is None or not self._active(state):
            return
        try:
            await self._client.seek(state.partition, state.rewind_offset, expected_epoch=state.epoch)
        except _TRANSPORT_ERRORS:
            # Reinitialization must reload authoritative group progress before
            # fetching again if rewinding was unavailable or ambiguous.
            state.ready = False
            state.reload_required = True
        state.rewind_offset = None

    @staticmethod
    def _due(state: _Partition) -> bool:
        return state.held is None or (state.held.retry_at is not None and datetime.now(UTC) >= state.held.retry_at)

    def _start_due_tasks(self) -> None:
        for state in tuple(self._partitions.values()):
            if state.task is not None and state.task.done():
                if not state.task.cancelled():
                    state.task.result()
                state.task = None
            if (
                self._owned(state)
                and state.task is None
                and not state.closing
                and state.fence is None
                and self._due(state)
            ):
                state.held = None
                state.task = asyncio.create_task(self._advance(state))

    async def _tick(self) -> None:
        if not self._accepting_work():
            return
        if not self._admission_open():
            await self.close_admission()
            return
        self._start_due_tasks()
        await self._commit_positions(tuple(self._partitions.values()))
        candidates: list[int] = []
        epoch = self._client.epoch
        for state in tuple(self._partitions.values()):
            available = (
                not self._closing
                and state.eligible
                and self._owned(state)
                and state.ready
                and not state.closing
                and state.fence is None
                and state.held is None
                and self._admission_open()
                and self._resolution_open()
                and state.rewind_offset is None
                and state.pending_failure is None
                and len(state.records) < self._settings.event_partition_max_records
                and self.queued_records < self._settings.event_queue_max_records
                and self.queued_bytes < self._settings.event_queue_max_bytes
            )
            if await self._pause(state, paused=not available) and available:
                candidates.append(state.partition)
        if not self._accepting_work() or not self._admission_open():
            return
        context = EventSourceMetadata(
            integration_id=self.snapshot.integration_identity,
            subscription_id=self.snapshot.subscription_id,
            source_generation=self.snapshot.source_generation,
            received_at=datetime.now(UTC),
        )
        self._fetching = frozenset(candidates)
        self._fetch_idle.clear()
        try:
            async with self._fetch_lock:
                batches = await self._client.fetch(
                    candidates,
                    context,
                    expected_epoch=epoch,
                    max_records=min(self._settings.event_fetch_max_records, self._settings.event_queue_max_records),
                    timeout_ms=self._settings.event_fetch_timeout_ms,
                )
                await self._enqueue(batches, epoch)
        except _TRANSPORT_ERRORS:
            await self._broker_failed(candidates, epoch)
        finally:
            await self._finish_fetch()

    async def _finish_fetch(self) -> None:
        self._fetching = frozenset()
        try:
            for state in tuple(self._partitions.values()):
                await self._rewind(state)
        finally:
            self._fetch_idle.set()

    async def _broker_failed(self, partitions: list[int], epoch: int) -> None:
        for partition in partitions:
            state = self._partitions.get(partition)
            if state is not None and self._owned(state) and state.epoch == epoch:
                state.held = self._retry("broker_unavailable")
                await self._pause(state, paused=True)

    async def _pause(self, state: _Partition, *, paused: bool) -> bool:
        if not self._owned(state):
            return False
        try:
            if paused != state.paused:
                operation = self._client.pause if paused else self._client.resume
                await operation([state.partition], expected_epoch=state.epoch)
                state.paused = paused
            return True
        except _TRANSPORT_ERRORS:
            return False

    async def _enqueue(self, batches: dict[int, list[RawEvent]], epoch: int) -> None:
        for partition, events in batches.items():
            state = self._partitions.get(partition)
            if state is None or state.epoch != epoch or not self._owned(state):
                continue
            if state.fence is not None or state.closing or not self._admission_open():
                self._remember_inspection(state, events)
                continue
            if state.held is not None or state.pending_failure is not None:
                if events:
                    self._remember_inspection(state, events)
                    self._request_rewind(state, self._identity(events[0]).record.offset)
                    await self._pause(state, paused=True)
                continue
            await self._enqueue_partition(state, events)
            if partition not in self._fetching:
                await self._rewind(state)

    async def _enqueue_partition(self, state: _Partition, events: list[RawEvent]) -> None:
        for index, event in enumerate(events):
            size = raw_event_size(event)
            count_full = (
                len(state.records) >= self._settings.event_partition_max_records
                or self.queued_records >= self._settings.event_queue_max_records
            )
            if count_full or self.queued_bytes + size > self._settings.event_queue_max_bytes:
                # Rewind only the unqueued tail, never a fetched position or
                # an invented missing offset. Existing queued work stays first.
                self._request_rewind(state, self._identity(event).record.offset)
                self._remember_inspection(state, events[index:])
                if not count_full and size > self._settings.event_queue_max_bytes:
                    if state.records:
                        # Earlier records finish first; inspect the tail on refetch.
                        state.content_gate_unknown = True
                    else:
                        await self._stage_content_failure(state, event)
                elif not state.records:
                    state.held = self._retry("queue_capacity")
                await self._pause(state, paused=True)
                break
            if state.records and self._identity(event).record.offset <= self._identity(state.records[-1]).record.offset:
                msg = "Kafka delivered records out of order"
                raise ValueError(msg)
            state.records.append(event)
            state.byte_count += size

    async def _inspect_delivered(
        self, state: _Partition, event: RawEvent, *, work_held: bool = False
    ) -> ResolvedDelivery | HeldRecord | InspectedRecord:
        try:
            async with asyncio.timeout(self._settings.event_fetch_timeout_ms / 1000):
                if state.task is not None and state.task is not asyncio.current_task() and not state.task.done():
                    await asyncio.shield(state.task)
                if work_held:
                    return await self._processing.inspect_only(
                        self.snapshot, self._identity(event), event, self._owner, **self._processing_guard()
                    )
                async with self._work:
                    return await self._processing.inspect_only(
                        self.snapshot, self._identity(event), event, self._owner, **self._processing_guard()
                    )
        except TimeoutError:
            return self._retry("inspection_unavailable")

    async def _stage_content_failure(self, state: _Partition, event: RawEvent) -> None:
        """Inspect before releasing unbufferable bytes; never classify before the marker."""
        result = await self._inspect_delivered(state, event)
        state.pending_failure = PendingContentFailure(identity=self._identity(event))
        if isinstance(result, HeldRecord):
            state.held = result
            state.content_gate_unknown = not result.permanent_content_error
            if result.permanent_content_error:
                state.pending_failure = None
        elif isinstance(result, InspectedRecord):
            if result.identity == self._identity(event):
                state.pending_failure = PendingContentFailure(identity=result.identity, validated=True)
                self._note_inspected(state, result.identity.record.offset)
                state.held = self._retry("queue_capacity")
            else:
                state.held = self._retry("evidence_mismatch")
        else:
            # Reuse the terminal-evidence checks without another service call.
            await self._apply_pending_result(state, result)

    def _remember_inspection(self, state: _Partition, events: list[RawEvent]) -> None:
        offsets = [self._identity(event).record.offset for event in events]
        self._remember_offsets(state, offsets)

    @staticmethod
    def _remember_offsets(state: _Partition, offsets: list[int]) -> None:
        if not offsets:
            return
        first, last = min(offsets), max(offsets)
        state.inspection_next_offset = (
            first if state.inspection_next_offset is None else min(first, state.inspection_next_offset)
        )
        state.inspection_end_offset = (
            last if state.inspection_end_offset is None else max(last, state.inspection_end_offset)
        )
        state.content_gate_unknown = True

    @staticmethod
    def _note_inspected(state: _Partition, offset: int) -> None:
        first, end = state.inspection_next_offset, state.inspection_end_offset
        if first is None or end is None or offset < first:
            return
        if offset >= end:
            state.inspection_next_offset = state.inspection_end_offset = None
            state.content_gate_unknown = False
        else:
            state.inspection_next_offset = offset + 1

    async def _inspect_recovery_window(self, state: _Partition) -> None:
        """Re-read only the delivered uninspected window, without granting admission."""
        async with self._fetch_lock:
            for _ in range(FieldLimits.MAX_ITEMS_PER_PAGE):
                offset, end = state.inspection_next_offset, state.inspection_end_offset
                if offset is None or end is None or not self._owned(state):
                    return
                event = await self._read_inspection(state, offset)
                if event is None or not offset <= self._identity(event).record.offset <= end:
                    return
                result = await self._inspect_delivered(state, event)
                if isinstance(result, HeldRecord):
                    state.held = result
                    return
                identity = result.identity if isinstance(result, InspectedRecord) else result.terminal.identity
                if identity != self._identity(event) or (
                    isinstance(result, ResolvedDelivery) and result.terminal.state == DeliveryState.REJECTED
                ):
                    return
                delivered = identity.record.offset
                if delivered == end:
                    state.inspection_next_offset = state.inspection_end_offset = None
                    state.content_gate_unknown = False
                    state.pending_failure = None
                    state.held = None
                    return
                state.inspection_next_offset = delivered + 1

    async def _read_inspection(self, state: _Partition, offset: int) -> RawEvent | None:
        context = EventSourceMetadata(
            integration_id=self.snapshot.integration_identity,
            subscription_id=self.snapshot.subscription_id,
            source_generation=self.snapshot.source_generation,
            received_at=datetime.now(UTC),
        )
        await self._client.seek(state.partition, offset, expected_epoch=state.epoch)
        await self._client.resume([state.partition], expected_epoch=state.epoch)
        try:
            batches = await self._client.fetch(
                [state.partition],
                context,
                expected_epoch=state.epoch,
                max_records=1,
                timeout_ms=self._settings.event_fetch_timeout_ms,
            )
        finally:
            await self._client.pause([state.partition], expected_epoch=state.epoch)
        events = batches.get(state.partition, [])
        return events[0] if events else None

    async def _inspect_pending_identity(self, state: _Partition, identity: DeliveryIdentity) -> bool:
        state.ready = False
        async with self._fetch_lock:
            # A probe seek invalidates queued positions. Initialization reloads
            # authoritative progress after repair; queued tails cannot skip it.
            state.records.clear()
            state.byte_count = 0
            event = await self._read_inspection(state, identity.record.offset)
            if event is None or self._identity(event) != identity:
                state.held = self._retry("inspection_record_unavailable")
                return False
            result = await self._inspect_delivered(state, event, work_held=True)
        if isinstance(result, HeldRecord):
            state.held = result
            return False
        inspected = result.identity if isinstance(result, InspectedRecord) else result.terminal.identity
        if inspected != identity or (
            isinstance(result, ResolvedDelivery) and result.terminal.state == DeliveryState.REJECTED
        ):
            state.held = self._retry("inspection_evidence_mismatch")
            return False
        self._note_inspected(state, identity.record.offset)
        state.reload_required = True
        return True

    async def _commit_positions(self, states: tuple[_Partition, ...]) -> None:
        async with self._commit_lock:
            epoch = self._client.epoch
            offsets = {
                state.partition: state.resolved_next_offset
                for state in states
                if self._commit_allowed(state) and state.resolved_next_offset is not None
            }
            if not offsets:
                return
            try:
                async with asyncio.timeout(EventDeliveryDefaults.COMMITTED_POSITION_TIMEOUT_SECONDS):
                    await self._client.commit(offsets, expected_epoch=epoch)
            except (*_TRANSPORT_ERRORS, TimeoutError, OSError):
                return
            for state in states:
                if (
                    self._owned(state)
                    and state.epoch == epoch
                    and state.resolved_next_offset == offsets.get(state.partition)
                ):
                    state.resolved_next_offset = None

    @staticmethod
    def _settled(task: asyncio.Task[None]) -> None:
        if not task.cancelled():
            task.exception()

    async def _drain_states(self, states: list[_Partition], deadline: float, *, commit: bool) -> bool:
        for state in states:
            await self._pause(state, paused=True)
        tasks = {state.task for state in states if state.task is not None and not state.task.done()}
        remaining = max(0.0, deadline - asyncio.get_running_loop().time())
        pending: set[asyncio.Task[None]] = set()
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=remaining)
        for task in pending:
            task.cancel()
            task.add_done_callback(self._settled)
        if pending:
            await asyncio.sleep(0)
        remaining = deadline - asyncio.get_running_loop().time()
        if commit and remaining > 0:
            try:
                async with asyncio.timeout(remaining):
                    await self._commit_positions(tuple(states))
            except TimeoutError:
                pass
        return not pending

    async def drain(self) -> None:
        """Close new work; unfinished database/Temporal evidence remains recoverable."""
        self._closing = True
        states = list(self._partitions.values())
        for state in states:
            state.closing = True
        if self._drain_deadline is None:
            self._drain_deadline = asyncio.get_running_loop().time() + self._settings.event_drain_timeout_seconds
        await self._drain_states(states, self._drain_deadline, commit=True)
        await self._flush_pending_content(states, self._drain_deadline)

    async def close_admission(self) -> None:
        """Begin full runner drain after placement loss; preserve frozen handoffs.

        The supervisor supplies lease trust/expiry through the shared gate or
        calls this port directly. Reopening intake requires a new runner.
        """
        await self.drain()

    async def _flush_pending_content(self, states: list[_Partition], deadline: float) -> None:
        """Persist staged evidence without starting new workflow admission."""
        try:
            async with asyncio.timeout_at(deadline):
                for state in states:
                    if (
                        state.pending_failure is None
                        or state.records
                        or (state.task is not None and not state.task.done())
                    ):
                        continue
                    async with self._work:
                        await self._hold_pending_content(state)
                await self._commit_positions(tuple(states))
        except TimeoutError:
            # The unresolved metadata and broker checkpoint remain untouched.
            # This does not establish durable content evidence after a DB outage.
            logger.warning("event_record_content_drain_incomplete", source_id=str(self.snapshot.source_id))

    async def stop(self) -> None:
        """Close the client, including cancellation and partial startup."""
        async with self._stop_lock:
            if self._stopped:
                return
            try:
                await self.drain()
            finally:
                async with asyncio.timeout(self._settings.event_drain_timeout_seconds):
                    await self._client.stop()
                self._stopped = True

    async def close_and_drain(self, request: PositionRequest, *, token: UUID, boundary: int) -> DrainEvidence:
        """Fence local tasks/commits for the upstream explicit gap-recovery service."""
        if not 0 <= boundary <= MAX_POSITION_OFFSET:
            msg = "Recovery boundary must be a valid next offset"
            raise ValueError(msg)
        state = self._partitions.get(request.partition)
        if state is None or not self._matches(request, state) or not self._owned(state):
            return DrainEvidence(quiescent=False, retained_evidence_complete=False, permanent_content_error=True)
        state.fence = token
        self._invalidate_gate()
        state.reconciled_until = 0
        state.resolved_next_offset = None
        state.rewind_offset = None
        deadline = asyncio.get_running_loop().time() + self._settings.event_drain_timeout_seconds
        try:
            async with asyncio.timeout_at(deadline):
                if request.partition in self._fetching:
                    await self._fetch_idle.wait()
                async with self._commit_lock:
                    pass  # Previously issued commits must settle before the boundary changes.
                quiescent = await self._drain_states([state], deadline, commit=False)
                if quiescent:
                    self._remember_inspection(state, list(state.records))
                    if state.pending_failure is not None:
                        if state.pending_failure.validated:
                            state.pending_failure = None
                        else:
                            self._remember_offsets(state, [state.pending_failure.identity.record.offset])
                    state.records.clear()
                    state.byte_count = 0
                    await self._inspect_recovery_window(state)
                gated = await self._deliveries.has_content_gate(self.snapshot, state.partition)
                gated |= (
                    state.content_gate_unknown
                    or state.pending_failure is not None
                    or (state.held is not None and state.held.permanent_content_error)
                )
        except SQLAlchemyError:
            self._invalidate_gate()
            quiescent, gated = False, True
        except (*_TRANSPORT_ERRORS, OSError, TimeoutError, ValueError):
            quiescent, gated = False, True
        state.records.clear()
        state.byte_count = 0
        # A local queue/empty ledger cannot prove complete retained-window
        # coverage. The service requires explicit duplicate-risk acknowledgement.
        return DrainEvidence(quiescent=quiescent, retained_evidence_complete=False, permanent_content_error=gated)

    async def is_fenced(self, request: PositionRequest, *, token: UUID) -> bool:
        """Only the same source/revision/epoch/token retains this local fence."""
        state = self._partitions.get(request.partition)
        return state is not None and self._matches(request, state) and self._owned(state) and state.fence == token

    async def resume_after_recovery(self, request: PositionRequest, *, token: UUID) -> bool:
        """Reopen only after completed recovery and fresh lifecycle/ownership checks."""
        if (
            self._closing
            or not self._admission_open()
            or not self._resolution_open()
            or not await self.is_fenced(request, token=token)
        ):
            return False
        state = self._partitions[request.partition]
        if (
            (state.task is not None and not state.task.done())
            or (state.held is not None and state.held.permanent_content_error)
            or state.pending_failure is not None
            or state.content_gate_unknown
        ):
            return False
        try:
            async with self._work:
                if await self._deliveries.has_content_gate(self.snapshot, request.partition):
                    return False
                position = await self._positions.initialize(request)
                eligible = await self._processing.admission_eligible(self.snapshot)
        except (*_TRANSPORT_ERRORS, SQLAlchemyError, OSError, TimeoutError, ValueError) as exc:
            if isinstance(exc, SQLAlchemyError):
                self._invalidate_gate()
            return False
        if (
            position.status != PositionStatus.READY
            or position.assignment_epoch != request.assignment_epoch
            or not eligible
            or not self._admission_open()
            or not self._resolution_open()
            or not await self.is_fenced(request, token=token)
        ):
            return False
        state = self._partitions[request.partition]
        state.fence = None
        state.ready = True
        state.eligible = True
        state.held = None
        state.task = None
        state.reconciled_until = asyncio.get_running_loop().time() + EventSchedulingDefaults.TRANSIENT_PROBE_SECONDS
        return True
