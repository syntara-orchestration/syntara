"""Resolve accepted runs before decoding and admitting new Kafka records."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import get_settings
from syntara.core.constants import EventSchedulingDefaults
from syntara.core.exceptions import SyntaraError
from syntara.eventstreams.adapters.record_identity import record_matches_metadata
from syntara.eventstreams.core.deduplication import DeliveryIdentity
from syntara.eventstreams.core.envelope import RawEvent
from syntara.eventstreams.core.filter_input import EventFilterInput, FilterPayload
from syntara.eventstreams.core.handler import ResolvedDelivery, RetryDelivery, SchedulingFailureCode
from syntara.eventstreams.core.preparation import PreparedExecution
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
logger = structlog.stdlib.get_logger(__name__)


class EventRecordProcessingService:
    """Keep unresolved records in the partition queue; never discard without activity evidence."""

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

    def _scheduled(self, snapshot: SubscriptionSnapshot, result: SchedulingResult) -> ResolvedDelivery | HeldRecord:
        if isinstance(result, ResolvedDelivery):
            return result
        if result.error_code == SchedulingFailureCode.STORAGE_UNAVAILABLE:
            self._dependency_failed(snapshot)
        if isinstance(result, RetryDelivery):
            return HeldRecord(reason=result.error_code.value, retry_at=result.next_attempt_at)
        return self._hold(result.error_code.value)

    async def _accepted(
        self, snapshot: SubscriptionSnapshot, identity: DeliveryIdentity
    ) -> ResolvedDelivery | HeldRecord | None:
        result = await self._admission.recover_accepted(identity)
        return None if result is None else self._scheduled(snapshot, result)

    async def process(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        event: RawEvent | None,
        *,
        admission_guard: Callable[[], bool] | None = None,
    ) -> RecordResult:
        """Check Execution and Temporal before current decoding, resources and capacity."""
        try:
            accepted = await self._accepted(snapshot, identity)
            if accepted is not None:
                return accepted
            if (
                event is None
                or not self._admission_open(snapshot, admission_guard)
                or not await self.admission_eligible(snapshot)
            ):
                return self._hold("admission_closed")
            if not self._event_matches(snapshot, identity, event):
                return self._hold("delivery_evidence_mismatch")
            decoded = self.evaluate_filter(snapshot, identity, event)
            if isinstance(decoded, SkippedRecord):
                return decoded if self._admission_open(snapshot, admission_guard) else self._hold("admission_closed")
            return await self._prepare_and_schedule(snapshot, identity, decoded, admission_guard)
        except (SQLAlchemyError, OSError, TimeoutError, SyntaraError, ValueError) as exc:
            if isinstance(exc, (SQLAlchemyError, OSError, TimeoutError)):
                self._dependency_failed(snapshot)
            return self._hold("dependency_unavailable")

    async def _prepare_and_schedule(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        decoded: EventDecodeSuccess | EventDecodeFailure,
        guard: Callable[[], bool] | None,
    ) -> RecordResult:
        if isinstance(decoded, EventDecodeFailure):
            return HeldRecord(reason="activity_log_unavailable", permanent_content_error=True)
        if not self._admission_open(snapshot, guard):
            return self._hold("admission_closed")
        prepared = await self._preparation.prepare_delivery(snapshot, identity, decoded.envelope)
        if isinstance(prepared, EventDecodeFailure):
            return HeldRecord(reason="activity_log_unavailable", permanent_content_error=True)
        if not isinstance(prepared, PreparedExecution):
            return self._hold(prepared.reason)
        if not self._admission_open(snapshot, guard):
            return self._hold("admission_closed")
        return self._scheduled(snapshot, await self._admission.schedule(prepared))

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
        accepted = await self._accepted(snapshot, identity)
        if accepted is not None:
            return accepted
        if not self._event_matches(snapshot, identity, event):
            return self._hold("delivery_evidence_mismatch")
        # Inspection grants no start or commit permission. It must remain
        # available behind the partition fence that requested this drain.
        if apply_filter:
            if not self._admission_open(snapshot, admission_guard) or not await self.admission_eligible(snapshot):
                return self._hold("admission_closed")
            decoded = self.evaluate_filter(snapshot, identity, event)
            if isinstance(decoded, SkippedRecord):
                return decoded if self._admission_open(snapshot, admission_guard) else self._hold("admission_closed")
        else:
            decoded = self._decoder.decode(event, schema=snapshot.model_dump(mode="json")["input_schema"])
        if isinstance(decoded, EventDecodeFailure):
            return HeldRecord(reason="activity_log_unavailable", permanent_content_error=True)
        return InspectedRecord(identity=identity)

    async def hold_content_failure(
        self,
        snapshot: SubscriptionSnapshot,
        identity: DeliveryIdentity,
        failure: EventDecodeFailure,
        *,
        admission_guard: Callable[[], bool] | None = None,
    ) -> RecordResult:
        """Keep unbufferable invalid content uncommitted until activity logging exists."""
        accepted = await self._accepted(snapshot, identity)
        if accepted is not None:
            return accepted
        if not self._admission_open(snapshot, admission_guard):
            return self._hold("admission_closed")
        return HeldRecord(reason=failure.code.value, permanent_content_error=True)

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
        decoded = self._decoder.decode(event, schema=snapshot.model_dump(mode="json")["input_schema"])
        if isinstance(decoded, EventDecodeSuccess) and prepared is not None and view is not None:
            view.payload = FilterPayload(state="decoded", value=decoded.envelope.payload)
            result = prepared.evaluate(view)
            if result.outcome != FilterOutcome.MATCH:
                return self._skip_filter(snapshot, identity, result)
        return decoded

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
