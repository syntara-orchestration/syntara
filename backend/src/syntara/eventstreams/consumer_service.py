"""Transport-neutral reconciliation and local subscription supervision."""

import asyncio
import random
from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy.exc import SQLAlchemyError

from syntara.core.config.base import get_settings
from syntara.core.constants import EventSchedulingDefaults, EventWorkerDefaults
from syntara.eventstreams.core.runtime import RuntimeState, SubscriptionRunnerFactory
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.runtime_control_service import EventRuntimeControlService
from syntara.eventstreams.services.subscription_reader import EventSubscriptionReader
from syntara.eventstreams.services.subscription_supervisor import SubscriptionSupervisor

logger = structlog.stdlib.get_logger(__name__)


class EventWorkerManager:
    """Reconcile every active subscription locally; brokers own partition placement."""

    def __init__(
        self,
        reader: EventSubscriptionReader,
        runner_factory: SubscriptionRunnerFactory,
        *,
        controls: EventRuntimeControlService | None = None,
    ) -> None:
        """Inject authoritative reads and transport construction, never a session."""
        self._reader = reader
        self._factory = runner_factory
        self._controls = controls
        self._registered: dict[UUID, SubscriptionSnapshot] = {}
        self._supervisors: dict[UUID, SubscriptionSupervisor] = {}
        self._desired: dict[UUID, SubscriptionSnapshot] = {}
        self._pending: dict[UUID, SubscriptionSnapshot | None] = {}
        self._busy: set[UUID] = set()
        self._retiring: set[UUID] = set()
        self._retirement_retries: dict[UUID, asyncio.TimerHandle] = {}
        self._hint = asyncio.Event()
        self._work_ready = asyncio.Event()
        self._start_lock = asyncio.Lock()
        self._reconcile_lock = asyncio.Lock()
        self._workers: list[asyncio.Task[None]] = []
        self._loop: asyncio.Task[None] | None = None
        self._closing = False
        self._ready = False

    @property
    def ready(self) -> bool:
        """Initial authoritative reconciliation completed and shutdown has not begun."""
        return self._ready and not self._closing

    @property
    def reconciliation_task(self) -> asyncio.Task[None] | None:
        """Allow process lifecycle to detect an unexpected manager failure."""
        return self._loop

    @property
    def subscription_ids(self) -> frozenset[UUID]:
        """Observe local supervision without exposing credentials or transport clients."""
        return frozenset(self._supervisors)

    def request_reconcile(self) -> None:
        """Coalesce best-effort hints; their contents confer no authority."""
        if not self._closing:
            self._hint.set()

    async def start(self) -> None:
        """Perform initial reconciliation before readiness; broker startup is independent."""
        async with self._start_lock:
            if self._closing or self._workers:
                return
            self._workers = [
                asyncio.create_task(self._apply_loop(), name=f"event-subscription-start-{index}")
                for index in range(EventWorkerDefaults.STARTUP_CONCURRENCY)
            ]
            await self._reconcile_safely()
            if not self._closing:
                self._loop = asyncio.create_task(self._reconcile_loop(), name="event-subscription-reconcile")

    async def reconcile(self) -> None:
        """Replace desired state only after a complete successful authoritative read."""
        async with self._reconcile_lock:
            if self._closing:
                return
            self._hint.clear()
            snapshots = await self._reader.read()
            if self._closing:
                return  # type: ignore[unreachable]  # changed by signal/shutdown while reading
            desired = {
                snapshot.subscription_id: snapshot
                for snapshot in snapshots
                if snapshot.desired_enabled and not snapshot.paused and not snapshot.retired
            }
            if len({snapshot.subscription_id for snapshot in snapshots}) != len(snapshots):
                msg = "Authoritative subscription snapshots contain duplicate identities"
                raise RuntimeError(msg)
            self._desired = desired
            self._pending.update(desired)
            for subscription_id in self._supervisors.keys() | self._busy:
                if subscription_id not in desired:
                    self._pending[subscription_id] = None
            self._notify_work()
            self._ready = True

    async def _reconcile_safely(self) -> None:
        try:
            await self.reconcile()
        except (SQLAlchemyError, TimeoutError, OSError):
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

    def _notify_work(self) -> None:
        if any(key not in self._busy and key not in self._retirement_retries for key in self._pending):
            self._work_ready.set()
        else:
            self._work_ready.clear()

    async def _apply_loop(self) -> None:
        while not self._closing:
            await self._work_ready.wait()
            if self._closing:
                return  # type: ignore[unreachable]  # changed while awaiting queued work
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
            except Exception:  # noqa: BLE001 - isolate a single subscription, including teardown failures
                logger.warning("event_subscription_reconcile_failed", subscription_id=str(key))
            finally:
                self._busy.discard(key)
                self._notify_work()

    async def _apply(self, key: UUID, snapshot: SubscriptionSnapshot | None) -> None:
        if self._closing:
            return
        supervisor = self._supervisors.get(key)
        previous = self._registered.get(key)
        replaced = previous is not None and snapshot is not None and previous.source_id != snapshot.source_id
        if supervisor is not None and (snapshot is None or key in self._retiring or replaced):
            self._retiring.add(key)
            status = await supervisor.stop()
            if self._controls is not None and previous is not None:
                await self._controls.acknowledge(previous, status)
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
                    self._notify_work()
                return
            del self._supervisors[key]
            self._retiring.discard(key)
            supervisor = None
            self._registered.pop(key, None)
        # Recheck after awaiting teardown so a newer inactive request cannot start a client.
        snapshot = self._desired.get(key)
        if self._closing or snapshot is None:
            return
        if not await self._register(key, snapshot):
            return
        if supervisor is None:
            supervisor = SubscriptionSupervisor(
                key, self._factory, startup_timeout_seconds=EventWorkerDefaults.STARTUP_TIMEOUT_SECONDS
            )
            self._supervisors[key] = supervisor
        status = await supervisor.apply(snapshot)
        if self._controls is not None:
            await self._controls.acknowledge(snapshot, status)

    async def _register(self, key: UUID, snapshot: SubscriptionSnapshot) -> bool:
        if self._controls is not None and self._registered.get(key) != snapshot:
            if not await self._controls.register(snapshot):
                return False
            self._registered[key] = snapshot
        return True

    async def _stop_supervisor(self, key: UUID, supervisor: SubscriptionSupervisor) -> None:
        status = await supervisor.stop()
        snapshot = self._registered.get(key)
        if self._controls is not None and snapshot is not None:
            await self._controls.acknowledge(snapshot, status)

    def _retry_retirement(self, key: UUID) -> None:
        self._retirement_retries.pop(key, None)
        if not self._closing:
            self._notify_work()

    def close_reconciliation(self) -> None:
        """Stop reads, queued starts, and in-progress replacements synchronously."""
        self._closing = True
        self._ready = False
        self._pending.clear()
        for handle in self._retirement_retries.values():
            handle.cancel()
        self._retirement_retries.clear()
        for task in [*self._workers, *([self._loop] if self._loop is not None else [])]:
            if not task.done():
                task.cancel()

    async def stop(self) -> None:
        """Delegate bounded teardown; no durable delivery state is deleted or resolved."""
        self.close_reconciliation()
        tasks = {
            *self._workers,
            *([self._loop] if self._loop is not None else []),
            *(
                asyncio.create_task(self._stop_supervisor(key, supervisor))
                for key, supervisor in self._supervisors.items()
            ),
        }
        if not tasks:
            return
        _, pending = await asyncio.wait(tasks, timeout=get_settings().event_drain_timeout_seconds)
        for task in tasks:
            if task in pending:
                task.cancel()
                task.add_done_callback(self._consume_result)
            else:
                self._consume_result(task)
        if pending:
            logger.warning("event_worker_drain_incomplete", task_count=len(pending))

    @staticmethod
    def _consume_result(task: asyncio.Task[object]) -> None:
        if not task.cancelled():
            task.exception()
