"""Compose durable record processing without transport or process ownership."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import get_settings
from syntara.core.constants import EventSchedulingDefaults
from syntara.core.exceptions import SyntaraError
from syntara.eventstreams.core.deduplication import (
    ClaimBusy,
    ClaimLost,
    DeliveryClaim,
    DeliveryExpectation,
    DeliveryIdentity,
    DeliveryState,
    RevisionChanged,
    StorageBackpressure,
    TerminalDelivery,
    TerminalDeliveryCache,
)
from syntara.eventstreams.core.envelope import RawEvent, WorkflowEventEnvelope
from syntara.eventstreams.core.handler import ResolvedDelivery, RetryDelivery, SchedulingFailureCode
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.core.processing import (
    CONTENT_INSPECTION_PENDING,
    HeldRecord,
    InspectedRecord,
    RecordProcessingGate,
)
from syntara.eventstreams.core.results import EventDecodeFailure, EventFailureCode
from syntara.eventstreams.core.serialization import EventDecodeSuccess, JsonEventDecoder
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.admission_service import EventAdmissionService, SchedulingResult
from syntara.eventstreams.services.connection_provider import EventConnectionProvider
from syntara.eventstreams.services.deduplication_store import EventDeliveryStore
from syntara.eventstreams.services.execution_preparation_service import EventExecutionPreparationService
from syntara.eventstreams.services.subscription_service import lock_source_lifecycle
from syntara.workflows.models.workflow import Workflow

type RecordResult = ResolvedDelivery | HeldRecord
_CONTENT_CODES = frozenset(code.value for code in EventFailureCode)


class EventRecordProcessingService:
    """Use fresh, short sessions and upstream token-fenced scheduling services."""

    def __init__(
        self,
        session_factory: Callable[..., AsyncSession],
        preparation: EventExecutionPreparationService,
        admission: EventAdmissionService,
        *,
        decoder: JsonEventDecoder | None = None,
        lookup: TerminalDeliveryCache | None = None,
        gate: RecordProcessingGate | None = None,
    ) -> None:
        """Inject completed services; no Kafka client or designer grants are needed."""
        self._session_factory = session_factory
        self._preparation = preparation
        self._admission = admission
        self._lookup = lookup
        self._gate = gate
        settings = get_settings()
        self._decoder = (
            decoder
            if decoder is not None
            else JsonEventDecoder(
                max_value_bytes=settings.event_max_value_bytes,
                max_envelope_bytes=settings.event_max_envelope_bytes,
                max_headers=settings.event_max_headers,
            )
        )

    @staticmethod
    def _hold(reason: str) -> HeldRecord:
        return HeldRecord(
            reason=reason,
            retry_at=datetime.now(UTC) + timedelta(seconds=EventSchedulingDefaults.TRANSIENT_PROBE_SECONDS),
        )

    @staticmethod
    def _terminal(terminal: TerminalDelivery) -> RecordResult:
        if terminal.state == DeliveryState.REJECTED:
            # A ledger marker is not the required author-accessible activity log.
            return HeldRecord(reason="activity_log_unavailable", permanent_content_error=True)
        return ResolvedDelivery(terminal=terminal)

    def _dependency_failed(self, snapshot: SubscriptionSnapshot) -> None:
        if self._gate is not None:
            self._gate.dependency_failed(snapshot)

    def _admission_open(
        self, snapshot: SubscriptionSnapshot, admission_guard: Callable[[], bool] | None = None
    ) -> bool:
        return (admission_guard is None or admission_guard() is True) and (
            self._gate is None
            or (self._gate.admission_open(snapshot) is True and self._gate.resolution_open(snapshot) is True)
        )

    async def admission_eligible(self, snapshot: SubscriptionSnapshot) -> bool:
        """Recheck current lifecycle/resources before active fetching or new decoding."""
        try:
            async with self._session_factory() as session, session.begin():
                lifecycle = await lock_source_lifecycle(session, snapshot.source_id)
                if lifecycle is None:
                    self._dependency_failed(snapshot)
                    return False
                subscription, source = lifecycle
                current = SubscriptionSnapshot.from_models(subscription, source)
                workflow = await session.get(Workflow, snapshot.workflow_id)
                if (
                    current.subscription_id != snapshot.subscription_id
                    or current.source_generation != snapshot.source_generation
                    or current.configuration_revision != snapshot.configuration_revision
                    or current.published_version_id != snapshot.published_version_id
                    or subscription.active_source_generation != source.generation
                    or source.retired_at is not None
                    or not current.desired_enabled
                    or current.paused
                    or current.retired
                    or workflow is None
                    or not workflow.is_enabled
                    or workflow.published_version_id != snapshot.published_version_id
                ):
                    self._dependency_failed(snapshot)
                    return False
                await EventConnectionProvider(session).resolve_revision(current)
            return True
        except (SQLAlchemyError, OSError, TimeoutError):
            self._dependency_failed(snapshot)
            return False
        except (SyntaraError, ValueError):
            self._dependency_failed(snapshot)
            return False

    async def _existing(
        self, identity: DeliveryIdentity, *, cache_admitted: bool = False
    ) -> TerminalDelivery | EventDelivery | None:
        if cache_admitted and self._lookup is not None:
            try:
                terminal = await self._lookup.lookup(identity)
            except (RedisError, OSError, TimeoutError, ValueError):
                terminal = None
            if terminal is not None and terminal.identity == identity:
                return terminal
        async with self._session_factory() as session, session.begin():
            terminal = await EventDeliveryStore(session).lookup_terminal(identity)
            if terminal is not None:
                return terminal
            row = await session.get(EventDelivery, identity.digest, populate_existing=True)
            if row is None:
                return None
            if row.delivery_identity() != identity:
                msg = "Retained delivery identity mismatch"
                raise ValueError(msg)
            return EventDelivery(**row.model_dump())

    async def process(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        event: RawEvent | None,
        owner_worker_id: str,
        *,
        cache_admitted: bool = False,
        admission_guard: Callable[[], bool] | None = None,
    ) -> RecordResult:
        """Inspect evidence before reevaluation; recovery may omit the source event."""
        try:
            if cache_admitted and (
                self._gate is None
                or self._gate.resolution_open(snapshot) is not True
                or self._gate.admission_open(snapshot) is not True
            ):
                return self._hold("admission_closed")
            existing = await self._existing(identity, cache_admitted=cache_admitted)
            return await self._process_existing(
                snapshot,
                identity,
                event,
                owner_worker_id,
                existing,
                cache_admitted=cache_admitted,
                admission_guard=admission_guard,
            )
        except (SQLAlchemyError, OSError, TimeoutError):
            self._dependency_failed(snapshot)
            return self._hold("dependency_unavailable")
        except (SyntaraError, ValueError):
            return self._hold("dependency_unavailable")

    async def _process_existing(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        event: RawEvent | None,
        owner_worker_id: str,
        existing: TerminalDelivery | EventDelivery | None,
        *,
        cache_admitted: bool,
        admission_guard: Callable[[], bool] | None,
    ) -> RecordResult:
        if isinstance(existing, TerminalDelivery):
            if cache_admitted and self._gate is not None and self._gate.resolution_open(snapshot) is not True:
                return self._hold("dependency_unavailable")
            return self._terminal(existing)
        if existing is not None and existing.frozen_binding is not None:
            return await self._prepare_and_schedule(snapshot, identity, None, owner_worker_id)
        if existing is not None and existing.last_error_code in _CONTENT_CODES:
            return HeldRecord(reason="activity_log_unavailable", permanent_content_error=True)
        if existing is not None and existing.last_error_code == CONTENT_INSPECTION_PENDING and event is None:
            return self._hold(CONTENT_INSPECTION_PENDING)
        return await self._process_new(snapshot, identity, event, owner_worker_id, admission_guard=admission_guard)

    async def hold_content_failure(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        failure: EventDecodeFailure,
        owner_worker_id: str,
        *,
        admission_guard: Callable[[], bool] | None = None,
    ) -> RecordResult:
        """Persist a bounded content error when its source bytes cannot be queued.

        The adapter supplies only a proven size/header failure and its identity.
        Retained evidence still wins before any new error decision is persisted.
        """
        try:
            existing = await self._existing(identity)
            if isinstance(existing, TerminalDelivery):
                return self._terminal(existing)
            if existing is not None and existing.frozen_binding is not None:
                return await self._prepare_and_schedule(snapshot, identity, None, owner_worker_id)
            if existing is not None and existing.last_error_code in _CONTENT_CODES:
                return HeldRecord(reason="activity_log_unavailable", permanent_content_error=True)
            if not await self.admission_eligible(snapshot) or not self._admission_open(snapshot, admission_guard):
                return self._hold("admission_closed")
            return await self._block_content(
                snapshot, identity, failure, owner_worker_id, admission_guard=admission_guard
            )
        except (SQLAlchemyError, OSError, TimeoutError, SyntaraError, ValueError) as exc:
            if isinstance(exc, (SQLAlchemyError, OSError, TimeoutError)):
                self._dependency_failed(snapshot)
            return self._hold("dependency_unavailable")

    async def _process_new(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        event: RawEvent | None,
        owner_worker_id: str,
        *,
        admission_guard: Callable[[], bool] | None = None,
    ) -> RecordResult:
        if event is None:
            return self._hold("delivery_evidence_unavailable")
        if (
            not self._admission_open(snapshot, admission_guard)
            or not await self.admission_eligible(snapshot)
            or not self._admission_open(snapshot, admission_guard)
        ):
            return self._hold("admission_closed")
        decoded = await self._inspect_content(
            snapshot, identity, event, owner_worker_id, keep_pending=True, admission_guard=admission_guard
        )
        if not isinstance(decoded, EventDecodeSuccess):
            return decoded
        return await self._prepare_and_schedule(
            snapshot, identity, decoded.envelope, owner_worker_id, admission_guard=admission_guard
        )

    async def inspect_only(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        event: RawEvent,
        owner_worker_id: str,
        *,
        admission_guard: Callable[[], bool] | None = None,
    ) -> RecordResult | InspectedRecord:
        """Inspect delivered content behind a fence without new workflow admission."""
        try:
            existing = await self._existing(identity)
            if isinstance(existing, TerminalDelivery):
                return self._terminal(existing)
            if existing is not None and existing.frozen_binding is not None:
                return await self._prepare_and_schedule(snapshot, identity, None, owner_worker_id)
            if existing is not None and existing.last_error_code in _CONTENT_CODES:
                return HeldRecord(reason="activity_log_unavailable", permanent_content_error=True)
            result = await self._inspect_content(
                snapshot, identity, event, owner_worker_id, admission_guard=admission_guard
            )
            return InspectedRecord(identity=identity) if isinstance(result, EventDecodeSuccess) else result
        except (SQLAlchemyError, OSError, TimeoutError):
            self._dependency_failed(snapshot)
            return self._hold("dependency_unavailable")
        except (SyntaraError, ValueError):
            return self._hold("dependency_unavailable")

    @classmethod
    def _inspection_hold(
        cls, result: ClaimBusy | ClaimLost | TerminalDelivery | RevisionChanged | StorageBackpressure | HeldRecord
    ) -> RecordResult:
        if isinstance(result, TerminalDelivery):
            return cls._terminal(result)
        if isinstance(result, HeldRecord):
            return result
        if isinstance(result, ClaimBusy):
            return HeldRecord(reason="claim_busy", retry_at=result.lease_until)
        return cls._hold(result.reason)

    async def _inspect_content(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        event: RawEvent | EventDecodeFailure,
        owner_worker_id: str,
        *,
        keep_pending: bool = False,
        admission_guard: Callable[[], bool] | None = None,
    ) -> EventDecodeSuccess | RecordResult:
        async with self._session_factory() as session, session.begin():
            if admission_guard is not None and admission_guard() is not True:
                return self._hold("admission_closed")
            acquired = await EventDeliveryStore(session).acquire_inspection(
                identity,
                DeliveryExpectation(
                    published_version_id=snapshot.published_version_id,
                    configuration_revision=snapshot.configuration_revision,
                ),
                owner_worker_id,
            )
        if not isinstance(acquired, DeliveryClaim):
            return self._inspection_hold(acquired)
        # No source content is classified until the unknown-content marker commits.
        decoded = (
            event
            if isinstance(event, EventDecodeFailure)
            else self._decoder.decode(event, schema=snapshot.model_dump(mode="json")["input_schema"])
        )
        failure = decoded if isinstance(decoded, EventDecodeFailure) else None
        async with self._session_factory() as session, session.begin():
            lost = await EventDeliveryStore(session).finish_inspection(acquired, failure, keep_pending=keep_pending)
        if lost is not None:
            return self._hold("inspection_claim_lost")
        if isinstance(decoded, EventDecodeFailure):
            return HeldRecord(reason="activity_log_unavailable", permanent_content_error=True)
        return decoded

    async def _prepare_and_schedule(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        envelope: WorkflowEventEnvelope | None,
        owner_worker_id: str,
        *,
        admission_guard: Callable[[], bool] | None = None,
    ) -> RecordResult:
        if envelope is not None and not self._admission_open(snapshot, admission_guard):
            return self._hold("admission_closed")
        prepared = await self._preparation.prepare_delivery(snapshot, identity, envelope, owner_worker_id)
        if isinstance(prepared, TerminalDelivery):
            return self._terminal(prepared)
        if isinstance(prepared, EventDecodeFailure):
            return await self._block_content(
                snapshot, identity, prepared, owner_worker_id, admission_guard=admission_guard
            )
        if isinstance(prepared, ClaimBusy):
            return HeldRecord(reason="claim_busy", retry_at=prepared.lease_until)
        if not isinstance(prepared, PreparedExecution):
            return self._hold(prepared.reason)
        scheduled = await self._admission.schedule(prepared)
        if not isinstance(scheduled, (ResolvedDelivery, ClaimLost)) and scheduled.error_code in {
            SchedulingFailureCode.STORAGE_UNAVAILABLE,
            SchedulingFailureCode.ATTEMPT_UNCERTAIN,
        }:
            self._dependency_failed(snapshot)
        return self._scheduled(scheduled)

    def _scheduled(self, scheduled: SchedulingResult) -> RecordResult:
        if isinstance(scheduled, ResolvedDelivery):
            return self._terminal(scheduled.terminal)
        if isinstance(scheduled, RetryDelivery):
            return HeldRecord(reason=scheduled.error_code.value, retry_at=scheduled.next_attempt_at)
        return self._hold("scheduling_unresolved")

    async def _block_content(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        failure: EventDecodeFailure,
        owner_worker_id: str,
        *,
        admission_guard: Callable[[], bool] | None = None,
    ) -> RecordResult:
        """Commit safe unresolved evidence, never an internal rejection shortcut."""
        result = await self._inspect_content(
            snapshot, identity, failure, owner_worker_id, admission_guard=admission_guard
        )
        return self._hold("inspection_evidence_mismatch") if isinstance(result, EventDecodeSuccess) else result
