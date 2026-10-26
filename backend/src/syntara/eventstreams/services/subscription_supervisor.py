"""Apply persisted desired state to one local runner, independently of recovery."""

import asyncio
import random
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog

from syntara.core.config.base import get_settings
from syntara.core.constants import EventSchedulingDefaults
from syntara.core.exceptions import SyntaraError
from syntara.eventstreams.core.placement import PlacementAuthority
from syntara.eventstreams.core.runtime import (
    RuntimeFailureCode,
    RuntimeRevision,
    RuntimeState,
    SubscriptionRunner,
    SubscriptionRunnerFactory,
    SubscriptionRuntimeError,
    SubscriptionRuntimeStatus,
)
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot

logger = structlog.stdlib.get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SubscriptionSupervisor:
    """One subscription's local lifecycle; callers periodically reapply snapshots.

    The injected factory composes real clients and completed services. This class
    owns neither a worker manager nor process-level prepared-delivery recovery.
    A stopped consumer is not durable resolution: no claim, frozen Execution,
    source identity, group position, or permanent-content evidence is changed.
    """

    def __init__(
        self, subscription_id: UUID, runner_factory: SubscriptionRunnerFactory, *, placement: PlacementAuthority
    ) -> None:
        """Keep retry/circuit state local and reuse the existing drain deadline."""
        if placement.subscription_id != subscription_id:
            msg = "Placement belongs to a different subscription"
            raise ValueError(msg)
        self._subscription_id = subscription_id
        self._factory = runner_factory
        self._placement = placement
        self._placement_task: asyncio.Task[None] | None = None
        self._drain_timeout = get_settings().event_drain_timeout_seconds
        self._lock = asyncio.Lock()
        self._desired: SubscriptionSnapshot | None = None
        self._target: tuple[RuntimeRevision, bool] | None = None
        self._runner: SubscriptionRunner | None = None
        self._runner_revision: RuntimeRevision | None = None
        self._applied: RuntimeRevision | None = None
        self._task: asyncio.Task[None] | None = None
        self._startup_task: asyncio.Task[None] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._drain_task: asyncio.Task[None] | None = None
        self._starting = False
        self._local_contention = False
        self._draining = False
        self._closed = False
        self._failure: SubscriptionRuntimeError | None = None
        self._failure_count = 0
        self._retry_at: datetime | None = None
        self._stop_retry_at: datetime | None = None

    @staticmethod
    def _active(snapshot: SubscriptionSnapshot) -> bool:
        return snapshot.desired_enabled and not snapshot.paused and not snapshot.retired

    @property
    def status(self) -> SubscriptionRuntimeStatus:
        """Distinguish requested state, applied binding, and unfinished convergence."""
        state, reason, permanent = RuntimeState.STOPPED, None, False
        circuit = (
            self._failure is not None
            and self._failure.transient
            and (self._failure_count >= EventSchedulingDefaults.IMMEDIATE_ATTEMPTS)
        )
        if self._draining or (self._closed and self._runner is not None):
            state = RuntimeState.DRAINING
            reason = RuntimeFailureCode.STOP_INCOMPLETE.value if self._stop_retry_at is not None else None
        elif not self._closed:
            if self._desired is not None and self._active(self._desired) and not self._placement.is_current():
                state = RuntimeState.DRAINING if self._placement.local_in_use else RuntimeState.BLOCKED
                reason = RuntimeFailureCode.PLACEMENT_LOST.value
            elif self._local_contention and self._desired is not None and self._active(self._desired):
                state = RuntimeState.BLOCKED
                reason = RuntimeFailureCode.LOCAL_RUNNER_BUSY.value
            elif self._failure is not None:
                state = RuntimeState.BACKOFF if self._failure.transient and not circuit else RuntimeState.BLOCKED
                reason = self._failure.code.value
            elif self._starting:
                state = RuntimeState.STARTING
            elif self._runner is not None:
                observed = self._runner.status
                state, reason, permanent = observed.state, observed.reason, observed.permanent_content_error
        return SubscriptionRuntimeStatus(
            subscription_id=self._subscription_id,
            desired_revision=RuntimeRevision.from_snapshot(self._desired) if self._desired is not None else None,
            desired_active=self._desired is not None and self._active(self._desired),
            applied_revision=self._applied,
            state=state,
            reason=reason,
            permanent_content_error=permanent,
            failure_count=self._failure_count,
            retry_at=self._stop_retry_at if self._draining else self._retry_at,
            circuit_open=circuit,
        )

    async def apply(self, snapshot: SubscriptionSnapshot) -> SubscriptionRuntimeStatus:
        """Reconcile the latest request; identical snapshots never reset retry budgets."""
        if snapshot.subscription_id != self._subscription_id:
            msg = "Snapshot belongs to a different subscription"
            raise ValueError(msg)
        if snapshot.deployment_id != self._placement.worker.deployment_id:
            msg = "Snapshot belongs to a different deployment"
            raise ValueError(msg)
        # Publish desire before waiting for an earlier start/drain. Recheck it
        # after every replacement so a superseded request cannot start a client.
        self._desired = snapshot
        self._watch_placement()
        if not self._active(snapshot):
            self._interrupt_startup()
            deadline = asyncio.get_running_loop().time() + self._drain_timeout
            try:
                async with asyncio.timeout_at(deadline), self._lock:
                    await self._converge(deadline=deadline)
            except TimeoutError:
                if self._desired == snapshot:
                    self._draining = True
                    self._stop_failed()
            return self.status
        async with self._lock:
            await self._converge()
        return self.status

    def _interrupt_startup(self) -> None:
        task = self._startup_task
        if task is not None and not task.done():
            self._draining = True
            # Repeated control requests must not cancel startup's cleanup again.
            if not task.cancelling():
                task.cancel()

    def _watch_placement(self) -> None:
        if (
            not self._closed
            and self._placement.is_current()
            and (self._placement_task is None or self._placement_task.done())
        ):
            self._placement_task = asyncio.create_task(self._observe_placement())

    async def _observe_placement(self) -> None:
        await self._placement.wait_lost()
        await self.placement_lost()

    async def placement_lost(self) -> SubscriptionRuntimeStatus:
        """Manager/watchdog hook: close admission independently of slow startup.

        The runner's synchronous guard already rejects new intake. This port
        pauses/drains/stops locally; it never cancels a Temporal execution or
        changes a delivery token, evidence, or placement row.
        """
        self._placement.invalidate()
        self._interrupt_startup()
        deadline = asyncio.get_running_loop().time() + self._drain_timeout
        try:
            async with asyncio.timeout_at(deadline), self._lock:
                await self._stop_current(force=True, deadline=deadline)
        except TimeoutError:
            self._draining = True
            self._stop_failed()
        return self.status

    def _clear_failure(self) -> None:
        self._failure = None
        self._failure_count = 0
        self._retry_at = None

    def _record_failure(self, exc: Exception) -> None:
        if isinstance(exc, SubscriptionRuntimeError):
            failure = exc
        elif isinstance(exc, (TimeoutError, OSError)):
            failure = SubscriptionRuntimeError(RuntimeFailureCode.CONNECTION_UNAVAILABLE, transient=True)
        else:
            code = (
                RuntimeFailureCode.CONFIGURATION_UNAVAILABLE
                if isinstance(exc, (SyntaraError, ValueError))
                else RuntimeFailureCode.RUNNER_FAILED
            )
            failure = SubscriptionRuntimeError(code)
        self._failure = failure
        self._failure_count += 1
        self._retry_at = None
        if failure.transient:
            delay = (
                EventSchedulingDefaults.TRANSIENT_PROBE_SECONDS
                if self._failure_count >= EventSchedulingDefaults.IMMEDIATE_ATTEMPTS
                else min(2 ** (self._failure_count - 1), EventSchedulingDefaults.MAX_BACKOFF_SECONDS)
                * random.uniform(0.5, 1.0)  # noqa: S311 - dependency retry jitter, not security
            )
            self._retry_at = _utc_now() + timedelta(seconds=delay)
        logger.warning(
            "event_subscription_runtime_unavailable",
            subscription_id=str(self._subscription_id),
            code=failure.code.value,
        )

    async def _converge(self, *, deadline: float | None = None) -> None:
        while not self._closed and self._desired is not None:
            snapshot = self._desired
            revision = RuntimeRevision.from_snapshot(snapshot)
            active = self._active(snapshot)
            if not self._placement.is_current():
                await self._stop_current(deadline=deadline)
                return
            if deadline is not None and active:
                return  # A superseded inactive request must not start newer active work.
            target = (revision, active)
            if target != self._target:
                self._target = target
                self._clear_failure()
            if self._runner is not None:
                if (
                    active
                    and self._runner_revision == revision
                    and self._task is not None
                    and not self._task.done()
                    and not self._draining
                ):
                    return
                if not await self._stop_current(deadline=deadline):
                    return
                continue
            if not active or (
                self._failure is not None
                and (not self._failure.transient or (self._retry_at is not None and _utc_now() < self._retry_at))
            ):
                return
            await self._start_runner(snapshot, revision)
            if self._desired == snapshot or self._draining:
                return

    async def _start_runner(self, snapshot: SubscriptionSnapshot, revision: RuntimeRevision) -> None:
        if not self._placement.reserve_local(self):
            self._local_contention = self._placement.is_current()
            return
        self._local_contention = False
        self._starting = True
        self._startup_task = asyncio.create_task(self._open_runner(snapshot, revision))
        try:
            await self._startup_task
            if self._closed or self._desired != snapshot or not self._placement.is_current():
                await self._stop_current(force=True)
                return
            self._failure = None
            self._retry_at = None
            if self._runner is not None:
                self._task = asyncio.create_task(self._serve(self._runner))
        except asyncio.CancelledError:
            await self._stop_current(force=True)
            caller = asyncio.current_task()
            if (caller is not None and caller.cancelling()) or (
                not self._closed and self._desired == snapshot and self._placement.is_current()
            ):
                raise
        except Exception as exc:  # noqa: BLE001 - isolate failures to this subscription
            self._record_failure(exc)
            await self._stop_current(force=True)
        finally:
            self._startup_task = None
            self._starting = False

    async def _open_runner(self, snapshot: SubscriptionSnapshot, revision: RuntimeRevision) -> None:
        runner = await self._factory(snapshot)
        self._runner, self._runner_revision = runner, revision
        if runner.snapshot != snapshot:
            raise SubscriptionRuntimeError(RuntimeFailureCode.CONFIGURATION_UNAVAILABLE)
        runner.bind_placement(self._placement.is_current)
        if self._closed or self._desired != snapshot or not self._placement.is_current():
            return
        await runner.start()
        if self._closed or self._desired != snapshot or not self._placement.is_current():
            return
        if not runner.open_admission():
            raise SubscriptionRuntimeError(RuntimeFailureCode.PLACEMENT_LOST)
        self._applied = revision

    async def _serve(self, runner: SubscriptionRunner) -> None:
        try:
            await runner.run()
        except asyncio.CancelledError:
            if self._runner is runner and not self._draining:
                self._record_failure(SubscriptionRuntimeError(RuntimeFailureCode.RUNNER_FAILED, transient=True))
            raise
        except Exception as exc:  # noqa: BLE001 - never cancel unrelated subscription tasks
            if self._runner is runner and not self._draining:
                self._record_failure(exc)
        else:
            if self._runner is runner and not self._draining:
                self._record_failure(SubscriptionRuntimeError(RuntimeFailureCode.RUNNER_FAILED, transient=True))

    async def _stop_current(self, *, force: bool = False, deadline: float | None = None) -> bool:
        runner = self._runner
        if runner is None:
            self._draining = False
            self._local_contention = False
            self._stop_retry_at = None
            self._placement.local_stopped(self)
            return True
        if (
            not force
            and self._stop_retry_at is not None
            and _utc_now() < self._stop_retry_at
            and (self._cleanup_task is None or not self._cleanup_task.done())
        ):
            return False
        self._draining = True
        if deadline is None:
            deadline = asyncio.get_running_loop().time() + self._drain_timeout
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._close_runner(runner, self._task, deadline))
            self._cleanup_task.add_done_callback(self._cleanup_settled)
        try:
            # Observe cleanup without directly awaiting a port that may delay
            # cancellation. Timeout/caller cancellation never drops ownership
            # of the still-running cleanup or starts a second stop operation.
            _, pending = await asyncio.wait(
                {self._cleanup_task}, timeout=max(0.0, deadline - asyncio.get_running_loop().time())
            )
            if pending:
                return self._stop_failed()
            self._cleanup_task.result()
        except asyncio.CancelledError:
            self._stop_retry_at = _utc_now() + timedelta(seconds=EventSchedulingDefaults.TRANSIENT_PROBE_SECONDS)
            raise
        except Exception:  # noqa: BLE001 - retain this runner until stop is verified
            self._cleanup_task = None  # Settled failure may be retried; pending cleanup is always retained.
            return self._stop_failed()
        self._cleanup_task = None
        self._drain_task = None
        self._runner = None
        self._runner_revision = self._applied = None
        self._task = None
        self._draining = False
        self._stop_retry_at = None
        self._placement.local_stopped(self)
        return True

    @staticmethod
    def _cleanup_settled(task: asyncio.Task[None]) -> None:
        if not task.cancelled():
            task.exception()

    async def _close_runner(
        self, runner: SubscriptionRunner, serving: asyncio.Task[None] | None, deadline: float
    ) -> None:
        if self._drain_task is None:
            closing = runner.drain() if self._placement.is_current() else runner.close_admission()
            self._drain_task = asyncio.create_task(closing)
            self._drain_task.add_done_callback(self._cleanup_settled)
        draining = self._drain_task
        try:
            _, pending = await asyncio.wait({draining}, timeout=max(0.0, deadline - asyncio.get_running_loop().time()))
            if pending:
                draining.cancel()
                logger.warning("event_subscription_drain_incomplete", subscription_id=str(self._subscription_id))
            elif not draining.cancelled() and draining.exception() is not None:
                logger.warning("event_subscription_drain_incomplete", subscription_id=str(self._subscription_id))
            # Always attempt client stop, even if drain exhausted its budget or
            # delays cancellation. The observer remains bounded, and this task
            # retains the local reservation until BOTH operations have settled.
            await runner.stop()
        finally:
            await asyncio.gather(draining, return_exceptions=True)
        if serving is not None:
            if not serving.done():
                serving.cancel()
            await asyncio.gather(serving, return_exceptions=True)

    def _stop_failed(self) -> bool:
        self._stop_retry_at = _utc_now() + timedelta(seconds=EventSchedulingDefaults.TRANSIENT_PROBE_SECONDS)
        logger.warning("event_subscription_stop_incomplete", subscription_id=str(self._subscription_id))
        return False

    async def retry(self) -> SubscriptionRuntimeStatus:
        """Explicitly retry local setup/teardown after correction; never clear durable holds."""
        self._watch_placement()
        async with self._lock:
            self._clear_failure()
            self._stop_retry_at = None
            await self._converge()
        return self.status

    async def drain(self) -> SubscriptionRuntimeStatus:
        """Close this supervisor to new starts and bound drain; recovery stays independent."""
        return await self._shutdown(drain_only=True)

    async def stop(self) -> SubscriptionRuntimeStatus:
        """Close reconciliation and stop locally; a failed stop remains visibly draining."""
        return await self._shutdown(drain_only=False)

    async def _shutdown(self, *, drain_only: bool) -> SubscriptionRuntimeStatus:
        self._closed = True
        self._interrupt_startup()
        deadline = asyncio.get_running_loop().time() + self._drain_timeout
        try:
            async with asyncio.timeout_at(deadline), self._lock:
                if drain_only and self._runner is not None:
                    self._draining = True
                    if self._drain_task is None:
                        self._drain_task = asyncio.create_task(self._runner.drain())
                        self._drain_task.add_done_callback(self._cleanup_settled)
                    _, pending = await asyncio.wait(
                        {self._drain_task}, timeout=max(0.0, deadline - asyncio.get_running_loop().time())
                    )
                    if pending:
                        self._stop_failed()
                    else:
                        self._drain_task.result()
                else:
                    await self._stop_current(force=True, deadline=deadline)
        except Exception:  # noqa: BLE001 - retain startup/runner ownership when shutdown is incomplete
            self._draining = True
            self._stop_failed()
        if self._placement_task is not None and self._placement_task is not asyncio.current_task():
            self._placement_task.cancel()
            self._placement_task.add_done_callback(self._cleanup_settled)
            await asyncio.wait({self._placement_task}, timeout=max(0.0, deadline - asyncio.get_running_loop().time()))
        return self.status
