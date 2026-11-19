"""Single-subscription Kafka runner; durable services own scheduling decisions."""

import asyncio
import re
import sqlite3
from collections import deque
from collections.abc import Callable
from contextlib import nullcontext, suppress
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import TypedDict
from uuid import UUID

import structlog
from aiokafka.errors import KafkaError, KafkaTimeoutError
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import get_settings
from syntara.core.constants import EventSchedulingDefaults, EventStreamLimits, FieldLimits
from syntara.eventstreams.adapters.kafka_consumer import KafkaCommitUncertainError, KafkaPartitionConsumer
from syntara.eventstreams.adapters.kafka_initial_position import PositionRequest, PositionResult, PositionStatus
from syntara.eventstreams.adapters.kafka_initial_position_service import KafkaInitialPositionService
from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata
from syntara.eventstreams.adapters.kafka_position_control import DrainEvidence
from syntara.eventstreams.adapters.kafka_position_store import KafkaInitialPositionStore
from syntara.eventstreams.adapters.kafka_record_identity import KafkaRecordIdentity
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.core.consumer import MAX_POSITION_OFFSET
from syntara.eventstreams.core.deduplication import DeliveryIdentity
from syntara.eventstreams.core.envelope import RawEvent
from syntara.eventstreams.core.handler import ResolvedDelivery
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.core.processing import (
    HeldRecord,
    InspectedRecord,
    PendingContentFailure,
    RecordProcessingGate,
    SkippedRecord,
)
from syntara.eventstreams.core.results import EventDecodeFailure
from syntara.eventstreams.core.runtime import (
    PendingInspections,
    RunnerStatus,
    RuntimeFailureCode,
    RuntimeState,
    SubscriptionRuntimeError,
    connection_retry_delay,
)
from syntara.eventstreams.core.source_metadata import EventSourceMetadata
from syntara.eventstreams.exceptions import (
    ConsumerNotRunningError,
    KafkaTransportError,
    OwnershipRevokedError,
    StaleEpochError,
)
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.admission_service import EventAdmissionService
from syntara.eventstreams.services.execution_preparation_service import EventExecutionPreparationService
from syntara.eventstreams.services.record_processing_service import EventRecordProcessingService

logger = structlog.stdlib.get_logger(__name__)
_TRANSPORT_ERRORS = (ConsumerNotRunningError, KafkaTransportError, OwnershipRevokedError, StaleEpochError)


class _ProcessingGuardArguments(TypedDict, total=False):
    admission_guard: Callable[[], bool]


@dataclass(frozen=True)
class _RetainedHandoff:
    prepared: PreparedExecution
    argument_bytes: int
    probe_after: float = 0


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
    handoff: PreparedExecution | None = None
    resolved_next_offset: int | None = None
    local_skip_next_offset: int | None = None
    replay_next_offset: int | None = None
    inspection_position: int | None = None
    rewind_offset: int | None = None
    reload_required: bool = False
    cursor_revision: int = 0
    pending_failure: PendingContentFailure | None = None
    probe_before: int | None = None
    inspections: PendingInspections = field(default_factory=PendingInspections)
    fence: UUID | None = None
    recovery_drained: bool = False
    initialization: PositionResult | None = None
    control_task: asyncio.Task[None] | None = None
    control_due: float = 0
    connection_failures: int = 0


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
        processing: EventRecordProcessingService | None = None,
        positions: KafkaInitialPositionService | None = None,
        work_semaphore: asyncio.Semaphore | None = None,
        inspection_semaphore: asyncio.Semaphore | None = None,
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
        self._settings = get_settings()
        self._gate = gate
        self._processing = (
            processing
            if processing is not None
            else EventRecordProcessingService(session_factory, preparation, admission, gate=gate)
        )
        self._positions = (
            positions
            if positions is not None
            else KafkaInitialPositionService(
                KafkaInitialPositionStore(session_factory),
                client,
                self,
            )
        )
        self._work = (
            work_semaphore
            if work_semaphore is not None
            else asyncio.Semaphore(self._settings.event_processing_concurrency)
        )
        self._inspection_work = inspection_semaphore if inspection_semaphore is not None else asyncio.Semaphore(1)
        self._partitions: dict[int, _Partition] = {}
        self._assignment_epoch: int | None = None
        self._commit_lock = asyncio.Lock()
        self._commit_task: asyncio.Task[None] | None = None
        self._handoffs: dict[str, _RetainedHandoff] = {}
        self._detached_handoff_task: asyncio.Task[None] | None = None
        self._detached_handoff_partition: int | None = None
        self._draining_tasks: dict[asyncio.Task[None], int] = {}
        self._fetch_lock = asyncio.Lock()
        self._inspection_probe_lock = asyncio.Lock()
        self._last_inspection_probe = -1
        self._stop_lock = asyncio.Lock()
        self._closing = False
        self._started = False
        self._placement_authority: Callable[[], bool] | None = None
        self._placement_enabled = True
        self._stopped = False
        self._retained_content_gate = False
        self._retained_content_partitions: set[int] = set()
        self._retained_inspection: dict[int, PendingInspections] = {}
        self._drain_deadline: float | None = None
        self._fetching: frozenset[int] = frozenset()
        self._fetch_idle = asyncio.Event()
        self._fetch_idle.set()
        self._client.set_rebalance_callback(self)

    @property
    def queued_records(self) -> int:
        """Count queued records and detached handoffs, sharing a slot with a buffered head."""
        count = len(self._handoffs)
        for state in self._partitions.values():
            count += len(state.records) + int(state.pending_failure is not None)
            if self._buffered_handoff(state) is not None:
                count -= 1
        return count

    @property
    def queued_bytes(self) -> int:
        """Count actual queued raw bytes and the retained argument reservations."""
        return sum(state.byte_count for state in self._partitions.values()) + sum(
            item.argument_bytes for item in self._handoffs.values()
        )

    def _buffered_handoff(self, state: _Partition) -> _RetainedHandoff | None:
        if state.records and state.handoff is not None and state.handoff.identity == self._identity(state.records[0]):
            return self._handoffs.get(state.handoff.identity.digest)
        return None

    def _partition_record_count(self, state: _Partition) -> int:
        detached = state.handoff is not None and self._buffered_handoff(state) is None
        return len(state.records) + int(state.pending_failure is not None) + int(detached)

    @property
    def ready_partitions(self) -> frozenset[int]:
        """Report partial initialization without making client startup mean readiness."""
        return frozenset(state.partition for state in self._partitions.values() if state.ready and self._owned(state))

    def _resolution_open(self) -> bool:
        return self._gate is None or self._gate.resolution_open(self.snapshot) is True

    def _admission_open(self) -> bool:
        return self._accepting_work() and (self._gate is None or self._gate.admission_open(self.snapshot) is True)

    def _transport_open(self) -> bool:
        return self._placement_open() and (self._gate is None or self._gate.transport_open(self.snapshot) is True)

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

    def _commit_allowed(self, state: _Partition, offset: int) -> bool:
        # Admission/content gates protect the unresolved head. A later hold or
        # expired admission snapshot cannot invalidate an earlier resolved prefix.
        return (
            self._owned(state)
            and state.ready
            and state.fence is None
            and self._resolution_open()
            and not self._crosses_inspection(state, offset)
            and (state.handoff is None or offset <= state.handoff.identity.record.offset)
            and not any(
                item.prepared.identity.record.partition == state.partition
                and offset > item.prepared.identity.record.offset
                for item in self._handoffs.values()
            )
            and (self._drain_deadline is None or asyncio.get_running_loop().time() < self._drain_deadline)
        )

    @property
    def status(self) -> RunnerStatus:
        """Observe local convergence without granting admission or position authority."""
        if self._stopped:
            return RunnerStatus(
                state=RuntimeState.STOPPED,
                permanent_content_error=self._retained_content_gate
                or any(
                    state.held is not None and state.held.permanent_content_error for state in self._partitions.values()
                ),
            )
        if self._closing:
            return RunnerStatus(state=RuntimeState.DRAINING, permanent_content_error=self._retained_content_gate)
        if self._retained_content_gate:
            return RunnerStatus(
                state=RuntimeState.BLOCKED, reason="activity_log_unavailable", permanent_content_error=True
            )
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
        return self._delivery_identity(metadata.partition, metadata.offset)

    def _delivery_identity(self, partition: int, offset: int | str) -> DeliveryIdentity:
        return DeliveryIdentity(
            deployment_id=self.snapshot.deployment_id,
            integration_identity=self.snapshot.integration_identity,
            source_id=self.snapshot.source_id,
            source_generation=self.snapshot.source_generation,
            workflow_id=self.snapshot.workflow_id,
            subscription_id=self.snapshot.subscription_id,
            record=KafkaRecordIdentity(topic=self._client.topic, partition=partition, offset=offset),
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

    @staticmethod
    def _connection_retry(state: _Partition, reason: str) -> HeldRecord:
        state.connection_failures += 1
        return HeldRecord(
            reason=reason,
            retry_at=datetime.now(UTC) + timedelta(seconds=connection_retry_delay(state.connection_failures)),
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
        """Pause first; initialization runs outside the rebalance callback."""
        if partitions:
            await self._client.pause(partitions, expected_epoch=epoch)
        for partition in partitions:
            previous = self._partitions.get(partition)
            if previous is None:
                state = _Partition(
                    partition=partition,
                    epoch=epoch,
                    closing=self._closing,
                    handoff=self._partition_handoff(partition),
                    held=HeldRecord(reason="activity_log_unavailable", permanent_content_error=True)
                    if partition in self._retained_content_partitions
                    else None,
                )
                state.inspections = self._retained_inspection.pop(partition, PendingInspections())
                self._partitions[partition] = state
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
                inspections=previous.inspections.copy(),
                task=None,
                control_task=None,
                control_due=0,
                closing=self._closing,
                paused=True,
                inspection_position=None,
            )
        if epoch == self._client.epoch:
            self._assignment_epoch = epoch

    def pending_inspections(self) -> dict[int, PendingInspections]:
        """Carry exact delivered offsets into a replacement for this publication."""
        retained = {partition: offsets.copy() for partition, offsets in self._retained_inspection.items()}
        for state in self._partitions.values():
            inspections = state.inspections.copy()
            self._remember_pending_inspections(state, inspections)
            if inspections.first is not None:
                retained[state.partition] = inspections
        return retained

    def restore_inspections(self, inspections: dict[int, PendingInspections]) -> None:
        """Install replay requirements before any partition initializes."""
        self._retained_inspection = {partition: offsets.copy() for partition, offsets in inspections.items()}

    async def on_partitions_revoked(self, partitions: frozenset[int], epoch: int) -> None:
        """Close admission and bound drain without waiting for the fetch loop."""
        if self._assignment_epoch == epoch:
            self._assignment_epoch = None
        states = [state for p, state in self._partitions.items() if p in partitions and state.epoch == epoch]
        for state in states:
            state.closing = True
            self._retain_handoff(state)
        deadline = self._drain_deadline or (
            asyncio.get_running_loop().time() + self._settings.event_drain_timeout_seconds
        )
        await self._drain_states(states, deadline, commit=True)
        await self._flush_pending_content(states, deadline)
        for state in states:
            if self._partitions.get(state.partition) is state:
                self._remember_pending_inspections(state, state.inspections)
                if state.inspections.first is not None:
                    self._retained_inspection[state.partition] = state.inspections
                if state.held is not None and state.held.permanent_content_error:
                    self._retained_content_partitions.add(state.partition)
                    self._retained_content_gate = True
                del self._partitions[state.partition]

    async def _advance(self, state: _Partition) -> None:
        try:
            if state.reload_required and self._active(state):
                await self._invalidate_cursor(state)
            if self._needs_inspection_replay(state):
                await self._replay_at_inspection_limit(state)
                return
            await self._process_partition(state)
        except Exception as exc:  # noqa: BLE001 - unexpected failures hold the partition, never reject content
            self._processing_failed(state, exc)
        finally:
            if state.held is not None and self._owned(state) and state.fence is None:
                await self._park(state)

    async def _process_partition(self, state: _Partition) -> None:
        if not await self._prepare_prior_inspection(state):
            return
        async with self._work:
            if not self._active(state) or state.reload_required:
                return
            if state.handoff is None:
                state.handoff = self._partition_handoff(state.partition)
            if state.handoff is not None and (not state.records or not state.ready):
                # Resolve an idle handoff before initialization can move the cursor.
                await self._finish_handoff(state)
                if state.handoff is not None:
                    return
            if await self._reconcile_partition(state):
                await self._process_head(state)

    async def _run_partition(self, state: _Partition) -> None:
        # Keep one in-flight handoff per partition, but do not charge every
        # queued record another fetch-loop sleep. Release the shared semaphore
        # between records so other partitions/subscriptions can make progress.
        while self._active(state):
            await self._advance(state)
            if state.held is not None or not state.records:
                return
            await asyncio.sleep(0)

    def _processing_failed(self, state: _Partition, failure: Exception) -> None:
        durable = isinstance(failure, (SQLAlchemyError, OSError, TimeoutError))
        if durable:
            self._invalidate_gate()
        state.held = self._retry("dependency_unavailable" if durable else "processing_unavailable")
        logger.warning(
            "event_record_processing_unavailable", source_id=str(self.snapshot.source_id), partition=state.partition
        )

    async def _reconcile_partition(self, state: _Partition) -> bool:
        if not await self._prepare_queue(state):
            return False
        if not state.ready:
            position = await self._positions.initialize(self._request(state))
            state.initialization = position
            if position.status != PositionStatus.READY or position.assignment_epoch != state.epoch:
                if position.reason in {
                    "storage_unavailable",
                    "recovery_hold_unavailable",
                }:
                    self._invalidate_gate()
                elif self._gate is not None and position.reason in {
                    "source_identity_unavailable",
                    "source_recreated",
                    "source_revision_changed",
                }:
                    self._gate.source_failed(self.snapshot)
                state.held = self._connection_retry(state, "initialization_unresolved")
                return False
            if self._gate is not None:
                self._gate.source_verified(self.snapshot)
            if position.next_offset is not None:
                # A verified group checkpoint already covers these offsets.
                state.inspections.cover_before(position.next_offset)
            state.replay_next_offset = position.next_offset
            state.ready = True
        if not state.records:
            # Refresh intake eligibility between batches. Buffered records use
            # the shared local gates; only matches need per-record DB checks.
            state.eligible = await self._processing.admission_eligible(self.snapshot)
        return True

    async def _invalidate_cursor(self, state: _Partition) -> None:
        """Retire old cursor work and settle commits without occupying a processing slot."""
        if state.partition in self._fetching:
            await self._fetch_idle.wait()
        if not self._active(state):
            return
        self._remember_pending_inspections(state, state.inspections)
        state.records.clear()
        state.byte_count = 0
        state.pending_failure = None
        state.probe_before = None
        state.resolved_next_offset = None
        state.local_skip_next_offset = None
        state.replay_next_offset = None
        state.inspection_position = None
        state.rewind_offset = None
        state.ready = False
        state.cursor_revision += 1
        async with self._commit_lock:
            state.reload_required = False

    async def _prepare_queue(self, state: _Partition) -> bool:
        if not self._active(state):
            return False
        if not state.ready:
            return True  # Reload the authoritative cursor before acting on work from the previous one.
        if state.probe_before is not None:
            return False  # An oversized fetch staged new work during the preflight.
        if state.pending_failure is not None and not state.records:
            await self._hold_pending_content(state)
            return False
        return True

    async def _prepare_prior_inspection(self, state: _Partition) -> bool:
        """Check older delivery evidence without occupying a normal processing slot."""
        if not state.ready or not self._active(state):
            return True
        if state.handoff is not None and not state.records:
            return True  # The saved arguments take priority over a proof-only lookup.
        staged = state.probe_before
        if staged is None:
            if not state.records:
                return True
            identity = self._identity(state.records[0])
            if state.handoff is not None and state.handoff.identity != identity:
                return True
            target = identity.record.offset
        else:
            target = staged
        try:
            if not self._crosses_inspection(state, target):
                return True
            async with self._inspection_work:
                return self._active(state) and await self._check_prior_inspection(state, target)
        finally:
            # A missing Execution does not prevent replay of an earlier retained record.
            if staged is not None and state.probe_before == staged:
                state.probe_before = None

    def _active(self, state: _Partition) -> bool:
        return (
            self._owned(state)
            and state.fence is None
            and not state.closing
            and self._accepting_work()
            and state.partition != self._detached_handoff_partition
            and state.partition not in self._draining_tasks.values()
        )

    def _accepting_work(self) -> bool:
        return (
            not self._closing
            and not self._stopped
            and self._client.commits_interrupted is not True
            and self._placement_open()
        )

    def _processing_guard(self, state: _Partition) -> _ProcessingGuardArguments:
        # Keep the guard scoped to this invocation, including injected/shared
        # processing providers. Accepted-run recovery never requires this guard.
        return {} if self._placement_authority is None else {"admission_guard": lambda: self._active(state)}

    async def _process_head(self, state: _Partition) -> None:
        if not state.records or not self._active(state):
            return
        identity = self._identity(state.records[0])
        if state.handoff is not None and state.handoff.identity != identity:
            # Finish the attempted identity before processing a different fetched head.
            await self._finish_handoff(state)
            return
        if self._crosses_inspection(state, identity.record.offset):
            return
        epoch = state.epoch
        guard = self._processing_guard(state)
        detached = False

        def reserve(prepared: PreparedExecution) -> bool:
            nonlocal detached
            detached = self._reserve_handoff(state, prepared)
            return detached

        if state.handoff is not None:
            result = await self._processing.process(self.snapshot, identity, None, handoff=state.handoff, **guard)
        else:
            received_at = state.inspections.matched_at(identity.record.offset)
            result = await self._processing.process(
                self.snapshot,
                identity,
                state.records[0],
                reserve_handoff=reserve,
                matched_at=received_at,
                remember_match=lambda received: state.inspections.remember_match(identity.record.offset, received),
                **guard,
            )
        self._apply_head_result(state, identity, result, epoch=epoch, detached=detached)
        if detached and state.held is not None and self._active(state):
            self._request_rewind(state, identity.record.offset)

    def _apply_head_result(
        self,
        state: _Partition,
        identity: DeliveryIdentity,
        result: ResolvedDelivery | HeldRecord | SkippedRecord,
        *,
        epoch: int,
        detached: bool,
    ) -> None:
        """Apply a processing result only after ownership and offset-safety checks."""
        confirmed = isinstance(result, ResolvedDelivery) and result.terminal.identity == identity
        if confirmed or (isinstance(result, HeldRecord) and result.handoff_rejected):
            self._release_handoff(identity, state, confirmed=confirmed)
        elif isinstance(result, HeldRecord) and result.handoff is not None:
            state.handoff = result.handoff
            self._retain_handoff(state)
        if not self._owned(state) or state.epoch != epoch:
            return
        if not detached and (not state.records or self._identity(state.records[0]) != identity):
            state.held = self._retry("evidence_mismatch")
            return
        if not self._resolution_open():
            state.held = self._retry("dependency_unavailable")
            return
        if isinstance(result, SkippedRecord) and (
            result.identity != identity
            or result.configuration_revision != self.snapshot.configuration_revision
            or not self._active(state)
            or not self._admission_open()
            or state.inspections.requires_delivery(identity.record.offset)
        ):
            state.held = self._retry("admission_closed")
        elif not isinstance(result, (ResolvedDelivery, SkippedRecord)) or (
            isinstance(result, ResolvedDelivery) and result.terminal.identity != identity
        ):
            state.held = result if isinstance(result, HeldRecord) else self._retry("evidence_mismatch")
        elif identity.record.offset == MAX_POSITION_OFFSET:
            state.held = HeldRecord(reason="offset_exhausted")
        else:
            if isinstance(result, SkippedRecord):
                state.local_skip_next_offset = identity.record.offset + 1
            self._complete_head(state, identity.record.offset, detached=detached)

    async def _finish_handoff(self, state: _Partition) -> None:
        """Confirm the saved identity without resolving a different fetched record."""
        prepared = state.handoff
        if prepared is None:
            return
        epoch = state.epoch
        result = await self._processing.process(
            self.snapshot, prepared.identity, None, handoff=prepared, **self._processing_guard(state)
        )
        confirmed = isinstance(result, ResolvedDelivery) and result.terminal.identity == prepared.identity
        if confirmed:
            self._release_handoff(prepared.identity, state, confirmed=True)
        if not self._owned(state) or state.epoch != epoch:
            return
        if not self._resolution_open():
            state.held = self._retry("dependency_unavailable")
        elif isinstance(result, HeldRecord):
            state.held = result
        elif not confirmed:
            state.held = self._retry("evidence_mismatch")
        else:
            state.held = None

    def _complete_head(self, state: _Partition, offset: int, *, detached: bool) -> None:
        """Advance only the delivered head after completion and ownership validation."""
        if not detached:
            state.byte_count -= raw_event_size(state.records.popleft())
        if state.fence is None:
            state.resolved_next_offset = offset + 1
            state.replay_next_offset = offset + 1
        state.inspections.resolve(offset)
        state.held = None

    async def _hold_pending_content(self, state: _Partition) -> None:
        pending = state.pending_failure
        if pending is None:
            return
        result = (
            await self._recover_delivery(pending.identity)
            if pending.failure is None
            else await self._processing.hold_content_failure(
                self.snapshot, pending.identity, pending.failure, **self._processing_guard(state)
            )
        )
        await self._apply_pending_result(state, result)

    async def _apply_pending_result(
        self, state: _Partition, result: ResolvedDelivery | HeldRecord | SkippedRecord
    ) -> None:
        pending = state.pending_failure
        if pending is None or not self._owned(state):
            return
        if isinstance(result, SkippedRecord):
            state.held = self._retry("recovery_evidence_mismatch")
            return
        if isinstance(result, HeldRecord):
            state.held = self._retry("queue_capacity") if pending.validated else result
            if result.permanent_content_error:
                state.pending_failure = None  # Kafka retains the uncommitted record for retry.
        elif result.terminal.identity != pending.identity:
            state.held = self._retry("evidence_mismatch")
        elif pending.identity.record.offset == MAX_POSITION_OFFSET:
            state.held = HeldRecord(reason="offset_exhausted")
        else:
            # This identity was delivered and all earlier heads have finished.
            # Terminal evidence resolves it without retaining its source bytes.
            state.pending_failure = None
            state.held = None
            if state.fence is None:
                state.resolved_next_offset = pending.identity.record.offset + 1
                state.replay_next_offset = pending.identity.record.offset + 1
            await self._resume_after_terminal(state, pending.identity.record.offset)

    async def _resume_after_terminal(self, state: _Partition, offset: int) -> None:
        state.inspections.resolve(offset)
        if self._active(state):
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
        if state.records:
            self._remember_inspection(state, list(state.records))
            first = state.inspections.first
            if first is not None:
                self._request_rewind(state, first)
            await self._pause(state, paused=True)
        if state.partition not in self._fetching:
            await self._rewind(state)
        state.records.clear()
        state.byte_count = 0

    async def _rewind(self, state: _Partition) -> None:
        if state.rewind_offset is None or state.reload_required or not self._active(state):
            return
        try:
            state.inspection_position = None
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

    async def _recover_requested(self, state: _Partition) -> None:
        """Recover only the assigned partition, independently of its processing task."""
        if not self._owned(state) or self._closing:
            return
        if state.initialization is None or state.initialization.status != PositionStatus.RECOVERY_GAP:
            return
        try:
            request = self._request(state)
            result = await self._positions.recover_automatically(request)
            if result.status == PositionStatus.READY:
                if state.fence is not None and not await self.resume_after_recovery(request, token=state.fence):
                    return
                state.initialization = result
        except (SQLAlchemyError, OSError, TimeoutError, ValueError):
            state.held = self._retry("recovery_control_unavailable")

    def _poll_control(self, state: _Partition) -> None:
        automatic = state.initialization is not None and state.initialization.status == PositionStatus.RECOVERY_GAP
        if not automatic or not self._owned(state) or state.closing:
            return
        if state.control_task is not None and state.control_task.done():
            if not state.control_task.cancelled():
                state.control_task.result()
            state.control_task = None
        if state.control_task is None and asyncio.get_running_loop().time() >= state.control_due:
            state.control_due = asyncio.get_running_loop().time() + 5
            state.control_task = asyncio.create_task(self._recover_requested(state))

    def _start_due_tasks(self) -> None:
        probe_candidates = []
        for state in tuple(self._partitions.values()):
            self._poll_control(state)
            if state.task is not None and state.task.done():
                if not state.task.cancelled():
                    state.task.result()
                state.task = None
            if (
                self._owned(state)
                and state.task is None
                and not state.closing
                and state.fence is None
                and (state.control_task is None or state.control_task.done())
                and self._due(state)
            ):
                if self._needs_inspection_replay(state):
                    probe_candidates.append(state)
                else:
                    self._start_partition_task(state)
        if probe_candidates and not self._inspection_probe_lock.locked():
            # Rotate both Kafka reads and proof-only work. Capacity recovery
            # must not queue ahead of ready records on the worker semaphore.
            state = min(
                probe_candidates,
                key=lambda candidate: (candidate.partition <= self._last_inspection_probe, candidate.partition),
            )
            self._last_inspection_probe = state.partition
            self._start_partition_task(state)

    def _start_partition_task(self, state: _Partition) -> None:
        state.held = None
        state.task = asyncio.create_task(self._run_partition(state))

    async def _tick(self) -> None:
        if self._client.commits_interrupted is True:
            self._closing = True
        if not self._accepting_work():
            return
        if not self._transport_open():
            await self.close_admission()
            return
        self._poll_detached_handoffs()
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
                and state.probe_before is None
                and not self._inspection_replay_needed(state)
                and self._partition_record_count(state) < self._settings.event_partition_max_records
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
                    max_records=self._fetch_limit,
                    timeout_ms=self._settings.event_fetch_timeout_ms,
                )
                for partition in candidates:
                    fetched_state = self._partitions.get(partition)
                    if fetched_state is not None and fetched_state.epoch == epoch and self._owned(fetched_state):
                        fetched_state.connection_failures = 0
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
                # Fetch errors can include an offset that retention removed.
                # Discard queued tails and reload the checkpoint/bounds before
                # fetching again, including after the SDK's silent reset.
                state.ready = False
                state.reload_required = True
                state.held = self._connection_retry(state, "broker_unavailable")
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

    def _remember_batches(
        self, batches: dict[int, list[RawEvent]], epoch: int
    ) -> list[tuple[_Partition, list[RawEvent]]]:
        """Protect every returned partition before staging any of its work."""
        owned_batches = []
        for partition, events in batches.items():
            state = self._partitions.get(partition)
            if state is None or state.epoch != epoch or not self._owned(state):
                continue
            if events:
                state.inspection_position = None
            self._remember_inspection(state, events)
            owned_batches.append((state, events))
        return owned_batches

    async def _enqueue(self, batches: dict[int, list[RawEvent]], epoch: int) -> None:
        for state, events in self._remember_batches(batches, epoch):
            if not self._owned(state):
                continue
            if state.fence is not None or state.closing or not state.eligible or not self._admission_open():
                if events:
                    self._request_rewind(state, self._identity(events[0]).record.offset)
                continue
            if state.rewind_offset is not None or state.held is not None or state.pending_failure is not None:
                # Reservation can evict buffered records while this fetch is
                # outstanding. Never append a suffix from the old cursor.
                if events:
                    self._request_rewind(state, self._identity(events[0]).record.offset)
                    await self._pause(state, paused=True)
                continue
            try:
                await self._enqueue_partition(state, events)
            except sqlite3.Error as exc:
                self._processing_failed(state, exc)
            if state.partition not in self._fetching:
                await self._rewind(state)

    async def _enqueue_partition(self, state: _Partition, events: list[RawEvent]) -> None:
        for event in events:
            size = raw_event_size(event)
            count_full = (
                self._partition_record_count(state) >= self._settings.event_partition_max_records
                or self.queued_records >= self._settings.event_queue_max_records
            )
            if count_full or self.queued_bytes + size > self._settings.event_queue_max_bytes:
                # Rewind only the unqueued tail, never a fetched position or
                # an invented missing offset. Existing queued work stays first.
                self._request_rewind(state, self._identity(event).record.offset)
                if not count_full and size > self._settings.event_queue_max_bytes:
                    # Earlier records finish first; inspect the tail on refetch.
                    if not state.records:
                        await self._stage_content_failure(state, event)
                elif not state.records and state.handoff is None:
                    state.held = self._retry("queue_capacity")
                await self._pause(state, paused=True)
                break
            if state.records and self._identity(event).record.offset <= self._identity(state.records[-1]).record.offset:
                msg = "Kafka delivered records out of order"
                raise ValueError(msg)
            state.records.append(event)
            state.byte_count += size

    async def _stage_content_failure(self, state: _Partition, event: RawEvent) -> None:
        """Classify unbufferable bytes locally; partition work checks prior acceptance."""
        identity = self._identity(event)
        offset = identity.record.offset
        first = state.inspections.first
        if first is not None and first < offset:
            state.probe_before = offset
            self._request_rewind(state, first)
            return
        if state.handoff is not None:
            return  # The partition task already owns this delivery.
        if state.inspections.requires_delivery(offset):
            state.pending_failure = PendingContentFailure(identity=identity, validated=True)
            return
        result = self._processing.inspect_unbuffered(self.snapshot, identity, event, **self._processing_guard(state))
        if isinstance(result, SkippedRecord):
            await self._apply_unbuffered_skip(state, identity, result)
        elif isinstance(result, HeldRecord):
            state.held = result
        elif isinstance(result, EventDecodeFailure):
            state.pending_failure = PendingContentFailure(identity=identity, failure=result)
        elif result.identity == identity:
            state.inspections.remember_match(offset, event.source_metadata.received_at)
            state.pending_failure = PendingContentFailure(identity=identity, validated=True)
        else:
            state.held = self._retry("evidence_mismatch")

    async def _apply_unbuffered_skip(
        self, state: _Partition, identity: DeliveryIdentity, result: SkippedRecord
    ) -> None:
        offset = identity.record.offset
        if (
            result.identity != identity
            or result.configuration_revision != self.snapshot.configuration_revision
            or not self._active(state)
            or not self._admission_open()
            or not self._resolution_open()
            or state.inspections.requires_delivery(offset)
        ):
            state.held = self._retry("admission_closed")
        elif offset == MAX_POSITION_OFFSET:
            state.held = HeldRecord(reason="offset_exhausted")
        else:
            state.resolved_next_offset = offset + 1
            state.local_skip_next_offset = offset + 1
            state.replay_next_offset = offset + 1
            state.held = None
            await self._resume_after_terminal(state, offset)

    def _remember_inspection(self, state: _Partition, events: list[RawEvent]) -> None:
        for event in events:
            state.inspections.remember(self._identity(event).record.offset)

    def _remember_pending_inspections(self, state: _Partition, inspections: PendingInspections) -> None:
        for event in state.records:
            inspections.remember(self._identity(event).record.offset)
        if state.pending_failure is not None:
            inspections.remember(state.pending_failure.identity.record.offset)

    @property
    def _fetch_limit(self) -> int:
        return min(self._settings.event_queue_max_records, self._settings.event_fetch_max_records)

    @property
    def _inspection_limit(self) -> int:
        return self._settings.event_queue_max_records + self._fetch_limit

    def _inspection_replay_needed(self, state: _Partition) -> bool:
        # The fetch limit is shared across partitions. Reserve a full batch per
        # candidate so a nearly full partition does not reduce sibling intake.
        return len(state.inspections) > self._settings.event_queue_max_records

    def _needs_inspection_replay(self, state: _Partition) -> bool:
        return (
            self._active(state)
            and state.ready
            and state.eligible
            and self._admission_open()
            and self._resolution_open()
            and not state.records
            and state.handoff is None
            and state.pending_failure is None
            and state.probe_before is None
            and self._inspection_replay_needed(state)
        )

    def _inspection_probe_start(self, state: _Partition, first: int) -> int | None:
        start = first if state.replay_next_offset is None else min(first, state.replay_next_offset)
        if state.inspections.gap_covers(start, first):
            return None
        return start

    async def _replay_at_inspection_limit(self, state: _Partition) -> None:
        """Read one old record or confirm it by identity while normal intake is paused."""
        first = state.inspections.first
        if first is None or self._inspection_probe_lock.locked():
            return
        async with self._inspection_probe_lock:
            if self._inspection_probe_start(state, first) is not None and not await self._probe_inspection_replay(
                state, first
            ):
                return
            async with self._inspection_work:
                if self._needs_inspection_replay(state) and state.inspections.first == first:
                    await self._confirm_inspected_delivery(state, first)

    async def _probe_inspection_replay(self, state: _Partition, first: int) -> bool:
        """Reread at most one record. Return whether to check for terminal proof."""
        try:
            async with self._fetch_lock:
                if not self._needs_inspection_replay(state) or state.inspections.first != first:
                    return False
                # Recovery may have reopened a safe prefix before the first protected record.
                start = self._inspection_probe_start(state, first)
                if start is None:
                    return True
                if not self._reserve_inspection_read(state):
                    return True
                event = await self._read_inspection(state, start)
                if event is not None and self._owned(state):
                    offset = self._identity(event).record.offset
                    if offset > first:
                        state.inspections.read_gap = (start, offset)
                    elif self._active(state):
                        await self._enqueue({state.partition: [event]}, state.epoch)
                        return False
                if event is not None and self._active(state):
                    await self._client.seek(state.partition, start, expected_epoch=state.epoch)
                return self._active(state)
        except _TRANSPORT_ERRORS:
            await self._broker_failed([state.partition], state.epoch)
        return False

    def _reserve_inspection_read(self, state: _Partition) -> bool:
        # In addition to the normal batch, reserve a lookahead, an earlier
        # recovery prefix, and a lookahead if that prefix gets compacted.
        if state.inspections.reserve_replay_read(self._inspection_limit + 3):
            return True
        logger.warning("event_record_inspection_storage_unavailable", partition=state.partition)
        return False

    @staticmethod
    def _crosses_inspection(state: _Partition, offset: int) -> bool:
        first = state.inspections.first
        return first is not None and first < offset

    async def _recover_delivery(self, identity: DeliveryIdentity) -> ResolvedDelivery | HeldRecord:
        """Confirm an existing Execution or accepted run without the Kafka payload."""
        try:
            async with asyncio.timeout(EventSchedulingDefaults.RPC_TIMEOUT_SECONDS):
                result = await self._processing.process(self.snapshot, identity, None)
        except TimeoutError:
            return self._retry("delivery_confirmation_pending")
        if isinstance(result, ResolvedDelivery) and result.terminal.identity == identity:
            return result
        if isinstance(result, HeldRecord):
            return self._retry("delivery_confirmation_pending") if result.reason == "admission_closed" else result
        return self._retry("recovery_evidence_mismatch")

    async def _confirm_inspected_delivery(self, state: _Partition, offset: int) -> bool:
        result = await self._recover_delivery(self._delivery_identity(state.partition, offset))
        if not self._owned(state):
            return False
        if isinstance(result, HeldRecord):
            state.held = result
            return False
        state.inspections.resolve(offset)
        state.held = None
        return True

    async def _check_prior_inspection(self, state: _Partition, offset: int) -> bool:
        first = state.inspections.first
        if first is None or first >= offset:
            return True
        matched = state.inspections.requires_delivery(first)
        if await self._confirm_inspected_delivery(state, first) and not self._crosses_inspection(state, offset):
            return True
        if state.held is None or (not matched and state.held.reason == "delivery_confirmation_pending"):
            state.held = self._retry("inspection_unavailable")
        return False

    async def _inspect_recovery_window(self, state: _Partition, boundary: int) -> None:
        """Inspect reached offsets without granting admission or losing later evidence."""
        for _ in range(FieldLimits.MAX_ITEMS_PER_PAGE):
            offset = state.inspections.first
            if offset is None or offset >= boundary or not self._owned(state):
                return
            if not await self._inspect_recovery_offset(state, offset):
                return

    async def _inspect_recovery_offset(self, state: _Partition, offset: int) -> bool:
        matched = state.inspections.requires_delivery(offset)
        event = None
        if not matched and not state.inspections.gap_covers(offset, offset):
            async with self._fetch_lock:
                if self._owned(state) and self._reserve_inspection_read(state):
                    # Retention can make the offset unreadable. Exact terminal
                    # evidence can still resolve it.
                    with suppress(KafkaTransportError):
                        event = await self._read_inspection(state, offset)
        identity = self._delivery_identity(state.partition, offset)
        if event is None or self._identity(event) != identity:
            if event is not None:
                state.inspections.read_gap = (offset, self._identity(event).record.offset)
            async with self._inspection_work:
                return await self._confirm_inspected_delivery(state, offset)

        async with self._work:
            result = await self._processing.inspect_only(self.snapshot, identity, event)
        if not self._owned(state):
            return False
        if isinstance(result, (HeldRecord, SkippedRecord)):
            state.held = result if isinstance(result, HeldRecord) else self._retry("recovery_evidence_mismatch")
            return False
        inspected = result.identity if isinstance(result, InspectedRecord) else result.terminal.identity
        if inspected != identity:
            return False
        state.inspections.resolve(offset)
        if state.inspections.first is None:
            state.held = None
        return True

    async def _read_inspection(self, state: _Partition, offset: int) -> RawEvent | None:
        """Read one record with space reserved, retaining any owned result."""
        context = EventSourceMetadata(
            integration_id=self.snapshot.integration_identity,
            subscription_id=self.snapshot.subscription_id,
            source_generation=self.snapshot.source_generation,
            received_at=datetime.now(UTC),
        )
        try:
            if state.inspection_position != offset:
                await self._client.seek(state.partition, offset, expected_epoch=state.epoch)
                state.inspection_position = offset
            await self._client.resume([state.partition], expected_epoch=state.epoch)
            try:
                batches = await self._client.fetch(
                    [state.partition],
                    context,
                    expected_epoch=state.epoch,
                    max_records=1,
                    timeout_ms=self._settings.event_fetch_timeout_ms,
                )
                events = batches.get(state.partition, [])
                if events and self._owned(state):
                    state.inspection_position = None
                    state.inspections.remember(self._identity(events[0]).record.offset)
                    return events[0]
                return None
            finally:
                await self._client.pause([state.partition], expected_epoch=state.epoch)
                state.paused = True
        except BaseException:
            # Only a successful empty poll keeps the cached position. A seek
            # is needed to clear an SDK offset reset before the next attempt.
            state.inspection_position = None
            raise

    async def _commit_positions(self, states: tuple[_Partition, ...]) -> None:
        """Bound the observer, never cancel a commit that owns a revision lock."""
        task = self._commit_task
        if task is None or task.done():
            if task is not None:
                task.result()
            if not any(
                (offset := state.resolved_next_offset) is not None and self._commit_allowed(state, offset)
                for state in states
            ):
                return
            task = asyncio.create_task(self._commit_batch(states))
            task.add_done_callback(self._settled)
            self._commit_task = task
        done, _ = await asyncio.wait({task}, timeout=EventStreamLimits.COMMITTED_POSITION_TIMEOUT_SECONDS)
        if done:
            task.result()

    async def _commit_batch(self, states: tuple[_Partition, ...]) -> None:
        """Own the lock until the broker operation settles or membership is fenced."""
        async with self._commit_lock:
            epoch = self._client.epoch
            offsets = {
                state.partition: offset
                for state in states
                if (offset := state.resolved_next_offset) is not None and self._commit_allowed(state, offset)
            }
            if not offsets:
                return
            cursor_revisions = {
                state.partition: state.cursor_revision for state in states if state.partition in offsets
            }
            skip_partitions = {state.partition for state in states if state.local_skip_next_offset is not None}
            try:
                async with (
                    self._processing.local_skip_commit_guard(self.snapshot)
                    if skip_partitions.intersection(offsets)
                    else nullcontext(enter_result=True)
                ) as current_revision:
                    # Ownership, drain deadlines and recovery fences can
                    # change while the authoritative revision lock waits.
                    offsets = {
                        state.partition: offsets[state.partition]
                        for state in states
                        if state.partition in offsets
                        and state.cursor_revision == cursor_revisions[state.partition]
                        and state.resolved_next_offset is not None
                        and state.resolved_next_offset >= offsets[state.partition]
                        and self._commit_allowed(state, offsets[state.partition])
                        and (current_revision or state.partition not in skip_partitions)
                    }
                    if not offsets:
                        return
                    try:
                        await self._client.commit(offsets, expected_epoch=epoch)
                    except (*_TRANSPORT_ERRORS, TimeoutError, OSError) as exc:
                        if isinstance(exc, KafkaCommitUncertainError) and skip_partitions.intersection(offsets):
                            await self._fence_failed_commit(exc)
                        return
            except SQLAlchemyError:
                self._invalidate_gate()
                return
            except (*_TRANSPORT_ERRORS, TimeoutError, OSError):
                return
            self._apply_committed_offsets(states, offsets, cursor_revisions, epoch)

    def _apply_committed_offsets(
        self,
        states: tuple[_Partition, ...],
        offsets: dict[int, int],
        cursor_revisions: dict[int, int],
        epoch: int,
    ) -> None:
        for state in states:
            committed = offsets.get(state.partition)
            if (
                committed is None
                or not self._owned(state)
                or state.epoch != epoch
                or state.cursor_revision != cursor_revisions[state.partition]
            ):
                continue
            if state.local_skip_next_offset is not None and state.local_skip_next_offset <= committed:
                state.local_skip_next_offset = None
            if state.resolved_next_offset == committed:
                state.resolved_next_offset = None

    async def _fence_failed_commit(self, failure: KafkaCommitUncertainError) -> None:
        """Keep publication blocked until Kafka confirms this member cannot commit."""
        self._closing = True
        while True:
            try:
                await self._client.fence_commits(failure)
                return
            except (*_TRANSPORT_ERRORS, OSError, TimeoutError):
                logger.warning("event_record_commit_fence_incomplete", source_id=str(self.snapshot.source_id))
                try:
                    async with asyncio.timeout(EventSchedulingDefaults.TRANSIENT_PROBE_SECONDS):
                        await failure.settled.wait()
                except TimeoutError:
                    continue
                return

    @staticmethod
    def _settled(task: asyncio.Task[None]) -> None:
        if not task.cancelled():
            task.exception()

    async def _drain_states(
        self, states: list[_Partition], deadline: float, *, commit: bool, include_controls: bool = True
    ) -> bool:
        for state in states:
            await self._pause(state, paused=True)
        tasks = {
            task: state.partition
            for state in states
            for task in ((state.task, state.control_task) if include_controls else (state.task,))
            if task is not None and not task.done() and task is not asyncio.current_task()
        }
        remaining = max(0.0, deadline - asyncio.get_running_loop().time())
        pending: set[asyncio.Task[None]] = set()
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=remaining)
        for task in pending:
            if task in self._draining_tasks:
                continue
            self._draining_tasks[task] = tasks[task]
            task.add_done_callback(self._draining_tasks.pop)
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
            self._retain_handoff(state)
        if self._drain_deadline is None:
            self._drain_deadline = asyncio.get_running_loop().time() + self._settings.event_drain_timeout_seconds
        await self._drain_states(states, self._drain_deadline, commit=True)
        await self._flush_pending_content(states, self._drain_deadline)
        await self._flush_handoffs(self._drain_deadline)

    def _retain_handoff(self, state: _Partition) -> None:
        """Retain attempted arguments independently of partition assignment."""
        prepared = state.handoff
        if prepared is not None and prepared.identity.digest not in self._handoffs:
            self._handoffs[prepared.identity.digest] = _RetainedHandoff(prepared, prepared.encoded_arguments_size())

    def _partition_handoff(self, partition: int) -> PreparedExecution | None:
        return next(
            (item.prepared for item in self._handoffs.values() if item.prepared.identity.record.partition == partition),
            None,
        )

    def _reserve_handoff(self, state: _Partition, prepared: PreparedExecution) -> bool:
        """Budget detached arguments before any Temporal start can be submitted."""
        if not self._active(state) or not state.records or self._identity(state.records[0]) != prepared.identity:
            return False
        size = prepared.encoded_arguments_size()
        limit = self._settings.event_queue_max_bytes
        if size > limit:
            return False
        head_size = raw_event_size(state.records[0])
        additional = size - head_size
        used = self.queued_bytes
        evicted_offsets: list[int] = []
        while used + additional > limit and len(state.records) > 1:
            tail = state.records.pop()
            evicted_offsets.append(self._identity(tail).record.offset)
            tail_size = raw_event_size(tail)
            state.byte_count -= tail_size
            used -= tail_size
        if evicted_offsets:
            self._request_rewind(state, min(evicted_offsets))
            for offset in evicted_offsets:
                state.inspections.remember(offset)
        if used + additional > limit:
            return False
        head = state.records.popleft()
        state.byte_count -= head_size
        state.inspections.remember_match(prepared.identity.record.offset, head.source_metadata.received_at)
        state.handoff = prepared
        self._handoffs[prepared.identity.digest] = _RetainedHandoff(prepared, size)
        return True

    def _release_handoff(
        self, identity: DeliveryIdentity, state: _Partition | None = None, *, confirmed: bool = False
    ) -> None:
        current = self._partitions.get(identity.record.partition)
        candidates = (current,) if state is current else (state, current)
        # Release the arguments and their queue reservation together before
        # trying to retire local evidence, which may be on disk.
        self._handoffs.pop(identity.digest, None)
        for candidate in candidates:
            if candidate is not None and candidate.handoff is not None and candidate.handoff.identity == identity:
                candidate.handoff = None
        if confirmed:
            # An unavailable spill retains its guard. Replay can clear it
            # later using the confirmed Execution.
            for candidate in candidates:
                if candidate is not None:
                    with suppress(sqlite3.Error):
                        candidate.inspections.resolve(identity.record.offset)
            with suppress(sqlite3.Error):
                offsets = self._retained_inspection.get(identity.record.partition)
                if offsets is not None:
                    offsets.resolve(identity.record.offset)
                    if offsets.first is None:
                        del self._retained_inspection[identity.record.partition]

    def _poll_detached_handoffs(self) -> None:
        """Recover a revoked partition's reservation while healthy partitions keep running."""
        if self._detached_handoff_task is not None:
            if not self._detached_handoff_task.done():
                return
            self._detached_handoff_task.result()
            self._detached_handoff_task = None
        now = asyncio.get_running_loop().time()
        due: tuple[str, _RetainedHandoff] | None = None
        for digest, retained in self._handoffs.items():
            partition = retained.prepared.identity.record.partition
            if (
                partition in self._partitions
                or partition in self._draining_tasks.values()
                or now < retained.probe_after
            ):
                continue
            if due is None or retained.probe_after < due[1].probe_after:
                due = (digest, retained)
        if due is None:
            return
        digest, retained = due
        self._handoffs[digest] = replace(retained, probe_after=now + EventSchedulingDefaults.TRANSIENT_PROBE_SECONDS)
        self._detached_handoff_partition = retained.prepared.identity.record.partition
        self._detached_handoff_task = asyncio.create_task(self._recover_detached_handoff(retained.prepared))
        self._detached_handoff_task.add_done_callback(self._settled)

    async def _recover_detached_handoff(self, prepared: PreparedExecution) -> None:
        try:
            async with asyncio.timeout(self._settings.event_drain_timeout_seconds), self._work:
                if not self._closing and prepared.identity.record.partition not in self._partitions:
                    await self._confirm_handoff(prepared)
        except TimeoutError:
            logger.warning("event_record_handoff_probe_incomplete", source_id=str(self.snapshot.source_id))
        finally:
            self._detached_handoff_partition = None

    async def _confirm_handoff(self, prepared: PreparedExecution) -> None:
        """Repair accepted work without granting admission for another start."""
        try:
            result = await self._processing.process(
                self.snapshot, prepared.identity, None, handoff=prepared, admission_guard=lambda: False
            )
        except Exception:  # noqa: BLE001 - retain the reservation and let the next probe retry
            logger.warning("event_record_handoff_probe_failed", source_id=str(self.snapshot.source_id))
            return
        if isinstance(result, ResolvedDelivery) and result.terminal.identity == prepared.identity:
            self._release_handoff(prepared.identity, confirmed=True)

    async def _flush_handoffs(self, deadline: float) -> None:
        """Repair parked attempts without filtering again or permitting a new start."""
        if any(not task.done() for task in self._draining_tasks):
            return  # A cancellation-resistant task may still return a handoff.
        try:
            async with asyncio.timeout_at(deadline):
                if self._detached_handoff_task is not None:
                    await asyncio.shield(self._detached_handoff_task)
                for retained in tuple(self._handoffs.values()):
                    async with self._work:
                        await self._confirm_handoff(retained.prepared)
        except TimeoutError:
            logger.warning("event_record_handoff_drain_incomplete", source_id=str(self.snapshot.source_id))

    async def close_admission(self) -> None:
        """Begin full runner drain after placement loss; preserve accepted handoffs.

        The supervisor supplies lease trust/expiry through the shared gate or
        calls this port directly. Reopening intake requires a new runner.
        """
        await self.drain()

    async def _flush_pending_content(self, states: list[_Partition], deadline: float) -> None:
        """Check accepted runs for staged records without starting new workflows."""
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
                        try:
                            await self._hold_pending_content(state)
                        except sqlite3.Error as exc:
                            self._processing_failed(state, exc)
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
            await self.drain()
            if self._commit_task is not None and not self._commit_task.done():
                self._client.interrupt_commits()
            if self._draining_tasks:
                _, pending = await asyncio.wait(
                    self._draining_tasks, timeout=self._settings.event_drain_timeout_seconds
                )
                if pending:
                    raise SubscriptionRuntimeError(RuntimeFailureCode.STOP_INCOMPLETE)
            if self._commit_task is not None:
                done, _ = await asyncio.wait({self._commit_task}, timeout=self._settings.event_drain_timeout_seconds)
                if not done:
                    raise SubscriptionRuntimeError(RuntimeFailureCode.STOP_INCOMPLETE)
                self._commit_task.result()
            try:
                async with asyncio.timeout(self._settings.event_drain_timeout_seconds):
                    await self._client.stop()
            finally:
                for state in self._partitions.values():
                    self._retain_handoff(state)
            await self._flush_handoffs(asyncio.get_running_loop().time() + self._settings.event_drain_timeout_seconds)
            if self._handoffs:
                raise SubscriptionRuntimeError(RuntimeFailureCode.STOP_INCOMPLETE)
            if not await self._positions.settle_operations(self._settings.event_drain_timeout_seconds):
                raise SubscriptionRuntimeError(RuntimeFailureCode.STOP_INCOMPLETE)
            self._stopped = True

    async def _finish_recovery_handoff(self, state: _Partition, boundary: int) -> bool:
        """Require confirmed persistence for a saved identity below the new checkpoint."""
        self._retain_handoff(state)
        for retained in tuple(self._handoffs.values()):
            prepared = retained.prepared
            if prepared.identity.record.partition != state.partition or boundary <= prepared.identity.record.offset:
                continue
            state.handoff = prepared
            async with self._work:
                await self._finish_handoff(state)
            if state.handoff is not None:
                return False
        return True

    async def close_and_drain(self, request: PositionRequest, *, token: UUID, boundary: int) -> DrainEvidence:
        """Fence local tasks/commits for the upstream explicit gap-recovery service."""
        if not 0 <= boundary <= MAX_POSITION_OFFSET:
            msg = "Recovery boundary must be a valid next offset"
            raise ValueError(msg)
        state = self._partitions.get(request.partition)
        if state is None or not self._matches(request, state) or not self._owned(state):
            return DrainEvidence(quiescent=False, retained_evidence_complete=False, permanent_content_error=True)
        if state.fence != token:
            state.inspection_position = None
        state.fence = token
        state.cursor_revision += 1
        state.recovery_drained = False
        state.resolved_next_offset = None
        state.rewind_offset = None
        deadline = asyncio.get_running_loop().time() + self._settings.event_drain_timeout_seconds
        try:
            async with asyncio.timeout_at(deadline):
                if request.partition in self._fetching:
                    await self._fetch_idle.wait()
                async with self._commit_lock:
                    pass  # Previously issued commits must settle before the boundary changes.
                # The upstream position service shields an inner operation from
                # its caller. Waiting for the parent control task here would
                # make that operation wait on its own completion.
                quiescent = await self._drain_states([state], deadline, commit=False, include_controls=False)
                quiescent = (
                    quiescent
                    and state.partition != self._detached_handoff_partition
                    and state.partition not in self._draining_tasks.values()
                )
                if quiescent:
                    self._remember_pending_inspections(state, state.inspections)
                    state.pending_failure = None
                    state.records.clear()
                    state.byte_count = 0
                    quiescent = await self._finish_recovery_handoff(state, boundary)
                    if quiescent:
                        await self._inspect_recovery_window(state, boundary)
                return self._recovery_evidence(state, boundary, quiescent=quiescent)
        except SQLAlchemyError:
            self._invalidate_gate()
        except sqlite3.Error as exc:
            self._processing_failed(state, exc)
        except (*_TRANSPORT_ERRORS, OSError, TimeoutError, ValueError):
            pass
        finally:
            self._remember_inspection(state, list(state.records))
            state.records.clear()
            state.byte_count = 0
        return DrainEvidence(quiescent=False, retained_evidence_complete=False, permanent_content_error=True)

    def _recovery_evidence(self, state: _Partition, boundary: int, *, quiescent: bool) -> DrainEvidence:
        first = state.inspections.first
        crosses = first is not None and first < boundary
        delivery_pending = crosses and first is not None and state.inspections.requires_delivery(first)
        permanent_hold = state.held is not None and state.held.permanent_content_error and (first is None or crosses)
        gated = (crosses and not delivery_pending) or permanent_hold
        quiescent = quiescent and not delivery_pending
        state.recovery_drained = quiescent and not gated
        # A local queue cannot prove complete retained-window
        # coverage. Automatic offset recovery accepts the proposal's bounded
        # duplicate protection; administrative recovery keeps its explicit guard.
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
            or not state.recovery_drained
            or state.pending_failure is not None
        ):
            return False
        try:
            async with self._work:
                position = await self._positions.initialize(request)
                eligible = await self._processing.admission_eligible(self.snapshot)
        except (*_TRANSPORT_ERRORS, SQLAlchemyError, OSError, TimeoutError, ValueError) as exc:
            if isinstance(exc, SQLAlchemyError):
                self._invalidate_gate()
            return False
        if (
            position.status != PositionStatus.READY
            or position.assignment_epoch != request.assignment_epoch
            or position.next_offset is None
            or self._crosses_inspection(state, position.next_offset)
            or not eligible
            or not self._admission_open()
            or not self._resolution_open()
            or not await self.is_fenced(request, token=token)
        ):
            return False
        state = self._partitions[request.partition]
        state.rewind_offset = None
        state.reload_required = False
        state.probe_before = None
        state.replay_next_offset = position.next_offset
        state.inspection_position = None
        state.fence = None
        state.recovery_drained = False
        state.ready = True
        state.eligible = True
        state.held = None
        state.task = None
        return True
