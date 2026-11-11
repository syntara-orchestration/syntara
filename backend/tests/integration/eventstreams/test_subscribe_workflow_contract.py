"""Component integration of Subscribe validation, envelopes, and activity mapping."""

import copy
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from syntara.core.exceptions import SafeValueError
from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata
from syntara.eventstreams.adapters.subscribe_parameters import validate_event_subscribe_parameters
from syntara.eventstreams.core.envelope import RawEvent, RawEventHeader
from syntara.eventstreams.core.serialization import EventDecodeSuccess, JsonEventDecoder, encode_envelope
from syntara.workflows.validators.workflow_definition import WorkflowValidator
from syntara.workflows.workflow_engine.activities.event_subscribe_trigger import event_subscribe_trigger


@pytest.fixture(autouse=True)
def _seed_authenticated_group() -> None:
    """Override the parent DB seed for a component path without persistence."""


@pytest.fixture
def definition() -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "name": "Subscribe",
        "nodes": [],
        "edges": [],
        "triggers": [
            {
                "id": "incoming",
                "type": "event_subscribe_trigger",
                "parameters": {
                    "topic": "alerts",
                    "integration_id": str(uuid4()),
                    "credential_id": str(uuid4()),
                    "input_schema": {"type": "object", "required": ["count"]},
                },
            }
        ],
    }


async def test_definition_to_envelope_output_mapping(definition: dict[str, Any]) -> None:
    WorkflowValidator().validate_workflow_definition(definition)
    assert WorkflowValidator().collect_findings(definition).error_count == 0
    config = validate_event_subscribe_parameters(definition["triggers"][0]["parameters"])
    source = RawEvent(
        value=b' {"count": 2} \n',
        key=b"\xff",
        headers=[RawEventHeader(name="trace", value=b"\xff"), RawEventHeader(name="trace", value=None)],
        source_metadata=KafkaSourceMetadata(
            integration_id=config.integration_id,
            subscription_id=uuid4(),
            source_generation=1,
            received_at=datetime.now(UTC),
            topic="alerts",
            partition=1,
            offset="9007199254740993",
        ),
    )
    before = source.model_copy(deep=True)
    decoded = JsonEventDecoder().decode(source, schema=config.input_schema)
    assert isinstance(decoded, EventDecodeSuccess)
    envelope = json.loads(encode_envelope(decoded.envelope))
    frozen = copy.deepcopy(envelope)
    assert await event_subscribe_trigger(envelope, None) == {"output": frozen}
    assert await event_subscribe_trigger(envelope, {"count": "${result.payload.count}"}) == {"output": {"count": 2}}
    assert await event_subscribe_trigger(envelope, {}) == {"output": {}}
    assert envelope == frozen
    assert source == before
    assert envelope["metadata"]["offset"] == "9007199254740993"
    assert envelope["original"]["headers"] == [
        {"name": "trace", "value_base64": "/w=="},
        {"name": "trace", "value_base64": None},
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("group_id", "caller-group"),
        ("source", {"topic": "nested"}),
        ("execution_account_id", "selected"),
        ("service_account_id", "selected"),
        ("execution_service_account_id", "selected"),
        ("selected_account_id", "selected"),
        ("unknown", True),
        # `transport` is no longer a trigger parameter — it must be rejected as an extra field.
        ("transport", "sns"),
        ("integration_id", "${trigger.integration}"),
        ("credential_id", "${trigger.credential}"),
        ("input_schema", {"$ref": "https://example.com/schema"}),
        ("input_schema", {"type": "invalid"}),
        ("input_schema", {"type": "string", "pattern": "(a+)+"}),
    ],
)
def test_definition_boundaries_reject_invalid_parameters(
    definition: dict[str, Any],
    field: str,
    value: Any,  # noqa: ANN401
) -> None:
    definition["triggers"][0]["parameters"][field] = value
    validator = WorkflowValidator()
    assert validator.collect_findings(definition).error_count > 0
    with pytest.raises(SafeValueError):
        validator.validate_workflow_definition(definition)


@pytest.mark.parametrize("field", ["integration_id", "credential_id", "topic"])
def test_definition_requires_explicit_bindings(definition: dict[str, Any], field: str) -> None:
    definition["triggers"][0]["parameters"].pop(field)
    with pytest.raises(SafeValueError):
        WorkflowValidator().validate_workflow_definition(definition)


@pytest.mark.parametrize("input_schema", [None, {}, {"type": "object"}])
def test_optional_schema_supported(definition: dict[str, Any], input_schema: dict[str, Any] | None) -> None:
    definition["triggers"][0]["parameters"]["input_schema"] = input_schema
    WorkflowValidator().validate_workflow_definition(definition)


@pytest.mark.parametrize("structured", [False, True])
async def test_cloudevents_definition_decode_and_output_mapping(
    definition: dict[str, Any], *, structured: bool
) -> None:
    WorkflowValidator().validate_workflow_definition(definition)
    config = validate_event_subscribe_parameters(definition["triggers"][0]["parameters"])
    attributes = {"specversion": "1.0", "id": "event-1", "source": "/alerts", "type": "alert.created"}
    headers = [RawEventHeader(name="routing", value=b"route-1")]
    if structured:
        value = json.dumps({**attributes, "data": {"count": 2}}).encode()
        headers.append(RawEventHeader(name="content-type", value=b"application/cloudevents+json"))
    else:
        value = b'{"count":2}'
        headers.extend(RawEventHeader(name="ce_" + name, value=item.encode()) for name, item in attributes.items())
    source = RawEvent(
        value=value,
        key=b"key-1",
        headers=tuple(headers),
        source_metadata=KafkaSourceMetadata(
            integration_id=config.integration_id,
            subscription_id=uuid4(),
            source_generation=1,
            received_at=datetime.now(UTC),
            topic=config.topic,
            partition=0,
            offset="1",
        ),
    )
    decoded = JsonEventDecoder().decode(source, schema=config.input_schema)
    assert isinstance(decoded, EventDecodeSuccess)
    envelope = json.loads(encode_envelope(decoded.envelope))
    output = await event_subscribe_trigger(
        envelope, {"count": "${result.payload.count}", "eventType": "${result.cloudevents.type}"}
    )
    assert output == {"output": {"count": 2, "eventType": "alert.created"}}
    assert envelope["original"]["key_base64"] == "a2V5LTE="
    assert envelope["original"]["headers"][0] == {"name": "routing", "value_base64": "cm91dGUtMQ=="}


async def test_cloudevents_definition_to_envelope_output_mapping(definition: dict[str, Any]) -> None:
    definition["triggers"][0]["parameters"]["input_schema"] = {
        "type": "object",
        "required": ["orderId"],
        "properties": {"orderId": {"type": "integer"}},
        "additionalProperties": False,
    }
    validator = WorkflowValidator()
    validator.validate_workflow_definition(definition)
    assert validator.collect_findings(definition).error_count == 0
    config = validate_event_subscribe_parameters(definition["triggers"][0]["parameters"])
    source = RawEvent(
        value=b'{"orderId":123}',
        key=b"order-123",
        headers=[
            RawEventHeader(name="content-type", value=b"application/json"),
            RawEventHeader(name="ce_specversion", value=b"1.0"),
            RawEventHeader(name="ce_id", value=b"event-123"),
            RawEventHeader(name="ce_source", value=b"/orders"),
            RawEventHeader(name="ce_type", value=b"order.created"),
            RawEventHeader(name="routing", value=b"orders"),
            RawEventHeader(name="routing", value=None),
        ],
        source_metadata=KafkaSourceMetadata(
            integration_id=config.integration_id,
            subscription_id=uuid4(),
            source_generation=1,
            received_at=datetime.now(UTC),
            topic=config.topic,
            partition=0,
            offset="42",
        ),
    )
    before = source.model_copy(deep=True)
    decoded = JsonEventDecoder().decode(source, schema=config.input_schema)
    assert isinstance(decoded, EventDecodeSuccess)
    envelope = json.loads(encode_envelope(decoded.envelope))
    frozen = copy.deepcopy(envelope)
    assert await event_subscribe_trigger(envelope, None) == {"output": frozen}
    assert await event_subscribe_trigger(
        envelope,
        {"orderId": "${result.payload.orderId}", "eventType": "${result.cloudevents.type}"},
    ) == {"output": {"orderId": 123, "eventType": "order.created"}}
    assert envelope["payload"] == {"orderId": 123}
    assert envelope["cloudevents"]["id"] == "event-123"
    assert envelope["original"]["key_base64"] == "b3JkZXItMTIz"
    assert envelope["original"]["headers"][-2:] == [
        {"name": "routing", "value_base64": "b3JkZXJz"},
        {"name": "routing", "value_base64": None},
    ]
    assert envelope == frozen
    assert source == before
