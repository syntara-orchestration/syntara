"""Real persisted subscriptions with local CEL skips and no execution/audit writes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from sqlmodel import select

from syntara.audit.outbox.models import AuditOutboxRecord
from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata
from syntara.eventstreams.core.envelope import RawEvent
from syntara.eventstreams.core.processing import HeldRecord, SkippedRecord
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services import record_processing_service as module
from syntara.eventstreams.services.record_processing_service import EventRecordProcessingService
from syntara.workflows.models.execution import Execution
from tests.integration.eventstreams import test_execution_preparation
from tests.integration.eventstreams.conftest import DeliveryContext

pytestmark = pytest.mark.integration
preparation_context = test_execution_preparation.preparation_context


async def processing(
    context: DeliveryContext, expression: str
) -> tuple[EventRecordProcessingService, AsyncMock, AsyncMock, RawEvent]:
    """Publish a real expression and load the same frozen snapshot as the listener."""
    async with context.session_factory() as session, session.begin():
        subscription = await session.get(EventSubscription, context.snapshot.subscription_id)
        source = await session.get(EventSubscriptionSource, context.snapshot.source_id)
        assert subscription is not None
        assert source is not None
        subscription.filter = {"expression": expression}
        subscription.configuration_revision += 1
        await session.flush()
        context.snapshot = SubscriptionSnapshot.from_models(subscription, source)
    preparation, admission = AsyncMock(), AsyncMock()
    admission.recover_accepted.return_value = None
    service = EventRecordProcessingService(context.session_factory, preparation, admission)
    identity = context.identity()
    event = RawEvent(
        value=b"{}",
        source_metadata=KafkaSourceMetadata(
            integration_id=identity.integration_identity,
            subscription_id=identity.subscription_id,
            source_generation=identity.source_generation,
            received_at=datetime.now(UTC),
            topic=identity.record.topic,
            partition=identity.record.partition,
            offset=str(identity.record.offset),
        ),
    )
    return service, preparation, admission, event


@pytest.mark.parametrize(
    ("expression", "value", "outcome", "code"),
    [
        ("false", b"{}", "no_match", None),
        ("input.payload.value.missing", b"{}", "no_match", None),
        ("input.payload.value.count", b'{"count":1}', "evaluation_error", "filter_non_boolean"),
        ("input.payload.value.count + 1 == 2", b'{"count":"text"}', "evaluation_error", "filter_wrong_type"),
        (
            "input.payload.value.text.matches(input.payload.value.pattern)",
            b'{"text":"private","pattern":"["}',
            "evaluation_error",
            "filter_evaluation_failed",
        ),
    ],
)
async def test_cel_skips_leave_no_execution_or_audit_rows(
    preparation_context, monkeypatch, expression, value, outcome, code
) -> None:
    context = preparation_context
    service, preparation, admission, event = await processing(context, expression)
    log = Mock()
    monkeypatch.setattr(module, "logger", log)
    result = await service.process(
        context.snapshot, context.identity(), event.model_copy(update={"value": value})
    )
    assert isinstance(result, SkippedRecord)
    assert result.outcome == outcome
    assert result.error_code == code
    async with context.session_factory() as session:
        assert await session.get(Execution, context.identity().execution_id) is None
        assert not (await session.exec(select(AuditOutboxRecord))).all()
    admission.recover_accepted.assert_awaited_once_with(context.identity())
    preparation.prepare_delivery.assert_not_awaited()
    admission.schedule.assert_not_awaited()
    (log.error if code else log.info).assert_called_once()
    assert "private" not in str(log.mock_calls)


async def test_redelivery_uses_new_filter_without_persisting_the_old_skip(preparation_context, monkeypatch) -> None:
    context = preparation_context
    service, _preparation, _admission, event = await processing(context, "false")
    first = await service.process(context.snapshot, context.identity(), event)
    assert isinstance(first, SkippedRecord)
    service, _preparation, _admission, event = await processing(context, "true")
    prepared_result = object()
    prepare = AsyncMock(return_value=prepared_result)
    monkeypatch.setattr(service, "_prepare_and_schedule", prepare)
    second = await service.process(context.snapshot, context.identity(), event)
    assert second is prepared_result
    prepare.assert_awaited_once()
    async with context.session_factory() as session:
        assert await session.get(Execution, context.identity().execution_id) is None


async def test_false_key_condition_can_skip_invalid_json_without_decoding(preparation_context) -> None:
    context = preparation_context
    service, _preparation, _admission, event = await processing(
        context, 'input.key.text == "wanted" && input.payload.value.ok'
    )
    decoder = Mock()
    decoder.decode.side_effect = AssertionError("Proven false needs no decoder")
    service._decoder = decoder
    result = await service.process(
        context.snapshot, context.identity(), event.model_copy(update={"key": b"other", "value": b"invalid"})
    )
    assert isinstance(result, SkippedRecord)
    assert result.outcome == "no_match"
    decoder.decode.assert_not_called()


@pytest.mark.parametrize("value", [b"not-json", None], ids=["invalid-json", "tombstone"])
async def test_matching_filter_holds_invalid_content_without_execution(
    preparation_context, monkeypatch, value
) -> None:
    context = preparation_context
    service, preparation, admission, event = await processing(context, "true")
    logs = Mock()
    monkeypatch.setattr(module, "logger", logs)
    result = await service.process(
        context.snapshot, context.identity(), event.model_copy(update={"value": value})
    )
    assert isinstance(result, HeldRecord)
    assert result.permanent_content_error
    async with context.session_factory() as session:
        assert await session.get(Execution, context.identity().execution_id) is None
    logs.error.assert_not_called()
    preparation.prepare_delivery.assert_not_awaited()
    admission.schedule.assert_not_awaited()
