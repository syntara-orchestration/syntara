"""Minimum-retention cleanup protected by durable partition recovery fences."""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

import structlog
from sqlalchemy import func, or_, tuple_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.constants import EventDeliveryDefaults, FieldLimits
from syntara.eventstreams.adapters.kafka_initial_position import KafkaPartitionInitialPosition
from syntara.eventstreams.core.deduplication import (
    CleanupCandidate,
    CommittedPositionUnavailableError,
    CommittedPositionVerifier,
    DeliveryIdentity,
    DeliveryState,
)
from syntara.eventstreams.models.control import EventSubscriptionRuntime
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.services.delivery_cache_policy import DeliveryEvidencePolicy
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
        policy: DeliveryEvidencePolicy | None = None,
        deployment_id: UUID | None = None,
        permits_cleanup: Callable[[], bool] | None = None,
    ) -> None:
        """Inject the committed-position port; absent verification always retains evidence."""
        if retention_seconds is not None and (
            not isinstance(retention_seconds, int) or isinstance(retention_seconds, bool) or retention_seconds <= 0
        ):
            msg = "Delivery retention must be a positive integer"
            raise ValueError(msg)
        if policy is not None and retention_seconds is not None and policy.retention_seconds != retention_seconds:
            msg = "Cleanup retention must match the shared delivery evidence policy"
            raise ValueError(msg)
        self.session_factory = session_factory
        self.verifier = verifier
        self.policy = (
            DeliveryEvidencePolicy.from_settings(retention_seconds=retention_seconds) if policy is None else policy
        )
        self.retention_seconds = self.policy.retention_seconds
        self.deployment_id = deployment_id
        self._permits_cleanup = permits_cleanup
        self._scan_lock = asyncio.Lock()
        self._scan_after: tuple[UUID, datetime, str] | None = None
        self._scan_cutoff: datetime | None = None
        self.last_scan_count = 0

    async def _candidate(self, session: AsyncSession, identity: DeliveryIdentity) -> CleanupCandidate | None:
        if (self.deployment_id is not None and identity.deployment_id != self.deployment_id) or (
            self._permits_cleanup is not None and not self._permits_cleanup()
        ):
            return None
        lifecycle = await lock_source_lifecycle(session, identity.source_id)
        if lifecycle is None:
            return None
        subscription, source = lifecycle
        if (
            subscription.id != identity.subscription_id
            or subscription.workflow_id != identity.workflow_id
            or source.generation != identity.source_generation
            or source.deployment_id != identity.deployment_id
            or source.integration_identity != identity.integration_identity
            or source.transport != identity.record.transport
        ):
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
        if now < self.policy.cleanup_after(row.resolved_at) or await self._protected(session, identity):
            return None
        return CleanupCandidate(
            identity=identity, resolved_at=row.resolved_at, evidence_revision=source.delivery_evidence_revision
        )

    async def _protected(self, session: AsyncSession, identity: DeliveryIdentity) -> bool:
        """Check recovery and content protection while the caller holds lifecycle locks."""
        hold = (
            await session.exec(
                select(KafkaPartitionInitialPosition.partition)
                .where(
                    col(KafkaPartitionInitialPosition.source_id) == identity.source_id,
                    or_(
                        col(KafkaPartitionInitialPosition.recovery_token).is_not(None),
                        col(KafkaPartitionInitialPosition.gap_detected_at).is_not(None),
                    ),
                )
                .limit(1)
            )
        ).first()
        if hold is not None:
            return True
        # Durable content errors remain protective after consumer stop.
        content_gate = (
            await session.exec(
                select(EventSubscriptionRuntime.source_id)
                .where(
                    EventSubscriptionRuntime.source_id == identity.source_id,
                    col(EventSubscriptionRuntime.permanent_content_error).is_(True),
                )
                .limit(1)
            )
        ).first()
        return content_gate is not None or (self._permits_cleanup is not None and not self._permits_cleanup())

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
            if (
                current != candidate
                or row is None
                or (self._permits_cleanup is not None and not self._permits_cleanup())
            ):
                return False
            await session.delete(row)
            return True

    async def _cleanup_page(self, limit: int) -> list[tuple[DeliveryIdentity, datetime]]:
        """Read the next bounded page, including rows previous batches could not delete.

        Freeze the eligible resolution-time boundary for one sweep. Otherwise a
        busy early source could keep adding eligible rows ahead of the cursor and
        prevent later sources from ever being visited. Deletion still rechecks
        current database time, recovery holds and broker evidence per record.
        """
        async with self.session_factory() as session, session.begin():
            if self._scan_cutoff is None:
                self._scan_cutoff = cast(
                    "datetime",
                    (
                        await session.exec(select(func.clock_timestamp() - timedelta(seconds=self.retention_seconds)))
                    ).one(),
                )
            statement = select(EventDelivery).where(
                col(EventDelivery.state) != DeliveryState.IN_PROGRESS.value,
                col(EventDelivery.resolved_at) <= self._scan_cutoff,
            )
            if self.deployment_id is not None:
                statement = statement.where(EventDelivery.deployment_id == self.deployment_id)
            if self._scan_after is not None:
                statement = statement.where(
                    tuple_(
                        col(EventDelivery.source_id), col(EventDelivery.resolved_at), col(EventDelivery.identity_digest)
                    )
                    > self._scan_after
                )
            rows = (
                await session.exec(
                    statement.order_by(
                        col(EventDelivery.source_id), col(EventDelivery.resolved_at), col(EventDelivery.identity_digest)
                    ).limit(limit)
                )
            ).all()
            # Detach values while the session is open; callers must not depend
            # on ORM attributes after its transaction has committed.
            return [(row.delivery_identity(), cast("datetime", row.resolved_at)) for row in rows]

    async def cleanup(self, *, limit: int) -> int:
        """Scan one bounded page; retain unsafe rows without starving later sources.

        A cursor is local and disposable, never permission to delete. A restart
        begins another sweep; an empty page wraps back to previously retained
        rows. Callers must keep the service instance across batches and use
        last_scan_count, not the deletion count, to detect scan progress.
        """
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= FieldLimits.MAX_ITEMS_PER_PAGE:
            msg = "Cleanup batch size must be between 1 and 100"
            raise ValueError(msg)
        async with self._scan_lock:
            self.last_scan_count = 0
            if self.verifier is None:
                return 0
            rows = await self._cleanup_page(limit)
            if not rows:
                self._scan_after = None
                self._scan_cutoff = None
                return 0
            removed = 0
            for identity, resolved_at in rows:
                # Advance even when verification retains the row or fails. It
                # will be revisited next sweep; no evidence is erased by a skip.
                try:
                    removed += await self.cleanup_one(identity)
                finally:
                    self._scan_after = (identity.source_id, resolved_at, identity.digest)
                    self.last_scan_count += 1
            return removed
