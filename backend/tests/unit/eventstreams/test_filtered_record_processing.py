"""CEL skips perform no database/audit/cache writes after partition recovery."""

from unittest.mock import AsyncMock, Mock

import pytest

from syntara.eventstreams.core.deduplication import DeliveryState
from syntara.eventstreams.core.handler import ResolvedDelivery
from syntara.eventstreams.core.preparation import PreparedExecution
from syntara.eventstreams.core.processing import HeldRecord, SkippedRecord
from syntara.eventstreams.models.delivery import EventDelivery
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.eventstreams.services import record_processing_service as module
from syntara.filtering import evaluator as filter_evaluator
from tests.unit.eventstreams.test_record_processing_service import processing_context, retained, terminal


def filtered_context(monkeypatch: pytest.MonkeyPatch, configuration: dict[str, object]):
    """Keep native filtering/decoding real while isolating storage and scheduling."""
    context, service, admission, event = processing_context(monkeypatch)
    context.subscription.filter = configuration
    context.snapshot = SubscriptionSnapshot.model_validate(
        {**context.snapshot.model_dump(mode="json"), "filter": configuration}
    )
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
async def test_local_outcomes_do_not_touch_database_or_schedule(monkeypatch, expression, value, outcome, code) -> None:
    context, service, admission, event, logs = filtered_context(monkeypatch, {"expression": expression})
    context.events.clear()
    service._session_factory = Mock(side_effect=AssertionError("CEL skip must not access the database"))
    service._existing = AsyncMock(side_effect=AssertionError("CEL skip must not look up delivery evidence"))
    service.admission_eligible = AsyncMock(
        side_effect=AssertionError("Eligibility belongs to partition reconciliation")
    )
    result = await service.process(
        context.snapshot, context.identity, event.model_copy(update={"value": value}), "worker", recovery_checked=True
    )
    assert isinstance(result, SkippedRecord)
    assert result.identity == context.identity
    assert result.configuration_revision == context.snapshot.configuration_revision
    assert result.outcome == outcome
    assert result.error_code == code
    assert context.events == []
    service._session_factory.assert_not_called()
    service._existing.assert_not_awaited()
    admission.schedule.assert_not_awaited()
    (logs.error if code else logs.info).assert_called_once()
    assert "secret" not in str(logs.mock_calls)


async def test_preliminary_false_skips_invalid_payload_without_decoding(monkeypatch) -> None:
    context, service, admission, event, _logs = filtered_context(
        monkeypatch,
        {
            "expression": 'input.key.text == "wanted" && input.payload.value.ok',
        },
    )
    service._decoder = Mock(side_effect=AssertionError("Proven false needs no decoder"))
    service._session_factory = Mock(side_effect=AssertionError("Proven false needs no database"))
    result = await service.process(
        context.snapshot,
        context.identity,
        event.model_copy(update={"key": b"other", "value": b"invalid"}),
        "worker",
        recovery_checked=True,
    )
    assert isinstance(result, SkippedRecord)
    assert result.outcome == "no_match"
    admission.schedule.assert_not_awaited()


async def test_log_failure_does_not_block_filter_skip(monkeypatch) -> None:
    context, service, _admission, event, logs = filtered_context(monkeypatch, {"expression": "false"})
    logs.info.side_effect = OSError("Log destination unavailable")
    result = await service.process(context.snapshot, context.identity, event, "worker", recovery_checked=True)
    assert isinstance(result, SkippedRecord)


async def test_cache_miss_does_not_read_database_for_a_skip(monkeypatch) -> None:
    context, service, _admission, event, _logs = filtered_context(monkeypatch, {"expression": "false"})
    gate = Mock()
    gate.admission_open.return_value = gate.resolution_open.return_value = True
    service._gate = gate
    service._lookup = Mock()
    service._lookup.lookup_cached = AsyncMock(return_value=None)
    service._lookup.lookup = AsyncMock(side_effect=AssertionError("Do not use database-fallback cache lookup"))
    service._session_factory = Mock(side_effect=AssertionError("Do not access PostgreSQL on cache miss"))
    result = await service.process(
        context.snapshot, context.identity, event, "worker", recovery_checked=True, cache_admitted=True
    )
    assert isinstance(result, SkippedRecord)
    service._lookup.lookup_cached.assert_awaited_once_with(context.identity)
    service._lookup.lookup.assert_not_awaited()


@pytest.mark.parametrize("state", [DeliveryState.SCHEDULED, DeliveryState.REJECTED])
async def test_verified_cache_hit_preserves_stored_outcome(monkeypatch, state: DeliveryState) -> None:
    context, service, _admission, event, logs = filtered_context(monkeypatch, {"expression": "false"})
    gate = Mock()
    gate.admission_open.return_value = gate.resolution_open.return_value = True
    service._gate = gate
    service._lookup = Mock()
    proof = terminal(context.identity, state).terminal
    service._lookup.lookup_cached = AsyncMock(return_value=proof)
    service._decoder = Mock(side_effect=AssertionError("Terminal proof bypasses decoding"))
    result = await service.process(
        context.snapshot, context.identity, event, "worker", recovery_checked=True, cache_admitted=True
    )
    assert isinstance(result, ResolvedDelivery)
    assert result.terminal == proof
    logs.info.assert_not_called()


async def test_prepared_execution_recovery_ignores_a_new_false_filter(monkeypatch) -> None:
    context, service, admission, _event, logs = filtered_context(monkeypatch, {"expression": "false"})
    prepared = await context.prepare()
    assert isinstance(prepared, PreparedExecution)
    context.rows[EventDelivery] = retained(context.identity, frozen_binding=prepared.claim.binding)
    context.store.acquire.side_effect = None
    context.store.acquire.return_value = prepared.claim
    result = await service.process(context.snapshot, context.identity, None, "worker")
    assert isinstance(result, ResolvedDelivery)
    admission.schedule.assert_awaited_once()
    logs.info.assert_not_called()


async def test_redelivery_can_match_a_new_filter_after_an_earlier_local_skip(monkeypatch) -> None:
    context, service, _admission, event, _logs = filtered_context(monkeypatch, {"expression": "false"})
    first = await service.process(context.snapshot, context.identity, event, "worker", recovery_checked=True)
    assert isinstance(first, SkippedRecord)
    assert EventDelivery not in context.rows
    revised = SubscriptionSnapshot.model_validate(
        {
            **context.snapshot.model_dump(mode="json"),
            "configuration_revision": context.snapshot.configuration_revision + 1,
            "filter": {"expression": "true"},
        }
    )
    service._prepare_and_schedule = AsyncMock(return_value=terminal(context.identity))
    result = await service.process(revised, context.identity, event, "worker", recovery_checked=True)
    assert isinstance(result, ResolvedDelivery)
    service._prepare_and_schedule.assert_awaited_once()


async def test_closed_admission_cannot_authorize_a_local_skip(monkeypatch) -> None:
    context, service, _admission, event, logs = filtered_context(monkeypatch, {"expression": "false"})
    result = await service.process(
        context.snapshot, context.identity, event, "worker", recovery_checked=True, admission_guard=lambda: False
    )
    assert isinstance(result, HeldRecord)
    logs.info.assert_not_called()


async def test_foreign_event_cannot_authorize_a_local_skip(monkeypatch) -> None:
    context, service, _admission, event, logs = filtered_context(monkeypatch, {"expression": "false"})
    event = event.model_copy(
        update={"source_metadata": event.source_metadata.model_copy(update={"source_generation": 99})}
    )
    result = await service.process(context.snapshot, context.identity, event, "worker", recovery_checked=True)
    assert isinstance(result, HeldRecord)
    assert result.reason == "delivery_evidence_mismatch"
    logs.info.assert_not_called()


async def test_resource_checks_do_not_recompile_loaded_filters(monkeypatch) -> None:
    context, service, _admission, _event, _logs = filtered_context(monkeypatch, {"expression": "true"})
    monkeypatch.setattr(filter_evaluator, "compile_expression", Mock(side_effect=AssertionError("recompiled")))
    await service.admission_eligible(context.snapshot)
