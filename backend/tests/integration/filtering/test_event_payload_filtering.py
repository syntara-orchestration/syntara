"""Real decoder, native CEL C++ evaluator and unchanged trigger-envelope integration."""

import copy
from datetime import UTC, datetime
from uuid import UUID

import pytest

from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata
from syntara.eventstreams.core.envelope import RawEvent, RawEventHeader
from syntara.eventstreams.core.results import EventDecodeFailure, EventFailureCode
from syntara.eventstreams.core.serialization import EventDecodeSuccess, JsonEventDecoder, encode_envelope
from syntara.filtering.evaluator import PreparedFilter
from syntara.filtering.models.result import FilterErrorCode, FilterOutcome
from syntara.workflows.workflow_engine.activities.event_subscribe_trigger import event_subscribe_trigger

pytestmark = pytest.mark.integration


def _event(value: bytes | None) -> RawEvent:
    """Supply real source metadata and lossless binary/null/duplicate originals."""
    return RawEvent(
        value=value,
        key=b"\xff",
        headers=(
            RawEventHeader(name="content-type", value=b"application/json"),
            RawEventHeader(name="trace", value=b"\xff"),
            RawEventHeader(name="trace", value=None),
            RawEventHeader(name="trace", value=b""),
        ),
        source_metadata=KafkaSourceMetadata(
            integration_id=UUID(int=1),
            subscription_id=UUID(int=2),
            source_generation=1,
            received_at=datetime(2026, 1, 1, tzinfo=UTC),
            topic="orders",
            partition=0,
            offset="9007199254740993",
        ),
    )


@pytest.mark.parametrize(
    ("raw_json", "expression"),
    [
        ('{"severity":"critical"}', 'input.severity == "critical"'),
        ('[{"ok":true},{"ok":true}]', "input.all(item, item.ok)"),
        ('"critical"', 'input.matches("^crit.*$")'),
        ('"café"', 'input == "café"'),
        ("42", "input + 1 == 43"),
        ("1.5", "input > 1.0"),
        ("true", "input"),
        ("null", "input == null"),
    ],
)
def test_decoded_json_values_are_supported_without_changing_envelope(raw_json: str, expression: str) -> None:
    event = _event(raw_json.encode("utf-8"))
    original = event.model_copy(deep=True)
    decoded = JsonEventDecoder().decode(event)
    assert isinstance(decoded, EventDecodeSuccess)
    before = encode_envelope(decoded.envelope)
    result = PreparedFilter(expression).evaluate(decoded.envelope.payload)
    assert result.outcome == FilterOutcome.MATCH
    assert result.error_code is None
    assert encode_envelope(decoded.envelope) == before
    assert event == original


def test_one_native_program_handles_repeated_decoded_message_outcomes() -> None:
    prepared = PreparedFilter('input.severity.startsWith("crit")')
    decoder = JsonEventDecoder()
    cases = [
        (b'{"severity":"critical"}', FilterOutcome.MATCH, None),
        (b'{"severity":"warning"}', FilterOutcome.NO_MATCH, None),
        (b"{}", FilterOutcome.NO_MATCH, None),
        (b'{"severity":42}', FilterOutcome.EVALUATION_ERROR, FilterErrorCode.WRONG_TYPE),
        (b'{"severity":"critical"}', FilterOutcome.MATCH, None),
    ]
    for value, outcome, error_code in cases:
        decoded = decoder.decode(_event(value), schema={"type": "object"})
        assert isinstance(decoded, EventDecodeSuccess)
        before = encode_envelope(decoded.envelope)
        result = prepared.evaluate(decoded.envelope.payload)
        assert result.outcome == outcome
        assert result.error_code == error_code
        assert encode_envelope(decoded.envelope) == before


@pytest.mark.parametrize("missing_first", [False, True])
def test_native_error_ordering_survives_json_decoding(*, missing_first: bool) -> None:
    operands = ["input.text + 1 == 2", "input.missing"]
    if missing_first:
        operands.reverse()
    decoded = JsonEventDecoder().decode(_event(b'{"text":"x"}'))
    assert isinstance(decoded, EventDecodeSuccess)
    before = encode_envelope(decoded.envelope)
    result = PreparedFilter(f"({operands[0]}) && ({operands[1]})").evaluate(decoded.envelope.payload)
    assert result.outcome == (FilterOutcome.NO_MATCH if missing_first else FilterOutcome.EVALUATION_ERROR)
    assert result.error_code == (None if missing_first else FilterErrorCode.WRONG_TYPE)
    assert encode_envelope(decoded.envelope) == before


@pytest.mark.parametrize("expression", ['input.labels.env == "prod"', 'input.labels["env"] == "prod"'])
def test_dot_and_bracket_access_agree_across_decoded_messages(expression: str) -> None:
    prepared = PreparedFilter(expression)
    for value, outcome, error_code in [
        (b"{}", FilterOutcome.NO_MATCH, None),
        (b'{"labels":{}}', FilterOutcome.NO_MATCH, None),
        (b'{"labels":{"env":"prod"}}', FilterOutcome.MATCH, None),
        (b'{"labels":null}', FilterOutcome.EVALUATION_ERROR, FilterErrorCode.WRONG_TYPE),
        (b'{"labels":1}', FilterOutcome.EVALUATION_ERROR, FilterErrorCode.WRONG_TYPE),
        (b'{"labels":{"env":"dev"}}', FilterOutcome.NO_MATCH, None),
    ]:
        decoded = JsonEventDecoder().decode(_event(value))
        assert isinstance(decoded, EventDecodeSuccess)
        before = encode_envelope(decoded.envelope)
        result = prepared.evaluate(decoded.envelope.payload)
        assert result.outcome == outcome
        assert result.error_code == error_code
        assert encode_envelope(decoded.envelope) == before


def test_literal_key_presence_uses_native_cel_membership() -> None:
    prepared = PreparedFilter('"event-type" in input && input["event-type"] == "created"')
    for value, outcome in [
        (b'{"event-type":"created"}', FilterOutcome.MATCH),
        (b"{}", FilterOutcome.NO_MATCH),
        (b'{"event-type":null}', FilterOutcome.NO_MATCH),
        (b'{"event-type":"updated"}', FilterOutcome.NO_MATCH),
    ]:
        decoded = JsonEventDecoder().decode(_event(value))
        assert isinstance(decoded, EventDecodeSuccess)
        assert prepared.evaluate(decoded.envelope.payload).outcome == outcome


def test_decoded_json_null_is_distinct_from_a_source_tombstone() -> None:
    decoder = JsonEventDecoder()
    decoded_null = decoder.decode(_event(b"null"))
    tombstone = decoder.decode(_event(None))
    assert isinstance(decoded_null, EventDecodeSuccess)
    assert decoded_null.envelope.payload is None
    assert PreparedFilter("input == null").evaluate(decoded_null.envelope.payload).outcome == FilterOutcome.MATCH
    assert isinstance(tombstone, EventDecodeFailure)
    assert tombstone.code == EventFailureCode.tombstone


async def test_filter_evaluation_preserves_trigger_envelope_and_output_mapping() -> None:
    decoded = JsonEventDecoder().decode(
        _event(b'{"severity":"critical","count":2}'),
        schema={"type": "object", "required": ["severity", "count"]},
    )
    assert isinstance(decoded, EventDecodeSuccess)
    envelope = decoded.envelope.model_dump(mode="json", by_alias=True)
    frozen = copy.deepcopy(envelope)
    before = encode_envelope(decoded.envelope)
    result = PreparedFilter('input.severity == "critical"').evaluate(decoded.envelope.payload)
    assert result.outcome == FilterOutcome.MATCH
    assert await event_subscribe_trigger(envelope, None) == {"output": frozen}
    assert await event_subscribe_trigger(envelope, {"count": "${result.payload.count}"}) == {"output": {"count": 2}}
    assert encode_envelope(decoded.envelope) == before
    assert envelope == frozen
    assert envelope["metadata"]["offset"] == "9007199254740993"
    assert envelope["original"]["key_base64"] == "/w=="
    assert envelope["original"]["headers"][1:] == [
        {"name": "trace", "value_base64": "/w=="},
        {"name": "trace", "value_base64": None},
        {"name": "trace", "value_base64": ""},
    ]
