"""Apply persisted desired state to one local runner, independently of recovery."""

import asyncio
import random
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog

from syntara.core.config.base import get_settings
from syntara.core.constants import EventSchedulingDefaults
from syntara.core.exceptions import SyntaraError
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
        self,
        subscription_id: UUID,
        runner_factory: SubscriptionRunnerFactory,
        *,
        startup_timeout_seconds: float | None = None,
    ) -> None:
        """Keep retry/circuit state local and reuse the existing drain deadline."""
        self._subscription_id = subscription_id
        self._factory = runner_factory
        self._startup_timeout = startup_timeout_seconds
        self._drain_timeout = get_settings().event_drain_timeout_seconds
        self._lock = asyncio.Lock()
        self._desired: SubscriptionSnapshot | None = None
        self._target: tuple[RuntimeRevision, bool] | None = None
        self._runner: SubscriptionRunner | None = None
        self._runner_revision: RuntimeRevision | None = None
        self._applied: RuntimeRevision | None = None
        self._task: asyncio.Task[None] | None = None
        self._startup_task: asyncio.Task[None] | None = None
        self._starting = False
        self._draining = False
        self._closed = False
        self._failure: SubscriptionRuntimeError | None = None
        self._failure_count = 0
        self._retry_at: datetime | None = None
        self._stop_retry_at: datetime | None = None
        self._retained_content_gate = False

    @staticmethod
    def _active(snapshot: SubscriptionSnapshot) -> bool:
        return snapshot.desired_enabled and not snapshot.paused and not snapshot.retired

    @property
    def status(self) -> SubscriptionRuntimeStatus:
        """Distinguish requested state, applied binding, and unfinished convergence."""
        state, reason, permanent = RuntimeState.STOPPED, None, self._retained_content_gate
        circuit = (
            self._failure is not None
            and self._failure.transient
            and (self._failure_count >= EventSchedulingDefaults.IMMEDIATE_ATTEMPTS)
        )
        if self._draining or (self._closed and self._runner is not None):
            state = RuntimeState.DRAINING
            reason = RuntimeFailureCode.STOP_INCOMPLETE.value if self._stop_retry_at is not None else None
        elif not self._closed:
            if self._retained_content_gate:
                state, reason = RuntimeState.BLOCKED, "activity_log_unavailable"
            elif self._failure is not None:
                state = RuntimeState.BACKOFF if self._failure.transient and not circuit else RuntimeState.BLOCKED
                reason = self._failure.code.value
            elif self._starting:
                state = RuntimeState.STARTING
            elif self._runner is not None:
                observed = self._runner.status
                state, reason, permanent = (
                    observed.state,
                    observed.reason,
                    observed.permanent_content_error or self._retained_content_gate,
                )
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
        # Publish desire before waiting for an earlier start/drain. Recheck it
        # after every replacement so a superseded request cannot start a client.
        self._desired = snapshot
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
            if (
                not active
                or self._retained_content_gate
                or (
                    self._failure is not None
                    and (not self._failure.transient or (self._retry_at is not None and _utc_now() < self._retry_at))
                )
            ):
                return
            await self._start_runner(snapshot, revision)
            if self._desired == snapshot or self._draining:
                return

    async def _start_runner(self, snapshot: SubscriptionSnapshot, revision: RuntimeRevision) -> None:
        self._starting = True
        self._startup_task = asyncio.create_task(self._open_runner(snapshot, revision))
        try:
            await self._startup_task
            if self._closed or self._desired != snapshot:
                await self._stop_current(force=True)
                return
            self._failure = None
            self._retry_at = None
            if self._runner is not None:
                self._task = asyncio.create_task(self._serve(self._runner))
        except asyncio.CancelledError:
            await self._stop_current(force=True)
            caller = asyncio.current_task()
            if (caller is not None and caller.cancelling()) or (not self._closed and self._desired == snapshot):
                raise
        except Exception as exc:  # noqa: BLE001 - isolate failures to this subscription
            self._record_failure(exc)
            await self._stop_current(force=True)
        finally:
            self._startup_task = None
            self._starting = False

    async def _open_runner(self, snapshot: SubscriptionSnapshot, revision: RuntimeRevision) -> None:
        async with asyncio.timeout(self._startup_timeout):
            runner = await self._factory(snapshot)
            self._runner, self._runner_revision = runner, revision
            if runner.snapshot != snapshot:
                raise SubscriptionRuntimeError(RuntimeFailureCode.CONFIGURATION_UNAVAILABLE)
            if self._closed or self._desired != snapshot:
                return
            await runner.start()
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
            self._stop_retry_at = None
            return True
        self._retained_content_gate |= runner.status.permanent_content_error
        if not force and self._stop_retry_at is not None and _utc_now() < self._stop_retry_at:
            return False
        self._draining = True
        if deadline is None:
            deadline = asyncio.get_running_loop().time() + self._drain_timeout
        try:
            try:
                async with asyncio.timeout_at(deadline):
                    await runner.drain()
            except Exception:  # noqa: BLE001 - stop must still close the client after failed drain
                logger.warning("event_subscription_drain_incomplete", subscription_id=str(self._subscription_id))
            async with asyncio.timeout_at(deadline):
                await runner.stop()
            self._retained_content_gate |= runner.status.permanent_content_error
            task = self._task
            if task is not None and not task.done():
                task.cancel()
                _, pending = await asyncio.wait({task}, timeout=max(0.0, deadline - asyncio.get_running_loop().time()))
                if pending:
                    return self._stop_failed()
        except asyncio.CancelledError:
            self._stop_retry_at = _utc_now() + timedelta(seconds=EventSchedulingDefaults.TRANSIENT_PROBE_SECONDS)
            raise
        except Exception:  # noqa: BLE001 - retain this runner until stop is verified
            return self._stop_failed()
        self._runner = None
        self._runner_revision = self._applied = None
        self._task = None
        self._draining = False
        self._stop_retry_at = None
        return True

    def _stop_failed(self) -> bool:
        self._stop_retry_at = _utc_now() + timedelta(seconds=EventSchedulingDefaults.TRANSIENT_PROBE_SECONDS)
        logger.warning("event_subscription_stop_incomplete", subscription_id=str(self._subscription_id))
        return False

    async def retry(self) -> SubscriptionRuntimeStatus:
        """Explicitly retry local setup/teardown after correction; never clear durable holds."""
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
                    await self._runner.drain()
                else:
                    await self._stop_current(force=True, deadline=deadline)
        except Exception:  # noqa: BLE001 - retain startup/runner ownership when shutdown is incomplete
            self._draining = True
            self._stop_failed()
        return self.status
