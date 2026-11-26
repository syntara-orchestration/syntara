"""Real persisted subscriptions with local CEL skips and no execution/audit writes."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from sqlmodel import select

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.outbox.models import AuditOutboxRecord
from syntara.core.constants import EventStreamLimits
from syntara.eventstreams.adapters.kafka_consumer import KafkaPartitionConsumer
from syntara.eventstreams.adapters.kafka_initial_position_service import KafkaInitialPositionService
from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata
from syntara.eventstreams.adapters.kafka_record_runner import KafkaRecordRunner
from syntara.eventstreams.core.envelope import RawEvent
from syntara.eventstreams.core.processing import SkippedRecord
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services import record_processing_service as module
from syntara.eventstreams.services.record_processing_service import EventRecordProcessingService
from syntara.eventstreams.services.subscription_service import lock_source_lifecycle
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
    admission.lookup_execution.return_value = None
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
    sessions = Mock(side_effect=AssertionError("Local filter outcomes must not open a database session"))
    service._sessions = sessions
    log = Mock()
    monkeypatch.setattr(module, "logger", log)
    result = await service.process(context.snapshot, context.identity(), event.model_copy(update={"value": value}))
    assert isinstance(result, SkippedRecord)
    assert result.outcome == outcome
    assert result.error_code == code
    async with context.session_factory() as session:
        assert await session.get(Execution, context.identity().execution_id) is None
        assert not (await session.exec(select(AuditOutboxRecord))).all()
    sessions.assert_not_called()
    admission.lookup_execution.assert_not_awaited()
    admission.recover_accepted.assert_not_awaited()
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
async def test_matching_filter_audits_and_skips_invalid_content_without_execution(
    preparation_context, monkeypatch, value
) -> None:
    context = preparation_context
    service, preparation, admission, event = await processing(context, "true")
    logs = Mock()
    monkeypatch.setattr(module, "logger", logs)
    audit = Mock()
    monkeypatch.setattr(AuditEventDispatcher, "dispatch", audit)
    result = await service.process(context.snapshot, context.identity(), event.model_copy(update={"value": value}))
    assert isinstance(result, SkippedRecord)
    assert result.outcome == "invalid_content"
    audit.assert_called_once()
    async with context.session_factory() as session:
        assert await session.get(Execution, context.identity().execution_id) is None
    logs.error.assert_not_called()
    preparation.prepare_delivery.assert_not_awaited()
    admission.schedule.assert_not_awaited()


@pytest.mark.parametrize("revision_lock_after_timeout", [False, True])
async def test_publication_waits_for_skip_commit_after_the_caller_times_out(  # noqa: PLR0915 - One publication/commit race.
    preparation_context, monkeypatch, *, revision_lock_after_timeout: bool
) -> None:
    context = preparation_context
    service, preparation, admission, record = await processing(context, "false")
    monkeypatch.setattr(EventStreamLimits, "COMMITTED_POSITION_TIMEOUT_SECONDS", 0.01)
    client = MagicMock(spec=KafkaPartitionConsumer)
    client.topic, client.group_id = context.snapshot.configuration.topic, context.snapshot.configuration.group_id
    partition = context.identity().record.partition
    client.epoch, client.assignment = 7, frozenset({partition})
    runner = KafkaRecordRunner(
        context.snapshot,
        client,
        context.session_factory,
        preparation,
        admission,
        processing=service,
        positions=MagicMock(spec=KafkaInitialPositionService),
    )
    entered, release, publishing, allow_lock = (asyncio.Event() for _ in range(4))
    observer = publication = None
    if revision_lock_after_timeout:

        async def delayed_lock(session, source_id) -> tuple[EventSubscription, EventSubscriptionSource] | None:
            await allow_lock.wait()
            return await lock_source_lifecycle(session, source_id)

        monkeypatch.setattr(module, "lock_source_lifecycle", delayed_lock)

    async def broker_commit() -> None:
        await release.wait()

    broker = asyncio.create_task(broker_commit())

    async def commit(_offsets, *, expected_epoch: int) -> None:
        assert expected_epoch == 7
        entered.set()
        await asyncio.shield(broker)

    async def publish() -> None:
        publishing.set()
        await processing(context, "true")

    client.commit.side_effect = commit
    try:
        await runner.start()
        await runner.on_partitions_assigned(client.assignment, client.epoch)
        state = runner._partitions[partition]
        state.ready = state.eligible = True
        await runner._enqueue({partition: [record]}, client.epoch)
        await runner._advance(state)
        observer = asyncio.create_task(runner._commit_positions((state,)))
        if revision_lock_after_timeout:
            await asyncio.wait_for(observer, timeout=5)
            assert not entered.is_set()
            allow_lock.set()
        # The caller's timeout also includes PostgreSQL lock acquisition.
        # Wait for broker entry independently of that short observer deadline.
        await asyncio.wait_for(entered.wait(), timeout=5)
        await asyncio.wait_for(observer, timeout=5)
        assert runner._commit_task is not None
        assert not runner._commit_task.done()
        publication = asyncio.create_task(publish())
        await publishing.wait()
        # This is a real PostgreSQL row lock held by the retained commit task.
        done, _ = await asyncio.wait({publication}, timeout=0.05)
        assert not done
        release.set()
        await runner._commit_task
        await asyncio.wait_for(publication, timeout=2)
        assert context.snapshot.configuration_revision > runner.snapshot.configuration_revision
    finally:
        allow_lock.set()
        release.set()
        await broker
        if observer is not None:
            await observer
        if runner._commit_task is not None:
            await runner._commit_task
        if publication is not None:
            await publication
        await runner.stop()
