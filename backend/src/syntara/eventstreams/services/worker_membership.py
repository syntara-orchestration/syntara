"""Process scheduling of completed membership/placement ports; no broker calls."""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from uuid import UUID

import structlog
from sqlalchemy.exc import SQLAlchemyError

from syntara.core.config.base import get_settings
from syntara.core.constants import EventWorkerDefaults
from syntara.eventstreams.core.placement import PlacementLost, PlacementUncertainError, SubscriptionPlacementLease
from syntara.eventstreams.services.placement_service import SubscriptionPlacementService
from syntara.eventstreams.services.worker_resources import EventWorkerResources

logger = structlog.stdlib.get_logger(__name__)
PLACEMENT_ERRORS = (SQLAlchemyError, OSError, TimeoutError, PlacementUncertainError)


class EventWorkerMembership:
    """Keep database ownership maintenance independent of reconciliation and Kafka."""

    def __init__(
        self,
        placement: SubscriptionPlacementService,
        resources: EventWorkerResources,
        owned: set[UUID],
        lost: Callable[[UUID], None],
        changed: Callable[[], None],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Share process ownership and serialize local lease mutations through one port."""
        self.placement = placement
        self._resources = resources
        self._owned = owned
        self._lost = lost
        self._changed = changed
        self._clock = clock
        self._settings = get_settings()
        self._operations = asyncio.Lock()
        self._membership_changed = asyncio.Event()
        self._deadline = 0.0
        self._draining = False
        self.task: asyncio.Task[None] | None = None

    @property
    def trusted(self) -> bool:
        """Check the last confirmed membership budget without waiting for the watchdog."""
        return self._clock() < self._deadline

    def _check_trust(self) -> None:
        if not self.trusted:
            msg = "Worker membership is not trusted for placement work"
            raise PlacementUncertainError(msg)

    async def call[T](self, operation: Callable[[], Awaitable[T]], *, require_trusted: bool = True) -> T:
        """Bound database I/O and keep each call outside all client startup/drain waits."""
        try:
            async with self._resources.placement, self._operations:
                if require_trusted:
                    self._check_trust()
                async with asyncio.timeout(EventWorkerDefaults.PLACEMENT_TIMEOUT_SECONDS):
                    return await operation()
        except BaseException:
            self._resources.database_failed()
            self.placement.distrust()
            raise

    async def register(self) -> None:
        """Commit process registration before any placement reconciliation or claim."""
        await self._heartbeat()
        if self.task is None:
            self.task = asyncio.create_task(self._run(), name="event-worker-membership")

    async def _heartbeat(self) -> None:
        started = self._clock()
        gate = self._resources.gate
        generation = gate.generation if gate is not None else 0
        membership = await self.call(
            lambda: self.placement.heartbeat_worker(self.placement.worker, draining=self._draining),
            require_trusted=False,
        )
        if membership.worker != self.placement.worker or (membership.draining and not self._draining):
            msg = "Worker membership is not available for this process"
            raise RuntimeError(msg)
        # heartbeat_worker writes database-now + configured liveness. Starting
        # the local budget BEFORE I/O can only shorten that confirmed lifetime.
        self._deadline = started + self._settings.event_worker_liveness_seconds
        if self._clock() >= self._deadline:
            self.placement.distrust()
            msg = "Worker membership acknowledgement exceeded its confirmed lifetime"
            raise RuntimeError(msg)
        if gate is not None:
            gate.membership_confirmed(self._deadline, generation=generation)
        self._membership_changed.set()
        if not self._resources.scheduling_open:
            self._changed()

    async def _renew_one(self, key: UUID) -> None:
        was_pending = key in self.placement.pending_reconciliation

        async def renew() -> SubscriptionPlacementLease | PlacementLost | None:
            if key not in self._owned:
                return None
            authority = self.placement.authority(key)
            if key in self.placement.pending_reconciliation:
                return await self.placement.reconcile_placement(key)
            lease = authority.lease
            if lease is None or not authority.is_current():
                authority.invalidate()
                return PlacementLost(subscription_id=key)
            return await self.placement.renew_placement(lease)

        result = await self.call(renew)
        if isinstance(result, PlacementLost):
            self.placement.authority(key).invalidate()
            self._lost(key)
        elif result is not None and was_pending:
            self._changed()

    async def renew_owned(self) -> None:
        """Use a fixed task bound and fresh provider sessions for owned leases."""
        keys = iter(tuple(self._owned))

        async def renew() -> None:
            for key in keys:
                try:
                    await self._renew_one(key)
                except PLACEMENT_ERRORS:
                    self._lost(key)
                    logger.warning("event_worker_placement_renewal_unavailable", subscription_id=str(key))

        tasks = [asyncio.create_task(renew()) for _ in range(EventWorkerDefaults.PLACEMENT_CONCURRENCY)]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(
                self._settings.event_worker_heartbeat_interval_seconds * random.uniform(0.9, 1.1)  # noqa: S311
            )
            try:
                await self._heartbeat()
            except PLACEMENT_ERRORS:
                logger.warning("event_worker_membership_unavailable")

    async def _renewal_loop(self) -> None:
        while True:
            await asyncio.sleep(
                self._settings.event_worker_heartbeat_interval_seconds * random.uniform(0.9, 1.1)  # noqa: S311
            )
            await self.renew_owned()

    async def _watch_deadline(self) -> None:
        while True:
            self._membership_changed.clear()
            remaining = self._deadline - self._clock()
            if remaining <= 0:
                self.placement.distrust()
                self._resources.database_failed()
                msg = "Worker membership deadline is no longer trustworthy"
                raise RuntimeError(msg)
            try:
                async with asyncio.timeout(remaining):
                    await self._membership_changed.wait()
            except TimeoutError:
                continue

    @staticmethod
    async def _monitor_tasks(tasks: set[asyncio.Task[None]]) -> None:
        """Raise if any ownership maintenance task exits or fails."""
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            await task
        msg = "Worker membership maintenance exited unexpectedly"
        raise RuntimeError(msg)

    async def _run(self) -> None:
        tasks = {
            asyncio.create_task(self._heartbeat_loop(), name="event-worker-heartbeat"),
            asyncio.create_task(self._renewal_loop(), name="event-worker-renewal"),
            asyncio.create_task(self._watch_deadline(), name="event-worker-membership-deadline"),
        }
        try:
            await self._monitor_tasks(tasks)
        except Exception:
            self.placement.distrust()
            self._resources.database_failed()
            raise
        finally:
            for task in tasks:
                task.cancel()
            _, pending = await asyncio.wait(tasks, timeout=EventWorkerDefaults.HINT_TIMEOUT_SECONDS)
            for task in tasks:
                if task in pending:
                    task.add_done_callback(self._consume_result)
                else:
                    self._consume_result(task)

    async def mark_draining(self) -> None:
        """Exclude this process from targets while still renewing its owned leases."""
        self._draining = True
        try:
            await self._heartbeat()
        except PLACEMENT_ERRORS:
            logger.warning("event_worker_draining_membership_retry")
            await self._heartbeat()

    async def stop(self) -> None:
        """Stop membership only after consumer drain/release cleanup has finished."""
        if self.task is not None:
            if not self.task.done() and not self.task.cancelling():
                self.task.cancel()
            _, pending = await asyncio.wait({self.task}, timeout=EventWorkerDefaults.HINT_TIMEOUT_SECONDS)
            if pending:
                self.task.add_done_callback(self._consume_result)
            else:
                self._consume_result(self.task)

    @staticmethod
    def _consume_result(task: asyncio.Task[object]) -> None:
        if not task.cancelled():
            task.exception()
