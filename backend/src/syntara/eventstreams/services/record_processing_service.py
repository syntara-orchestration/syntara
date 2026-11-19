"""Filter locally before Execution lookup and new Kafka workflow admission."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.core.config.base import get_settings
from syntara.core.constants import EventSchedulingDefaults
from syntara.core.exceptions import SyntaraError
from syntara.eventstreams.adapters.record_identity import record_matches_metadata, record_matches_source
from syntara.eventstreams.audit.record_rejection import EventRecordRejectedEvent
from syntara.eventstreams.core.deduplication import DeliveryIdentity
from syntara.eventstreams.core.envelope import RawEvent
from syntara.eventstreams.core.filter_input import EventFilterInput, FilterPayload
from syntara.eventstreams.core.handler import ResolvedDelivery, RetryDelivery, SchedulingFailureCode
from syntara.eventstreams.core.preparation import ExecutionCapacityUnavailable, PreparedExecution
from syntara.eventstreams.core.processing import HeldRecord, InspectedRecord, RecordProcessingGate, SkippedRecord
from syntara.eventstreams.core.results import EventDecodeFailure
from syntara.eventstreams.core.serialization import EventDecodeSuccess, JsonEventDecoder
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services.admission_service import EventAdmissionService, SchedulingResult
from syntara.eventstreams.services.connection_provider import EventConnectionProvider
from syntara.eventstreams.services.execution_preparation_service import EventExecutionPreparationService
from syntara.eventstreams.services.subscription_service import lock_source_lifecycle
from syntara.filtering.models.result import FilterOutcome, FilterResult
from syntara.workflows.models.workflow import Workflow

type RecordResult = ResolvedDelivery | HeldRecord | SkippedRecord
type HandoffReservation = Callable[[PreparedExecution], bool]
logger = structlog.stdlib.get_logger(__name__)


class EventRecordProcessingService:
    """Keep unresolved work queued; classify local skips without activity-log dependencies."""

    def __init__(
        self,
        session_factory: Callable[..., AsyncSession],
        preparation: EventExecutionPreparationService,
        admission: EventAdmissionService,
        *,
        decoder: JsonEventDecoder | None = None,
        gate: RecordProcessingGate | None = None,
    ) -> None:
        """Receive normal Execution services, decoding and process-owned admission gates."""
        self._sessions, self._preparation, self._admission, self._gate = session_factory, preparation, admission, gate
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
            retry_at=datetime.now(UTC) + timedelta(seconds=EventSchedulingDefaults.MAX_BACKOFF_SECONDS),
        )

    def _dependency_failed(self, snapshot: SubscriptionSnapshot) -> None:
        if self._gate is not None:
            self._gate.dependency_failed(snapshot)

    def _admission_open(self, snapshot: SubscriptionSnapshot, guard: Callable[[], bool] | None = None) -> bool:
        return (guard is None or guard() is True) and (
            self._gate is None
            or (self._gate.admission_open(snapshot) is True and self._gate.resolution_open(snapshot) is True)
        )

    async def admission_eligible(self, snapshot: SubscriptionSnapshot) -> bool:
        """Recheck current publication and source credentials before admitting new work."""
        try:
            async with self._sessions() as session, session.begin():
                lifecycle = await lock_source_lifecycle(session, snapshot.source_id)
                if lifecycle is None:
                    return False
                subscription, source = lifecycle
                workflow = await session.get(Workflow, snapshot.workflow_id)
                if (
                    subscription.id != snapshot.subscription_id
                    or source.id != snapshot.source_id
                    or subscription.configuration_revision != snapshot.configuration_revision
                    or subscription.published_version_id != snapshot.published_version_id
                    or subscription.active_source_generation != source.generation
                    or source.retired_at is not None
                    or not subscription.desired_enabled
                    or subscription.paused
                    or subscription.retired
                    or workflow is None
                    or not workflow.is_enabled
                    or workflow.published_version_id != snapshot.published_version_id
                ):
                    return False
                await EventConnectionProvider(session).resolve_revision(snapshot)
            return True
        except (SQLAlchemyError, OSError, TimeoutError):
            self._dependency_failed(snapshot)
            return False
        except (SyntaraError, ValueError):
            return False

    @asynccontextmanager
    async def local_skip_commit_guard(self, snapshot: SubscriptionSnapshot) -> AsyncIterator[bool]:
        """Serialize a skip batch's checkpoint with publication on its source.

        Keep the lifecycle locks until the broker commit settles or its group
        membership is fenced, even after the caller stops waiting. A
        reconciled local gate alone cannot fence a publication it has not seen.
        Already completed skips may drain after local admission closes.
        """
        async with self._sessions() as session, session.begin():
            lifecycle = await lock_source_lifecycle(session, snapshot.source_id)
            if lifecycle is None:
                yield False
                return
            subscription, source = lifecycle
            yield (
                subscription.id == snapshot.subscription_id
                and subscription.workflow_id == snapshot.workflow_id
                and subscription.configuration_revision == snapshot.configuration_revision
                and subscription.published_version_id == snapshot.published_version_id
                and subscription.active_source_generation == source.generation == snapshot.source_generation
                and source.id == snapshot.source_id
                and source.retired_at is None
            )

    def _scheduled(self, snapshot: SubscriptionSnapshot, result: SchedulingResult) -> ResolvedDelivery | HeldRecord:
        if isinstance(result, ResolvedDelivery):
            return result
        if result.error_code == SchedulingFailureCode.STORAGE_UNAVAILABLE:
            self._dependency_failed(snapshot)
        if isinstance(result, RetryDelivery):
            return HeldRecord(reason=result.error_code.value, retry_at=result.next_attempt_at)
        return self._hold(result.error_code.value)

    async def _accepted(
        self, snapshot: SubscriptionSnapshot, identity: DeliveryIdentity, *, recover: bool = False
    ) -> ResolvedDelivery | HeldRecord | None:
        result = await (
            self._admission.recover_accepted(identity) if recover else self._admission.lookup_execution(identity)
        )
        return None if result is None else self._scheduled(snapshot, result)

    async def process(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        event: RawEvent | None,
        *,
        admission_guard: Callable[[], bool] | None = None,
        handoff: PreparedExecution | None = None,
        reserve_handoff: HandoffReservation | None = None,
        matched_at: datetime | None = None,
        remember_match: Callable[[datetime], None] | None = None,
    ) -> RecordResult:
        """Complete local skips before I/O; look up Execution only for valid matches."""
        try:
            if handoff is not None:
                if handoff.identity != identity:
                    return self._hold("delivery_evidence_mismatch")
                return await self._resume_handoff(snapshot, handoff, admission_guard)
            if event is None:
                accepted = await self._accepted(snapshot, identity, recover=True)
                return accepted if accepted is not None else self._hold("admission_closed")
            decoded = self._decode_event(snapshot, identity, event, admission_guard, matched_at)
            # The queue owns the raw bytes until preparation converts its reservation.
            del event
            if isinstance(decoded, (SkippedRecord, HeldRecord)):
                return decoded
            result: RecordResult
            if isinstance(decoded, EventDecodeFailure):
                result = await self.hold_content_failure(snapshot, identity, decoded, admission_guard=admission_guard)
            else:
                if remember_match is not None:
                    remember_match(decoded.envelope.source_metadata.received_at)
                result = await self._process_match(
                    snapshot, identity, decoded, admission_guard, reserve_handoff, recover=matched_at is not None
                )
            return result
        except (SQLAlchemyError, OSError, TimeoutError, SyntaraError, ValueError) as exc:
            if isinstance(exc, (SQLAlchemyError, OSError, TimeoutError)):
                self._dependency_failed(snapshot)
            return self._hold("dependency_unavailable").model_copy(update={"handoff": handoff})

    def _decode_event(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        event: RawEvent,
        guard: Callable[[], bool] | None,
        matched_at: datetime | None = None,
    ) -> EventDecodeSuccess | EventDecodeFailure | SkippedRecord | HeldRecord:
        """Validate trusted coordinates and complete local filter outcomes before I/O."""
        if not self._event_matches(snapshot, identity, event):
            return self._hold("delivery_evidence_mismatch")
        if not self._admission_open(snapshot, guard):
            return self._hold("admission_closed")
        if matched_at is not None:
            metadata = event.source_metadata.model_copy(update={"received_at": matched_at})
            return self._decode_payload(snapshot, event.model_copy(update={"source_metadata": metadata}))
        decoded = self.evaluate_filter(snapshot, identity, event)
        if isinstance(decoded, SkippedRecord) and not self._admission_open(snapshot, guard):
            return self._hold("admission_closed")
        return decoded

    def inspect_unbuffered(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        event: RawEvent,
        *,
        admission_guard: Callable[[], bool] | None = None,
    ) -> InspectedRecord | EventDecodeFailure | SkippedRecord | HeldRecord:
        """Classify the payload while its bytes are available, without downstream I/O."""
        decoded = self._decode_event(snapshot, identity, event, admission_guard)
        return InspectedRecord(identity=identity) if isinstance(decoded, EventDecodeSuccess) else decoded

    async def _process_match(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        decoded: EventDecodeSuccess,
        guard: Callable[[], bool] | None,
        reserve_handoff: HandoffReservation | None,
        *,
        recover: bool = False,
    ) -> RecordResult:
        """Reuse an existing Execution before checking admission for a direct start."""
        accepted = await self._accepted(snapshot, identity, recover=recover)
        if accepted is not None:
            return accepted
        if not self._admission_open(snapshot, guard) or not await self.admission_eligible(snapshot):
            return self._hold("admission_closed")
        return await self._prepare_and_schedule(snapshot, identity, decoded, guard, reserve_handoff)

    async def _resume_handoff(
        self, snapshot: SubscriptionSnapshot, prepared: PreparedExecution, guard: Callable[[], bool] | None
    ) -> RecordResult:
        """Keep attempted arguments through local retries, even after admission closes."""
        accepted = await self._accepted(snapshot, prepared.identity, recover=True)
        if accepted is not None:
            return accepted.model_copy(update={"handoff": prepared}) if isinstance(accepted, HeldRecord) else accepted
        if not self._admission_open(snapshot, guard) or not await self.admission_eligible(snapshot):
            return self._hold("admission_closed").model_copy(update={"handoff": prepared})
        return await self._schedule(snapshot, prepared, already_retained=True)

    async def _schedule(
        self,
        snapshot: SubscriptionSnapshot,
        prepared: PreparedExecution,
        *,
        reserve_handoff: HandoffReservation | None = None,
        already_retained: bool = False,
    ) -> RecordResult:
        if reserve_handoff is not None and not reserve_handoff(prepared):
            return await self._accepted(snapshot, prepared.identity, recover=True) or self._hold("queue_capacity")
        scheduled = await self._admission.schedule(prepared)
        result = self._scheduled(snapshot, scheduled)
        if isinstance(scheduled, ResolvedDelivery):
            return scheduled
        # A rejection of a retry cannot clear an earlier ambiguous submission.
        if scheduled.start_rejected and not already_retained:
            return result.model_copy(update={"handoff_rejected": True})
        return result.model_copy(update={"handoff": prepared})

    async def _prepare_and_schedule(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        decoded: EventDecodeSuccess,
        guard: Callable[[], bool] | None,
        reserve_handoff: HandoffReservation | None,
    ) -> RecordResult:
        if not self._admission_open(snapshot, guard):
            return self._hold("admission_closed")
        prepared = await self._preparation.prepare_delivery(snapshot, identity, decoded.envelope)
        if isinstance(prepared, EventDecodeFailure):
            return await self.hold_content_failure(snapshot, identity, prepared, admission_guard=guard)
        if isinstance(prepared, ExecutionCapacityUnavailable):
            return await self._accepted(snapshot, identity, recover=True) or self._hold(prepared.reason)
        if not isinstance(prepared, PreparedExecution):
            return self._hold(prepared.reason)
        if not self._admission_open(snapshot, guard):
            return self._hold("admission_closed")
        return await self._schedule(snapshot, prepared, reserve_handoff=reserve_handoff)

    async def inspect_only(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        event: RawEvent,
        *,
        apply_filter: bool = False,
        admission_guard: Callable[[], bool] | None = None,
    ) -> RecordResult | InspectedRecord:
        """Resolve accepted work or inspect delivered content without starting a workflow."""
        if not self._event_matches(snapshot, identity, event):
            return self._hold("delivery_evidence_mismatch")
        # Inspection grants no start or commit permission. It must remain
        # available behind the partition fence that requested this drain.
        if apply_filter and not self._admission_open(snapshot, admission_guard):
            return self._hold("admission_closed")
        decoded = self.evaluate_filter(snapshot, identity, event)
        if isinstance(decoded, SkippedRecord):
            if apply_filter:
                return decoded if self._admission_open(snapshot, admission_guard) else self._hold("admission_closed")
            return InspectedRecord(identity=identity)
        if isinstance(decoded, EventDecodeFailure) and apply_filter:
            return await self.hold_content_failure(snapshot, identity, decoded, admission_guard=admission_guard)
        accepted = await self._accepted(snapshot, identity, recover=not apply_filter)
        if accepted is None and isinstance(decoded, EventDecodeFailure):
            self._audit_content_failure(snapshot, identity, decoded)
        return accepted if accepted is not None else InspectedRecord(identity=identity)

    async def hold_content_failure(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        failure: EventDecodeFailure,
        *,
        admission_guard: Callable[[], bool] | None = None,
    ) -> RecordResult:
        """Recover accepted work or classify proven invalid content under current gates."""
        accepted = await self._accepted(snapshot, identity, recover=True)
        if accepted is not None:
            return accepted
        return self._skip_content(snapshot, identity, failure, admission_guard)

    def _skip_content(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        failure: EventDecodeFailure,
        guard: Callable[[], bool] | None,
    ) -> SkippedRecord | HeldRecord:
        if (
            identity.subscription_id != snapshot.subscription_id
            or identity.workflow_id != snapshot.workflow_id
            or identity.source_id != snapshot.source_id
            or identity.source_generation != snapshot.source_generation
            or identity.integration_identity != snapshot.integration_identity
            or identity.deployment_id != snapshot.deployment_id
            or not record_matches_source(identity.record, snapshot.configuration)
        ):
            return self._hold("delivery_evidence_mismatch")
        if not self._admission_open(snapshot, guard):
            return self._hold("admission_closed")
        self._audit_content_failure(snapshot, identity, failure)
        if not self._admission_open(snapshot, guard):
            return self._hold("admission_closed")
        return SkippedRecord(
            identity=identity,
            configuration_revision=snapshot.configuration_revision,
            outcome="invalid_content",
            error_code=failure.code,
        )

    @staticmethod
    def _audit_content_failure(
        snapshot: SubscriptionSnapshot, identity: DeliveryIdentity, failure: EventDecodeFailure
    ) -> None:
        """Use existing best-effort OTEL audit delivery; it is never offset evidence."""
        with suppress(Exception):
            AuditEventDispatcher.dispatch(
                EventRecordRejectedEvent(
                    identity=identity,
                    configuration_revision=snapshot.configuration_revision,
                    error_code=failure.code,
                ),
                max_pending=get_settings().audit_writer_max_concurrent_writes,
            )

    @staticmethod
    def _event_matches(snapshot: SubscriptionSnapshot, identity: DeliveryIdentity, event: RawEvent) -> bool:
        """Apply the same trusted-coordinate checks used by Execution preparation."""
        metadata = event.source_metadata
        return (
            identity.subscription_id == snapshot.subscription_id
            and identity.workflow_id == snapshot.workflow_id
            and identity.source_id == snapshot.source_id
            and identity.source_generation == snapshot.source_generation
            and identity.integration_identity == snapshot.integration_identity
            and identity.deployment_id == snapshot.deployment_id
            and metadata.integration_id == identity.integration_identity
            and metadata.subscription_id == identity.subscription_id
            and metadata.source_generation == identity.source_generation
            and record_matches_metadata(identity.record, metadata)
        )

    def evaluate_filter(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        event: RawEvent,
    ) -> EventDecodeSuccess | EventDecodeFailure | SkippedRecord:
        """Evaluate the same native expression before/after ordinary payload decoding."""
        if not self._event_matches(snapshot, identity, event):
            message = "Delivered event does not match the trusted filter identity"
            raise ValueError(message)
        prepared = snapshot.prepared_filter
        view = EventFilterInput.from_event(event) if prepared is not None else None
        if prepared is not None and view is not None:
            result = prepared.precheck(view)
            if result.outcome != FilterOutcome.MATCH:
                return self._skip_filter(snapshot, identity, result)
        decoded = self._decode_payload(snapshot, event)
        if isinstance(decoded, EventDecodeSuccess) and prepared is not None and view is not None:
            view.payload = FilterPayload(state="decoded", value=decoded.envelope.payload)
            view.cloudevents = decoded.envelope.cloudevents
            result = prepared.evaluate(view)
            if result.outcome != FilterOutcome.MATCH:
                return self._skip_filter(snapshot, identity, result)
        return decoded

    def _decode_payload(
        self, snapshot: SubscriptionSnapshot, event: RawEvent
    ) -> EventDecodeSuccess | EventDecodeFailure:
        return self._decoder.decode(event, schema=snapshot.model_dump(mode="json")["input_schema"])

    @staticmethod
    def _skip_filter(snapshot: SubscriptionSnapshot, identity: DeliveryIdentity, result: FilterResult) -> SkippedRecord:
        """Best-effort system logs carry identity and safe codes, never message content."""
        fields = {
            "subscription_id": str(identity.subscription_id),
            "source_id": str(identity.source_id),
            "source_generation": identity.source_generation,
            "configuration_revision": snapshot.configuration_revision,
            **identity.record.model_dump(mode="json"),
        }
        try:
            if result.outcome == FilterOutcome.EVALUATION_ERROR:
                logger.error("event_subscription_filter_error", error_code=result.error_code, **fields)
            else:
                logger.info("event_subscription_filter_no_match", **fields)
        except Exception:  # noqa: BLE001, S110 - best-effort logs never gate CEL skip completion
            pass
        return SkippedRecord(
            identity=identity,
            configuration_revision=snapshot.configuration_revision,
            outcome="evaluation_error" if result.outcome == FilterOutcome.EVALUATION_ERROR else "no_match",
            error_code=result.error_code,
        )
