"""Real decoder, shared evaluator and trigger-envelope component integration.

The generic evaluator receives the decoded payload directly under ``input``.
These tests do not stand in for the pending Subscribe filter input view or
worker processing, publication, durable outcomes or broker integration.
"""

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
    envelope_bytes = encode_envelope(decoded.envelope)
    result = PreparedFilter(expression).evaluate(decoded.envelope.payload)
    assert result.outcome == FilterOutcome.MATCH
    assert result.error_code is None
    assert encode_envelope(decoded.envelope) == envelope_bytes
    assert event == original


def test_one_prepared_filter_handles_a_sequence_of_decoded_message_outcomes() -> None:
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


@pytest.mark.parametrize(
    ("raw_json", "expression", "outcome"),
    [
        ('{"items":[{},{},{"ok":true}]}', "input.items.exists(item, item.ok)", FilterOutcome.MATCH),
        ('{"items":[{},{},{"ok":false}]}', "input.items.all(item, item.ok)", FilterOutcome.NO_MATCH),
        ("{}", "input.missing == 1 ? true : false", FilterOutcome.NO_MATCH),
        ("{}", '{"value": input.missing}.size() == 1', FilterOutcome.NO_MATCH),
        ("{}", 'true || ({"value": input.missing}.size() == 1)', FilterOutcome.MATCH),
    ],
)
def test_cel_error_rules_survive_json_decoding(raw_json: str, expression: str, outcome: FilterOutcome) -> None:
    decoded = JsonEventDecoder().decode(_event(raw_json.encode("utf-8")), schema={"type": "object"})
    assert isinstance(decoded, EventDecodeSuccess)
    result = PreparedFilter(expression).evaluate(decoded.envelope.payload)
    assert result.outcome == outcome
    assert result.error_code is None


@pytest.mark.parametrize(
    "expression",
    [
        "input.items.all(item, item.ok)",
        "input.items.exists(item, item.ok)",
        "input.items.exists_one(item, item.ok)",
        "input.items.filter(item, item.ok).size() > 0",
        'input.items.map(item, item.ok.startsWith("yes")).size() > 0',
    ],
)
def test_mixed_error_ordering_is_preserved_across_decoded_messages(expression: str) -> None:
    prepared = PreparedFilter(expression)
    decoder = JsonEventDecoder()
    for raw_json in [b'{"items":[{},{"ok":1}]}', b'{"items":[{"ok":1},{}]}']:
        decoded = decoder.decode(_event(raw_json), schema={"type": "object"})
        assert isinstance(decoded, EventDecodeSuccess)
        before = encode_envelope(decoded.envelope)
        result = prepared.evaluate(decoded.envelope.payload)
        assert result.outcome == FilterOutcome.EVALUATION_ERROR
        assert result.error_code == FilterErrorCode.WRONG_TYPE
        assert encode_envelope(decoded.envelope) == before


@pytest.mark.parametrize(
    ("failure", "error_code"),
    [
        ("input.value + 1", FilterErrorCode.WRONG_TYPE),
        ("input.value.matches(input.pattern)", FilterErrorCode.EVALUATION_FAILED),
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_map_literal_error_priority_survives_json_decoding(
    *, failure: str, error_code: FilterErrorCode, reverse: bool
) -> None:
    decoded = JsonEventDecoder().decode(_event(b'{"value":"text","pattern":"["}'), schema={"type": "object"})
    assert isinstance(decoded, EventDecodeSuccess)
    before = encode_envelope(decoded.envelope)
    entries = ['"missing": input.missing', f'"failed": {failure}']
    if reverse:
        entries.reverse()
    expression = "{" + ", ".join(entries) + "}.size() == 2"
    result = PreparedFilter(expression).evaluate(decoded.envelope.payload)
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == error_code
    assert encode_envelope(decoded.envelope) == before


@pytest.mark.parametrize("operator", ["&&", "||"])
@pytest.mark.parametrize("reverse", [False, True])
def test_logical_error_merging_is_reused_across_decoded_messages(*, operator: str, reverse: bool) -> None:
    operands = ['input.severity.startsWith("crit")', 'input.source.startsWith("pay")']
    if reverse:
        operands.reverse()
    prepared = PreparedFilter(f"({operands[0]}) {operator} ({operands[1]})")
    decoder = JsonEventDecoder()
    cases = [
        (b"{}", FilterOutcome.NO_MATCH, None),
        (b'{"severity":1}', FilterOutcome.EVALUATION_ERROR, FilterErrorCode.WRONG_TYPE),
        (b'{"source":1}', FilterOutcome.EVALUATION_ERROR, FilterErrorCode.WRONG_TYPE),
        (b'{"severity":"critical","source":"payments"}', FilterOutcome.MATCH, None),
        (b'{"severity":"warning","source":"other"}', FilterOutcome.NO_MATCH, None),
        (b"{}", FilterOutcome.NO_MATCH, None),
    ]
    for raw_json, outcome, error_code in cases:
        decoded = decoder.decode(_event(raw_json), schema={"type": "object"})
        assert isinstance(decoded, EventDecodeSuccess)
        before = encode_envelope(decoded.envelope)
        result = prepared.evaluate(decoded.envelope.payload)
        assert result.outcome == outcome
        assert result.error_code == error_code
        assert encode_envelope(decoded.envelope) == before


@pytest.mark.parametrize("expression", ['input.labels.env == "prod"', 'input.labels["env"] == "prod"'])
def test_dot_and_bracket_access_agree_across_decoded_messages(expression: str) -> None:
    prepared = PreparedFilter(expression)
    decoder = JsonEventDecoder()
    cases = [
        (b"{}", FilterOutcome.NO_MATCH, None),
        (b'{"labels":{}}', FilterOutcome.NO_MATCH, None),
        (b'{"labels":{"env":"prod"}}', FilterOutcome.MATCH, None),
        (b'{"labels":null}', FilterOutcome.EVALUATION_ERROR, FilterErrorCode.WRONG_TYPE),
        (b'{"labels":1}', FilterOutcome.EVALUATION_ERROR, FilterErrorCode.WRONG_TYPE),
        (b'{"labels":{"env":"dev"}}', FilterOutcome.NO_MATCH, None),
        (b"{}", FilterOutcome.NO_MATCH, None),
    ]
    for raw_json, outcome, error_code in cases:
        decoded = decoder.decode(_event(raw_json), schema={"type": "object"})
        assert isinstance(decoded, EventDecodeSuccess)
        before = encode_envelope(decoded.envelope)
        result = prepared.evaluate(decoded.envelope.payload)
        assert result.outcome == outcome
        assert result.error_code == error_code
        assert encode_envelope(decoded.envelope) == before


@pytest.mark.parametrize("operator", ["+", "-", "*", "/", "%"])
@pytest.mark.parametrize("reverse", [False, True])
def test_arithmetic_missing_operands_survive_decoding_and_program_reuse(*, operator: str, reverse: bool) -> None:
    operands = ["1", "input.value"]
    if reverse:
        operands.reverse()
    prepared = PreparedFilter(f"(({operands[0]}) {operator} ({operands[1]})) >= -10")
    decoder = JsonEventDecoder()
    cases = [
        (b"{}", FilterOutcome.NO_MATCH, None),
        (b'{"value":"text"}', FilterOutcome.EVALUATION_ERROR, FilterErrorCode.WRONG_TYPE),
        (b'{"value":2}', FilterOutcome.MATCH, None),
        (b"{}", FilterOutcome.NO_MATCH, None),
    ]
    for raw_json, outcome, error_code in cases:
        decoded = decoder.decode(_event(raw_json), schema={"type": "object"})
        assert isinstance(decoded, EventDecodeSuccess)
        before = encode_envelope(decoded.envelope)
        result = prepared.evaluate(decoded.envelope.payload)
        assert result.outcome == outcome
        assert result.error_code == error_code
        assert encode_envelope(decoded.envelope) == before


@pytest.mark.parametrize(
    ("expression", "error_code"),
    [
        ("[input.missing, input.text + 1].size() == 2", FilterErrorCode.WRONG_TYPE),
        ("(input.missing).startsWith(input.text + 1)", FilterErrorCode.WRONG_TYPE),
        ("has(input.value.field)", FilterErrorCode.WRONG_TYPE),
        ('{"missing": input.missing, [1]: 2}.size() == 2', FilterErrorCode.WRONG_TYPE),
        ("input.missing == input.text.matches(input.pattern)", FilterErrorCode.EVALUATION_FAILED),
    ],
)
def test_composed_error_paths_survive_json_decoding(expression: str, error_code: FilterErrorCode) -> None:
    decoded = JsonEventDecoder().decode(
        _event(b'{"text":"value","value":null,"pattern":"["}'), schema={"type": "object"}
    )
    assert isinstance(decoded, EventDecodeSuccess)
    before = encode_envelope(decoded.envelope)
    result = PreparedFilter(expression).evaluate(decoded.envelope.payload)
    assert result.outcome == FilterOutcome.EVALUATION_ERROR
    assert result.error_code == error_code
    assert encode_envelope(decoded.envelope) == before


def test_literal_key_presence_checks_are_reused_across_decoded_messages() -> None:
    prepared = PreparedFilter('has(input["event-type"]) && input["event-type"] == "created"')
    decoder = JsonEventDecoder()
    cases = [
        (b'{"event-type":"created"}', FilterOutcome.MATCH),
        (b"{}", FilterOutcome.NO_MATCH),
        (b'{"event-type":null}', FilterOutcome.NO_MATCH),
        (b'{"event-type":"updated"}', FilterOutcome.NO_MATCH),
        (b'{"event-type":"created"}', FilterOutcome.MATCH),
    ]
    for raw_json, outcome in cases:
        decoded = decoder.decode(_event(raw_json), schema={"type": "object"})
        assert isinstance(decoded, EventDecodeSuccess)
        before = encode_envelope(decoded.envelope)
        result = prepared.evaluate(decoded.envelope.payload)
        assert result.outcome == outcome
        assert result.error_code is None
        assert encode_envelope(decoded.envelope) == before


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
