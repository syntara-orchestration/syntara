"""Equivalent CloudEvents bindings through real decoding, CEL, and trigger mapping."""

import json
from datetime import UTC, datetime
from uuid import UUID

import pytest

from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata
from syntara.eventstreams.core.envelope import RawEvent, RawEventHeader
from syntara.eventstreams.core.filter_input import EventFilterInput
from syntara.eventstreams.core.filtering import PreparedSubscriptionFilter
from syntara.eventstreams.core.results import EventDecodeFailure
from syntara.eventstreams.core.serialization import EventDecodeSuccess, JsonEventDecoder, encode_envelope
from syntara.eventstreams.models.filter_configuration import FilterConfiguration
from syntara.filtering.models.result import FilterOutcome
from syntara.workflows.workflow_engine.activities.event_subscribe_trigger import event_subscribe_trigger

pytestmark = pytest.mark.integration


@pytest.fixture(params=["binary", "structured"])
def event(request: pytest.FixtureRequest) -> RawEvent:
    attributes = {
        "specversion": "1.0",
        "id": "event-123",
        "source": "/orders",
        "type": "order.created",
        "subject": "order-123",
        "time": "2026-11-12T01:02:03Z",
        "dataschema": "https://example.invalid/orders",
        "datacontenttype": "application/json",
    }
    headers = [
        RawEventHeader(name="routing", value=b"orders"),
        RawEventHeader(name="routing", value=None),
        RawEventHeader(name="routing", value=b""),
        RawEventHeader(name="routing", value=b"\xff"),
    ]
    data = {"amount": 1500}
    if request.param == "structured":
        value = json.dumps({**attributes, "priority": 3, "enabled": True, "data": data}).encode()
        headers.extend(
            [
                RawEventHeader(name="content-type", value=b"application/cloudevents+json"),
                RawEventHeader(name="ce_type", value=b"spoofed.type"),
            ]
        )
    else:
        value = json.dumps(data).encode()
        headers.append(RawEventHeader(name="content-type", value=b"application/json"))
        headers.extend(
            RawEventHeader(name="ce_" + name, value=text.encode())
            for name, text in attributes.items()
            if name != "datacontenttype"
        )
        headers.extend(
            [
                RawEventHeader(name="ce_priority", value=b"3"),
                RawEventHeader(name="ce_enabled", value=b"true"),
            ]
        )
    return RawEvent(
        value=value,
        key=b"order-123",
        headers=tuple(headers),
        source_metadata=KafkaSourceMetadata(
            integration_id=UUID(int=1),
            subscription_id=UUID(int=2),
            source_generation=1,
            received_at=datetime(2026, 11, 12, tzinfo=UTC),
            topic="orders",
            partition=0,
            offset="42",
        ),
    )


@pytest.mark.parametrize(
    ("expression", "outcome"),
    [
        ('input.cloudevents.type == "order.created" && input.payload.value.amount > 1000', FilterOutcome.MATCH),
        ('input.cloudevents.type == "order.cancelled"', FilterOutcome.NO_MATCH),
        (
            'input.cloudevents.extensions.priority == "3" && input.cloudevents.extensions.enabled == "true"',
            FilterOutcome.MATCH,
        ),
        ('input.cloudevents.extensions.priority == "4"', FilterOutcome.NO_MATCH),
        (
            'input.cloudevents.id == "event-123" && input.cloudevents.specversion == "1.0" '
            '&& input.cloudevents.source == "/orders"',
            FilterOutcome.MATCH,
        ),
        (
            'input.cloudevents.subject == "order-123" && input.cloudevents.time == "2026-11-12T01:02:03Z"',
            FilterOutcome.MATCH,
        ),
        (
            'input.cloudevents.datacontenttype == "application/json" && input.cloudevents.dataschema == "https://example.invalid/orders"',
            FilterOutcome.MATCH,
        ),
        (
            'input.key.text == "order-123" && input.headers.routing.exists(h, h.text == "orders") '
            '&& input.cloudevents.type == "order.created"',
            FilterOutcome.MATCH,
        ),
        ('input.key.text == "other" || input.cloudevents.type == "order.created"', FilterOutcome.MATCH),
        ('!(input.cloudevents.type == "order.created")', FilterOutcome.NO_MATCH),
        ('input["cloudevents"]["type"] == "order.created"', FilterOutcome.MATCH),
        ("input.cloudevents == null", FilterOutcome.NO_MATCH),
    ],
)
def test_equivalent_bindings_filter_normalized_attributes(
    event: RawEvent, expression: str, outcome: FilterOutcome
) -> None:
    before = event.model_copy(deep=True)
    prepared = PreparedSubscriptionFilter(FilterConfiguration(expression=expression))
    early = EventFilterInput.from_event(event)
    assert early.cloudevents is None
    # Attribute-dependent conditions cannot be decided using the pre-decode null.
    assert prepared.precheck(early).outcome == FilterOutcome.MATCH
    decoded = JsonEventDecoder().decode(event)
    assert isinstance(decoded, EventDecodeSuccess)
    encoded = encode_envelope(decoded.envelope)
    view = EventFilterInput.from_event(event, decoded)
    assert view.cloudevents is not None
    assert prepared.evaluate(view).outcome == outcome
    assert view.source_metadata == event.source_metadata.model_dump(mode="json")
    assert [item.kind for item in view.headers["routing"]] == ["text", "null", "text", "binary"]
    assert [item.text for item in view.headers["routing"]] == ["orders", None, "", None]
    assert view.key.text == "order-123"
    assert encode_envelope(decoded.envelope) == encoded
    assert event == before


@pytest.mark.parametrize("value", [b'{"amount":1500}', b"invalid-json"])
def test_non_cloudevents_inputs_keep_null_attributes(event: RawEvent, value: bytes) -> None:
    ordinary = event.model_copy(update={"value": value, "headers": ()})
    decoded = JsonEventDecoder().decode(ordinary)
    view = EventFilterInput.from_event(ordinary, decoded)
    assert view.cloudevents is None
    assert view.payload.state == ("decode_error" if isinstance(decoded, EventDecodeFailure) else "decoded")
    if isinstance(decoded, EventDecodeSuccess):
        for expression, expected in [
            ('input.cloudevents != null && input.cloudevents.type == "order.created"', FilterOutcome.NO_MATCH),
            ("input.cloudevents == null && input.payload.value.amount > 1000", FilterOutcome.MATCH),
        ]:
            prepared = PreparedSubscriptionFilter(FilterConfiguration(expression=expression))
            assert prepared.evaluate(view).outcome == expected


async def test_filtering_preserves_workflow_input_and_attribute_mapping(event: RawEvent) -> None:
    decoded = JsonEventDecoder().decode(event, schema={"type": "object", "required": ["amount"]})
    assert isinstance(decoded, EventDecodeSuccess)
    before = encode_envelope(decoded.envelope)
    prepared = PreparedSubscriptionFilter(FilterConfiguration(expression='input.cloudevents.type == "order.created"'))
    assert prepared.evaluate(EventFilterInput.from_event(event, decoded)).outcome == FilterOutcome.MATCH
    output = await event_subscribe_trigger(
        json.loads(before), {"amount": "${result.payload.amount}", "eventType": "${result.cloudevents.type}"}
    )
    assert output == {"output": {"amount": 1500, "eventType": "order.created"}}
    assert encode_envelope(decoded.envelope) == before
