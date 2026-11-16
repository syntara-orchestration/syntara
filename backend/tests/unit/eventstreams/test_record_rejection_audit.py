"""Record-rejection audits contain coordinates and fixed codes, never source contents."""

import asyncio
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from syntara.audit import emitter
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.models.audit_event import EventSeverity, EventStatus
from syntara.audit.outbox.worker import AuditOutboxWorker
from syntara.core.config.base import get_settings
from syntara.eventstreams.audit.record_rejection import EventRecordRejectedEvent, EventRecordRejectedHandler
from syntara.eventstreams.core.deduplication import DeliveryIdentity
from syntara.eventstreams.core.processing import SkippedRecord
from syntara.eventstreams.core.results import EventFailureCode
from syntara.eventstreams.services import record_processing_service as processing_module
from tests.unit.eventstreams.test_record_processing_service import processing_context


def test_record_rejection_audit_preserves_identity_without_content() -> None:
    identity = DeliveryIdentity.model_validate(
        {
            "deployment_id": UUID(int=1),
            "integration_identity": UUID(int=2),
            "source_id": UUID(int=3),
            "source_generation": 1,
            "workflow_id": UUID(int=4),
            "subscription_id": UUID(int=5),
            "record": {"transport": "kafka", "topic": "orders", "partition": 0, "offset": "9007199254740993"},
        }
    )

    audit = EventRecordRejectedHandler().handle(
        EventRecordRejectedEvent(identity=identity, configuration_revision=2, error_code=EventFailureCode.invalid_json)
    )

    assert audit.event_severity == EventSeverity.ERROR
    assert audit.event_status == EventStatus.ERROR
    assert audit.workflow_id == identity.workflow_id
    assert audit.event_action == "event_subscription_record_rejected"
    data = audit.structured_data.model_dump()
    assert data["source_id"] == str(identity.source_id)
    assert data["configuration_revision"] == 2
    assert data["record"]["offset"] == "9007199254740993"
    assert data["error_code"] == "invalid_json"
    assert not {"payload", "value", "key", "headers", "credential_id", "group_id"}.intersection(data)


@pytest.mark.asyncio
async def test_slow_audit_writer_keeps_pending_work_bounded_and_invalid_records_skippable(monkeypatch) -> None:
    settings = get_settings().model_copy(update={"audit_enabled": True, "audit_writer_max_concurrent_writes": 2})
    monkeypatch.setattr(processing_module, "get_settings", lambda: settings)
    monkeypatch.setattr(emitter, "get_settings", lambda: settings)
    worker = AuditOutboxWorker(name="rejection-audit", interval_seconds=1, coordinate=False)
    monkeypatch.setattr(emitter, "get_outbox_worker", lambda: worker)
    monkeypatch.setattr(AuditEventDispatcher, "_registry", {})
    AuditEventDispatcher.register({EventRecordRejectedEvent: EventRecordRejectedHandler()})
    release = asyncio.Event()

    async def blocked_write(_event) -> None:
        await release.wait()

    write = AsyncMock(side_effect=blocked_write)
    monkeypatch.setattr(worker, "_write", write)
    context, service, admission, event = processing_context(monkeypatch)
    monkeypatch.setattr(service, "admission_eligible", AsyncMock(return_value=True))
    invalid = event.model_copy(update={"value": b"invalid"})
    try:
        for _ in range(100):
            result = await service.process(context.snapshot, context.identity, invalid)
            assert isinstance(result, SkippedRecord)
            assert result.outcome == "invalid_content"
            assert len(worker._pending) <= 2
        assert len(worker._pending) == 2
        await asyncio.sleep(0)
        assert write.await_count == 2
    finally:
        release.set()
        await asyncio.gather(*worker._pending)
    assert not worker._pending
    admission.schedule.assert_not_awaited()
    context.session.add.assert_not_called()

    result = await service.process(context.snapshot, context.identity, invalid)
    assert isinstance(result, SkippedRecord)
    await asyncio.gather(*worker._pending)
    assert write.await_count == 3
