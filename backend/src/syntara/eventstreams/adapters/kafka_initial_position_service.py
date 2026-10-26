"""Kafka initialization and explicit gap recovery without worker or route imports."""

import asyncio
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from syntara.core.constants import EventDeliveryDefaults, EventSchedulingDefaults
from syntara.eventstreams.adapters.kafka_initial_position import (
    GapReason,
    InitializationKind,
    KafkaPartitionInitialPosition,
    PositionRequest,
    PositionResult,
    PositionStatus,
    RecoveryPolicy,
    RecoveryReplacementRequest,
    RecoveryRequest,
)
from syntara.eventstreams.adapters.kafka_position_control import (
    AssignedPartitionClient,
    PartitionRecoveryControl,
    RecoveryCacheCoordination,
)
from syntara.eventstreams.adapters.kafka_position_store import (
    KafkaInitialPositionStore,
    KafkaPositionError,
    PositionContext,
)
from syntara.eventstreams.core.consumer import CommittedPositionResult, SourceIdentityObservation
from syntara.eventstreams.core.consumer import PositionStatus as BrokerPositionStatus
from syntara.eventstreams.core.handler import ResolvedDelivery
from syntara.eventstreams.exceptions import (
    ConsumerNotRunningError,
    KafkaTransportError,
    OwnershipRevokedError,
    StaleEpochError,
)
from syntara.eventstreams.services.admission_service import EventAdmissionService

_DEPENDENCY_ERRORS = (SQLAlchemyError, OSError, TimeoutError, KafkaTransportError)


class KafkaInitialPositionService:
    """Finite operations; callers supply assignment-local control and upstream repair.

    A READY result is bound to its assignment epoch, source generation and
    configuration revision. Callers must retain their fence and recheck those
    values before processing; a result is never an ongoing ownership lease.
    """

    def __init__(
        self,
        store: KafkaInitialPositionStore,
        client: AssignedPartitionClient,
        admission: EventAdmissionService,
        control: PartitionRecoveryControl,
        *,
        cache_coordination: RecoveryCacheCoordination | None = None,
    ) -> None:
        """Inject the completed store/transport/repair services and the caller's control port."""
        self._store = store
        self._client = client
        self._admission = admission
        self._control = control
        self._cache_coordination = cache_coordination
        self._operations: set[asyncio.Task[PositionResult]] = set()

    def _assigned(self, request: PositionRequest) -> None:
        if request.assignment_epoch != self._client.epoch or request.partition not in self._client.assignment:
            msg = "assignment_lost"
            raise KafkaPositionError(msg, PositionStatus.OWNERSHIP_LOST)

    def _source(self, context: PositionContext) -> None:
        if context.configuration.topic != self._client.topic or context.configuration.group_id != self._client.group_id:
            msg = "consumer_source_mismatch"
            raise KafkaPositionError(msg, PositionStatus.REVISION_CHANGED)

    @staticmethod
    def _result(request: PositionRequest, status: PositionStatus, *, reason: str | None = None) -> PositionResult:
        return PositionResult(status=status, assignment_epoch=request.assignment_epoch, reason=reason)

    async def initialize(self, request: PositionRequest) -> PositionResult:
        """Initialize one new partition or resume its valid committed group position."""
        return await self._run(request, recover=False)

    async def recover(self, request: RecoveryRequest, *, owner_worker_id: str) -> PositionResult:
        """Run a caller-authorized decision; retries retain the original selected boundary."""
        return await self._run(request, recover=True, owner_worker_id=owner_worker_id)

    async def replace_recovery(self, request: RecoveryReplacementRequest, *, owner_worker_id: str) -> PositionResult:
        """Explicitly replace an expired decision; retries cannot select a new boundary."""
        return await self._run(request, recover=True, replacement=True, owner_worker_id=owner_worker_id)

    async def _run(
        self, request: PositionRequest, *, recover: bool, replacement: bool = False, owner_worker_id: str = ""
    ) -> PositionResult:
        # A caller timeout/cancellation must not release the partition gate while
        # its broker request can still complete. Retain the operation until done.
        task = asyncio.create_task(
            self._exclusive(request, recover=recover, replacement=replacement, owner_worker_id=owner_worker_id)
        )
        self._operations.add(task)
        task.add_done_callback(self._settled)
        return await asyncio.shield(task)

    def _settled(self, task: asyncio.Task[PositionResult]) -> None:
        self._operations.discard(task)
        if not task.cancelled():
            task.exception()  # Retrieve errors even when the caller was cancelled.

    async def _exclusive(
        self, request: PositionRequest, *, recover: bool, replacement: bool, owner_worker_id: str
    ) -> PositionResult:
        try:
            with self._client.position_operation(
                request.partition, expected_epoch=request.assignment_epoch
            ) as acquired:
                if not acquired:
                    return self._result(request, PositionStatus.BLOCKED, reason="position_operation_busy")
                return await self._run_checked(
                    request, recover=recover, replacement=replacement, owner_worker_id=owner_worker_id
                )
        except (OwnershipRevokedError, StaleEpochError, ConsumerNotRunningError):
            return self._result(request, PositionStatus.OWNERSHIP_LOST, reason="assignment_lost")

    async def _run_checked(
        self, request: PositionRequest, *, recover: bool, replacement: bool, owner_worker_id: str
    ) -> PositionResult:
        try:
            self._assigned(request)
            if replacement and isinstance(request, RecoveryReplacementRequest):
                return await self._replace_recovery(request, owner_worker_id)
            if recover and isinstance(request, RecoveryRequest):
                return await self._recover(request, owner_worker_id)
            return await self._initialize(request)
        except KafkaPositionError as exc:
            status, reason = exc.status, exc.reason
            if exc.status == PositionStatus.RECOVERY_GAP:
                try:
                    await self._store.mark_gap(request, GapReason(exc.reason))
                except KafkaPositionError as changed:
                    status, reason = changed.status, changed.reason
                except _DEPENDENCY_ERRORS:
                    status, reason = PositionStatus.BLOCKED, "storage_unavailable"
            return self._result(request, status, reason=reason)
        except (OwnershipRevokedError, StaleEpochError, ConsumerNotRunningError):
            return self._result(request, PositionStatus.OWNERSHIP_LOST, reason="assignment_lost")
        except _DEPENDENCY_ERRORS:
            return self._result(request, PositionStatus.BLOCKED, reason="dependency_unavailable")

    async def _fenced(self, request: PositionRequest, *, token: UUID) -> bool:
        self._assigned(request)
        async with asyncio.timeout(EventDeliveryDefaults.COMMITTED_POSITION_TIMEOUT_SECONDS):
            fenced = await self._control.is_fenced(request, token=token)
        self._assigned(request)
        return fenced

    async def _observe_identity(self, request: PositionRequest) -> SourceIdentityObservation:
        self._assigned(request)
        observation = await self._client.observe_source_identity(expected_epoch=request.assignment_epoch)
        self._assigned(request)
        if observation.assignment_epoch != request.assignment_epoch:
            msg = "assignment_lost"
            raise KafkaPositionError(msg, PositionStatus.OWNERSHIP_LOST)
        await self._store.verify_identity(request, observation)
        self._assigned(request)
        return observation

    async def _committed(self, request: PositionRequest) -> CommittedPositionResult:
        self._assigned(request)
        positions = await self._client.committed([request.partition], expected_epoch=request.assignment_epoch)
        self._assigned(request)
        result = positions.get(request.partition)
        if result is None or result.partition != request.partition or result.status == BrokerPositionStatus.UNAVAILABLE:
            msg = "committed_position_unavailable"
            raise KafkaPositionError(msg)
        return result

    async def _bounds(self, request: PositionRequest) -> tuple[int, int]:
        self._assigned(request)
        beginnings = await self._client.beginning_offsets([request.partition], expected_epoch=request.assignment_epoch)
        self._assigned(request)
        ends = await self._client.end_offsets([request.partition], expected_epoch=request.assignment_epoch)
        self._assigned(request)
        beginning, end = beginnings.get(request.partition), ends.get(request.partition)
        if (
            beginning is None
            or end is None
            or beginning.partition != request.partition
            or end.partition != request.partition
            or beginning.status != BrokerPositionStatus.VERIFIED
            or end.status != BrokerPositionStatus.VERIFIED
            or beginning.offset is None
            or end.offset is None
            or beginning.offset > end.offset
        ):
            msg = "partition_bounds_unavailable"
            raise KafkaPositionError(msg)
        return beginning.offset, end.offset

    @staticmethod
    def _within_bounds(offset: int, bounds: tuple[int, int]) -> None:
        if not bounds[0] <= offset <= bounds[1]:
            raise KafkaPositionError(GapReason.OUT_OF_RANGE.value, PositionStatus.RECOVERY_GAP)

    @staticmethod
    def _gap_result(request: PositionRequest, row: KafkaPartitionInitialPosition) -> PositionResult:
        return PositionResult(
            status=PositionStatus.RECOVERY_GAP,
            assignment_epoch=request.assignment_epoch,
            recovery_revision=row.recovery_revision,
            reason="recovery_incomplete" if row.recovery_token is not None else row.gap_reason,
        )

    @staticmethod
    def _lower_boundary(row: KafkaPartitionInitialPosition) -> int:
        lower = row.authorized_lower_boundary
        if lower is None:
            raise KafkaPositionError(GapReason.INITIAL_METADATA_MISSING.value, PositionStatus.RECOVERY_GAP)
        return lower

    async def _existing_group_position(self, request: PositionRequest, offset: int) -> KafkaPartitionInitialPosition:
        # An initializer may have committed since the first database read.
        winner = await self._store.read(request)
        self._source(winner)
        if winner.position is not None:
            return winner.position
        try:
            return await self._store.record_missing_initial(request, offset)
        except _DEPENDENCY_ERRORS as exc:
            msg = "storage_unavailable"
            raise KafkaPositionError(msg) from exc

    async def _new_position(
        self, request: PositionRequest, committed: CommittedPositionResult, observation: SourceIdentityObservation
    ) -> KafkaPartitionInitialPosition:
        if committed.status == BrokerPositionStatus.VERIFIED and committed.offset is not None:
            return await self._existing_group_position(request, committed.offset)
        if committed.status != BrokerPositionStatus.ABSENT:
            msg = "committed_position_uncertain"
            raise KafkaPositionError(msg)
        configuration = await self._store.capture_initial_partitions(request, observation)
        self._assigned(request)
        bounds = await self._bounds(request)
        kind = KafkaInitialPositionStore.initialization_kind(configuration, request.partition)
        boundary = bounds[1] if kind == InitializationKind.FIRST_ACTIVATION else bounds[0]
        return await self._store.choose_initial(request, observation, boundary, initialization_kind=kind)

    @staticmethod
    def _initial_history(context: PositionContext, row: KafkaPartitionInitialPosition) -> None:
        if row.initialization_kind is None:
            if row.recovery_confirmed_at is None:
                raise KafkaPositionError(
                    GapReason.INITIALIZATION_HISTORY_UNAVAILABLE.value, PositionStatus.RECOVERY_GAP
                )
            return
        configuration = context.configuration
        if configuration.initial_partition_ids is None or row.initialization_kind != (
            KafkaInitialPositionStore.initialization_kind(configuration, row.partition)
        ):
            raise KafkaPositionError(GapReason.INITIALIZATION_HISTORY_UNAVAILABLE.value, PositionStatus.RECOVERY_GAP)

    async def _initialize(self, request: PositionRequest) -> PositionResult:
        context = await self._store.read(request)
        self._assigned(request)
        self._source(context)
        if not context.active:
            msg = "admission_closed"
            raise KafkaPositionError(msg)
        row = context.position
        if row is not None and row.gap_detected_at is not None:
            return self._gap_result(request, row)
        if context.recovery_held:
            msg = "waiting_for_source_recovery"
            raise KafkaPositionError(msg)
        observation = await self._observe_identity(request)
        committed = await self._committed(request)
        if row is None:
            row = await self._new_position(request, committed, observation)
            if row.gap_detected_at is not None:
                return self._gap_result(request, row)
            # Reload the winner's committed progress rather than overwriting it.
            committed = await self._committed(request)
            context = await self._store.read(request)
        self._initial_history(context, row)
        bounds = await self._bounds(request)
        return await self._activate(request, row, committed, bounds)

    async def _activate(
        self,
        request: PositionRequest,
        row: KafkaPartitionInitialPosition,
        committed: CommittedPositionResult,
        bounds: tuple[int, int],
    ) -> PositionResult:
        if row.gap_detected_at is not None or row.recovery_token is not None:
            msg = "recovery_incomplete"
            raise KafkaPositionError(msg)
        established = row.initial_commit_confirmed_at is not None or row.recovery_confirmed_at is not None
        if committed.status == BrokerPositionStatus.ABSENT:
            if established:
                raise KafkaPositionError(GapReason.MISSING_COMMIT.value, PositionStatus.RECOVERY_GAP)
            boundary = row.initial_next_offset
            if boundary is None:
                raise KafkaPositionError(GapReason.INITIAL_METADATA_MISSING.value, PositionStatus.RECOVERY_GAP)
            self._within_bounds(boundary, bounds)
            await self._commit_boundary(request, boundary)
        elif committed.status == BrokerPositionStatus.VERIFIED and committed.offset is not None:
            boundary = committed.offset
            self._within_bounds(boundary, bounds)
            if boundary < self._lower_boundary(row):
                raise KafkaPositionError(GapReason.BELOW_AUTHORIZED_BOUNDARY.value, PositionStatus.RECOVERY_GAP)
            self._assigned(request)
            await self._client.seek(request.partition, boundary, expected_epoch=request.assignment_epoch)
        else:
            if established:
                raise KafkaPositionError(GapReason.OUT_OF_RANGE.value, PositionStatus.RECOVERY_GAP)
            msg = "committed_position_uncertain"
            raise KafkaPositionError(msg)
        self._assigned(request)
        if not established:
            if row.initial_next_offset is None:
                raise KafkaPositionError(GapReason.INITIAL_METADATA_MISSING.value, PositionStatus.RECOVERY_GAP)
            await self._store.confirm_initial(request, boundary=row.initial_next_offset)
        return await self._ready(request, boundary)

    async def _commit_boundary(self, request: PositionRequest, boundary: int, *, token: UUID | None = None) -> None:
        self._assigned(request)
        if token is not None and not await self._fenced(request, token=token):
            msg = "recovery_fence_lost"
            raise KafkaPositionError(msg)
        self._assigned(request)
        await self._client.seek(request.partition, boundary, expected_epoch=request.assignment_epoch)
        self._assigned(request)
        await self._client.commit({request.partition: boundary}, expected_epoch=request.assignment_epoch)
        verified = await self._committed(request)
        if verified.status != BrokerPositionStatus.VERIFIED or verified.offset != boundary:
            msg = "commit_unconfirmed"
            raise KafkaPositionError(msg)
        if token is not None and not await self._fenced(request, token=token):
            msg = "recovery_fence_lost"
            raise KafkaPositionError(msg)
        self._assigned(request)

    async def _ready(self, request: PositionRequest, boundary: int) -> PositionResult:
        context = await self._store.read(request)
        self._source(context)
        row = context.position
        if context.recovery_held:
            msg = "waiting_for_source_recovery"
            raise KafkaPositionError(msg)
        if (
            row is None
            or not context.active
            or row.gap_detected_at is not None
            or (row.initial_commit_confirmed_at is None and row.recovery_confirmed_at is None)
        ):
            msg = "admission_closed"
            raise KafkaPositionError(msg)
        if boundary < self._lower_boundary(row):
            raise KafkaPositionError(GapReason.BELOW_AUTHORIZED_BOUNDARY.value, PositionStatus.RECOVERY_GAP)
        self._assigned(request)
        return PositionResult(
            status=PositionStatus.READY,
            next_offset=boundary,
            assignment_epoch=request.assignment_epoch,
            recovery_revision=row.recovery_revision,
        )

    async def _drain(self, request: RecoveryRequest, token: UUID, boundary: int) -> None:
        async with asyncio.timeout(EventSchedulingDefaults.RPC_TIMEOUT_SECONDS):
            evidence = await self._control.close_and_drain(request, token=token, boundary=boundary)
        self._assigned(request)
        if not evidence.quiescent or not await self._fenced(request, token=token):
            msg = "conflicting_work_not_drained"
            raise KafkaPositionError(msg)
        if evidence.permanent_content_error:
            msg = "permanent_content_error"
            raise KafkaPositionError(msg)
        if (
            request.policy == RecoveryPolicy.RETAINED_BEGINNING
            and not evidence.retained_evidence_complete
            and not request.acknowledge_duplicate_risk
        ):
            msg = "duplicate_risk_acknowledgement_required"
            raise KafkaPositionError(msg)

    async def _cache_coordinated(
        self, request: RecoveryRequest, row: KafkaPartitionInitialPosition, token: UUID, boundary: int
    ) -> None:
        lower = row.authorized_lower_boundary
        if lower is not None and boundary >= lower:
            return  # Forward recovery preserves the retained terminal outcomes.
        if self._cache_coordination is None:
            msg = "cache_epoch_coordination_required"
            raise KafkaPositionError(msg)
        self._assigned(request)
        async with asyncio.timeout(EventSchedulingDefaults.RPC_TIMEOUT_SECONDS):
            coordinated = await self._cache_coordination.is_coordinated(
                request, token=token, recovery_revision=row.recovery_revision, boundary=boundary
            )
        self._assigned(request)
        if coordinated is not True:
            msg = "cache_epoch_coordination_required"
            raise KafkaPositionError(msg)

    async def _recover(self, request: RecoveryRequest, owner_worker_id: str) -> PositionResult:
        context = await self._store.read(request)
        self._source(context)
        row = context.position
        if row is not None and row.gap_detected_at is None and row.recovery_confirmed_at is not None:
            if (
                request.expected_recovery_revision not in {row.recovery_revision, row.recovery_revision - 1}
                or row.recovery_policy != request.policy.value
                or row.recovery_reason != request.reason
                or row.duplicate_risk_acknowledged != request.acknowledge_duplicate_risk
            ):
                msg = "recovery_revision_changed"
                raise KafkaPositionError(msg, PositionStatus.REVISION_CHANGED)
            # A lost confirmation response must not seek backwards over resumed work.
            return await self._initialize(request)
        await self._observe_identity(request)
        row = await self._store.begin_recovery(request)
        token = row.recovery_token
        if token is None:
            msg = "recovery_hold_unavailable"
            raise KafkaPositionError(msg)
        bounds = await self._bounds(request)
        boundary = row.pending_boundary
        if boundary is None:
            boundary = bounds[0] if request.policy == RecoveryPolicy.RETAINED_BEGINNING else bounds[1]
        self._within_bounds(boundary, bounds)
        row = await self._store.select_recovery_boundary(request, token, boundary)
        boundary = row.pending_boundary
        if boundary is None:
            msg = "recovery_boundary_unavailable"
            raise KafkaPositionError(msg)
        self._within_bounds(boundary, bounds)
        await self._drain(request, token, boundary)
        await self._cache_coordinated(request, row, token, boundary)
        claims = await self._store.reconcile_claims(request, token, owner_worker_id)
        for claim in claims:
            result = await self._admission.recover_claim(claim)
            if not isinstance(result, ResolvedDelivery):
                msg = "ambiguous_start_unresolved"
                raise KafkaPositionError(msg)
        # Verify repair before changing positions; the selection is already
        # durable even if drain/repair failed during an earlier invocation.
        row = await self._store.stage_recovery(request, token, boundary)
        boundary = row.pending_boundary
        if boundary is None:
            msg = "recovery_boundary_unavailable"
            raise KafkaPositionError(msg)
        return await self._finish_recovery(request, row, token, boundary)

    async def _replace_recovery(self, request: RecoveryReplacementRequest, owner_worker_id: str) -> PositionResult:
        context = await self._store.read(request)
        self._source(context)
        row = context.position
        repeated = (
            row is not None
            and row.superseded_recovery_revision == request.expected_recovery_revision
            and row.superseded_recovery_boundary == request.expected_pending_boundary
            and row.recovery_revision == request.expected_recovery_revision + 1
        )
        if not repeated and (
            row is None
            or row.recovery_token is None
            or row.recovery_revision != request.expected_recovery_revision
            or row.pending_boundary != request.expected_pending_boundary
        ):
            msg = "recovery_revision_changed"
            raise KafkaPositionError(msg, PositionStatus.REVISION_CHANGED)
        await self._observe_identity(request)
        bounds = await self._bounds(request)
        if not repeated and bounds[0] <= request.expected_pending_boundary <= bounds[1]:
            msg = "recovery_boundary_not_expired"
            raise KafkaPositionError(msg)
        boundary = bounds[0] if request.policy == RecoveryPolicy.RETAINED_BEGINNING else bounds[1]
        await self._store.replace_recovery(request, boundary)
        return await self._recover(request, owner_worker_id)

    async def _finish_recovery(
        self, request: RecoveryRequest, row: KafkaPartitionInitialPosition, token: UUID, boundary: int
    ) -> PositionResult:
        await self._observe_identity(request)
        self._within_bounds(boundary, await self._bounds(request))
        await self._cache_coordinated(request, row, token, boundary)
        committed = await self._committed(request)
        if committed.status == BrokerPositionStatus.VERIFIED and committed.offset == boundary:
            if not await self._fenced(request, token=token):
                msg = "recovery_fence_lost"
                raise KafkaPositionError(msg)
            self._assigned(request)
            await self._client.seek(request.partition, boundary, expected_epoch=request.assignment_epoch)
        else:
            await self._commit_boundary(request, boundary, token=token)
        self._assigned(request)
        if not await self._fenced(request, token=token):
            msg = "recovery_fence_lost"
            raise KafkaPositionError(msg)
        await self._cache_coordinated(request, row, token, boundary)
        await self._store.confirm_recovery(request, token, boundary)
        return await self._ready(request, boundary)
