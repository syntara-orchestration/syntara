"""Serialized recovery reservations and fail-closed minimum-retention cleanup."""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import structlog
from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import get_settings
from syntara.core.constants import EventDeliveryDefaults, FieldLimits
from syntara.eventstreams.core.deduplication import (
    CleanupCandidate,
    CommittedPositionUnavailableError,
    CommittedPositionVerifier,
    DeliveryIdentity,
    DeliveryState,
    RecoveryReservation,
)
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.recovery_hold import EventDeliveryRecoveryHold
from syntara.eventstreams.services.subscription_service import lock_source_lifecycle

logger = structlog.stdlib.get_logger(__name__)


class EventDeliveryRetentionService:
    """Own fresh short sessions; never hold a transaction across broker verification."""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        *,
        verifier: CommittedPositionVerifier | None = None,
        retention_seconds: int | None = None,
    ) -> None:
        """Inject the committed-position port; absent verification always retains evidence."""
        retention = get_settings().event_delivery_retention_seconds if retention_seconds is None else retention_seconds
        if not isinstance(retention, int) or isinstance(retention, bool) or retention <= 0:
            msg = "Delivery retention must be a positive integer"
            raise ValueError(msg)
        self.session_factory = session_factory
        self.verifier = verifier
        self.retention_seconds = retention

    async def reserve_recovery(self, source_id: UUID, *, token: UUID | None = None) -> RecoveryReservation | None:
        """Commit a hold before recovery depends on evidence or changes any boundary.

        Missing source state fails closed. A reservation protects remaining
        evidence; callers must still establish that their required evidence exists.
        """
        reservation_token = uuid4() if token is None else token
        async with self.session_factory() as session, session.begin():
            lifecycle = await lock_source_lifecycle(session, source_id)
            if lifecycle is None:
                return None
            _, source = lifecycle
            existing = await session.get(EventDeliveryRecoveryHold, reservation_token, populate_existing=True)
            if existing is not None:
                if existing.source_id != source_id or existing.released_at is not None:
                    return None
                return RecoveryReservation(source_id=source_id, token=reservation_token)
            now = cast("datetime", (await session.exec(select(func.clock_timestamp()))).one())
            session.add(EventDeliveryRecoveryHold(token=reservation_token, source_id=source_id, created_at=now))
            source.delivery_evidence_revision += 1
            await session.flush()
            return RecoveryReservation(source_id=source_id, token=reservation_token)

    async def release_recovery(self, reservation: RecoveryReservation) -> bool:
        """Release only the named reservation after its recovery dependency is resolved."""
        async with self.session_factory() as session, session.begin():
            lifecycle = await lock_source_lifecycle(session, reservation.source_id)
            if lifecycle is None:
                return False
            _, source = lifecycle
            hold = (
                await session.exec(
                    select(EventDeliveryRecoveryHold)
                    .where(
                        col(EventDeliveryRecoveryHold.token) == reservation.token,
                        col(EventDeliveryRecoveryHold.source_id) == reservation.source_id,
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).one_or_none()
            if hold is None:
                return False
            if hold.released_at is None:
                hold.released_at = cast("datetime", (await session.exec(select(func.clock_timestamp()))).one())
                source.delivery_evidence_revision += 1
                await session.flush()
            return True

    async def _candidate(self, session: AsyncSession, identity: DeliveryIdentity) -> CleanupCandidate | None:
        lifecycle = await lock_source_lifecycle(session, identity.source_id)
        if lifecycle is None:
            return None
        subscription, source = lifecycle
        if subscription.id != identity.subscription_id or subscription.workflow_id != identity.workflow_id:
            return None
        row = (
            await session.exec(
                select(EventDelivery)
                .where(col(EventDelivery.identity_digest) == identity.digest)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if (
            row is None
            or row.state == DeliveryState.IN_PROGRESS
            or row.resolved_at is None
            or row.delivery_identity() != identity
        ):
            return None
        now = cast("datetime", (await session.exec(select(func.clock_timestamp()))).one())
        if now - row.resolved_at < timedelta(seconds=self.retention_seconds):
            return None
        hold = (
            await session.exec(
                select(EventDeliveryRecoveryHold.token)
                .where(
                    col(EventDeliveryRecoveryHold.source_id) == identity.source_id,
                    col(EventDeliveryRecoveryHold.released_at).is_(None),
                )
                .limit(1)
            )
        ).first()
        if hold is not None:
            return None
        return CleanupCandidate(
            identity=identity, resolved_at=row.resolved_at, evidence_revision=source.delivery_evidence_revision
        )

    async def cleanup_one(self, identity: DeliveryIdentity) -> bool:
        """Remove only old terminal evidence with verified progress and unchanged protection."""
        if self.verifier is None:
            return False
        async with self.session_factory() as session, session.begin():
            candidate = await self._candidate(session, identity)
        if candidate is None:
            return False
        try:
            async with asyncio.timeout(EventDeliveryDefaults.COMMITTED_POSITION_TIMEOUT_SECONDS):
                verified = await self.verifier.is_committed_beyond(identity)
        except (CommittedPositionUnavailableError, OSError, TimeoutError, ValueError):
            # The injected adapter may be unavailable or uncertain. Never use a
            # fallback position, local fetch state, or Redis to authorize deletion.
            logger.warning("event_delivery_committed_position_unavailable")
            return False
        if verified is not True:
            return False
        async with self.session_factory() as session, session.begin():
            current = await self._candidate(session, identity)
            row = await session.get(EventDelivery, identity.digest)
            if current != candidate or row is None:
                return False
            await session.delete(row)
            return True

    async def cleanup(self, *, limit: int) -> int:
        """Bound each cleanup batch; a missing verifier performs no deletion."""
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= FieldLimits.MAX_ITEMS_PER_PAGE:
            msg = "Cleanup batch size must be between 1 and 100"
            raise ValueError(msg)
        if self.verifier is None:
            return 0
        async with self.session_factory() as session, session.begin():
            rows = (
                await session.exec(
                    select(EventDelivery)
                    .where(
                        col(EventDelivery.state) != DeliveryState.IN_PROGRESS.value,
                        col(EventDelivery.resolved_at)
                        <= func.clock_timestamp() - timedelta(seconds=self.retention_seconds),
                    )
                    .order_by(
                        col(EventDelivery.source_id), col(EventDelivery.resolved_at), col(EventDelivery.identity_digest)
                    )
                    .limit(limit)
                )
            ).all()
            identities = [row.delivery_identity() for row in rows]
        removed = 0
        for identity in identities:
            removed += await self.cleanup_one(identity)
        return removed
