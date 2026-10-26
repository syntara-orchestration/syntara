"""Count-based placement and bounded local subscription supervision."""

import asyncio
import random
import time
from collections.abc import Iterable
from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID

import structlog

from syntara.core.config.base import get_settings
from syntara.core.constants import EventPlacementDefaults, EventSchedulingDefaults, EventWorkerDefaults
from syntara.eventstreams.core.placement import PlacementLost, SubscriptionPlacementLease
from syntara.eventstreams.core.runtime import RuntimeState, SubscriptionRunnerFactory
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.placement_service import SubscriptionPlacementService
from syntara.eventstreams.services.subscription_reader import EventSubscriptionReader
from syntara.eventstreams.services.subscription_supervisor import SubscriptionSupervisor
from syntara.eventstreams.services.worker_gate import EventWorkerGate
from syntara.eventstreams.services.worker_membership import PLACEMENT_ERRORS, EventWorkerMembership
from syntara.eventstreams.services.worker_resources import EventWorkerResources

logger = structlog.stdlib.get_logger(__name__)


def placement_targets(active_count: int, worker_ids: Iterable[UUID]) -> dict[UUID, int]:
    """Split subscription counts deterministically, including zero targets."""
    workers = sorted(set(worker_ids))
    if not workers:
        return {}
    base, remainder = divmod(active_count, len(workers))
    return {worker: base + int(index < remainder) for index, worker in enumerate(workers)}


class EventWorkerManager:
    """Reconcile only committed local placements; Kafka owns partition assignment."""

    def __init__(
        self,
        reader: EventSubscriptionReader,
        runner_factory: SubscriptionRunnerFactory,
        placement: SubscriptionPlacementService,
        resources: EventWorkerResources,
    ) -> None:
        """Inject completed provider ports and process-owned limits, never a session."""
        self._reader = reader
        self._factory = runner_factory
        self._placement = placement
        self._resources = resources
        self._gate = resources.gate if resources.gate is not None else EventWorkerGate(placement)
        resources.gate = self._gate
        self._owned: set[UUID] = set()
        self._abandoned: set[UUID] = set()
        self._selected: set[UUID] = set()
        self._supervisors: dict[UUID, SubscriptionSupervisor] = {}
        self._desired: dict[UUID, SubscriptionSnapshot] = {}
        self._pending: dict[UUID, SubscriptionSnapshot | None] = {}
        self._busy: set[UUID] = set()
        self._retiring: set[UUID] = set()
        self._retirement_retries: dict[UUID, asyncio.TimerHandle] = {}
        self._hint = asyncio.Event()
        self._work_ready = asyncio.Event()
        self._start_lock = asyncio.Lock()
        self._stop_lock = asyncio.Lock()
        self._shutdown_lock = asyncio.Lock()
        self._reconcile_lock = asyncio.Lock()
        self._workers: list[asyncio.Task[None]] = []
        self._loop: asyncio.Task[None] | None = None
        self._drain_tasks: set[asyncio.Task[None]] = set()
        self._drain_closed = False
        self._closing = False
        self._draining_requested = False
        self._ready = False
        self._membership = EventWorkerMembership(
            placement, resources, self._owned, self._placement_lost, self.request_reconcile
        )

    @property
    def ready(self) -> bool:
        """Registration and authoritative reconciliation succeeded; broker startup is independent."""
        task = self._membership.task
        return (
            self._ready
            and not self._closing
            and self._gate.scheduling_open
            and self._membership.trusted
            and self._loop is not None
            and not self._loop.done()
            and task is not None
            and not task.done()
        )

    @property
    def reconciliation_task(self) -> asyncio.Task[None] | None:
        """Expose reconciliation as process infrastructure."""
        return self._loop

    @property
    def membership_task(self) -> asyncio.Task[None] | None:
        """Expose independent ownership maintenance for process failure monitoring."""
        return self._membership.task

    @property
    def subscription_ids(self) -> frozenset[UUID]:
        """Include starting/draining local supervisors without exposing clients."""
        return frozenset(self._supervisors)

    @property
    def owned_subscription_ids(self) -> frozenset[UUID]:
        """Observe committed/uncertain ownership still requiring process cleanup."""
        return frozenset(self._owned)

    def request_reconcile(self) -> None:
        """Coalesce best-effort hints; PostgreSQL remains authoritative."""
        if not self._closing:
            self._hint.set()

    async def start(self) -> None:
        """Register before reconciliation and never await broker connections for readiness."""
        async with self._start_lock:
            if self._closing or self._workers:
                return
            await self._membership.register()
            if self._closing:
                return  # type: ignore[unreachable]  # signal while registering
            self._workers = [
                asyncio.create_task(self._apply_loop(), name=f"event-subscription-start-{index}")
                for index in range(EventWorkerDefaults.STARTUP_CONCURRENCY)
            ]
            await self._reconcile_safely()
            if not self._closing:
                self._loop = asyncio.create_task(self._reconcile_loop(), name="event-subscription-reconcile")

    async def _reconcile_uncertain(self) -> None:
        for key in tuple(self._placement.pending_reconciliation):

            async def reconcile(key: UUID = key) -> SubscriptionPlacementLease | PlacementLost:
                return await self._placement.reconcile_placement(key)

            result = await self._membership.call(reconcile, require_trusted=False)
            if key in self._abandoned:
                self._placement.authority(key).invalidate()
                if isinstance(result, PlacementLost):
                    self._abandoned.discard(key)
            else:
                self._owned.add(key)
                if isinstance(result, PlacementLost):
                    self._placement_lost(key, request_reconcile=False)

    async def _claim_deficit(self, deficit: int) -> list[SubscriptionPlacementLease]:
        async def claim() -> list[SubscriptionPlacementLease]:
            if self._closing:
                return []
            return await self._placement.claim_subscriptions(
                self._placement.worker, limit=min(deficit, EventPlacementDefaults.MAX_CLAIM_BATCH)
            )

        try:
            return await self._membership.call(claim)
        finally:
            # A lost commit response may already have assigned these rows. Queue
            # bounded cleanup now; release must still reconcile ownership first.
            uncertain = self._placement.pending_reconciliation - self._abandoned
            self._owned.update(uncertain)
            for key in uncertain:
                self._placement_lost(key, request_reconcile=False)

    async def _fill_deficit(self, target: int) -> None:
        """Select committed claims only for the remaining local ownership deficit."""
        deficit = max(0, target - len(self._owned))
        if deficit:
            for lease in await self._claim_deficit(deficit):
                key = lease.subscription_id
                self._owned.add(key)
                self._abandoned.discard(key)
                if key in self._desired and self._placement.authority(key).is_current():
                    self._selected.add(key)
                else:
                    self._retiring.add(key)
                    self._pending[key] = None

    async def reconcile(self) -> None:
        """Keep existing valid placements up to target; claim only the remaining deficit."""
        async with self._reconcile_lock:
            if self._closing:
                return
            self._hint.clear()
            generation, started = self._gate.generation, time.monotonic()
            async with asyncio.timeout(EventWorkerDefaults.STARTUP_TIMEOUT_SECONDS):
                snapshots = await self._reader.read()
                blocked = await self._reader.recovery_holds()
                members = await self._membership.call(self._placement.list_live_workers, require_trusted=False)
                await self._reconcile_uncertain()
            if self._closing:
                return  # type: ignore[unreachable]  # signal during authoritative reads
            desired = {
                snapshot.subscription_id: snapshot
                for snapshot in snapshots
                if snapshot.deployment_id == self._placement.worker.deployment_id
                and snapshot.desired_enabled
                and not snapshot.paused
                and not snapshot.retired
            }
            if len({snapshot.subscription_id for snapshot in snapshots}) != len(snapshots):
                msg = "Authoritative subscription snapshots contain duplicate identities"
                raise RuntimeError(msg)
            targets = placement_targets(
                len(desired),
                (
                    member.worker.worker_id
                    for member in members
                    if member.worker.deployment_id == self._placement.worker.deployment_id and not member.draining
                ),
            )
            target = targets.get(self._placement.worker.worker_id)
            if target is None:
                self._resources.database_failed()
                self._placement.distrust()
                msg = "Registered worker is absent from authoritative live membership"
                raise RuntimeError(msg)
            self._desired = desired
            keep = sorted(
                key
                for key in self._owned
                if key in desired and key not in self._retiring and self._placement.authority(key).is_current()
            )[:target]
            self._selected = set(keep)
            for key in self._owned - self._selected:
                self._retiring.add(key)
                self._pending[key] = None
            await self._fill_deficit(target)
            if self._closing:
                return  # type: ignore[unreachable]  # signal during claim commit
            for key in self._selected:
                self._pending[key] = desired[key]
            self._ready = self._gate.reconciled(desired.values(), blocked, generation=generation, started=started)
            self._notify_work()

    async def _reconcile_safely(self) -> None:
        try:
            await self.reconcile()
        except PLACEMENT_ERRORS:
            self._resources.database_failed()
            self._placement.distrust()
            logger.warning("event_subscription_reconciliation_unavailable")

    async def _reconcile_loop(self) -> None:
        while not self._closing:
            delay = EventWorkerDefaults.RECONCILE_INTERVAL_SECONDS * random.uniform(  # noqa: S311
                1 - EventWorkerDefaults.RECONCILE_JITTER, 1 + EventWorkerDefaults.RECONCILE_JITTER
            )
            with suppress(TimeoutError):
                await asyncio.wait_for(self._hint.wait(), timeout=delay)
            if not self._closing:
                await self._reconcile_safely()

    def _placement_lost(self, key: UUID, *, request_reconcile: bool = True) -> None:
        newly_lost = key not in self._retiring
        self._placement.authority(key).invalidate()
        self._selected.discard(key)
        self._retiring.add(key)
        if not self._closing:
            self._pending[key] = None
            self._notify_work()
            if request_reconcile and newly_lost:
                self.request_reconcile()

    def _notify_work(self) -> None:
        if any(key not in self._busy and key not in self._retirement_retries for key in self._pending):
            self._work_ready.set()
        else:
            self._work_ready.clear()

    async def _apply_loop(self) -> None:
        while not self._closing:
            await self._work_ready.wait()
            if self._closing:
                return  # type: ignore[unreachable]  # signal during queue wait
            key = next(
                (key for key in self._pending if key not in self._busy and key not in self._retirement_retries), None
            )
            if key is None:
                self._notify_work()
                continue
            snapshot = self._pending.pop(key)
            self._busy.add(key)
            self._notify_work()
            try:
                await self._apply(key, snapshot)
            except Exception:  # noqa: BLE001 - isolate subscription startup and teardown failures
                logger.warning("event_subscription_reconcile_failed", subscription_id=str(key))
            finally:
                self._busy.discard(key)
                self._notify_work()

    async def _release(self, key: UUID) -> None:
        if self._drain_closed:
            return

        async def release() -> bool:
            self._owned.discard(key)
            if self._drain_closed:
                return False
            if key in self._placement.pending_reconciliation:
                await self._placement.reconcile_placement(key)
            if self._drain_closed:
                return False  # type: ignore[unreachable]  # shutdown during ownership reconciliation
            lease = self._placement.authority(key).lease
            return False if lease is None else await self._placement.release_placement(lease)

        self._abandoned.add(key)
        try:
            released = await self._membership.call(release, require_trusted=False)
            if released:
                self._abandoned.discard(key)
        except PLACEMENT_ERRORS:
            # The consumer is stopped. Never renew a failed release or reopen
            # on an ambiguous response; let the database lease expire.
            self._owned.discard(key)
            logger.warning("event_worker_placement_release_unavailable", subscription_id=str(key))
        finally:
            self._placement.authority(key).invalidate()

    async def _retire(self, key: UUID) -> None:
        supervisor = self._supervisors.get(key)
        if supervisor is not None:
            status = await supervisor.stop()
            if status.state != RuntimeState.STOPPED:
                if not self._closing:
                    self._pending[key] = None
                    delay = (
                        max(0.0, (status.retry_at - datetime.now(UTC)).total_seconds())
                        if status.retry_at is not None
                        else EventSchedulingDefaults.TRANSIENT_PROBE_SECONDS
                    )
                    self._retirement_retries[key] = asyncio.get_running_loop().call_later(
                        delay, self._retry_retirement, key
                    )
                return
            del self._supervisors[key]
        await self._release(key)
        self._retiring.discard(key)
        self._selected.discard(key)
        self.request_reconcile()

    async def _apply(self, key: UUID, snapshot: SubscriptionSnapshot | None) -> None:
        if self._closing:
            return
        if snapshot is None or key in self._retiring:
            await self._retire(key)
            return
        snapshot = self._desired.get(key)
        if snapshot is None or key not in self._selected or key not in self._owned:
            return
        authority = self._placement.authority(key)
        if not authority.is_current() or not self._gate.transport_open(snapshot):
            return
        supervisor = self._supervisors.get(key)
        if supervisor is None:
            supervisor = SubscriptionSupervisor(
                key,
                self._factory,
                placement=authority,
                startup_timeout_seconds=EventWorkerDefaults.STARTUP_TIMEOUT_SECONDS,
            )
            self._supervisors[key] = supervisor
        await supervisor.apply(snapshot)

    def _retry_retirement(self, key: UUID) -> None:
        self._retirement_retries.pop(key, None)
        if not self._closing:
            self._notify_work()

    def close_reconciliation(self) -> None:
        """Fence new claims and replacements without stopping ownership maintenance."""
        self._closing = True
        self._ready = False
        self._pending.clear()
        for handle in self._retirement_retries.values():
            handle.cancel()
        self._retirement_retries.clear()
        for task in [*self._workers, *([self._loop] if self._loop is not None else [])]:
            if not task.done() and not task.cancelling():
                task.cancel()

    async def begin_shutdown(self) -> None:
        """Mark membership draining before asynchronous consumer drain/release work."""
        self.close_reconciliation()
        async with self._shutdown_lock:
            try:
                if not self._draining_requested:
                    self._draining_requested = True
                    await self._membership.mark_draining()
            finally:
                self._resources.close_admission()

    async def stop_membership(self) -> None:
        """Lifecycle fallback after bounded consumer cleanup, before shared clients close."""
        await self._membership.stop()

    async def stop(self, *, deadline: float | None = None) -> None:
        """Renew through bounded drain; release only after confirmed local stop."""
        async with self._stop_lock:
            if self._drain_closed:
                return
            loop = asyncio.get_running_loop()
            if deadline is None:
                deadline = loop.time() + get_settings().event_drain_timeout_seconds
            self.close_reconciliation()
            self._drain_tasks.update(self._workers)
            if self._loop is not None:
                self._drain_tasks.add(self._loop)
            try:
                try:
                    async with asyncio.timeout_at(
                        min(deadline, loop.time() + EventWorkerDefaults.PLACEMENT_TIMEOUT_SECONDS)
                    ):
                        await self.begin_shutdown()
                except Exception:  # noqa: BLE001 - membership failure must not skip consumer cleanup
                    self._resources.database_failed()
                    logger.warning("event_worker_draining_membership_unavailable")
                keys = iter(
                    tuple(
                        (self._owned | self._supervisors.keys() | self._placement.pending_reconciliation)
                        - self._abandoned
                    )
                )

                async def drain() -> None:
                    for key in keys:
                        if self._drain_closed:
                            return
                        try:
                            await self._retire(key)
                        except Exception:  # noqa: BLE001 - continue cleanup of unrelated subscriptions
                            logger.warning("event_worker_subscription_drain_incomplete", subscription_id=str(key))

                self._drain_tasks.update(
                    asyncio.create_task(drain(), name=f"event-subscription-drain-{index}")
                    for index in range(EventWorkerDefaults.STARTUP_CONCURRENCY)
                )
                await asyncio.wait(self._drain_tasks, timeout=max(0.0, deadline - loop.time()))
            finally:
                await self._finish_drain()

    async def _finish_drain(self) -> None:
        """Fence and retain every drain child before stopping ownership maintenance."""
        # A delayed stop cannot release a lease after shared clients close.
        self._drain_closed = True
        for task in self._drain_tasks:
            if not task.done() and not task.cancelling():
                task.cancel()
        try:
            if self._drain_tasks:
                await asyncio.wait(self._drain_tasks, timeout=EventWorkerDefaults.HINT_TIMEOUT_SECONDS)
        finally:
            for task in tuple(self._drain_tasks):
                if task.done():
                    self._drain_settled(task)
                else:
                    task.add_done_callback(self._drain_settled)
            await self.stop_membership()

    def _drain_settled(self, task: asyncio.Task[None]) -> None:
        self._drain_tasks.discard(task)
        self._consume_result(task)

    @staticmethod
    def _consume_result(task: asyncio.Task[object]) -> None:
        if not task.cancelled():
            task.exception()
