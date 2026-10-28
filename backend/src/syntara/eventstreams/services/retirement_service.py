"""Recovery-safe disposition and deletion eligibility under lifecycle locks.

This service never expires or discards evidence. Terminal identities must first
pass the existing retention service's window and verified-commit checks.
"""

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.eventstreams.adapters.kafka_initial_position import KafkaPartitionInitialPosition
from syntara.eventstreams.core.deduplication import DeliveryState
from syntara.eventstreams.core.processing import CONTENT_INSPECTION_PENDING
from syntara.eventstreams.core.results import EventFailureCode
from syntara.eventstreams.core.scheduling_metadata import EVENT_DELIVERY_METADATA_KEY, SCHEDULING_STATE_KEY
from syntara.eventstreams.exceptions import EventSubscriptionControlConflictError
from syntara.eventstreams.models.control import EventSubscriptionRecovery, EventSubscriptionRuntime
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.recovery_hold import EventDeliveryRecoveryHold
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.workflows.models.execution import Execution, ExecutionStatus

CONTENT_GATES = frozenset({CONTENT_INSPECTION_PENDING, *(code.value for code in EventFailureCode)})


def reject_content_gates(deliveries: list[EventDelivery]) -> None:
    """Known errors and uninspected content cannot bypass the activity-log gate."""
    if any(row.state == DeliveryState.REJECTED or row.last_error_code in CONTENT_GATES for row in deliveries):
        msg = "permanent_content_error_requires_activity_log"
        raise EventSubscriptionControlConflictError(msg)


async def cancel_unstarted(session: AsyncSession, delivery: EventDelivery, now: datetime) -> None:
    """Fence and atomically cancel only work for which no start RPC was authorized.

    The caller owns lifecycle and delivery locks. Every start must persist its
    attempt under those locks before sending an RPC; invalidating the token here
    therefore prevents both future attempts and stale workers from starting.
    """
    reject_content_gates([delivery])
    if (
        delivery.attempt_count
        or delivery.first_start_attempt_at
        or delivery.temporal_run_id
        or delivery.execution_confirmed_at
    ):
        msg = "prior_start_acceptance_unresolved"
        raise EventSubscriptionControlConflictError(msg)
    execution = await session.get(Execution, delivery.execution_identity, with_for_update=True, populate_existing=True)
    if delivery.frozen_binding is not None:
        if execution is None or delivery.execution_id != execution.id or execution.status != ExecutionStatus.PENDING:
            msg = "pending_execution_evidence_unavailable"
            raise EventSubscriptionControlConflictError(msg)
        metadata = (execution.execution_metadata or {}).get(EVENT_DELIVERY_METADATA_KEY, {})
        if (
            not isinstance(metadata, dict)
            or metadata.get(SCHEDULING_STATE_KEY) != "prepared"
            or metadata.get("attempt_count", 0)
            or metadata.get("temporal_run_id")
            or metadata.get("start_attempt_id")
        ):
            msg = "prior_start_acceptance_unresolved"
            raise EventSubscriptionControlConflictError(msg)
        execution.status = ExecutionStatus.CANCELLED
        execution.completed_at = now
        execution.error_details = "cancelled_by_lifecycle"
        execution.execution_metadata = {
            **(execution.execution_metadata or {}),
            EVENT_DELIVERY_METADATA_KEY: {
                **metadata,
                SCHEDULING_STATE_KEY: "cancelled",
                "reason": "cancelled_by_lifecycle",
            },
        }
    elif execution is not None or delivery.execution_id is not None:
        msg = "unexpected_execution_evidence"
        raise EventSubscriptionControlConflictError(msg)
    delivery.state = DeliveryState.CANCELLED
    delivery.resolved_at = now
    delivery.last_error_code = "cancelled_by_lifecycle"
    delivery.claim_token = None
    delivery.owner_worker_id = None
    delivery.lease_until = None


class EventRetirementService:
    """Never use a local drain, not-found, or expired lease as fleet-wide proof."""

    def __init__(self, session: AsyncSession) -> None:
        """Reuse the caller's lifecycle transaction; never commit independently."""
        self.session = session

    async def assert_no_content_gate(self, source_id: UUID) -> None:
        """Preserve durable and shutdown-carried errors across all control paths."""
        runtime = (
            await self.session.exec(
                select(EventSubscriptionRuntime.worker_id)
                .where(
                    EventSubscriptionRuntime.source_id == source_id,
                    col(EventSubscriptionRuntime.permanent_content_error).is_(True),
                )
                .limit(1)
            )
        ).first()
        delivery = (
            await self.session.exec(
                select(EventDelivery.identity_digest)
                .where(
                    EventDelivery.source_id == source_id,
                    or_(
                        col(EventDelivery.state) == DeliveryState.REJECTED.value,
                        col(EventDelivery.last_error_code).in_(CONTENT_GATES),
                    ),
                )
                .limit(1)
            )
        ).first()
        if runtime is not None or delivery is not None:
            msg = "permanent_content_error_requires_activity_log"
            raise EventSubscriptionControlConflictError(msg)

    async def can_detach(self, source: EventSubscriptionSource) -> bool:
        """Retain resources until no delivery, recovery decision or hold needs them."""
        if (
            source.retired_at is None
            or not await self.stopped(source.id)
            or await self.has_retained_deliveries(source.id)
        ):
            return False
        hold = (
            await self.session.exec(
                select(EventDeliveryRecoveryHold.token)
                .where(
                    EventDeliveryRecoveryHold.source_id == source.id,
                    col(EventDeliveryRecoveryHold.released_at).is_(None),
                )
                .limit(1)
            )
        ).first()
        position = (
            await self.session.exec(
                select(KafkaPartitionInitialPosition.partition)
                .where(
                    KafkaPartitionInitialPosition.source_id == source.id,
                    col(KafkaPartitionInitialPosition.gap_detected_at).is_not(None),
                )
                .limit(1)
            )
        ).first()
        request = (
            await self.session.exec(
                select(EventSubscriptionRecovery.partition)
                .where(
                    EventSubscriptionRecovery.source_id == source.id,
                    col(EventSubscriptionRecovery.completed).is_(False),
                )
                .limit(1)
            )
        ).first()
        return hold is None and position is None and request is None

    async def stopped(self, source_id: UUID) -> bool:
        """Registration serializes with publication; missing acknowledgements persist."""
        gate = (
            await self.session.exec(
                select(EventSubscriptionRuntime.worker_id)
                .where(
                    EventSubscriptionRuntime.source_id == source_id,
                    col(EventSubscriptionRuntime.permanent_content_error).is_(True),
                )
                .limit(1)
            )
        ).first()
        if gate is not None:
            msg = "permanent_content_error_requires_activity_log"
            raise EventSubscriptionControlConflictError(msg)
        return (
            await self.session.exec(
                select(EventSubscriptionRuntime.worker_id)
                .where(
                    EventSubscriptionRuntime.source_id == source_id, col(EventSubscriptionRuntime.stopped).is_(False)
                )
                .limit(1)
            )
        ).first() is None

    async def deliveries(self, source_id: UUID) -> list[EventDelivery]:
        """Lock unresolved/gated work without loading the terminal retention window."""
        return list(
            (
                await self.session.exec(
                    select(EventDelivery)
                    .where(
                        EventDelivery.source_id == source_id,
                        or_(
                            col(EventDelivery.state) == DeliveryState.IN_PROGRESS.value,
                            col(EventDelivery.state) == DeliveryState.REJECTED.value,
                            col(EventDelivery.last_error_code).in_(CONTENT_GATES),
                        ),
                    )
                    .order_by(EventDelivery.identity_digest)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )

    async def has_retained_deliveries(self, source_id: UUID) -> bool:
        """Test retention eligibility without materializing terminal history."""
        return (
            await self.session.exec(
                select(EventDelivery.identity_digest).where(EventDelivery.source_id == source_id).limit(1)
            )
        ).first() is not None

    async def retire(self, source: EventSubscriptionSource, *, resolve_unscheduled: bool) -> None:
        """Retain bound references and all evidence after any safe disposition."""
        if source.retired_at is None:
            msg = "remove_or_replace_published_listener_first"
            raise EventSubscriptionControlConflictError(msg)
        if not await self.stopped(source.id):
            msg = "consumer_stop_acknowledgements_pending"
            raise EventSubscriptionControlConflictError(msg)
        deliveries = await self.deliveries(source.id)
        reject_content_gates(deliveries)
        pending = [row for row in deliveries if row.state == DeliveryState.IN_PROGRESS]
        if pending and not resolve_unscheduled:
            msg = "unresolved_deliveries_require_disposition"
            raise EventSubscriptionControlConflictError(msg)
        now = cast("datetime", (await self.session.exec(select(func.clock_timestamp()))).one())
        for row in pending:
            await cancel_unstarted(self.session, row, now)
        source.delivery_evidence_revision += 1

    async def release_empty_source(self, source: EventSubscriptionSource) -> None:
        """Release only when retained identities no longer require any source evidence."""
        if source.retired_at is None or not await self.stopped(source.id):
            msg = "source_retirement_pending"
            raise EventSubscriptionControlConflictError(msg)
        if await self.has_retained_deliveries(source.id):
            msg = "retained_delivery_evidence_blocks_deletion"
            raise EventSubscriptionControlConflictError(msg)
        holds = list(
            (
                await self.session.exec(
                    select(EventDeliveryRecoveryHold).where(EventDeliveryRecoveryHold.source_id == source.id)
                )
            ).all()
        )
        positions = list(
            (
                await self.session.exec(
                    select(KafkaPartitionInitialPosition).where(KafkaPartitionInitialPosition.source_id == source.id)
                )
            ).all()
        )
        if any(hold.released_at is None for hold in holds) or any(
            position.gap_detected_at is not None or position.recovery_token is not None for position in positions
        ):
            msg = "recovery_evidence_blocks_deletion"
            raise EventSubscriptionControlConflictError(msg)
        requests = list(
            (
                await self.session.exec(
                    select(EventSubscriptionRecovery).where(EventSubscriptionRecovery.source_id == source.id)
                )
            ).all()
        )
        if any(not request.completed for request in requests):
            msg = "recovery_request_pending"
            raise EventSubscriptionControlConflictError(msg)
        for position in positions:
            await self.session.delete(position)
        await self.session.flush()
        for item in [*holds, *requests]:
            await self.session.delete(item)
        runtimes = (
            await self.session.exec(
                select(EventSubscriptionRuntime).where(EventSubscriptionRuntime.source_id == source.id)
            )
        ).all()
        for runtime in runtimes:
            await self.session.delete(runtime)
        await self.session.flush()
        await self.session.delete(source)
