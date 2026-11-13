"""Original expression contracts and conservative native-AST early checks."""

from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata
from syntara.eventstreams.adapters.subscribe_parameters import validate_event_subscribe_parameters
from syntara.eventstreams.core.envelope import RawEvent, RawEventHeader
from syntara.eventstreams.core.filter_input import EventFilterInput
from syntara.eventstreams.core.filtering import PreparedSubscriptionFilter
from syntara.eventstreams.core.serialization import EventDecodeSuccess, JsonEventDecoder
from syntara.eventstreams.models.filter_configuration import FilterConfiguration
from syntara.filtering import evaluator as evaluator_module
from syntara.filtering.evaluator import PreparedFilter
from syntara.filtering.models.result import FilterErrorCode, FilterOutcome


def raw_event(
    *, key: bytes | None = b"orders-1", headers: tuple[RawEventHeader, ...] = (), value: bytes | None = b'{"ok":true}'
) -> RawEvent:
    """Use real Kafka metadata without broker connectivity."""
    return RawEvent(
        key=key,
        headers=headers,
        value=value,
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


@pytest.mark.parametrize("integration_type", [None, "kafka"])
def test_original_combined_expression_survives_parameter_round_trip(integration_type: str | None) -> None:
    expression = '  input.key.text == "orders-1" || input.payload.value.ok  '
    parameters = {
        "integration_id": str(uuid4()),
        "credential_id": str(uuid4()),
        "topic": "orders",
        "filter": {"expression": expression},
    }
    validated = validate_event_subscribe_parameters(parameters, integration_type=integration_type)
    assert validated.model_dump(mode="json")["filter"] == {"expression": expression}


@pytest.mark.parametrize(
    "configuration",
    [
        {"expression": "input =="},
        {"expression": "unknown(input)"},
        {"expression": "message.value"},
        {"expression": "42"},
        {"expression": "true && 1"},
        {"expression": 1},
        {"expression": "true", "format_version": 1},
        {"key": {"pattern": "orders-*"}},
    ],
)
def test_invalid_filters_are_rejected(configuration: object) -> None:
    with pytest.raises(ValidationError):
        validate_event_subscribe_parameters(
            {
                "integration_id": str(uuid4()),
                "credential_id": str(uuid4()),
                "topic": "orders",
                "filter": configuration,
            }
        )


@pytest.mark.parametrize("expression", ["", "  ", "\n\t"])
def test_cleared_editor_normalizes_to_null(expression: str) -> None:
    validated = validate_event_subscribe_parameters(
        {
            "integration_id": str(uuid4()),
            "credential_id": str(uuid4()),
            "topic": "orders",
            "filter": {"expression": expression},
        }
    )
    assert validated.filter is None
    assert validated.model_dump(mode="json")["filter"] is None


@pytest.mark.parametrize(
    ("expression", "key", "expected"),
    [
        ('input.key.text == "wanted" && input.payload.value.ok', b"other", FilterOutcome.NO_MATCH),
        ('input.key.text == "wanted" || input.payload.value.ok', b"other", FilterOutcome.MATCH),
        ('!(input.key.text == "wanted" || input.payload.value.ok)', b"other", FilterOutcome.MATCH),
        ('input["key"].text == "wanted" && input.payload.value.ok', b"other", FilterOutcome.NO_MATCH),
        ('input[input.payload.value.field].text == "wanted"', b"other", FilterOutcome.MATCH),
        ("input.key.missing && input.payload.value.ok", b"other", FilterOutcome.MATCH),
        ("input.key.text + 1 == 2 && input.payload.value.ok", b"other", FilterOutcome.MATCH),
    ],
)
def test_precheck_rejects_only_proven_false_mandatory_conditions(expression, key, expected) -> None:
    prepared = PreparedSubscriptionFilter(FilterConfiguration(expression=expression))
    assert prepared.precheck(EventFilterInput.from_event(raw_event(key=key))).outcome == expected


def test_extracted_errors_wait_for_complete_boolean_resolution() -> None:
    prepared = PreparedSubscriptionFilter(
        FilterConfiguration(expression="input.key.text + 1 == 2 && input.payload.value.ok")
    )
    event = raw_event(value=b'{"ok":false}')
    decoded = JsonEventDecoder().decode(event)
    assert isinstance(decoded, EventDecodeSuccess)
    assert prepared.precheck(EventFilterInput.from_event(event)).outcome == FilterOutcome.MATCH
    assert prepared.evaluate(EventFilterInput.from_event(event, decoded)).outcome == FilterOutcome.NO_MATCH


def test_duplicate_header_macro_can_reject_before_decoding() -> None:
    prepared = PreparedSubscriptionFilter(
        FilterConfiguration(expression='input.headers.env.exists(h, h.text == "prod") && input.payload.value.ok')
    )
    event = raw_event(headers=(RawEventHeader(name="env", value=b"dev"),), value=b"invalid-json")
    assert prepared.precheck(EventFilterInput.from_event(event)).outcome == FilterOutcome.NO_MATCH


def test_input_shadowing_does_not_create_a_false_early_rejection() -> None:
    prepared = PreparedSubscriptionFilter(
        FilterConfiguration(expression='input.payload.value.items.all(input, input.key == "x")')
    )
    assert prepared.precheck(EventFilterInput.from_event(raw_event())).outcome == FilterOutcome.MATCH


def test_native_program_is_compiled_once_and_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    compiler = Mock(wraps=evaluator_module.compile_expression)
    monkeypatch.setattr(evaluator_module, "compile_expression", compiler)
    expression = 'input.key.text.startsWith("orders-") && input.payload.value.ok'
    configuration = FilterConfiguration(expression=expression)
    prepared = PreparedSubscriptionFilter(configuration)
    event = raw_event()
    decoded = JsonEventDecoder().decode(event)
    assert isinstance(decoded, EventDecodeSuccess)
    for _ in range(3):
        assert prepared.precheck(EventFilterInput.from_event(event)).outcome == FilterOutcome.MATCH
        assert prepared.evaluate(EventFilterInput.from_event(event, decoded)).outcome == FilterOutcome.MATCH
    compiler.assert_called_once_with(expression)


def test_binary_null_empty_and_duplicate_values_are_lossless() -> None:
    event = raw_event(
        key=b"\xff",
        headers=(
            RawEventHeader(name="env", value=None),
            RawEventHeader(name="env", value=b""),
            RawEventHeader(name="env", value=b"\xff"),
            RawEventHeader(name="env", value=b"prod"),
        ),
    )
    view = EventFilterInput.from_event(event)
    assert view.key.kind == "binary"
    assert view.key.base64 == "/w=="
    assert [value.kind for value in view.headers["env"]] == ["null", "text", "binary", "text"]
    assert view.headers["env"][1].text == ""
    assert view.source_metadata["offset"] == "9007199254740993"
    prepared = PreparedSubscriptionFilter(
        FilterConfiguration(expression='input.headers.env.exists(h, h.text == "prod")')
    )
    assert prepared.precheck(view).outcome == FilterOutcome.MATCH


def test_standard_regex_is_available_without_custom_wildcard_functions() -> None:
    view = EventFilterInput.from_event(raw_event())
    prepared = PreparedSubscriptionFilter(FilterConfiguration(expression='input.key.text.matches("^orders-[0-9]+$")'))
    assert prepared.precheck(view).outcome == FilterOutcome.MATCH
    error = PreparedSubscriptionFilter(FilterConfiguration(expression='input.key.text.matches(input.key.text + "[")'))
    assert error.precheck(view).error_code == FilterErrorCode.EVALUATION_FAILED


@pytest.mark.parametrize(
    ("expression", "outcome"),
    [
        ('input.key.text == "other" || input.payload.value.ok', FilterOutcome.MATCH),
        ('!(input.key.text == "other" || input.payload.value.ok)', FilterOutcome.NO_MATCH),
        ('(input.key.text == "other" || input.payload.value.ok) && input.key.kind == "text"', FilterOutcome.MATCH),
        ("input.key.missing || input.payload.value.ok", FilterOutcome.MATCH),
        ("input.key.text + 1 == 2 || input.payload.value.ok", FilterOutcome.MATCH),
        ('input.key.text == "other" && input.payload.value.missing', FilterOutcome.NO_MATCH),
    ],
)
def test_precheck_and_full_expression_preserve_native_boolean_and_error_behavior(
    expression: str,
    outcome: FilterOutcome,
) -> None:
    event = raw_event()
    decoded = JsonEventDecoder().decode(event)
    assert isinstance(decoded, EventDecodeSuccess)
    prepared = PreparedSubscriptionFilter(FilterConfiguration(expression=expression))
    before = prepared.precheck(EventFilterInput.from_event(event))
    view = EventFilterInput.from_event(event, decoded)
    complete = PreparedFilter(expression).evaluate(view.model_dump(mode="json", exclude_unset=True))
    assert complete.outcome == outcome
    assert prepared.evaluate(view) == complete
    if before.outcome != FilterOutcome.MATCH:
        assert before == complete
