"""PostgreSQL-backed authoritative queue and fencing operations for the PoCs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .contracts import Claim, Submission, SubmitTask
from .models import POCAttempt, POCExecution, POCPool, POCReservation, POCWakeOutbox, as_utc, utc_now


class IdempotencyConflictError(ValueError):
    """A queue/idempotency key was reused for a different task request."""


class AsyncExecutionStore:
    """Store operations whose transactions establish task ownership.

    Notification transports deliberately do not appear here. A transport only
    observes :class:`POCWakeOutbox` after this store transaction commits.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        lease_duration: timedelta = timedelta(seconds=10),
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._lease_duration = lease_duration
        self._now = now

    @staticmethod
    def _request_hash(request: SubmitTask) -> str:
        canonical = json.dumps(
            request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _wake_for(execution: POCExecution, now: datetime) -> POCWakeOutbox:
        return POCWakeOutbox(
            queue=execution.queue,
            execution_id=execution.id,
            not_before=execution.next_attempt_at,
            next_publication_at=max(now, execution.next_attempt_at),
        )

    async def enqueue(self, request: SubmitTask) -> Submission:
        """Atomically persist a task and its first scheduler wake-up intent."""
        request_hash = self._request_hash(request)
        now = self._now()
        next_attempt_at = request.not_before or now
        async with self._session_factory() as session:
            try:
                async with session.begin():
                    existing = await session.exec(
                        select(POCExecution).where(
                            POCExecution.queue == request.queue,
                            POCExecution.idempotency_key == request.idempotency_key,
                        )
                    )
                    execution = existing.one_or_none()
                    if execution is not None:
                        if execution.request_hash != request_hash:
                            raise IdempotencyConflictError("idempotency key was reused with a different request")
                        pending = await session.exec(
                            select(POCWakeOutbox)
                            .where(
                                POCWakeOutbox.execution_id == execution.id,
                                POCWakeOutbox.publication_state == "pending",
                            )
                            .order_by(POCWakeOutbox.next_publication_at)
                        )
                        wake = pending.first()
                        if wake is not None:
                            wake.next_publication_at = min(wake.next_publication_at, now)
                        return Submission(
                            execution_id=execution.id,
                            state=execution.state,
                            created=False,
                            wake_event_id=wake.event_id if wake else None,
                        )

                    pool = await session.exec(select(POCPool).where(POCPool.queue == request.queue))
                    if pool.one_or_none() is None:
                        session.add(POCPool(queue=request.queue))
                    execution = POCExecution(
                        queue=request.queue,
                        idempotency_key=request.idempotency_key,
                        request_hash=request_hash,
                        task=request.task,
                        next_attempt_at=next_attempt_at,
                        deadline=request.deadline,
                    )
                    session.add(execution)
                    await session.flush()
                    wake = self._wake_for(execution, now)
                    session.add(wake)
                    return Submission(execution_id=execution.id, state=execution.state, created=True, wake_event_id=wake.event_id)
            except IntegrityError:
                # Another submitter won the unique-key race. Read its result in
                # a fresh transaction and retain the normal idempotency contract.
                await session.rollback()

        async with self._session_factory() as session:
            existing = await session.exec(
                select(POCExecution).where(
                    POCExecution.queue == request.queue,
                    POCExecution.idempotency_key == request.idempotency_key,
                )
            )
            execution = existing.one()
            if execution.request_hash != request_hash:
                raise IdempotencyConflictError("idempotency key was reused with a different request")
            return Submission(execution_id=execution.id, state=execution.state, created=False)

    async def claim_ready(self, queue: str, owner: str, limit: int) -> list[Claim]:
        """Claim up to ``limit`` due executions using persisted fencing tokens."""
        if limit <= 0:
            return []
        now = self._now()
        lease_expires_at = now + self._lease_duration
        try:
            async with self._session_factory() as session, session.begin():
                pool_result = await session.exec(
                select(POCPool).where(POCPool.queue == queue).with_for_update()
            )
                pool = pool_result.one_or_none()
                if pool is None:
                    return []
                available = limit if pool.capacity_limit is None else max(0, pool.capacity_limit - pool.reserved_count)
                if available == 0:
                    return []
                candidates = await session.exec(
                select(POCExecution)
                .where(
                    POCExecution.queue == queue,
                    POCExecution.state == "queued",
                    POCExecution.next_attempt_at <= now,
                    or_(POCExecution.deadline.is_(None), POCExecution.deadline > now),
                )
                .order_by(POCExecution.next_attempt_at, POCExecution.created_at, POCExecution.id)
                .limit(min(limit, available))
                .with_for_update(skip_locked=True)
            )
                executions = list(candidates)
                claims: list[Claim] = []
                for execution in executions:
                    token = execution.current_fencing_token + 1
                    attempt = POCAttempt(
                    execution_id=execution.id,
                    fencing_token=token,
                    owner_id=owner,
                    lease_expires_at=lease_expires_at,
                )
                    execution.state = "claimed"
                    execution.current_owner_id = owner
                    execution.current_attempt_id = attempt.id
                    execution.current_fencing_token = token
                    execution.lease_expires_at = lease_expires_at
                    execution.transition_reason = None
                    session.add(attempt)
                    if pool.capacity_limit is not None:
                        pool.reserved_count += 1
                        session.add(POCReservation(attempt_id=attempt.id, pool_id=pool.id))
                    claims.append(
                    Claim(
                        execution_id=execution.id,
                        attempt_id=attempt.id,
                        queue=queue,
                        fencing_token=token,
                        owner_id=owner,
                        lease_expires_at=lease_expires_at,
                    )
                    )
                return claims
        except IntegrityError:
            # SQLite ignores SELECT .. FOR UPDATE and is used only for the
            # fast harness. PostgreSQL's SKIP LOCKED prevents this race; the
            # uniqueness fence makes the SQLite fallback safe as well.
            return []

    async def renew(self, claim: Claim) -> bool:
        """Extend a lease only when this still is the current valid owner."""
        now = self._now()
        async with self._session_factory() as session, session.begin():
            execution = await session.get(POCExecution, claim.execution_id, with_for_update=True)
            if not self._is_current_claim(execution, claim, now):
                return False
            assert execution is not None
            lease_expires_at = now + self._lease_duration
            attempt = await session.get(POCAttempt, claim.attempt_id, with_for_update=True)
            if attempt is None or attempt.finished_at is not None:
                return False
            execution.lease_expires_at = lease_expires_at
            attempt.lease_expires_at = lease_expires_at
            return True

    async def complete(self, claim: Claim, result: dict[str, Any]) -> bool:
        """Complete a valid claim, atomically releasing its pool reservation."""
        now = self._now()
        async with self._session_factory() as session, session.begin():
            execution = await session.get(POCExecution, claim.execution_id, with_for_update=True)
            if not self._is_current_claim(execution, claim, now):
                return False
            assert execution is not None
            attempt = await session.get(POCAttempt, claim.attempt_id, with_for_update=True)
            if attempt is None or attempt.finished_at is not None:
                return False
            attempt.finished_at = now
            attempt.terminal_reason = "completed"
            execution.state = "succeeded"
            execution.result = result
            execution.transition_reason = "completed"
            execution.current_owner_id = None
            execution.current_attempt_id = None
            execution.lease_expires_at = None
            await self._release_reservation(session, attempt.id, now)
            return True

    async def recover_expired(self, queue: str, limit: int) -> int:
        """Requeue expired claims and create fresh durable wake intents."""
        if limit <= 0:
            return 0
        now = self._now()
        async with self._session_factory() as session, session.begin():
            expired = await session.exec(
                select(POCExecution)
                .where(
                    POCExecution.queue == queue,
                    POCExecution.state == "claimed",
                    POCExecution.lease_expires_at.is_not(None),
                    POCExecution.lease_expires_at <= now,
                )
                .order_by(POCExecution.lease_expires_at, POCExecution.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            executions = list(expired)
            for execution in executions:
                if execution.current_attempt_id is not None:
                    attempt = await session.get(POCAttempt, execution.current_attempt_id, with_for_update=True)
                    if attempt is not None and attempt.finished_at is None:
                        attempt.finished_at = now
                        attempt.terminal_reason = "lease_expired"
                        await self._release_reservation(session, attempt.id, now)
                execution.state = "queued"
                execution.next_attempt_at = now
                execution.current_owner_id = None
                execution.current_attempt_id = None
                execution.lease_expires_at = None
                execution.transition_reason = "lease_expired"
                session.add(self._wake_for(execution, now))
            return len(executions)

    async def eligible_queues(self, limit: int) -> list[str]:
        """Return distinct queues with currently due unclaimed work.

        This is used only by the explicitly enabled recovery sweep.  Normal
        low-latency scheduling is driven by the transport hint/outbox path.
        """
        if limit <= 0:
            return []
        now = self._now()
        async with self._session_factory() as session:
            result = await session.exec(
                select(POCExecution.queue)
                .where(
                    POCExecution.state == "queued",
                    POCExecution.next_attempt_at <= now,
                    or_(POCExecution.deadline.is_(None), POCExecution.deadline > now),
                )
                .distinct()
                .order_by(POCExecution.queue)
                .limit(limit)
            )
            return list(result)

    async def set_capacity(self, queue: str, capacity_limit: int | None) -> UUID | None:
        """Set sample pool capacity and wake schedulers when it increases."""
        if capacity_limit is not None and capacity_limit < 0:
            raise ValueError("capacity_limit must be non-negative")
        now = self._now()
        async with self._session_factory() as session, session.begin():
            result = await session.exec(select(POCPool).where(POCPool.queue == queue).with_for_update())
            pool = result.one_or_none()
            if pool is None:
                raise KeyError(f"unknown queue: {queue}")
            old_available = float("inf") if pool.capacity_limit is None else pool.capacity_limit - pool.reserved_count
            pool.capacity_limit = capacity_limit
            new_available = float("inf") if capacity_limit is None else capacity_limit - pool.reserved_count
            if new_available <= old_available:
                return None
            wake = POCWakeOutbox(queue=queue, not_before=now, next_publication_at=now)
            session.add(wake)
            return wake.event_id

    async def due_outbox(self, owner: str, limit: int, lease_duration: timedelta = timedelta(seconds=10)) -> list[POCWakeOutbox]:
        """Lease due publication intents without holding a transaction during I/O."""
        if limit <= 0:
            return []
        now = self._now()
        async with self._session_factory() as session, session.begin():
            result = await session.exec(
                select(POCWakeOutbox)
                .where(
                    POCWakeOutbox.not_before <= now,
                    POCWakeOutbox.next_publication_at <= now,
                    POCWakeOutbox.publication_state == "pending",
                    or_(
                        POCWakeOutbox.publication_lease_expires_at.is_(None),
                        POCWakeOutbox.publication_lease_expires_at <= now,
                    ),
                )
                .order_by(POCWakeOutbox.next_publication_at, POCWakeOutbox.event_id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            events = list(result)
            for event in events:
                event.publication_lease_owner = owner
                event.publication_lease_token += 1
                event.publication_lease_expires_at = now + lease_duration
                event.tries += 1
            return events

    async def mark_outbox_accepted(self, event_id: UUID, owner: str, token: int) -> bool:
        now = self._now()
        async with self._session_factory() as session, session.begin():
            event = await session.get(POCWakeOutbox, event_id, with_for_update=True)
            if event is None or event.publication_state != "pending":
                return False
            if event.publication_lease_owner != owner or event.publication_lease_token != token:
                return False
            event.publication_state = "accepted"
            event.accepted_at = now
            event.publication_lease_expires_at = None
            event.last_safe_error = None
            return True

    async def record_publish_failure(
        self, event_id: UUID, owner: str, token: int, error: str, retry_at: datetime
    ) -> bool:
        async with self._session_factory() as session, session.begin():
            event = await session.get(POCWakeOutbox, event_id, with_for_update=True)
            if event is None or event.publication_state != "pending":
                return False
            if event.publication_lease_owner != owner or event.publication_lease_token != token:
                return False
            event.publication_lease_expires_at = None
            event.next_publication_at = retry_at
            event.last_safe_error = error[:2048]
            return True

    @staticmethod
    def _is_current_claim(execution: POCExecution | None, claim: Claim, now: datetime) -> bool:
        return bool(
            execution
            and execution.state == "claimed"
            and execution.current_attempt_id == claim.attempt_id
            and execution.current_owner_id == claim.owner_id
            and execution.current_fencing_token == claim.fencing_token
            and execution.lease_expires_at is not None
            and as_utc(execution.lease_expires_at) > now
        )

    @staticmethod
    async def _release_reservation(session: AsyncSession, attempt_id: UUID, now: datetime) -> None:
        result = await session.exec(
            select(POCReservation)
            .where(POCReservation.attempt_id == attempt_id, POCReservation.released_at.is_(None))
            .with_for_update()
        )
        reservation = result.one_or_none()
        if reservation is None:
            return
        pool = await session.get(POCPool, reservation.pool_id, with_for_update=True)
        if pool is not None:
            pool.reserved_count = max(0, pool.reserved_count - 1)
        reservation.released_at = now
