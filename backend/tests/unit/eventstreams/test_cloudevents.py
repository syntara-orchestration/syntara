"""Kafka CloudEvents decoding contracts, including ordinary JSON boundaries."""

import base64
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError
from temporalio.converter import DataConverter

from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata
from syntara.eventstreams.core.cloudevents import CloudEventAttributes
from syntara.eventstreams.core.envelope import RawEvent, RawEventHeader, WorkflowEventEnvelope
from syntara.eventstreams.core.results import EventDecodeFailure, EventFailureCode
from syntara.eventstreams.core.serialization import EventDecodeSuccess, JsonEventDecoder, encode_envelope


def _headers(**overrides: bytes | None) -> list[tuple[str, bytes | None]]:
    return list(
        {
            "ce_specversion": b"1.0",
            "ce_id": b"order-123",
            "ce_source": b"/orders",
            "ce_type": b"order.created",
            **overrides,
        }.items()
    )


def _record(value: bytes | None = b'{"orderId":123}', **overrides: Any) -> RawEvent:  # noqa: ANN401
    headers = overrides.pop("headers", _headers())
    return RawEvent(
        value=value,
        headers=tuple(RawEventHeader(name=name, value=data) for name, data in headers),
        source_metadata=KafkaSourceMetadata(
            integration_id=UUID(int=1),
            subscription_id=UUID(int=2),
            source_generation=1,
            received_at=datetime(2026, 11, 5, tzinfo=UTC),
            topic="orders",
            partition=0,
            offset="9007199254740993",
        ),
        **overrides,
    )


def test_complete_binary_event_preserves_original_and_typed_temporal_round_trip() -> None:
    headers = [
        *_headers(
            ce_subject="注文/123".encode(),
            ce_time=b"2026-11-05T12:34:56.123456789+05:30",
            ce_dataschema=b"https://example.com/schemas/order",
            ce_partitionkey=b"routing-key",
            ce_attempt=b"123",
            ce_enabled=b"true",
        ),
        ("Content-Type", b'application/vnd.example+json; charset="UTF-8"'),
        ("routing", b"\x00\xff"),
        ("routing", None),
        ("routing", b""),
    ]
    record = _record(b' {"orderId":123} \n', key=b"\xff\x00", headers=headers)
    before = record.model_copy(deep=True)
    result = JsonEventDecoder().decode(record)
    assert isinstance(result, EventDecodeSuccess)
    envelope = result.envelope
    assert envelope.payload == {"orderId": 123}
    assert envelope.cloudevents is not None
    assert envelope.cloudevents.model_dump() == {
        "specversion": "1.0",
        "id": "order-123",
        "source": "/orders",
        "type": "order.created",
        "subject": "注文/123",
        "time": "2026-11-05T12:34:56.123456789+05:30",
        "dataschema": "https://example.com/schemas/order",
        "datacontenttype": 'application/vnd.example+json; charset="UTF-8"',
        "extensions": {"partitionkey": "routing-key", "attempt": "123", "enabled": "true"},
    }
    assert base64.b64decode(envelope.original.value_base64) == record.value
    assert envelope.original.key_base64 is not None
    assert base64.b64decode(envelope.original.key_base64) == record.key
    assert [
        (header.name, None if header.value_base64 is None else base64.b64decode(header.value_base64))
        for header in envelope.original.headers
    ] == headers
    assert envelope.source_metadata == record.source_metadata
    assert record == before
    converter = DataConverter.default.payload_converter
    encoded = converter.to_payloads([envelope])
    assert encoded[0].data == encode_envelope(envelope)
    assert len(encoded[0].data) == result.encoded_envelope_bytes
    restored = converter.from_payloads(encoded, [WorkflowEventEnvelope])[0]
    assert restored == envelope
    assert isinstance(restored.cloudevents, CloudEventAttributes)


@pytest.mark.parametrize("value", [b"null", b"true", b"42", b'"text"', b"[1,null]", b'{"a":1}'])
@pytest.mark.parametrize("content_type", [None, b"application/json", b"application/example+json; charset=utf8"])
def test_supported_json_roots_and_content_types(value: bytes, content_type: bytes | None) -> None:
    headers = _headers()
    if content_type is not None:
        headers.append(("content-type", content_type))
    result = JsonEventDecoder().decode(_record(value, headers=headers))
    assert isinstance(result, EventDecodeSuccess)
    assert result.envelope.payload == json.loads(value)
    assert result.envelope.cloudevents is not None
    assert result.envelope.cloudevents.datacontenttype == (None if content_type is None else content_type.decode())


@pytest.mark.parametrize("header", ["ce_specversion", "ce_id", "ce_source", "ce_type"])
def test_each_required_header_identifies_an_incomplete_candidate(header: str) -> None:
    result = JsonEventDecoder().decode(_record(headers=[(header, b"1.0")]))
    assert isinstance(result, EventDecodeFailure)
    assert result.code == EventFailureCode.malformed_cloudevents


@pytest.mark.parametrize(
    "headers",
    [
        [],
        [("ce_traceparent", b"\xff")],
        [("ce_subject", None)],
        [("ce-type", b"order.created"), ("ce-specversion", b"1.0")],
        [("routing", b"\xff"), ("routing", None), ("routing", b"")],
    ],
)
def test_non_candidates_remain_ordinary_json(headers: list[tuple[str, bytes | None]]) -> None:
    # Body shape is deliberately CloudEvents-like; it is never used for detection.
    record = _record(b'{"specversion":"1.0","type":"example","data":{"a":1}}', headers=headers)
    result = JsonEventDecoder().decode(record)
    assert isinstance(result, EventDecodeSuccess)
    assert result.envelope.cloudevents is None
    assert result.envelope.payload == json.loads(record.value or b"")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ce_id", b""),
        ("ce_source", b""),
        ("ce_type", b""),
        ("ce_specversion", b""),
        ("ce_specversion", b"1.0\n"),
        ("ce_id", None),
        ("ce_subject", None),
        ("ce_subject", b""),
        ("ce_id", b"\xff"),
        ("ce_id", b"private\nvalue"),
        ("ce_id", "private\u0085value".encode()),
        ("ce_id", "private\ufdd0value".encode()),
        ("ce_id", "private\U0001ffffvalue".encode()),
        ("ce_source", b"not a uri"),
        ("ce_source", b"/broken%escape"),
        ("ce_dataschema", b"/relative/schema"),
        ("ce_dataschema", b"https://example.com/broken space"),
        ("ce_time", b"2026-11-05"),
        ("ce_time", b"2026-11-05T12:00:00"),
        ("ce_time", b"2026-02-30T12:00:00Z"),
        ("ce_time", b"2026-11-05T24:00:00Z"),
        ("ce_time", b"2026-11-05T12:00:00+24:00"),
        ("ce_custom", None),
        ("ce_custom", b"\xff"),
        ("ce_custom", b"private\x00value"),
        ("ce_bad_name", b"private"),
        ("ce_", b"private"),
        ("ce_data", b"private"),
        ("ce_datacontenttype", b"application/json"),
        ("ce_extensions", b"private"),
        ("CE_TYPE", b"private"),
        ("ce_Custom", b"private"),
    ],
)
def test_malformed_attributes_are_sanitized_and_do_not_poison_decoder(name: str, value: bytes | None) -> None:
    decoder = JsonEventDecoder()
    record = _record(headers=_headers(**{name: value}))
    before = record.model_copy(deep=True)
    result = decoder.decode(record)
    assert isinstance(result, EventDecodeFailure)
    assert result.code == EventFailureCode.malformed_cloudevents
    assert result.model_dump() == {"code": "malformed_cloudevents"}
    assert "private" not in result.message
    assert record == before
    assert isinstance(decoder.decode(_record()), EventDecodeSuccess)


@pytest.mark.parametrize("name", ["ce_id", "ce_specversion", "ce_subject", "ce_custom"])
def test_repeated_cloudevents_attributes_are_not_collapsed(name: str) -> None:
    headers = _headers()
    if name not in dict(headers):
        headers.append((name, b"value"))
    headers.append((name, dict(headers)[name]))
    result = JsonEventDecoder().decode(_record(headers=headers))
    assert isinstance(result, EventDecodeFailure)
    assert result.code == EventFailureCode.malformed_cloudevents


@pytest.mark.parametrize("version", [b"0.3", b"2.0", b"1.0.2"])
def test_unsupported_versions_have_a_distinct_failure(version: bytes) -> None:
    result = JsonEventDecoder().decode(_record(headers=_headers(ce_specversion=version)))
    assert isinstance(result, EventDecodeFailure)
    assert result.code == EventFailureCode.unsupported_cloudevents_version


@pytest.mark.parametrize(
    "content_type",
    [
        b"application/cloudevents+avro",
        b"application/cloudevents-batch+json",
    ],
)
@pytest.mark.parametrize("binary_headers", [False, True])
def test_unsupported_structured_formats_are_rejected_before_json_or_binary_fallback(
    content_type: bytes, *, binary_headers: bool
) -> None:
    headers = [*(_headers() if binary_headers else []), ("content-type", content_type)]
    result = JsonEventDecoder().decode(_record(b"not even json", headers=headers))
    assert isinstance(result, EventDecodeFailure)
    assert result.code == EventFailureCode.unsupported_cloudevents_mode


@pytest.mark.parametrize(
    ("value", "headers", "code"),
    [
        (None, _headers(), EventFailureCode.tombstone),
        (b"", _headers(), EventFailureCode.invalid_json),
        (b"{", _headers(), EventFailureCode.invalid_json),
        (b"\xff", _headers(), EventFailureCode.invalid_utf8),
        (b'{"a":1,"a":2}', _headers(), EventFailureCode.duplicate_member),
        (b"NaN", _headers(), EventFailureCode.non_finite_number),
        (b"\x00\x00\x00\x00\x01", _headers(), EventFailureCode.registry_framing),
        (b"{}", [*_headers(), ("content-type", b"application/avro")], EventFailureCode.unsupported_content_type),
        (
            b"{}",
            [*_headers(), ("content-type", b"application/json; charset=latin1")],
            EventFailureCode.unsupported_content_type,
        ),
        (b"{}", [*_headers(), ("content-type", b"broken")], EventFailureCode.malformed_content_type),
        (
            b"{}",
            [*_headers(), ("content-type", b"application/json"), ("Content-Type", b"application/json")],
            EventFailureCode.duplicate_content_type,
        ),
    ],
)
def test_existing_failures_apply_to_cloudevents(
    value: bytes | None, headers: list[tuple[str, bytes | None]], code: EventFailureCode
) -> None:
    result = JsonEventDecoder().decode(_record(value, headers=headers))
    assert isinstance(result, EventDecodeFailure)
    assert result.code == code


def test_schema_checks_only_payload_without_defaults_or_dataschema_fetch() -> None:
    record = _record(headers=_headers(ce_dataschema=b"https://example.invalid/do-not-fetch"))
    schema = {
        "type": "object",
        "required": ["orderId"],
        "additionalProperties": False,
        "properties": {"orderId": {"type": "integer"}, "extra": {"default": 1}},
    }
    result = JsonEventDecoder().decode(record, schema=schema)
    assert isinstance(result, EventDecodeSuccess)
    assert result.envelope.payload == {"orderId": 123}
    failure = JsonEventDecoder().decode(record, schema={"type": "array"})
    assert isinstance(failure, EventDecodeFailure)
    assert failure.code == EventFailureCode.schema_mismatch


def test_limits_include_normalized_attributes_and_preserved_originals() -> None:
    record = _record(headers=_headers(ce_custom="☃".encode() * 50))
    result = JsonEventDecoder().decode(record)
    assert isinstance(result, EventDecodeSuccess)
    size = result.encoded_envelope_bytes
    assert size == len(encode_envelope(result.envelope))
    assert isinstance(JsonEventDecoder(max_envelope_bytes=size).decode(record), EventDecodeSuccess)
    failure = JsonEventDecoder(max_envelope_bytes=size - 1).decode(record)
    assert isinstance(failure, EventDecodeFailure)
    assert failure.code == EventFailureCode.envelope_too_large
    without_attributes = result.envelope.model_copy(update={"cloudevents": None})
    failure = JsonEventDecoder(max_envelope_bytes=len(encode_envelope(without_attributes))).decode(record)
    assert isinstance(failure, EventDecodeFailure)
    assert failure.code == EventFailureCode.envelope_too_large
    assert record.value is not None
    assert isinstance(JsonEventDecoder(max_value_bytes=len(record.value)).decode(record), EventDecodeSuccess)
    failure = JsonEventDecoder(max_value_bytes=len(record.value) - 1).decode(record)
    assert isinstance(failure, EventDecodeFailure)
    assert failure.code == EventFailureCode.value_too_large
    failure = JsonEventDecoder(max_headers=len(record.headers) - 1).decode(record)
    assert isinstance(failure, EventDecodeFailure)
    assert failure.code == EventFailureCode.too_many_headers


@pytest.mark.parametrize("source", ["/orders", "orders/123", "urn:example:orders", "https://example.com/orders"])
def test_source_uri_references_are_preserved(source: str) -> None:
    result = JsonEventDecoder().decode(_record(headers=_headers(ce_source=source.encode())))
    assert isinstance(result, EventDecodeSuccess)
    assert result.envelope.cloudevents is not None
    assert result.envelope.cloudevents.source == source


@pytest.mark.parametrize("extensions", [{"id": "spoof"}, {"data": "spoof"}, {"Bad": "value"}])
def test_attribute_model_rejects_extension_collisions(extensions: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        CloudEventAttributes(specversion="1.0", id="1", source="/orders", type="example", extensions=extensions)
