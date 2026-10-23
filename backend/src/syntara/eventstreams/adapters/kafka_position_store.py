"""Short PostgreSQL transactions for Kafka partition initialization and recovery."""

from collections.abc import Callable
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, and_, func, not_, or_
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.constants import FieldLimits
from syntara.eventstreams.adapters.kafka_initial_position import (
    GapReason,
    KafkaPartitionInitialPosition,
    PositionRequest,
    PositionStatus,
    PositionValue,
    RecoveryReplacementRequest,
    RecoveryRequest,
)
from syntara.eventstreams.adapters.kafka_source_configuration import KafkaSourceConfiguration
from syntara.eventstreams.core.consumer import IdentityStatus, SourceIdentityObservation
from syntara.eventstreams.core.deduplication import (
    DeliveryClaim,
    DeliveryExpectation,
    DeliveryState,
    RecoveryReservation,
)
from syntara.eventstreams.core.processing import CONTENT_INSPECTION_PENDING
from syntara.eventstreams.core.results import EventFailureCode
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.recovery_hold import EventDeliveryRecoveryHold
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.services.deduplication_store import EventDeliveryStore
from syntara.eventstreams.services.delivery_retention_service import release_recovery_locked, reserve_recovery_locked
from syntara.eventstreams.services.subscription_service import lock_source_lifecycle
from syntara.workflows.models.execution import Execution

if TYPE_CHECKING:
    from datetime import datetime

_FENCED_BY_GAP_RECOVERY = "fenced_by_gap_recovery"


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
        if row is not None and row.recovery_token is not None:
            hold = await session.get(EventDeliveryRecoveryHold, row.recovery_token, populate_existing=True)
            if hold is None or hold.source_id != source.id or hold.released_at is not None:
                msg = "recovery_hold_unavailable"
                raise KafkaPositionError(msg)
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
    async def _held(session: AsyncSession, source_id: UUID) -> bool:
        return (
            await session.exec(
                select(EventDeliveryRecoveryHold.token)
                .where(
                    col(EventDeliveryRecoveryHold.source_id) == source_id,
                    col(EventDeliveryRecoveryHold.released_at).is_(None),
                )
                .limit(1)
            )
        ).first() is not None

    async def read(self, request: PositionRequest) -> PositionContext:
        """Load committed context, including pending initialization/recovery."""
        async with self._session_factory() as session, session.begin():
            subscription, source, row = await self._locked(session, request)
            result = PositionContext(
                configuration=source.configuration,
                position=None if row is None else self._copy(row),
                active=subscription.desired_enabled and not subscription.paused,
                recovery_held=await self._held(session, source.id),
            )
        return result  # noqa: RET504 - boundary evidence is usable only after commit

    async def choose_initial(
        self, request: PositionRequest, observation: SourceIdentityObservation, boundary: int
    ) -> KafkaPartitionInitialPosition:
        """Insert once, reload the winner, and populate verified source identifiers once."""
        async with self._session_factory() as session, session.begin():
            subscription, source, row = await self._locked(session, request)
            if not subscription.desired_enabled or subscription.paused or await self._held(session, source.id):
                msg = "admission_closed"
                raise KafkaPositionError(msg)
            self._identity(source, observation)
            if row is None:
                await session.execute(
                    insert(KafkaPartitionInitialPosition)
                    .values(source_id=source.id, partition=request.partition, initial_next_offset=boundary)
                    .on_conflict_do_nothing(index_elements=["source_id", "partition"])
                )
                _, _, row = await self._locked(session, request)
            if row is None:
                msg = "initial_boundary_unavailable"
                raise KafkaPositionError(msg)
            await session.flush()
            result = self._copy(row)
        return result  # noqa: RET504 - boundary evidence is usable only after commit

    async def verify_identity(self, request: PositionRequest, observation: SourceIdentityObservation) -> None:
        """Recheck the current source under its lifecycle lock before using observations."""
        async with self._session_factory() as session, session.begin():
            _, source, _ = await self._locked(session, request)
            self._identity(source, observation)

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
                or await self._held(session, source.id)
                or not subscription.desired_enabled
                or subscription.paused
            ):
                msg = "initial_confirmation_conflict"
                raise KafkaPositionError(msg)
            if row.initial_commit_confirmed_at is None:
                now = cast("datetime", (await session.exec(select(func.clock_timestamp()))).one())
                row.initial_commit_confirmed_at = now
                source.initialized_at = source.initialized_at or now

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
            _, source, row = await self._locked(session, request)
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
                hold = await session.get(EventDeliveryRecoveryHold, row.recovery_token)
                if hold is None or hold.source_id != source.id or hold.released_at is not None:
                    msg = "recovery_hold_unavailable"
                    raise KafkaPositionError(msg)
            else:
                if row.recovery_revision != request.expected_recovery_revision:
                    msg = "recovery_revision_changed"
                    raise KafkaPositionError(msg, PositionStatus.REVISION_CHANGED)
                reservation = await reserve_recovery_locked(session, source, uuid4())
                if reservation is None:
                    msg = "recovery_hold_unavailable"
                    raise KafkaPositionError(msg)
                row.recovery_revision += 1
                row.recovery_token = reservation.token
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
            _, source, row = await self._locked(session, request)
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
                old_reservation = RecoveryReservation(source_id=source.id, token=row.recovery_token)
                reservation = await reserve_recovery_locked(session, source, uuid4())
                if reservation is None:
                    msg = "recovery_hold_unavailable"
                    raise KafkaPositionError(msg)
                row.superseded_recovery_revision = row.recovery_revision
                row.superseded_recovery_boundary = row.pending_boundary
                row.recovery_revision += 1
                row.recovery_token = reservation.token
                row.pending_boundary = boundary
                row.pending_policy = request.policy.value
                row.pending_reason = request.reason
                row.pending_duplicate_risk_acknowledged = request.acknowledge_duplicate_risk
                if not await release_recovery_locked(session, source, old_reservation):
                    msg = "recovery_hold_unavailable"
                    raise KafkaPositionError(msg)
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

    @staticmethod
    async def _deliveries(session: AsyncSession, request: PositionRequest, boundary: int) -> list[EventDelivery]:
        # Exclude only proven unprepared work fenced for subsequent redelivery.
        # Otherwise a page of those rows could hide a later unresolved start.
        fenced_for_redelivery = and_(
            col(EventDelivery.state) == DeliveryState.IN_PROGRESS.value,
            col(EventDelivery.last_error_code).is_not(None),
            col(EventDelivery.last_error_code) == _FENCED_BY_GAP_RECOVERY,
            col(EventDelivery.frozen_binding).is_(None),
            col(EventDelivery.attempt_count) == 0,
            col(EventDelivery.temporal_run_id).is_(None),
            col(EventDelivery.execution_id).is_(None),
            col(EventDelivery.claim_token).is_(None),
            col(EventDelivery.owner_worker_id).is_(None),
            col(EventDelivery.lease_until).is_(None),
            sql_cast(col(EventDelivery.record_identity)["offset"].as_string(), BigInteger) >= boundary,
        )
        rows = (
            await session.exec(
                select(EventDelivery)
                .where(
                    col(EventDelivery.source_id) == request.source_id,
                    col(EventDelivery.transport) == "kafka",
                    col(EventDelivery.record_identity)["partition"].as_integer() == request.partition,
                    not_(fenced_for_redelivery),
                    or_(
                        col(EventDelivery.state) == DeliveryState.IN_PROGRESS.value,
                        col(EventDelivery.state) == DeliveryState.REJECTED.value,
                        col(EventDelivery.last_error_code).in_([code.value for code in EventFailureCode]),
                    ),
                )
                .order_by(col(EventDelivery.identity_digest))
                .limit(FieldLimits.MAX_ITEMS_PER_PAGE + 1)
                .with_for_update()
            )
        ).all()
        return list(rows)

    @staticmethod
    def _content_gate(rows: list[EventDelivery]) -> None:
        content_codes = {code.value for code in EventFailureCode}
        if any(row.state == DeliveryState.REJECTED or row.last_error_code in content_codes for row in rows):
            msg = "permanent_content_error"
            raise KafkaPositionError(msg)
        if any(row.last_error_code == CONTENT_INSPECTION_PENDING for row in rows):
            msg = "content_inspection_pending"
            raise KafkaPositionError(msg)

    async def reconcile_claims(
        self, request: RecoveryRequest, token: UUID, owner_worker_id: str
    ) -> list[DeliveryClaim]:
        """Fence unscheduled unprepared work; return prepared claims for upstream repair.

        Expiry alone never cancels: unprepared cancellation also requires no
        Execution binding, no start attempt, no accepted-run evidence, a durable
        recovery hold and the caller's verified drain/fence before this operation.
        """
        async with self._session_factory() as session, session.begin():
            subscription, _, row = await self._locked(session, request)
            row = self._pending(row, request, token)
            if row.pending_boundary is None:
                msg = "recovery_boundary_unavailable"
                raise KafkaPositionError(msg)
            rows = await self._deliveries(session, request, row.pending_boundary)
            self._content_gate(rows)
            now = cast("datetime", (await session.exec(select(func.clock_timestamp()))).one())
            claims: list[DeliveryClaim] = []
            for delivery in rows:
                if delivery.state != DeliveryState.IN_PROGRESS:
                    continue
                if delivery.lease_until is not None and delivery.lease_until > now:
                    msg = "conflicting_claim_busy"
                    raise KafkaPositionError(msg)
                if delivery.frozen_binding is None:
                    if (
                        delivery.attempt_count
                        or delivery.temporal_run_id is not None
                        or delivery.execution_id is not None
                        or await session.get(Execution, delivery.execution_identity) is not None
                    ):
                        msg = "unreconciled_start_evidence"
                        raise KafkaPositionError(msg)
                    if delivery.record_identity.offset < row.pending_boundary:
                        delivery.state = DeliveryState.CANCELLED
                        delivery.resolved_at = now
                        delivery.last_error_code = "cancelled_by_gap_recovery"
                    else:
                        delivery.last_error_code = _FENCED_BY_GAP_RECOVERY
                        delivery.next_attempt_at = now
                    delivery.claim_token = None
                    delivery.owner_worker_id = None
                    delivery.lease_until = None
                    continue
                if len(claims) >= FieldLimits.MAX_ITEMS_PER_PAGE:
                    continue
                store = EventDeliveryStore(session)
                # Lifecycle is already locked. Make parked work due without
                # granting a new duplicate-protection window or changing input.
                await store.request_scheduling_retry(delivery.delivery_identity())
                claimed = await store.acquire(
                    delivery.delivery_identity(),
                    DeliveryExpectation(
                        published_version_id=subscription.published_version_id,
                        configuration_revision=subscription.configuration_revision,
                    ),
                    owner_worker_id,
                )
                if not isinstance(claimed, DeliveryClaim):
                    msg = "conflicting_claim_busy"
                    raise KafkaPositionError(msg)
                claims.append(claimed)
        return claims

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
            rows = await self._deliveries(session, request, boundary)
            self._content_gate(rows)
            if any(delivery.state == DeliveryState.IN_PROGRESS for delivery in rows):
                msg = "claims_unresolved"
                raise KafkaPositionError(msg)
            result = self._copy(row)
        return result  # noqa: RET504 - boundary evidence is usable only after commit

    async def confirm_recovery(self, request: RecoveryRequest, token: UUID, boundary: int) -> None:
        """Confirm verified Kafka progress and release only this hold in one transaction."""
        async with self._session_factory() as session, session.begin():
            _, source, row = await self._locked(session, request)
            row = self._pending(row, request, token)
            rows = await self._deliveries(session, request, boundary)
            self._content_gate(rows)
            if row.pending_boundary != boundary or any(d.state == DeliveryState.IN_PROGRESS for d in rows):
                msg = "claims_unresolved"
                raise KafkaPositionError(msg)
            if not await release_recovery_locked(
                session, source, RecoveryReservation(source_id=source.id, token=token)
            ):
                msg = "recovery_hold_unavailable"
                raise KafkaPositionError(msg)
            row.recovery_boundary = boundary
            row.recovery_confirmed_at = cast("datetime", (await session.exec(select(func.clock_timestamp()))).one())
            source.initialized_at = source.initialized_at or row.recovery_confirmed_at
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
