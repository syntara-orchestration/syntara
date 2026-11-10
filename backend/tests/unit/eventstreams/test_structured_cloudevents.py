"""Structured Kafka CloudEvents, shared normalization, and raw JSON boundaries."""

import base64
import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import JsonValue
from temporalio.converter import DataConverter

from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata
from syntara.eventstreams.core.envelope import RawEvent, RawEventHeader, WorkflowEventEnvelope
from syntara.eventstreams.core.results import EventDecodeFailure, EventFailureCode
from syntara.eventstreams.core.serialization import EventDecodeSuccess, JsonEventDecoder, encode_envelope


def _attributes() -> dict[str, JsonValue]:
    return {"specversion": "1.0", "id": "order-123", "source": "/orders", "type": "order.created"}


def _event(value: bytes, headers: list[tuple[str, bytes | None]] | None = None) -> RawEvent:
    return RawEvent(
        value=value,
        key=b"\xff\x00",
        headers=tuple(
            RawEventHeader(name=name, value=item)
            for name, item in (headers if headers is not None else [("content-type", b"application/cloudevents+json")])
        ),
        source_metadata=KafkaSourceMetadata(
            integration_id=UUID(int=1),
            subscription_id=UUID(int=2),
            source_generation=1,
            received_at=datetime(2026, 11, 6, tzinfo=UTC),
            topic="orders",
            partition=0,
            offset="9007199254740993",
        ),
    )


def _structured(data: JsonValue = None, **attributes: JsonValue) -> RawEvent:
    return _event(json.dumps({**_attributes(), **attributes, "data": data}).encode())


@pytest.mark.parametrize(
    "content_type",
    [
        b"application/cloudevents+json",
        b'Application/CloudEvents+JSON; charset="UTF-8"',
        b"application/cloudevents+json; charset=utf8",
        b"application/cloudevents+json \t; charset=utf8",
        b" application/cloudevents+json\t",
    ],
)
def test_complete_event_and_mode_precedence_preserve_all_originals(content_type: bytes) -> None:
    record = _event(
        json.dumps(
            {
                **_attributes(),
                "subject": "注文/123",
                "time": "2026-11-06T01:02:03.123456789+05:30",
                "dataschema": "https://example.invalid/do-not-fetch",
                "datacontenttype": "application/json",
                "attempt": 123,
                "enabled": True,
                "label": "☃",
                "unset": None,
                "data": {"orderId": 123},
            }
        ).encode(),
        [
            ("Content-Type", content_type),
            ("ce_specversion", b"9.0"),
            ("ce_id", b"spoof"),
            ("ce_id", None),
            ("CE_TYPE", b"\xff"),
            ("routing", b"\xff"),
            ("routing", None),
            ("routing", b""),
        ],
    )
    before = record.model_copy(deep=True)
    result = JsonEventDecoder().decode(record)
    assert isinstance(result, EventDecodeSuccess)
    attributes = result.envelope.cloudevents
    assert attributes is not None
    assert attributes.id == "order-123"
    assert attributes.specversion == "1.0"
    assert attributes.subject == "注文/123"
    assert attributes.time == "2026-11-06T01:02:03.123456789+05:30"
    assert attributes.datacontenttype == "application/json"
    assert attributes.extensions == {"attempt": "123", "enabled": "true", "label": "☃"}
    assert result.envelope.payload == {"orderId": 123}
    assert record == before
    original = result.envelope.original
    assert base64.b64decode(original.value_base64) == record.value
    assert original.key_base64 is not None
    assert base64.b64decode(original.key_base64) == record.key
    assert [
        (item.name, None if item.value_base64 is None else base64.b64decode(item.value_base64))
        for item in original.headers
    ] == [(item.name, item.value) for item in record.headers]
    assert result.envelope.source_metadata == record.source_metadata
    assert "order-123" not in repr(result)
    converter = DataConverter.default.payload_converter
    encoded = converter.to_payloads([result.envelope])
    assert encoded[0].data == encode_envelope(result.envelope)
    assert len(encoded[0].data) == result.encoded_envelope_bytes
    assert converter.from_payloads(encoded, [WorkflowEventEnvelope])[0] == result.envelope


@pytest.mark.parametrize(
    "data", [None, True, False, 123, -1.25, "text", '{"nested":true}', [1, None], {"orderId": 123}]
)
@pytest.mark.parametrize("data_type", [None, "application/json", "application/example+json; charset=utf-8"])
def test_equivalent_bindings_have_equal_payload_and_attributes(data: JsonValue, data_type: str | None) -> None:
    structured = _structured(data, datacontenttype=data_type, attempt=123, enabled=True)
    binary = _event(
        json.dumps(data).encode(),
        [
            ("ce_specversion", b"1.0"),
            ("ce_id", b"order-123"),
            ("ce_source", b"/orders"),
            ("ce_type", b"order.created"),
            ("ce_attempt", b"123"),
            ("ce_enabled", b"true"),
            *([] if data_type is None else [("content-type", data_type.encode())]),
        ],
    )
    first = JsonEventDecoder().decode(structured)
    second = JsonEventDecoder().decode(binary)
    assert isinstance(first, EventDecodeSuccess)
    assert isinstance(second, EventDecodeSuccess)
    assert first.envelope.payload == second.envelope.payload == data
    assert first.envelope.cloudevents == second.envelope.cloudevents
    assert first.envelope.original.value_base64 != second.envelope.original.value_base64


def test_omitted_and_null_data_share_payload_but_preserve_original_distinction() -> None:
    omitted = JsonEventDecoder().decode(_event(json.dumps({**_attributes(), "subject": None, "time": None}).encode()))
    explicit = JsonEventDecoder().decode(_structured(None))
    assert isinstance(omitted, EventDecodeSuccess)
    assert isinstance(explicit, EventDecodeSuccess)
    assert omitted.envelope.payload is explicit.envelope.payload is None
    assert omitted.envelope.cloudevents == explicit.envelope.cloudevents
    assert omitted.envelope.original != explicit.envelope.original


@pytest.mark.parametrize("value", [None, True, 1, "text", [], [{"specversion": "1.0"}]])
def test_structured_root_must_be_an_object(value: JsonValue) -> None:
    result = JsonEventDecoder().decode(_event(json.dumps(value).encode()))
    assert isinstance(result, EventDecodeFailure)
    assert result.code == EventFailureCode.malformed_cloudevents


@pytest.mark.parametrize("name", ["specversion", "id", "source", "type"])
@pytest.mark.parametrize("invalid", [None, "", True, 123, [], {}])
def test_required_attributes_are_typed_nonempty_strings(name: str, invalid: JsonValue) -> None:
    result = JsonEventDecoder().decode(_structured({}, **{name: invalid}))
    assert isinstance(result, EventDecodeFailure)
    assert result.code == EventFailureCode.malformed_cloudevents
    body = _attributes()
    del body[name]
    result = JsonEventDecoder().decode(_event(json.dumps(body).encode()))
    assert isinstance(result, EventDecodeFailure)
    assert result.code == EventFailureCode.malformed_cloudevents


@pytest.mark.parametrize(
    "attributes",
    [
        {"source": "invalid source"},
        {"dataschema": "/relative"},
        {"subject": ""},
        {"time": "2026-02-30T00:00:00Z"},
        {"id": "private\nvalue"},
        {"ID": "private"},
        {"bad_name": "private"},
        {"extensions": {}},
        {"attempt": []},
        {"attempt": {}},
        {"attempt": 1.0},
        {"attempt": 2**31},
        {"attempt": -(2**31) - 1},
    ],
)
def test_invalid_metadata_and_extension_types_are_sanitized(attributes: dict[str, JsonValue]) -> None:
    decoder = JsonEventDecoder()
    event = _structured({}, **attributes)
    before = event.model_copy(deep=True)
    result = decoder.decode(event)
    assert isinstance(result, EventDecodeFailure)
    assert result.code == EventFailureCode.malformed_cloudevents
    assert "private" not in result.message
    assert result.model_dump(mode="json") == {"code": "malformed_cloudevents"}
    assert event == before
    assert isinstance(decoder.decode(_structured({})), EventDecodeSuccess)


@pytest.mark.parametrize("extension", ["", 0, -(2**31), 2**31 - 1, False, True])
def test_supported_extension_values_use_canonical_strings(extension: JsonValue) -> None:
    result = JsonEventDecoder().decode(_structured({}, custom=extension))
    assert isinstance(result, EventDecodeSuccess)
    assert result.envelope.cloudevents is not None
    assert result.envelope.cloudevents.extensions["custom"] == (
        str(extension).lower() if isinstance(extension, bool) else str(extension)
    )


@pytest.mark.parametrize("version", ["0.3", "2.0", "1.0.2"])
def test_unsupported_versions_are_not_raw_json(version: str) -> None:
    result = JsonEventDecoder().decode(_structured({}, specversion=version))
    assert isinstance(result, EventDecodeFailure)
    assert result.code == EventFailureCode.unsupported_cloudevents_version


@pytest.mark.parametrize(
    "body",
    [
        {**_attributes(), "data_base64": "PRIVATE"},
        {**_attributes(), "data_base64": None},
        {**_attributes(), "data": "xml", "datacontenttype": "text/xml"},
        {**_attributes(), "data": {}, "datacontenttype": "application/avro"},
        {**_attributes(), "data": {}, "datacontenttype": "application/json; charset=latin1"},
    ],
)
def test_excluded_data_encodings_are_classified(body: dict[str, JsonValue]) -> None:
    result = JsonEventDecoder().decode(_event(json.dumps(body).encode()))
    assert isinstance(result, EventDecodeFailure)
    assert result.code == EventFailureCode.unsupported_cloudevents_data
    assert "PRIVATE" not in result.message


def test_conflicting_data_members_are_malformed_even_when_null() -> None:
    record = _event(json.dumps({**_attributes(), "data": None, "data_base64": None}).encode())
    result = JsonEventDecoder().decode(record)
    assert isinstance(result, EventDecodeFailure)
    assert result.code == EventFailureCode.malformed_cloudevents


@pytest.mark.parametrize("data_type", ["bad", "application/json; charset=utf8; charset=utf8"])
def test_malformed_data_content_type_is_bad_metadata(data_type: str) -> None:
    result = JsonEventDecoder().decode(_structured({}, datacontenttype=data_type))
    assert isinstance(result, EventDecodeFailure)
    assert result.code == EventFailureCode.malformed_cloudevents


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (b"{", EventFailureCode.invalid_json),
        (b"\xff", EventFailureCode.invalid_utf8),
        (b'{"id":"a","id":"b"}', EventFailureCode.duplicate_member),
        (b'{"data":{"x":1,"x":2}}', EventFailureCode.duplicate_member),
        (b'{"data":NaN}', EventFailureCode.non_finite_number),
        (b'{"data":"\\ud800"}', EventFailureCode.invalid_utf8),
    ],
)
def test_strict_json_rules_apply_before_structured_normalization(value: bytes, code: EventFailureCode) -> None:
    result = JsonEventDecoder().decode(_event(value))
    assert isinstance(result, EventDecodeFailure)
    assert result.code == code


def test_schema_validates_extracted_data_without_defaults() -> None:
    event = _structured({"orderId": 123}, dataschema="https://example.invalid/no-fetch")
    schema = {
        "type": "object",
        "required": ["orderId"],
        "additionalProperties": False,
        "properties": {"orderId": {"type": "integer"}, "extra": {"default": 99}},
    }
    result = JsonEventDecoder().decode(event, schema=schema)
    assert isinstance(result, EventDecodeSuccess)
    assert result.envelope.payload == {"orderId": 123}
    failure = JsonEventDecoder().decode(event, schema={"required": ["specversion"]})
    assert isinstance(failure, EventDecodeFailure)
    assert failure.code == EventFailureCode.schema_mismatch


def test_limits_cover_full_source_and_normalized_envelope() -> None:
    event = _structured({"orderId": 123}, custom="☃" * 50)
    result = JsonEventDecoder().decode(event)
    assert isinstance(result, EventDecodeSuccess)
    assert event.value is not None
    size = result.encoded_envelope_bytes
    assert size == len(encode_envelope(result.envelope))
    assert isinstance(JsonEventDecoder(max_envelope_bytes=size).decode(event), EventDecodeSuccess)
    failure = JsonEventDecoder(max_envelope_bytes=size - 1).decode(event)
    assert isinstance(failure, EventDecodeFailure)
    assert failure.code == EventFailureCode.envelope_too_large
    assert isinstance(JsonEventDecoder(max_value_bytes=len(event.value)).decode(event), EventDecodeSuccess)
    failure = JsonEventDecoder(max_value_bytes=len(event.value) - 1).decode(event)
    assert isinstance(failure, EventDecodeFailure)
    assert failure.code == EventFailureCode.value_too_large
    header_limited = event.model_copy(update={"headers": (*event.headers, RawEventHeader(name="routing", value=b"x"))})
    failure = JsonEventDecoder(max_headers=1).decode(header_limited)
    assert isinstance(failure, EventDecodeFailure)
    assert failure.code == EventFailureCode.too_many_headers


@pytest.mark.parametrize("headers", [[], [("content-type", b"application/json")]])
def test_body_shape_does_not_reclassify_ordinary_json(headers: list[tuple[str, bytes | None]]) -> None:
    body = {**_attributes(), "data": {"orderId": 123}}
    result = JsonEventDecoder().decode(_event(json.dumps(body).encode(), headers))
    assert isinstance(result, EventDecodeSuccess)
    assert result.envelope.payload == body
    assert result.envelope.cloudevents is None
