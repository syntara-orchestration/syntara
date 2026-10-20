"""Token-fenced scheduling of prepared executions; no broker operations."""

import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import get_settings
from syntara.core.constants import EventSchedulingDefaults
from syntara.core.exceptions import SafeValueError
from syntara.eventstreams.core.deduplication import ClaimLost, DeliveryClaim, TemporalAcceptance, TerminalDelivery
from syntara.eventstreams.core.handler import (
    BlockedDelivery,
    EventLaunchError,
    ResolvedDelivery,
    RetryDelivery,
    SchedulingFailureCode,
    WorkflowLauncher,
)
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.core.scheduling_metadata import EVENT_DELIVERY_METADATA_KEY
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.connection_provider import EventConnectionProvider
from syntara.eventstreams.services.deduplication_store import EventDeliveryStore
from syntara.eventstreams.services.execution_preparation_service import EventExecutionPreparationService
from syntara.eventstreams.services.subscription_service import lock_source_lifecycle
from syntara.integrations.exceptions import IntegrationCredentialNotFoundError
from syntara.workflows.models.execution import Execution

type SchedulingResult = ResolvedDelivery | RetryDelivery | BlockedDelivery | ClaimLost
_STORAGE_ERRORS = (SQLAlchemyError, OSError, TimeoutError)


class EventAdmissionService:
    """Own separate short transactions around finite, isolated Temporal calls."""

    def __init__(self, session_factory: Callable[..., AsyncSession], launcher: WorkflowLauncher) -> None:
        """Inject the database factory and signed Temporal adapter."""
        self._session_factory = session_factory
        self._launcher = launcher
        self._preparation = EventExecutionPreparationService(session_factory)

    async def schedule(self, prepared: PreparedExecution) -> SchedulingResult:
        """Reload frozen arguments; a caller's mutable dictionaries are never authoritative."""
        return await self.recover_claim(prepared.claim)

    async def recover_claim(self, claim: DeliveryClaim) -> SchedulingResult:
        """Recover a current claim without a consumer, ownership epoch, or new reservation."""
        try:
            try:
                prepared = await self._reload(claim)
                if isinstance(prepared, TerminalDelivery):
                    return ResolvedDelivery(terminal=prepared)
                if isinstance(prepared, ClaimLost):
                    return prepared
                return await self._schedule(prepared)
            except ValueError:
                return await self._failure(
                    claim, EventLaunchError(SchedulingFailureCode.EVIDENCE_MISMATCH, transient=False)
                )
        except _STORAGE_ERRORS:
            return BlockedDelivery(error_code=SchedulingFailureCode.STORAGE_UNAVAILABLE)
        except ValueError:
            return BlockedDelivery(error_code=SchedulingFailureCode.EVIDENCE_MISMATCH)

    async def _reload(self, claim: DeliveryClaim) -> PreparedExecution | TerminalDelivery | ClaimLost:
        async with self._session_factory() as session, session.begin():
            terminal = await EventDeliveryStore(session).lookup_terminal(claim.identity)
            if terminal is not None:
                return terminal
            lifecycle = await lock_source_lifecycle(session, claim.identity.source_id)
            if lifecycle is None:
                return ClaimLost()
            snapshot = SubscriptionSnapshot.from_models(*lifecycle)
        result = await self._preparation.prepare_delivery(
            snapshot, claim.identity, None, claim.owner_worker_id, claim=claim
        )
        if isinstance(result, (PreparedExecution, TerminalDelivery, ClaimLost)):
            return result
        return ClaimLost()

    async def _schedule(self, prepared: PreparedExecution) -> SchedulingResult:
        if prepared.claim.attempt_count:
            recovered = await self._recover_previous(prepared)
            if recovered is not None:
                return recovered
        try:
            retention = await self._verified_retention()
            attempted = await self._record_attempt(prepared, retention)
            if isinstance(attempted, (ClaimLost, TerminalDelivery)):
                return ResolvedDelivery(terminal=attempted) if isinstance(attempted, TerminalDelivery) else attempted
            prepared = prepared.model_copy(update={"claim": attempted})
            acceptance = await self._launcher.start(prepared)
        except EventLaunchError as exc:
            return await self._recover_failed_start(prepared, exc)
        return await self._confirm(prepared, acceptance)

    async def _recover_previous(self, prepared: PreparedExecution) -> SchedulingResult | None:
        claim = prepared.claim
        try:
            acceptance = await self._launcher.describe(prepared)
        except EventLaunchError as exc:
            if exc.transient and (
                claim.start_retry_deadline is None or datetime.now(UTC) >= claim.start_retry_deadline
            ):
                return await self._failure(
                    claim, EventLaunchError(SchedulingFailureCode.HISTORY_EXPIRED, transient=False)
                )
            if exc.code != SchedulingFailureCode.TEMPORAL_NOT_FOUND:
                return await self._failure(claim, exc)
            if claim.temporal_run_id is not None:
                return await self._failure(
                    claim, EventLaunchError(SchedulingFailureCode.HISTORY_EXPIRED, transient=False)
                )
            # Not-found alone is insufficient. The persisted duplicate-protection
            # window and frozen availability must also permit another start.
            return None
        return await self._confirm(prepared, acceptance)

    async def _verified_retention(self) -> int:
        retention = get_settings().event_temporal_history_retention_seconds
        if await self._launcher.history_retention_seconds() < retention:
            raise EventLaunchError(SchedulingFailureCode.HISTORY_UNAVAILABLE, transient=False)
        return retention

    async def _recover_failed_start(self, prepared: PreparedExecution, failure: EventLaunchError) -> SchedulingResult:
        if failure.code != SchedulingFailureCode.TEMPORAL_UNAVAILABLE:
            return await self._failure(prepared.claim, failure)
        # A timeout may have accepted the start. Verification precedes retry.
        try:
            acceptance = await self._launcher.describe(prepared)
        except EventLaunchError as recovery:
            if recovery.code == SchedulingFailureCode.TEMPORAL_NOT_FOUND or (
                recovery.transient and not failure.transient
            ):
                recovery = failure
            return await self._failure(prepared.claim, recovery)
        return await self._confirm(prepared, acceptance)

    async def _record_attempt(
        self, prepared: PreparedExecution, retention: int
    ) -> DeliveryClaim | TerminalDelivery | ClaimLost:
        attempt_id = uuid4()
        try:
            return await self._write_attempt(prepared, retention, attempt_id)
        except _STORAGE_ERRORS:
            # The commit may have succeeded. Reconcile in a fresh transaction under
            # the same token before allowing the corresponding start invocation.
            return await self._reconcile_attempt(prepared, attempt_id)

    @staticmethod
    def _retry_deadline(claim: DeliveryClaim, now: datetime, retention: int) -> datetime:
        deadline = (claim.first_start_attempt_at or now) + timedelta(
            seconds=retention - EventSchedulingDefaults.HISTORY_SAFETY_MARGIN_SECONDS
        )
        if claim.attempt_count and claim.start_retry_deadline is None:
            raise EventLaunchError(SchedulingFailureCode.HISTORY_EXPIRED, transient=False)
        if claim.start_retry_deadline is not None:
            deadline = min(deadline, claim.start_retry_deadline)
        if now >= deadline:
            raise EventLaunchError(SchedulingFailureCode.HISTORY_EXPIRED, transient=False)
        return deadline

    @staticmethod
    async def _check_runtime(session: AsyncSession, prepared: PreparedExecution, claim: DeliveryClaim) -> None:
        execution = await session.get(Execution, prepared.execution_id)
        if execution is None:
            raise EventLaunchError(SchedulingFailureCode.EVIDENCE_MISMATCH, transient=False)
        try:
            await EventConnectionProvider(session).resolve_frozen(claim, execution.project_id)
        except (SafeValueError, IntegrationCredentialNotFoundError):
            raise EventLaunchError(SchedulingFailureCode.RUNTIME_UNAVAILABLE, transient=False) from None

    async def _write_attempt(
        self, prepared: PreparedExecution, retention: int, attempt_id: UUID
    ) -> DeliveryClaim | ClaimLost:
        async with self._session_factory() as session, session.begin():
            store = EventDeliveryStore(session)
            current = await store.renew(prepared.claim)
            if isinstance(current, ClaimLost):
                return current
            now = (await session.exec(select(func.clock_timestamp()))).one()
            deadline = self._retry_deadline(current, now, retention)
            await self._check_runtime(session, prepared, current)
            attempted = await store.record_start_attempt(current, retry_deadline=deadline, attempt_id=attempt_id)
        return attempted  # noqa: RET504 - RPC is forbidden before commit

    async def _reconcile_attempt(
        self, prepared: PreparedExecution, attempt_id: UUID
    ) -> DeliveryClaim | TerminalDelivery | ClaimLost:
        claim = prepared.claim
        async with self._session_factory() as session, session.begin():
            store = EventDeliveryStore(session)
            terminal = await store.lookup_terminal(claim.identity)
            if terminal is not None:
                return terminal
            reconciled = await store.renew(claim)
            if isinstance(reconciled, ClaimLost):
                return reconciled
            execution = await session.get(
                Execution, prepared.execution_id, with_for_update=True, populate_existing=True
            )
            if (
                execution is None
                or (execution.execution_metadata or {}).get(EVENT_DELIVERY_METADATA_KEY, {}).get("start_attempt_id")
                != str(attempt_id)
                or reconciled.attempt_count == 0
                or reconciled.start_retry_deadline is None
                or reconciled.first_start_attempt_at is None
            ):
                raise EventLaunchError(SchedulingFailureCode.ATTEMPT_UNCERTAIN)
            now = (await session.exec(select(func.clock_timestamp()))).one()
            if now >= reconciled.start_retry_deadline:
                raise EventLaunchError(SchedulingFailureCode.HISTORY_EXPIRED, transient=False)
            # Availability is checked again after the uncertain transaction.
            await self._check_runtime(session, prepared, reconciled)
        return reconciled

    async def _confirm(self, prepared: PreparedExecution, acceptance: TemporalAcceptance) -> SchedulingResult:
        try:
            async with self._session_factory() as session, session.begin():
                result = await EventDeliveryStore(session).finalize_scheduled(prepared.claim, acceptance)
            return ResolvedDelivery(terminal=result) if isinstance(result, TerminalDelivery) else result
        except _STORAGE_ERRORS:
            # A lost commit response may already have resolved scheduling.
            async with self._session_factory() as session, session.begin():
                store = EventDeliveryStore(session)
                terminal = await store.lookup_terminal(prepared.claim.identity)
                if terminal is not None:
                    return ResolvedDelivery(terminal=terminal)
                recorded = await store.record_acceptance(prepared.claim, acceptance)
            if isinstance(recorded, ClaimLost):
                return recorded
            return await self._failure(recorded, EventLaunchError(SchedulingFailureCode.STORAGE_UNAVAILABLE))

    async def _failure(self, claim: DeliveryClaim, failure: EventLaunchError) -> SchedulingResult:
        failures = claim.scheduling_failure_count + 1
        circuit_open = failures >= EventSchedulingDefaults.IMMEDIATE_ATTEMPTS
        async with self._session_factory() as session, session.begin():
            now = (await session.exec(select(func.clock_timestamp()))).one()
            if failure.transient:
                delay = (
                    EventSchedulingDefaults.TRANSIENT_PROBE_SECONDS
                    if circuit_open
                    else min(
                        EventSchedulingDefaults.MAX_BACKOFF_SECONDS,
                        2 ** (failures - 1) * random.uniform(0.9, 1.1),  # noqa: S311 - retry jitter, not a secret
                    )
                )
                next_attempt = now + timedelta(seconds=delay)
            else:
                next_attempt = datetime.max.replace(tzinfo=UTC)
            result = await EventDeliveryStore(session).record_scheduling_failure(
                claim, next_attempt_at=next_attempt, error_code=failure.code.value
            )
        if isinstance(result, ClaimLost):
            return result
        if not failure.transient:
            return BlockedDelivery(error_code=failure.code)
        return RetryDelivery(error_code=failure.code, next_attempt_at=next_attempt, circuit_open=circuit_open)
