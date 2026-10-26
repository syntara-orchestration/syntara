"""Short PostgreSQL placement transactions; no Kafka, Temporal or fleet manager loop."""

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import delete, func, or_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import get_settings
from syntara.core.constants import EventPlacementDefaults
from syntara.core.exceptions import SafeValueError
from syntara.core.models.installation import Installation
from syntara.eventstreams.core.placement import (
    PlacementAuthority,
    PlacementLost,
    PlacementUncertainError,
    SubscriptionPlacementLease,
    WorkerIdentity,
    WorkerMembership,
)
from syntara.eventstreams.models.consumer_worker import EventConsumerWorker
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.workflows.models.workflow import Workflow


class SubscriptionPlacementService:
    """One provider per process, shared by all local subscription supervisors.

    The process manager supplies heartbeat/renewal scheduling and fair-share
    limits. Local mutations serialize here. Guards reserve construction through
    confirmed stop, including lease loss and uncertain database commits.
    """

    def __init__(
        self,
        session_factory: Callable[..., AsyncSession],
        worker: WorkerIdentity,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Inject a process-owned factory rather than a request-scoped session or user."""
        self.worker = worker
        self._sessions = session_factory
        self._clock = clock
        self._settings = get_settings()
        self._lock = asyncio.Lock()
        self._authorities: dict[UUID, PlacementAuthority] = {}
        self._pending: set[UUID] = set()
        self._draining = False

    @classmethod
    async def create(cls, session_factory: Callable[..., AsyncSession]) -> "SubscriptionPlacementService":
        """Read the persisted namespace; generate only the process incarnation UUID."""
        async with session_factory() as session, session.begin():
            deployment_id = (await session.exec(select(Installation.id))).one()
        return cls(session_factory, WorkerIdentity(deployment_id=deployment_id))

    def authority(self, subscription_id: UUID) -> PlacementAuthority:
        """Return the same guard for claim, renewal and every local supervisor."""
        if subscription_id not in self._authorities:
            self._authorities[subscription_id] = PlacementAuthority(self.worker, subscription_id, clock=self._clock)
        return self._authorities[subscription_id]

    @property
    def pending_reconciliation(self) -> frozenset[UUID]:
        """Manager hook, including candidate IDs from an uncertain batch commit."""
        return frozenset(self._pending)

    def distrust(self) -> None:
        """Revoke database trust until explicit reconciliation restores authority."""
        for subscription_id, authority in self._authorities.items():
            if authority.lease is not None:
                self._pending.add(subscription_id)
            authority.invalidate()

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[AsyncSession]:
        try:
            async with self._sessions() as session:
                try:
                    async with session.begin():
                        yield session
                except BaseException:
                    # Invalidate before potentially slow rollback/session close.
                    self.distrust()
                    raise
        except (SQLAlchemyError, OSError, TimeoutError) as exc:
            self.distrust()
            msg = "Placement database outcome requires reconciliation"
            raise PlacementUncertainError(msg) from exc
        except BaseException:
            # Cancellation may arrive after the server committed but before its
            # acknowledgement. Never let that leave locally usable authority.
            self.distrust()
            raise

    async def _deployment(self, session: AsyncSession) -> None:
        deployment_id = (await session.exec(select(Installation.id))).one_or_none()
        if deployment_id != self.worker.deployment_id:
            msg = "Worker must use the persisted deployment UUID"
            raise SafeValueError(msg)

    def _check_worker(self, worker: WorkerIdentity) -> None:
        if worker != self.worker:
            msg = "Placement provider belongs to a different worker"
            raise SafeValueError(msg)

    @staticmethod
    async def _now(session: AsyncSession) -> datetime:
        return cast("datetime", (await session.exec(select(func.clock_timestamp()))).one())

    async def _member(self, session: AsyncSession, *, allow_draining: bool) -> EventConsumerWorker | None:
        await self._deployment(session)
        member = (
            await session.exec(
                select(EventConsumerWorker)
                .where(col(EventConsumerWorker.worker_id) == self.worker.worker_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        now = await self._now(session)
        if (
            member is None
            or member.deployment_id != self.worker.deployment_id
            or member.heartbeat_until <= now
            or (member.draining and not allow_draining)
        ):
            return None
        return member

    async def heartbeat_worker(self, worker: WorkerIdentity, *, draining: bool) -> WorkerMembership:
        """Register/renew membership in database time; draining still permits owned renewals."""
        self._check_worker(worker)
        # Draining is terminal for a process incarnation. A queued periodic
        # heartbeat must not undo a newer shutdown request.
        self._draining = self._draining or draining
        async with self._lock:
            async with self._transaction() as session:
                await self._deployment(session)
                now = await self._now(session)
                await session.execute(
                    insert(EventConsumerWorker)
                    .values(
                        worker_id=worker.worker_id,
                        deployment_id=worker.deployment_id,
                        heartbeat_until=now + timedelta(seconds=self._settings.event_worker_liveness_seconds),
                        draining=self._draining,
                    )
                    .on_conflict_do_nothing(index_elements=["worker_id"])
                )
                member = (
                    await session.exec(
                        select(EventConsumerWorker)
                        .where(col(EventConsumerWorker.worker_id) == worker.worker_id)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                ).one()
                if member.deployment_id != worker.deployment_id:
                    msg = "Worker incarnation belongs to a different deployment"
                    raise SafeValueError(msg)
                now = await self._now(session)
                member.heartbeat_until = now + timedelta(seconds=self._settings.event_worker_liveness_seconds)
                self._draining = self._draining or member.draining
                member.draining = self._draining
                await session.flush()
                result = WorkerMembership(
                    worker=worker, heartbeat_until=member.heartbeat_until, draining=member.draining
                )
            return result  # noqa: RET504 - return only after commit and session close.

    async def list_live_workers(self) -> list[WorkerMembership]:
        """Discover only this deployment's live non-draining process incarnations."""
        async with self._transaction() as session:
            await self._deployment(session)
            rows = (
                await session.exec(
                    select(EventConsumerWorker)
                    .where(
                        col(EventConsumerWorker.deployment_id) == self.worker.deployment_id,
                        col(EventConsumerWorker.draining).is_(False),
                        col(EventConsumerWorker.heartbeat_until) > func.clock_timestamp(),
                    )
                    .order_by(col(EventConsumerWorker.worker_id))
                )
            ).all()
            result = [
                WorkerMembership(
                    worker=WorkerIdentity(deployment_id=row.deployment_id, worker_id=row.worker_id),
                    heartbeat_until=row.heartbeat_until,
                    draining=row.draining,
                )
                for row in rows
            ]
        return result  # noqa: RET504 - return only after commit and session close.

    @staticmethod
    def _bound(limit: int) -> None:
        if not 1 <= limit <= EventPlacementDefaults.MAX_CLAIM_BATCH:
            msg = "Placement batch size is outside its bounded range"
            raise SafeValueError(msg)

    async def claim_subscriptions(self, worker: WorkerIdentity, *, limit: int) -> list[SubscriptionPlacementLease]:
        """Claim active candidates with workflow -> subscription -> source locks.

        Lock the membership row first so stale pruning cannot race a new lease.
        Workflow locks use SKIP LOCKED before subscription locks, matching the
        publication/lifecycle order. Contended rows may underfill the batch.
        """
        self._check_worker(worker)
        self._bound(limit)
        async with self._lock:
            if self._draining:
                return []
            started = self._clock()
            leases: list[SubscriptionPlacementLease] = []
            async with self._transaction() as session:
                member = await self._member(session, allow_draining=False)
                if member is None:
                    return []
                excluded = self._pending | {
                    key for key, authority in self._authorities.items() if authority.local_in_use
                }
                statement = (
                    select(Workflow, EventSubscription.id)
                    .join(EventSubscription, col(EventSubscription.workflow_id) == Workflow.id)
                    .join(
                        EventSubscriptionSource,
                        (col(EventSubscriptionSource.subscription_id) == EventSubscription.id)
                        & (col(EventSubscriptionSource.generation) == EventSubscription.active_source_generation),
                    )
                    .where(
                        col(Workflow.is_enabled).is_(True),
                        col(Workflow.published_version_id) == EventSubscription.published_version_id,
                        col(EventSubscription.desired_enabled).is_(True),
                        col(EventSubscription.paused).is_(False),
                        col(EventSubscription.retired).is_(False),
                        col(EventSubscriptionSource.retired_at).is_(None),
                        col(EventSubscriptionSource.deployment_id) == worker.deployment_id,
                        or_(
                            col(EventSubscription.assigned_worker_id).is_(None),
                            col(EventSubscription.assignment_lease_until) <= func.clock_timestamp(),
                        ),
                        col(EventSubscription.id).not_in(excluded),
                    )
                    .order_by(col(Workflow.id), col(EventSubscription.id))
                    .limit(limit)
                    .with_for_update(of=Workflow, skip_locked=True)
                    .execution_options(populate_existing=True)
                )
                candidates = (await session.exec(statement)).all()
                for workflow, subscription_id in candidates:
                    lease = await self._claim_locked(session, workflow, subscription_id, member)
                    if lease is not None:
                        leases.append(lease)
                await session.flush()
            # Only confirmed commits publish authority. Errors leave candidates
            # pending and excluded until a fresh-session reconciliation.
            usable: list[SubscriptionPlacementLease] = []
            for lease in leases:
                self._pending.discard(lease.subscription_id)
                if self.authority(lease.subscription_id).confirm(lease, request_started=started):
                    usable.append(lease)
                else:
                    self._pending.add(lease.subscription_id)
            return usable

    async def _claim_locked(
        self, session: AsyncSession, workflow: Workflow, subscription_id: UUID, member: EventConsumerWorker
    ) -> SubscriptionPlacementLease | None:
        subscription = (
            await session.exec(
                select(EventSubscription)
                .where(col(EventSubscription.id) == subscription_id)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if subscription is None:
            return None
        source = (
            await session.exec(
                select(EventSubscriptionSource)
                .where(
                    col(EventSubscriptionSource.subscription_id) == subscription_id,
                    col(EventSubscriptionSource.generation) == subscription.active_source_generation,
                )
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        now = await self._now(session)
        if (
            self.authority(subscription_id).local_in_use
            or self._draining
            or member.heartbeat_until <= now
            or member.draining
            or source is None
            or source.deployment_id != self.worker.deployment_id
            or source.retired_at is not None
            or subscription.workflow_id != workflow.id
            or not workflow.is_enabled
            or workflow.published_version_id != subscription.published_version_id
            or not subscription.desired_enabled
            or subscription.paused
            or subscription.retired
            or (subscription.assignment_lease_until is not None and subscription.assignment_lease_until > now)
        ):
            return None
        self._pending.add(subscription_id)
        subscription.assigned_worker_id = self.worker.worker_id
        subscription.assignment_lease_until = now + timedelta(seconds=self._settings.event_subscription_lease_seconds)
        return self._lease(subscription_id, now, subscription.assignment_lease_until)

    def _lease(self, subscription_id: UUID, now: datetime, expiry: datetime) -> SubscriptionPlacementLease:
        return SubscriptionPlacementLease(
            subscription_id=subscription_id, owner=self.worker, confirmed_at=now, expires_at=expiry
        )

    def _source_in_deployment(self, subscription_id: UUID) -> ColumnElement[bool]:
        return (
            select(EventSubscriptionSource.id)
            .where(
                col(EventSubscriptionSource.subscription_id) == subscription_id,
                col(EventSubscriptionSource.generation) == EventSubscription.active_source_generation,
                col(EventSubscriptionSource.deployment_id) == self.worker.deployment_id,
            )
            .exists()
        )

    async def renew_placement(self, lease: SubscriptionPlacementLease) -> SubscriptionPlacementLease | PlacementLost:
        """Renew only the owner-matching unexpired row, without reviving expired ownership."""
        key = lease.subscription_id
        if lease.owner != self.worker:
            msg = "Placement lease belongs to a different worker"
            raise SafeValueError(msg)
        async with self._lock:
            authority = self.authority(key)
            if key in self._pending:
                authority.invalidate()
                return PlacementLost(subscription_id=key)
            current = authority.lease
            if current is not None and current.expires_at != lease.expires_at:
                if authority.is_current():
                    return current  # Stale request; do not extend or revoke the confirmed newer lease.
                authority.invalidate()
                self._pending.add(key)
                return PlacementLost(subscription_id=key)
            started = self._clock()
            renewed = None
            async with self._transaction() as session:
                member = await self._member(session, allow_draining=True)
                if member is not None:
                    # Acquire the row before sampling expiry. An UPDATE whose
                    # predicate was evaluated before a lock wait is insufficient
                    # to establish that a renewal is still timely afterward.
                    await session.exec(
                        select(EventSubscription.id).where(col(EventSubscription.id) == key).with_for_update()
                    )
                    now = await self._now(session)
                    if member.heartbeat_until > now:
                        self._pending.add(key)
                        result = await session.execute(
                            update(EventSubscription)
                            .where(
                                col(EventSubscription.id) == key,
                                col(EventSubscription.assigned_worker_id) == self.worker.worker_id,
                                col(EventSubscription.assignment_lease_until) == lease.expires_at,
                                col(EventSubscription.assignment_lease_until) > func.clock_timestamp(),
                                self._source_in_deployment(key),
                            )
                            .values(
                                assignment_lease_until=now
                                + timedelta(seconds=self._settings.event_subscription_lease_seconds)
                            )
                            .returning(col(EventSubscription.assignment_lease_until))
                            .execution_options(synchronize_session=False)
                        )
                        expiry = result.scalar_one_or_none()
                        if expiry is not None:
                            renewed = self._lease(key, now, expiry)
            self._pending.discard(key)
            if renewed is None:
                authority.invalidate()
                return PlacementLost(subscription_id=key)
            if authority.confirm(renewed, request_started=started):
                return renewed
            authority.invalidate()
            self._pending.add(key)
            return PlacementLost(subscription_id=key)

    async def reconcile_placement(self, subscription_id: UUID) -> SubscriptionPlacementLease | PlacementLost:
        """Resolve uncertain commit with a fresh database read; never infer success from a timeout."""
        async with self._lock:
            started = self._clock()
            lease = None
            async with self._transaction() as session:
                member = await self._member(session, allow_draining=True)
                if member is not None:
                    # A row lock serializes with takeover; no network I/O is
                    # performed here. There is no workflow lock after this lock.
                    subscription = (
                        await session.exec(
                            select(EventSubscription)
                            .where(
                                col(EventSubscription.id) == subscription_id,
                                self._source_in_deployment(subscription_id),
                            )
                            .with_for_update()
                            .execution_options(populate_existing=True)
                        )
                    ).one_or_none()
                    now = await self._now(session)
                    if (
                        subscription is not None
                        and subscription.assigned_worker_id == self.worker.worker_id
                        and subscription.assignment_lease_until is not None
                        and subscription.assignment_lease_until > now
                    ):
                        lease = self._lease(subscription_id, now, subscription.assignment_lease_until)
            self._pending.discard(subscription_id)
            authority = self.authority(subscription_id)
            if lease is not None and authority.confirm(lease, request_started=started):
                return lease
            if lease is not None:
                self._pending.add(subscription_id)
            authority.invalidate()
            return PlacementLost(subscription_id=subscription_id)

    async def release_placement(self, lease: SubscriptionPlacementLease) -> bool:
        """Release only this process's lease, after confirmed local stop; retry uncertainty via reconciliation."""
        key = lease.subscription_id
        if lease.owner != self.worker:
            return False
        async with self._lock:
            authority = self.authority(key)
            if authority.local_in_use or key in self._pending:
                return False
            if authority.lease is not None and authority.lease.expires_at != lease.expires_at:
                return False  # A delayed release cannot clear a later renewal/reacquisition.
            authority.invalidate()
            async with self._transaction() as session:
                await self._deployment(session)
                self._pending.add(key)
                result = await session.execute(
                    update(EventSubscription)
                    .where(
                        col(EventSubscription.id) == key,
                        col(EventSubscription.assigned_worker_id) == self.worker.worker_id,
                        col(EventSubscription.assignment_lease_until) == lease.expires_at,
                        self._source_in_deployment(key),
                    )
                    .values(assigned_worker_id=None, assignment_lease_until=None)
                    .returning(col(EventSubscription.id))
                    .execution_options(synchronize_session=False)
                )
                released = result.scalar_one_or_none() is not None
            self._pending.discard(key)
            return released

    async def prune_stale_workers(self, *, limit: int = EventPlacementDefaults.MAX_CLAIM_BATCH) -> int:
        """Prune stale membership only when no dependent unexpired placement remains."""
        self._bound(limit)
        async with self._lock, self._transaction() as session:
            await self._deployment(session)
            members = (
                await session.exec(
                    select(EventConsumerWorker)
                    .where(
                        col(EventConsumerWorker.deployment_id) == self.worker.deployment_id,
                        col(EventConsumerWorker.heartbeat_until) <= func.clock_timestamp(),
                    )
                    .order_by(col(EventConsumerWorker.worker_id))
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            removed = 0
            for member in members:
                dependency = (
                    select(EventSubscription.id)
                    .where(
                        col(EventSubscription.assigned_worker_id) == member.worker_id,
                        col(EventSubscription.assignment_lease_until) > func.clock_timestamp(),
                    )
                    .exists()
                )
                result = await session.execute(
                    delete(EventConsumerWorker)
                    .where(col(EventConsumerWorker.worker_id) == member.worker_id, ~dependency)
                    .returning(col(EventConsumerWorker.worker_id))
                )
                removed += int(result.scalar_one_or_none() is not None)
        return removed
