"""Bounded due-delivery recovery scanner with start/tick/drain/stop lifecycle."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from syntara.core.constants import EventDeliveryDefaults, FieldLimits
from syntara.core.workers.periodic import PeriodicWorker
from syntara.eventstreams.core.handler import BlockedDelivery, RetryDelivery
from syntara.eventstreams.services.admission_service import EventAdmissionService, SchedulingResult
from syntara.eventstreams.services.deduplication_store import EventDeliveryStore

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.eventstreams.core.handler import WorkflowLauncher

logger = structlog.stdlib.get_logger(__name__)

RECOVERY_SCAN_INTERVAL_SECONDS = EventDeliveryDefaults.CLAIM_LEASE_SECONDS
RECOVERY_BATCH_LIMIT = FieldLimits.MAX_ITEMS_PER_PAGE
DRAIN_TIMEOUT_SECONDS = EventDeliveryDefaults.CLAIM_LEASE_SECONDS


class EventDeliveryRecoveryWorker:
    """Periodic recovery scanner with explicit lifecycle hooks.

    start/tick/drain/stop contract:
    - start: begin periodic scanning
    - tick: claim and recover one bounded batch of due prepared deliveries
    - drain: stop new claims and await in-flight recovery within a bound
    - stop: drain then cancel the periodic loop
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        launcher: WorkflowLauncher,
        *,
        interval_seconds: float = RECOVERY_SCAN_INTERVAL_SECONDS,
        batch_limit: int = RECOVERY_BATCH_LIMIT,
        worker_id: str = "recovery-scanner",
    ) -> None:
        """Inject session factory, Temporal adapter, and tuning parameters."""
        if not 1 <= batch_limit <= FieldLimits.MAX_ITEMS_PER_PAGE:
            msg = f"Batch limit must be between 1 and {FieldLimits.MAX_ITEMS_PER_PAGE}"
            raise ValueError(msg)
        self._session_factory = session_factory
        self._admission = EventAdmissionService(session_factory, launcher)
        self._worker_id = worker_id
        self._batch_limit = batch_limit
        self._draining = False
        self._in_flight: asyncio.Task[None] | None = None
        self._periodic = PeriodicWorker(
            name=f"event-delivery-{worker_id}",
            interval_seconds=interval_seconds,
            session_factory=session_factory,
            callback=self._tick_callback,
            coordinate=False,
        )

    def start(self) -> None:
        """Begin periodic recovery scanning."""
        self._draining = False
        self._periodic.start()
        logger.info("event_delivery_recovery_started", worker_id=self._worker_id)

    async def tick(self) -> int:
        """Claim one delivery at a time, recover immediately, repeat up to batch limit.

        Each claim's lease starts fresh just before its recovery attempt,
        so no claim waits behind slow Temporal calls with an aging lease.
        Skips if draining.
        """
        if self._draining:
            return 0
        recovered = blocked = retried = 0
        for _ in range(self._batch_limit):
            if self._draining:
                break  # type: ignore[unreachable]  # set concurrently by drain()
            result = await self._claim_and_recover_one()
            if result is None:
                break
            if isinstance(result, BlockedDelivery):
                blocked += 1
            elif isinstance(result, RetryDelivery):
                retried += 1
            else:
                recovered += 1
        total = recovered + blocked + retried
        if total:
            logger.info(
                "event_delivery_recovery_tick",
                worker_id=self._worker_id,
                total=total,
                recovered=recovered,
                blocked=blocked,
                retried=retried,
            )
        return total

    async def drain(self) -> None:
        """Stop new claims and await in-flight recovery within a bound."""
        self._draining = True
        if self._in_flight is not None and not self._in_flight.done():
            try:
                async with asyncio.timeout(DRAIN_TIMEOUT_SECONDS):
                    await self._in_flight
            except (TimeoutError, asyncio.CancelledError):
                logger.warning(
                    "event_delivery_recovery_drain_timeout",
                    worker_id=self._worker_id,
                )
        logger.info("event_delivery_recovery_drained", worker_id=self._worker_id)

    async def stop(self) -> None:
        """Drain in-flight work then stop the periodic loop."""
        await self.drain()
        await self._periodic.stop()
        logger.info("event_delivery_recovery_stopped", worker_id=self._worker_id)

    @property
    def draining(self) -> bool:
        """Whether new claims are suppressed pending shutdown."""
        return self._draining

    async def _claim_and_recover_one(self) -> SchedulingResult | None:
        """Claim a single due delivery and recover it immediately."""
        async with self._session_factory() as session, session.begin():
            claims = await EventDeliveryStore(session).claim_due(self._worker_id, limit=1, prepared_only=True)
        if not claims:
            return None
        return await self._admission.recover_claim(claims[0])

    async def _tick_callback(self, _session_factory: object) -> None:
        """PeriodicWorker callback — runs tick and tracks in-flight work."""
        task = asyncio.current_task()
        self._in_flight = task
        try:
            await self.tick()
        finally:
            if self._in_flight is task:
                self._in_flight = None
