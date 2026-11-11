"""Short PostgreSQL transactions for Kafka partition initialization and recovery."""

from collections.abc import Callable
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.adapters.kafka_initial_position import (
    GapReason,
    InitializationKind,
    KafkaPartitionInitialPosition,
    PositionRequest,
    PositionStatus,
    PositionValue,
    RecoveryReplacementRequest,
    RecoveryRequest,
)
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.core.consumer import IdentityStatus, PartitionSetStatus, SourceIdentityObservation
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.services.subscription_service import lock_source_lifecycle
from syntara.workflows.models.execution import Execution


class KafkaPositionError(Exception):
    """Safe failure without broker messages or payloads; no commit permission."""

    def __init__(self, reason: str, status: PositionStatus = PositionStatus.BLOCKED) -> None:
        """Retain only a bounded reason and typed failure result."""
        self.reason = reason
        self.status = status
        super().__init__(reason)


class PositionContext(PositionValue):
    """Detached database evidence; broker observations happen after its transaction."""

    configuration: KafkaSourceConfiguration
    position: KafkaPartitionInitialPosition | None
    active: bool
    recovery_held: bool
    source_initialized_at: datetime | None = None


class KafkaInitialPositionStore:
    """Own fresh sessions and reuse the shared lifecycle and hold boundaries."""

    def __init__(self, session_factory: Callable[..., AsyncSession]) -> None:
        """Inject fresh sessions shared with upstream admission and recovery."""
        self._session_factory = session_factory

    @staticmethod
    async def _locked(
        session: AsyncSession, request: PositionRequest
    ) -> tuple[EventSubscription, EventSubscriptionSource, KafkaPartitionInitialPosition | None]:
        lifecycle = await lock_source_lifecycle(session, request.source_id)
        if lifecycle is None:
            msg = "source_unavailable"
            raise KafkaPositionError(msg, PositionStatus.REVISION_CHANGED)
        subscription, source = lifecycle
        if (
            source.generation != request.source_generation
            or subscription.configuration_revision != request.configuration_revision
            or subscription.active_source_generation != source.generation
            or source.retired_at is not None
            or subscription.retired
            or source.transport != "kafka"
            or not isinstance(source.configuration, KafkaSourceConfiguration)
        ):
            msg = "source_revision_changed"
            raise KafkaPositionError(msg, PositionStatus.REVISION_CHANGED)
        row = await session.get(
            KafkaPartitionInitialPosition,
            (source.id, request.partition),
            with_for_update=True,
            populate_existing=True,
        )
        return subscription, source, row

    @staticmethod
    def _identity(source: EventSubscriptionSource, observation: SourceIdentityObservation) -> None:
        configuration = source.configuration
        if observation.topic != configuration.topic:
            msg = "source_recreated"
            raise KafkaPositionError(msg, PositionStatus.RECOVERY_GAP)
        updates: dict[str, str] = {}
        for name in ("cluster_id", "topic_id"):
            evidence = getattr(observation, name)
            saved = getattr(configuration, name)
            if evidence.status == IdentityStatus.VERIFIED:
                if saved is not None and saved != evidence.value:
                    msg = "source_recreated"
                    raise KafkaPositionError(msg, PositionStatus.RECOVERY_GAP)
                if saved is None:
                    updates[name] = evidence.value
            elif evidence.status != IdentityStatus.UNSUPPORTED or saved is not None:
                msg = "source_identity_unavailable"
                raise KafkaPositionError(msg)
        if updates:
            source.configuration = configuration.model_copy(update=updates)

    @staticmethod
    def _copy(row: KafkaPartitionInitialPosition) -> KafkaPartitionInitialPosition:
        return KafkaPartitionInitialPosition(**row.model_dump())

    @staticmethod
    async def _held(session: AsyncSession, source_id: UUID, partition: int) -> bool:
        return (
            await session.exec(
                select(KafkaPartitionInitialPosition.partition)
                .where(
                    col(KafkaPartitionInitialPosition.source_id) == source_id,
                    col(KafkaPartitionInitialPosition.partition) == partition,
                    col(KafkaPartitionInitialPosition.recovery_token).is_not(None),
                )
                .limit(1)
            )
        ).first() is not None

    @staticmethod
    def _partitions(request: PositionRequest, observation: SourceIdentityObservation) -> tuple[int, ...]:
        if observation.assignment_epoch != request.assignment_epoch:
            msg = "assignment_lost"
            raise KafkaPositionError(msg, PositionStatus.OWNERSHIP_LOST)
        evidence = observation.partitions
        if evidence.status != PartitionSetStatus.VERIFIED or not evidence.partition_ids:
            msg = "topic_partitions_unavailable"
            raise KafkaPositionError(msg)
        if request.partition not in evidence.partition_ids:
            raise KafkaPositionError(GapReason.SOURCE_RECREATED.value, PositionStatus.RECOVERY_GAP)
        return tuple(sorted(evidence.partition_ids))

    @staticmethod
    async def _has_initialization_history(session: AsyncSession, source: EventSubscriptionSource) -> bool:
        if source.initialized_at is not None:
            return True
        positions = (
            await session.exec(
                select(KafkaPartitionInitialPosition.source_id)
                .where(col(KafkaPartitionInitialPosition.source_id) == source.id)
                .limit(1)
            )
        ).first()
        if positions is not None:
            return True
        return (
            await session.exec(
                select(Execution.id)
                .where(
                    col(Execution.execution_metadata)["event"]["identity"]["source_id"].as_string() == str(source.id)
                )
                .limit(1)
            )
        ).first() is not None

    async def capture_initial_partitions(
        self, request: PositionRequest, observation: SourceIdentityObservation
    ) -> KafkaSourceConfiguration:
        """Save a complete first snapshot once; assignment never defines membership."""
        async with self._session_factory() as session, session.begin():
            subscription, source, row = await self._locked(session, request)
            if (
                not subscription.desired_enabled
                or subscription.paused
                or await self._held(session, source.id, request.partition)
            ):
                msg = "admission_closed"
                raise KafkaPositionError(msg)
            self._identity(source, observation)
            partitions = self._partitions(request, observation)
            if source.configuration.initial_partition_ids is None:
                if await self._has_initialization_history(session, source):
                    status = PositionStatus.BLOCKED if row is None else PositionStatus.RECOVERY_GAP
                    raise KafkaPositionError(GapReason.INITIALIZATION_HISTORY_UNAVAILABLE.value, status)
                source.configuration = source.configuration.model_copy(update={"initial_partition_ids": partitions})
                await session.flush()
            result = source.configuration
        return result  # noqa: RET504 - the winning set must commit before any boundary is selected

    @staticmethod
    def initialization_kind(configuration: KafkaSourceConfiguration, partition: int) -> InitializationKind:
        """Classify only against saved historical membership, never current assignment."""
        if configuration.initial_partition_ids is None:
            msg = GapReason.INITIALIZATION_HISTORY_UNAVAILABLE.value
            raise KafkaPositionError(msg)
        return (
            InitializationKind.FIRST_ACTIVATION
            if partition in configuration.initial_partition_ids
            else InitializationKind.ADDED_PARTITION
        )

    @classmethod
    def _validate_kind(cls, source: EventSubscriptionSource, row: KafkaPartitionInitialPosition) -> None:
        if row.initialization_kind != cls.initialization_kind(source.configuration, row.partition):
            raise KafkaPositionError(GapReason.INITIALIZATION_HISTORY_UNAVAILABLE.value, PositionStatus.RECOVERY_GAP)

    async def read(self, request: PositionRequest) -> PositionContext:
        """Load committed context, including pending initialization/recovery."""
        async with self._session_factory() as session, session.begin():
            subscription, source, row = await self._locked(session, request)
            result = PositionContext(
                configuration=source.configuration,
                position=None if row is None else self._copy(row),
                active=subscription.desired_enabled and not subscription.paused,
                recovery_held=await self._held(session, source.id, request.partition),
                source_initialized_at=source.initialized_at,
            )
        return result  # noqa: RET504 - boundary evidence is usable only after commit

    async def choose_initial(
        self,
        request: PositionRequest,
        observation: SourceIdentityObservation,
        boundary: int,
        *,
        initialization_kind: InitializationKind,
    ) -> KafkaPartitionInitialPosition:
        """Insert once, reload the winner, and populate verified source identifiers once."""
        async with self._session_factory() as session, session.begin():
            subscription, source, row = await self._locked(session, request)
            if (
                not subscription.desired_enabled
                or subscription.paused
                or await self._held(session, source.id, request.partition)
            ):
                msg = "admission_closed"
                raise KafkaPositionError(msg)
            self._identity(source, observation)
            self._partitions(request, observation)
            if row is None:
                if initialization_kind != self.initialization_kind(source.configuration, request.partition):
                    msg = "initialization_kind_changed"
                    raise KafkaPositionError(msg, PositionStatus.REVISION_CHANGED)
                retained = (
                    await session.exec(
                        select(Execution.id)
                        .where(
                            col(Execution.execution_metadata)["event"]["identity"]["source_id"].as_string()
                            == str(source.id),
                            col(Execution.execution_metadata)["event"]["identity"]["record"]["partition"].as_integer()
                            == request.partition,
                        )
                        .limit(1)
                    )
                ).first()
                if retained is not None:
                    msg = GapReason.INITIALIZATION_HISTORY_UNAVAILABLE.value
                    raise KafkaPositionError(msg)
                await session.execute(
                    insert(KafkaPartitionInitialPosition)
                    .values(
                        source_id=source.id,
                        partition=request.partition,
                        initialization_kind=initialization_kind.value,
                        initial_next_offset=boundary,
                    )
                    .on_conflict_do_nothing(index_elements=["source_id", "partition"])
                )
                _, _, row = await self._locked(session, request)
            if row is None:
                msg = "initial_boundary_unavailable"
                raise KafkaPositionError(msg)
            if row.initialization_kind is not None:
                self._validate_kind(source, row)
            await session.flush()
            result = self._copy(row)
        return result  # noqa: RET504 - boundary evidence is usable only after commit

    async def verify_identity(self, request: PositionRequest, observation: SourceIdentityObservation) -> None:
        """Recheck the current source under its lifecycle lock before using observations."""
        async with self._session_factory() as session, session.begin():
            _, source, _ = await self._locked(session, request)
            self._identity(source, observation)
            self._partitions(request, observation)

    async def record_missing_initial(
        self, request: PositionRequest, observed_group_offset: int
    ) -> KafkaPartitionInitialPosition:
        """Persist missing history without treating the current commit as the first boundary."""
        async with self._session_factory() as session, session.begin():
            _, source, row = await self._locked(session, request)
            if row is None:
                now = cast("datetime", (await session.exec(select(func.clock_timestamp()))).one())
                await session.execute(
                    insert(KafkaPartitionInitialPosition)
                    .values(
                        source_id=source.id,
                        partition=request.partition,
                        initial_next_offset=None,
                        initialized_at=None,
                        initial_metadata_missing=True,
                        observed_group_next_offset=observed_group_offset,
                        gap_detected_at=now,
                        gap_reason=GapReason.INITIAL_METADATA_MISSING.value,
                    )
                    .on_conflict_do_nothing(index_elements=["source_id", "partition"])
                )
                _, _, row = await self._locked(session, request)
            if row is None:
                msg = "initial_metadata_unavailable"
                raise KafkaPositionError(msg)
            result = self._copy(row)
        return result  # noqa: RET504 - boundary evidence is usable only after commit

    async def mark_gap(self, request: PositionRequest, reason: GapReason) -> None:
        """Never clear an existing recovery operation or its evidence hold."""
        async with self._session_factory() as session, session.begin():
            _, _, row = await self._locked(session, request)
            if row is None:
                msg = "initial_metadata_unavailable"
                raise KafkaPositionError(msg)
            if row.recovery_token is None:
                row.gap_detected_at = cast("datetime", (await session.exec(select(func.clock_timestamp()))).one())
                row.gap_reason = reason.value

    async def confirm_initial(self, request: PositionRequest, *, boundary: int) -> None:
        """Confirm only after verified Kafka commit; permit no earlier processing."""
        async with self._session_factory() as session, session.begin():
            subscription, source, row = await self._locked(session, request)
            if (
                row is None
                or row.initial_metadata_missing
                or row.initial_next_offset != boundary
                or row.gap_detected_at is not None
                or await self._held(session, source.id, request.partition)
                or not subscription.desired_enabled
                or subscription.paused
            ):
                msg = "initial_confirmation_conflict"
                raise KafkaPositionError(msg)
            if row.initial_commit_confirmed_at is None:
                self._validate_kind(source, row)
                now = cast("datetime", (await session.exec(select(func.clock_timestamp()))).one())
                row.initial_commit_confirmed_at = now
                await self._complete_first_activation(session, source, now)

    @staticmethod
    async def _complete_first_activation(session: AsyncSession, source: EventSubscriptionSource, now: datetime) -> None:
        if source.initialized_at is not None or source.configuration.initial_partition_ids is None:
            return
        await session.flush()
        confirmed = (
            await session.exec(
                select(KafkaPartitionInitialPosition.partition).where(
                    col(KafkaPartitionInitialPosition.source_id) == source.id,
                    col(KafkaPartitionInitialPosition.partition).in_(source.configuration.initial_partition_ids),
                    col(KafkaPartitionInitialPosition.initialization_kind) == InitializationKind.FIRST_ACTIVATION.value,
                    col(KafkaPartitionInitialPosition.initial_commit_confirmed_at).is_not(None),
                )
            )
        ).all()
        if set(confirmed) == set(source.configuration.initial_partition_ids):
            source.initialized_at = now

    @staticmethod
    def _pending(
        row: KafkaPartitionInitialPosition | None, request: RecoveryRequest, token: UUID
    ) -> KafkaPartitionInitialPosition:
        if (
            row is None
            or row.recovery_token != token
            or row.recovery_revision not in {request.expected_recovery_revision, request.expected_recovery_revision + 1}
            or row.pending_policy != request.policy.value
            or row.pending_reason != request.reason
            or row.pending_duplicate_risk_acknowledged != request.acknowledge_duplicate_risk
        ):
            msg = "recovery_revision_changed"
            raise KafkaPositionError(msg, PositionStatus.REVISION_CHANGED)
        return row

    async def begin_recovery(self, request: RecoveryRequest) -> KafkaPartitionInitialPosition:
        """Close admission/cleanup atomically before drain or any evidence inspection."""
        async with self._session_factory() as session, session.begin():
            _, _, row = await self._locked(session, request)
            if row is None or row.gap_detected_at is None:
                msg = "no_recorded_recovery_gap"
                raise KafkaPositionError(msg)
            if row.recovery_token is not None:
                if (
                    request.expected_recovery_revision == row.recovery_revision
                    and row.pending_policy == request.policy.value
                    and row.pending_reason == request.reason
                    and not row.pending_duplicate_risk_acknowledged
                    and request.acknowledge_duplicate_risk
                ):
                    # Acknowledgement may change at the current revision, but
                    # never the selected policy/boundary or the evidence hold.
                    row.recovery_revision += 1
                    row.pending_duplicate_risk_acknowledged = True
                self._pending(row, request, row.recovery_token)
            else:
                if row.recovery_revision != request.expected_recovery_revision:
                    msg = "recovery_revision_changed"
                    raise KafkaPositionError(msg, PositionStatus.REVISION_CHANGED)
                row.recovery_revision += 1
                row.recovery_token = uuid4()
                row.pending_policy = request.policy.value
                row.pending_reason = request.reason
                row.pending_duplicate_risk_acknowledged = request.acknowledge_duplicate_risk
            result = self._copy(row)
        return result  # noqa: RET504 - boundary evidence is usable only after commit

    async def replace_recovery(
        self, request: RecoveryReplacementRequest, boundary: int
    ) -> KafkaPartitionInitialPosition:
        """Supersede only the named revision; transfer protection without a cleanup window."""
        async with self._session_factory() as session, session.begin():
            _, _, row = await self._locked(session, request)
            if row is None:
                msg = "no_recorded_recovery_gap"
                raise KafkaPositionError(msg)
            repeated = (
                row.superseded_recovery_revision == request.expected_recovery_revision
                and row.superseded_recovery_boundary == request.expected_pending_boundary
                and row.recovery_revision == request.expected_recovery_revision + 1
            )
            if repeated:
                if row.recovery_token is not None:
                    self._pending(row, request, row.recovery_token)
                elif (
                    row.recovery_confirmed_at is None
                    or row.recovery_policy != request.policy.value
                    or row.recovery_reason != request.reason
                    or row.duplicate_risk_acknowledged != request.acknowledge_duplicate_risk
                ):
                    msg = "recovery_revision_changed"
                    raise KafkaPositionError(msg, PositionStatus.REVISION_CHANGED)
            else:
                if (
                    row.recovery_revision != request.expected_recovery_revision
                    or row.recovery_token is None
                    or row.gap_detected_at is None
                    or row.pending_boundary != request.expected_pending_boundary
                ):
                    msg = "recovery_revision_changed"
                    raise KafkaPositionError(msg, PositionStatus.REVISION_CHANGED)
                row.superseded_recovery_revision = row.recovery_revision
                row.superseded_recovery_boundary = row.pending_boundary
                row.recovery_revision += 1
                row.recovery_token = uuid4()
                row.pending_boundary = boundary
                row.pending_policy = request.policy.value
                row.pending_reason = request.reason
                row.pending_duplicate_risk_acknowledged = request.acknowledge_duplicate_risk
            result = self._copy(row)
        return result  # noqa: RET504 - boundary evidence is usable only after commit

    async def select_recovery_boundary(
        self, request: RecoveryRequest, token: UUID, boundary: int
    ) -> KafkaPartitionInitialPosition:
        """Persist the first selection before drain/repair; interrupted calls reuse it."""
        async with self._session_factory() as session, session.begin():
            _, _, row = await self._locked(session, request)
            row = self._pending(row, request, token)
            if row.pending_boundary is None:
                row.pending_boundary = boundary
            result = self._copy(row)
        return result  # noqa: RET504 - boundary evidence is usable only after commit

    async def stage_recovery(
        self, request: RecoveryRequest, token: UUID, boundary: int
    ) -> KafkaPartitionInitialPosition:
        """Check reconciliation of the recorded boundary before Kafka position changes."""
        async with self._session_factory() as session, session.begin():
            _, _, row = await self._locked(session, request)
            row = self._pending(row, request, token)
            if row.pending_boundary != boundary:
                msg = "recovery_boundary_changed"
                raise KafkaPositionError(msg)
            result = self._copy(row)
        return result  # noqa: RET504 - boundary evidence is usable only after commit

    async def confirm_recovery(self, request: RecoveryRequest, token: UUID, boundary: int) -> None:
        """Confirm verified Kafka progress and release only this hold in one transaction."""
        async with self._session_factory() as session, session.begin():
            _, source, row = await self._locked(session, request)
            row = self._pending(row, request, token)
            if row.pending_boundary != boundary:
                msg = "recovery_boundary_changed"
                raise KafkaPositionError(msg)
            row.recovery_boundary = boundary
            row.recovery_confirmed_at = cast("datetime", (await session.exec(select(func.clock_timestamp()))).one())
            row.recovery_policy = row.pending_policy
            row.recovery_reason = row.pending_reason
            row.duplicate_risk_acknowledged = row.pending_duplicate_risk_acknowledged
            row.pending_boundary = None
            row.pending_policy = None
            row.pending_reason = None
            row.pending_duplicate_risk_acknowledged = False
            row.recovery_token = None
            row.gap_detected_at = None
            row.gap_reason = None
            await self._complete_first_activation(session, source, row.recovery_confirmed_at)
