"""Start the stable Temporal identity, then persist the normal Execution."""

from collections.abc import Callable
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.constants import EventSchedulingDefaults
from syntara.eventstreams.core.deduplication import DeliveryIdentity, TemporalAcceptance
from syntara.eventstreams.core.handler import (
    BlockedDelivery,
    EventLaunchError,
    ResolvedDelivery,
    RetryDelivery,
    SchedulingFailureCode,
    WorkflowLauncher,
)
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.services.execution_store import EventExecutionStore
from syntara.eventstreams.services.worker_resources import EventWorkerResources

type SchedulingResult = ResolvedDelivery | RetryDelivery | BlockedDelivery
_STORAGE_ERRORS = (SQLAlchemyError, OSError, TimeoutError)


class EventAdmissionService:
    """Keep database transactions separate from finite Temporal requests."""

    def __init__(
        self,
        session_factory: Callable[..., AsyncSession],
        launcher: WorkflowLauncher,
        *,
        resources: EventWorkerResources | None = None,
    ) -> None:
        """Receive process-owned dependencies without retaining a session."""
        self._sessions = session_factory
        self._launcher = launcher
        self._resources = resources

    def _storage_failed(self) -> BlockedDelivery:
        if self._resources is not None:
            self._resources.database_failed()
        return BlockedDelivery(error_code=SchedulingFailureCode.STORAGE_UNAVAILABLE)

    @staticmethod
    def _failure(failure: EventLaunchError) -> RetryDelivery | BlockedDelivery:
        if not failure.transient:
            return BlockedDelivery(error_code=failure.code)
        return RetryDelivery(
            error_code=failure.code,
            next_attempt_at=datetime.now(UTC) + timedelta(seconds=EventSchedulingDefaults.MAX_BACKOFF_SECONDS),
            circuit_open=False,
        )

    async def lookup_execution(self, identity: DeliveryIdentity) -> SchedulingResult | None:
        """Reuse a retained Execution without making a preliminary Temporal call."""
        try:
            async with self._sessions() as session, session.begin():
                terminal = await EventExecutionStore(session).lookup(identity)
            return ResolvedDelivery(terminal=terminal) if terminal is not None else None
        except _STORAGE_ERRORS:
            return self._storage_failed()
        except (TypeError, ValueError):
            return BlockedDelivery(error_code=SchedulingFailureCode.EVIDENCE_MISMATCH)

    async def recover_accepted(self, identity: DeliveryIdentity) -> SchedulingResult | None:
        """Recover an unfinished handoff using original signed Temporal arguments."""
        existing = await self.lookup_execution(identity)
        if existing is not None:
            return existing
        try:
            accepted = await self._launcher.lookup(identity)
            return await self._confirm(accepted.preparation(), accepted.acceptance)
        except EventLaunchError as exc:
            return None if exc.code == SchedulingFailureCode.TEMPORAL_NOT_FOUND else self._failure(exc)
        except _STORAGE_ERRORS:
            return self._storage_failed()
        except (TypeError, ValueError):
            return BlockedDelivery(error_code=SchedulingFailureCode.EVIDENCE_MISMATCH)

    async def schedule(self, prepared: PreparedExecution) -> SchedulingResult:
        """Start detached arguments without a pre-start Execution or delivery write."""
        prepared = prepared.model_copy(deep=True)
        if self._resources is not None and not self._resources.scheduling_open:
            return BlockedDelivery(error_code=SchedulingFailureCode.STORAGE_UNAVAILABLE)
        try:
            acceptance = await self._launcher.start(prepared)
        except EventLaunchError as exc:
            return await self._recover_failed_start(prepared, exc)
        except (TypeError, ValueError):
            return BlockedDelivery(error_code=SchedulingFailureCode.EVIDENCE_MISMATCH)
        return await self._confirm(prepared, acceptance)

    async def _recover_failed_start(self, prepared: PreparedExecution, failure: EventLaunchError) -> SchedulingResult:
        if failure.code not in {SchedulingFailureCode.TEMPORAL_UNAVAILABLE, SchedulingFailureCode.EVIDENCE_MISMATCH}:
            return self._failure(failure)
        try:
            accepted = await self._launcher.lookup(prepared.identity)
        except EventLaunchError as exc:
            return self._failure(failure if exc.code == SchedulingFailureCode.TEMPORAL_NOT_FOUND else exc)
        return await self._confirm(accepted.preparation(), accepted.acceptance)

    async def _persist(self, prepared: PreparedExecution, acceptance: TemporalAcceptance) -> ResolvedDelivery:
        async with self._sessions() as session, session.begin():
            terminal = await EventExecutionStore(session).persist(prepared, acceptance)
        return ResolvedDelivery(terminal=terminal)

    async def _confirm(self, prepared: PreparedExecution, acceptance: TemporalAcceptance) -> SchedulingResult:
        async with self._resources.finalization if self._resources is not None else nullcontext():
            try:
                return await self._persist(prepared, acceptance)
            except _STORAGE_ERRORS:
                # Retry identical accepted arguments after a lost commit response.
                if self._resources is not None:
                    self._resources.database_failed()
                try:
                    return await self._persist(prepared, acceptance)
                except _STORAGE_ERRORS:
                    return self._storage_failed()
                except (TypeError, ValueError):
                    return BlockedDelivery(error_code=SchedulingFailureCode.EVIDENCE_MISMATCH)
            except (TypeError, ValueError):
                return BlockedDelivery(error_code=SchedulingFailureCode.EVIDENCE_MISMATCH)
