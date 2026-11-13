"""CEL skips complete before execution reads, writes or Temporal work."""

from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from syntara.eventstreams.core.envelope import RawEvent
from syntara.eventstreams.core.handler import ResolvedDelivery
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.core.processing import HeldRecord, SkippedRecord
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services import record_processing_service as module
from syntara.filtering import evaluator as filter_evaluator
from tests.unit.eventstreams.test_execution_preparation_service import PreparationContext
from tests.unit.eventstreams.test_record_processing_service import processing_context, terminal


def filtered_context(
    monkeypatch: pytest.MonkeyPatch, configuration: dict[str, object]
) -> tuple[PreparationContext, module.EventRecordProcessingService, MagicMock, RawEvent, Mock]:
    """Keep native filtering/decoding real while isolating admission reads and writes."""
    context, service, admission, event = processing_context(monkeypatch)
    context.subscription.filter = configuration
    context.snapshot = SubscriptionSnapshot.model_validate(
        {**context.snapshot.model_dump(mode="json"), "filter": configuration}
    )
    monkeypatch.setattr(service, "admission_eligible", AsyncMock(return_value=True))
    logs = Mock()
    monkeypatch.setattr(module, "logger", logs)
    return context, service, admission, event, logs


@pytest.mark.parametrize(
    ("expression", "value", "outcome", "code"),
    [
        ("false", b"{}", "no_match", None),
        ("input.payload.value.missing", b"{}", "no_match", None),
        ("input.payload.value.value", b'{"value":1}', "evaluation_error", "filter_non_boolean"),
        ("input.payload.value.value + 1 == 2", b'{"value":"secret"}', "evaluation_error", "filter_wrong_type"),
        (
            "input.payload.value.text.matches(input.payload.value.pattern)",
            b'{"text":"secret","pattern":"["}',
            "evaluation_error",
            "filter_evaluation_failed",
        ),
    ],
)
async def test_local_outcomes_do_not_write_or_schedule(monkeypatch, expression, value, outcome, code) -> None:
    context, service, admission, event, logs = filtered_context(monkeypatch, {"expression": expression})
    context.events.clear()
    result = await service.process(context.snapshot, context.identity, event.model_copy(update={"value": value}))
    assert isinstance(result, SkippedRecord)
    assert result.identity == context.identity
    assert result.configuration_revision == context.snapshot.configuration_revision
    assert result.outcome == outcome
    assert result.error_code == code
    assert context.events == []
    admission.lookup_execution.assert_not_awaited()
    admission.recover_accepted.assert_not_awaited()
    eligible = service.admission_eligible
    assert isinstance(eligible, AsyncMock)
    eligible.assert_not_awaited()
    assert context.session.mock_calls == []
    admission.schedule.assert_not_awaited()
    (logs.error if code else logs.info).assert_called_once()
    assert "secret" not in str(logs.mock_calls)


async def test_preliminary_false_skips_invalid_payload_without_decoding(monkeypatch) -> None:
    context, service, admission, event, _logs = filtered_context(
        monkeypatch, {"expression": 'input.key.text == "wanted" && input.payload.value.ok'}
    )
    decoder = Mock()
    decoder.decode.side_effect = AssertionError("Proven false needs no decoder")
    service._decoder = decoder
    result = await service.process(
        context.snapshot, context.identity, event.model_copy(update={"key": b"other", "value": b"invalid"})
    )
    assert isinstance(result, SkippedRecord)
    assert result.outcome == "no_match"
    decoder.decode.assert_not_called()
    admission.lookup_execution.assert_not_awaited()
    admission.recover_accepted.assert_not_awaited()
    admission.schedule.assert_not_awaited()


@pytest.mark.parametrize("apply_filter", [False, True])
@pytest.mark.parametrize("expression", ["false", "input.payload.value.count"])
async def test_inspection_filter_outcomes_need_no_database_or_temporal(
    monkeypatch, expression, *, apply_filter
) -> None:
    context, service, admission, event, _logs = filtered_context(monkeypatch, {"expression": expression})
    result = await service.inspect_only(context.snapshot, context.identity, event, apply_filter=apply_filter)
    assert not isinstance(result, HeldRecord)
    admission.lookup_execution.assert_not_awaited()
    admission.recover_accepted.assert_not_awaited()
    admission.schedule.assert_not_awaited()
    eligible = service.admission_eligible
    assert isinstance(eligible, AsyncMock)
    eligible.assert_not_awaited()
    assert context.session.mock_calls == []


async def test_log_failure_does_not_block_filter_skip(monkeypatch) -> None:
    context, service, _admission, event, logs = filtered_context(monkeypatch, {"expression": "false"})
    logs.info.side_effect = OSError("Log destination unavailable")
    result = await service.process(context.snapshot, context.identity, event)
    assert isinstance(result, SkippedRecord)


async def test_changed_false_filter_skips_previously_accepted_record_without_repair(monkeypatch) -> None:
    context, service, admission, event, logs = filtered_context(monkeypatch, {"expression": "false"})
    accepted = terminal(context.identity)
    admission.recover_accepted.return_value = accepted
    admission.lookup_execution.return_value = accepted
    monkeypatch.setattr(
        service, "admission_eligible", AsyncMock(side_effect=AssertionError("Accepted work bypasses new admission"))
    )
    result = await service.process(context.snapshot, context.identity, event)
    assert isinstance(result, SkippedRecord)
    admission.lookup_execution.assert_not_awaited()
    admission.recover_accepted.assert_not_awaited()
    admission.schedule.assert_not_awaited()
    logs.info.assert_called_once()
    logs.error.assert_not_called()


async def test_redelivery_can_match_a_new_filter_after_an_earlier_local_skip(monkeypatch) -> None:
    context, service, admission, event, _logs = filtered_context(monkeypatch, {"expression": "false"})
    first = await service.process(context.snapshot, context.identity, event)
    assert isinstance(first, SkippedRecord)
    context.session.add.assert_not_called()
    revised = SubscriptionSnapshot.model_validate(
        {
            **context.snapshot.model_dump(mode="json"),
            "configuration_revision": context.snapshot.configuration_revision + 1,
            "filter": {"expression": "true"},
        }
    )
    prepare = AsyncMock(return_value=terminal(context.identity))
    monkeypatch.setattr(service, "_prepare_and_schedule", prepare)
    result = await service.process(revised, context.identity, event)
    assert isinstance(result, ResolvedDelivery)
    prepare.assert_awaited_once()
    admission.lookup_execution.assert_awaited_once_with(context.identity)
    admission.recover_accepted.assert_not_awaited()


async def test_closed_admission_cannot_authorize_a_local_skip(monkeypatch) -> None:
    context, service, _admission, event, logs = filtered_context(monkeypatch, {"expression": "false"})
    result = await service.process(context.snapshot, context.identity, event, admission_guard=lambda: False)
    assert isinstance(result, HeldRecord)
    logs.info.assert_not_called()


async def test_foreign_event_cannot_authorize_a_local_skip(monkeypatch) -> None:
    context, service, _admission, event, logs = filtered_context(monkeypatch, {"expression": "false"})
    event = event.model_copy(
        update={"source_metadata": event.source_metadata.model_copy(update={"source_generation": 99})}
    )
    result = await service.process(context.snapshot, context.identity, event)
    assert isinstance(result, HeldRecord)
    assert result.reason == "delivery_evidence_mismatch"
    logs.info.assert_not_called()


async def test_preparation_does_not_recompile_loaded_filters(monkeypatch) -> None:
    context, _service, _admission, _event, _logs = filtered_context(monkeypatch, {"expression": "true"})
    monkeypatch.setattr(filter_evaluator, "compile_expression", Mock(side_effect=AssertionError("recompiled")))
    assert isinstance(await context.prepare(), PreparedExecution)
