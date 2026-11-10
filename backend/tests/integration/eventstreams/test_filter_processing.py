"""Real persisted subscriptions with local CEL skips and no delivery/audit rows."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from sqlmodel import select

from syntara.audit.outbox.models import AuditOutboxRecord
from syntara.eventstreams.adapters.kafka_delivery_reader import KafkaDeliveryReader
from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata
from syntara.eventstreams.core.deduplication import DeliveryState
from syntara.eventstreams.core.envelope import RawEvent
from syntara.eventstreams.core.handler import ResolvedDelivery
from syntara.eventstreams.core.processing import SkippedRecord
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services import record_processing_service as module
from syntara.eventstreams.services.record_processing_service import EventRecordProcessingService
from syntara.workflows.models.execution import Execution
from tests.integration.eventstreams.conftest import DeliveryContext

pytestmark = pytest.mark.integration


async def processing(context: DeliveryContext, expression: str):
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
async def test_cel_skips_leave_no_delivery_or_audit_rows(
    delivery_context, monkeypatch, expression, value, outcome, code
) -> None:
    context = delivery_context
    service, preparation, admission, event = await processing(context, expression)
    log = Mock()
    monkeypatch.setattr(module, "logger", log)
    service._session_factory = Mock(side_effect=AssertionError("Local CEL completion must not open a database session"))
    result = await service.process(
        context.snapshot, context.identity(), event.model_copy(update={"value": value}), "worker", recovery_checked=True
    )
    assert isinstance(result, SkippedRecord)
    assert result.outcome == outcome
    assert result.error_code == code
    async with context.session_factory() as session:
        assert await session.get(EventDelivery, context.identity().digest) is None
        assert not (await session.exec(select(AuditOutboxRecord))).all()
    service._session_factory.assert_not_called()
    preparation.prepare_delivery.assert_not_awaited()
    admission.schedule.assert_not_awaited()
    (log.error if code else log.info).assert_called_once()
    assert "private" not in str(log.mock_calls)


async def test_redelivery_uses_new_filter_without_persisting_the_old_skip(delivery_context) -> None:
    context = delivery_context
    service, _preparation, _admission, event = await processing(context, "false")
    first = await service.process(context.snapshot, context.identity(), event, "worker", recovery_checked=True)
    assert isinstance(first, SkippedRecord)
    service, _preparation, _admission, event = await processing(context, "true")
    prepared_result = object()
    service._prepare_and_schedule = AsyncMock(return_value=prepared_result)
    second = await service.process(context.snapshot, context.identity(), event, "worker", recovery_checked=True)
    assert second is prepared_result
    service._prepare_and_schedule.assert_awaited_once()
    async with context.session_factory() as session:
        assert await session.get(EventDelivery, context.identity().digest) is None


async def test_false_key_condition_can_skip_invalid_json_without_database(delivery_context) -> None:
    context = delivery_context
    service, _preparation, _admission, event = await processing(
        context, 'input.key.text == "wanted" && input.payload.value.ok'
    )
    service._session_factory = Mock(side_effect=AssertionError("No database work for a proven early no-match"))
    result = await service.process(
        context.snapshot,
        context.identity(),
        event.model_copy(update={"key": b"other", "value": b"invalid"}),
        "worker",
        recovery_checked=True,
    )
    assert isinstance(result, SkippedRecord)
    assert result.outcome == "no_match"


@pytest.mark.parametrize(("value", "code"), [(b"not-json", "invalid_json"), (None, "tombstone")])
async def test_matching_filter_commits_content_rejection_without_a_log_gate(
    delivery_context,
    monkeypatch,
    value,
    code,
) -> None:
    context = delivery_context
    service, preparation, admission, event = await processing(context, "true")
    monkeypatch.setattr(module, "EventDeliveryStore", context.store)
    logs = Mock()
    logs.error.side_effect = OSError("System log unavailable")
    monkeypatch.setattr(module, "logger", logs)
    result = await service.process(
        context.snapshot,
        context.identity(),
        event.model_copy(update={"value": value}),
        "worker",
        recovery_checked=True,
    )
    assert isinstance(result, ResolvedDelivery)
    assert result.terminal.state == DeliveryState.REJECTED
    async with context.session_factory() as session:
        row = await session.get(EventDelivery, context.identity().digest)
        assert row is not None
        assert row.state == DeliveryState.REJECTED
        assert row.resolved_at is not None
        assert row.last_error_code == code
        assert row.claim_token is None
        assert await session.get(Execution, context.identity().execution_id) is None
    reader = KafkaDeliveryReader(context.session_factory)
    assert await reader.first_pending(context.snapshot, 0) is None
    assert not await reader.has_content_gate(context.snapshot, 0)
    logs.error.assert_called_once()
    preparation.prepare_delivery.assert_not_awaited()
    admission.schedule.assert_not_awaited()
