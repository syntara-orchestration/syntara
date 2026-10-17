"""Contract tests for broker-independent JSON decoding and lossless envelopes."""

import base64
import copy
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from syntara.core.config.base import Settings
from syntara.core.constants import EventStreamLimits
from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata, KafkaTimestampType
from syntara.eventstreams.core.envelope import EventSourceMetadata, RawEvent, RawEventHeader
from syntara.eventstreams.core.exceptions import EventDecodeFailure, EventFailureCode
from syntara.eventstreams.core.serialization import (
    EventDecodeSuccess,
    JsonEventDecoder,
    encode_envelope,
    encoded_envelope_size,
    validate_payload,
)


def _metadata() -> KafkaSourceMetadata:
    return KafkaSourceMetadata(
        integration_id=UUID(int=1),
        subscription_id=UUID(int=2),
        source_generation=1,
        received_at=datetime(2026, 10, 17, tzinfo=UTC),
        topic="events",
        partition=2,
        offset="9223372036854775807",
        timestamp_ms=1792195200000,
        timestamp_type=KafkaTimestampType.create_time,
    )


def _event(
    value: bytes | None,
    *,
    key: bytes | None = None,
    headers: list[tuple[str, bytes | None]] | None = None,
    metadata: EventSourceMetadata | None = None,
) -> RawEvent:
    return RawEvent(
        value=value,
        key=key,
        headers=[RawEventHeader(name=name, value=data) for name, data in headers or []],
        source_metadata=metadata or _metadata(),
    )


@pytest.mark.parametrize(
    ("value", "payload"),
    [
        (b'{ "a": [1, true, null] }', {"a": [1, True, None]}),
        (b'[1, "two", null]', [1, "two", None]),
        (b'"hello"', "hello"),
        ('"snowman: ☃"'.encode(), "snowman: ☃"),
        (b"42", 42),
        (b"-1.25e2", -125.0),
        (b"true", True),
        (b"false", False),
        (b"null", None),
    ],
)
def test_supported_json_values(value: bytes, payload: object) -> None:
    """Every supported JSON root retains the decoded value and exact source."""
    result = JsonEventDecoder().decode(_event(value))
    assert isinstance(result, EventDecodeSuccess)
    assert result.envelope.envelope_version == 1
    assert result.envelope.payload == payload
    assert result.envelope.cloudevents is None
    assert base64.b64decode(result.envelope.original.value_base64) == value


@pytest.mark.parametrize("key", [None, b"", b"\x00\xffkey"])
def test_byte_fidelity_and_metadata(key: bytes | None) -> None:
    """Binary, null, empty, and repeated headers retain their order and bytes."""
    headers = [("repeat", b"\x00\xff"), ("repeat", b""), ("repeat", None)]
    event = _event(b' {"unicode":"\\u2603"} \n', key=key, headers=headers)
    before = event.model_copy(deep=True)
    result = JsonEventDecoder().decode(event)
    assert isinstance(result, EventDecodeSuccess)
    original = result.envelope.original
    assert (None if original.key_base64 is None else base64.b64decode(original.key_base64)) == key
    restored_headers = [
        (h.name, None if h.value_base64 is None else base64.b64decode(h.value_base64)) for h in original.headers
    ]
    assert restored_headers == headers
    encoded = json.loads(encode_envelope(result.envelope))
    assert encoded["metadata"] == {
        "integration_id": str(UUID(int=1)),
        "subscription_id": str(UUID(int=2)),
        "source_generation": 1,
        "received_at": "2026-10-17T00:00:00Z",
        "topic": "events",
        "partition": 2,
        "offset": "9223372036854775807",
        "timestamp_ms": 1792195200000,
        "timestamp_type": "create_time",
    }
    assert event == before


def test_shared_envelope_accepts_other_transport_metadata() -> None:
    """The common envelope preserves typed extensions without knowing Kafka."""

    class QueueMetadata(EventSourceMetadata):
        queue: str

    metadata = QueueMetadata(
        **_metadata().model_dump(include={"integration_id", "subscription_id", "source_generation", "received_at"}),
        queue="jobs",
    )
    result = JsonEventDecoder().decode(_event(b"null", metadata=metadata))
    assert isinstance(result, EventDecodeSuccess)
    assert result.envelope.source_metadata is metadata
    encoded_metadata = json.loads(encode_envelope(result.envelope))["metadata"]
    assert encoded_metadata["queue"] == "jobs"
    assert "topic" not in encoded_metadata
    assert "offset" not in encoded_metadata


@pytest.mark.parametrize("offset", [42, "-1", "01", "1.5"])
def test_offset_requires_canonical_decimal_string(offset: object) -> None:
    """Offset construction cannot silently round, coerce, or truncate values."""
    data = _metadata().model_dump()
    data["offset"] = offset
    with pytest.raises(ValidationError):
        KafkaSourceMetadata.model_validate(data)


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (None, EventFailureCode.tombstone),
        (b"", EventFailureCode.invalid_json),
        (b"\xff", EventFailureCode.invalid_utf8),
        (b"\xef\xbb\xbf{}", EventFailureCode.invalid_json),
        (b"{'a':1}", EventFailureCode.invalid_json),
        (b"{} trailing", EventFailureCode.invalid_json),
        (b'{"a":1,"a":2}', EventFailureCode.duplicate_member),
        (b'{"nested":{"a":1,"\\u0061":2}}', EventFailureCode.duplicate_member),
        (b"NaN", EventFailureCode.non_finite_number),
        (b"[Infinity]", EventFailureCode.non_finite_number),
        (b"-Infinity", EventFailureCode.non_finite_number),
        (b"1e999", EventFailureCode.non_finite_number),
        (b"\x00\x00\x00\x00\x01data", EventFailureCode.registry_framing),
    ],
)
def test_invalid_values_are_typed_failures(value: bytes | None, code: EventFailureCode) -> None:
    """Content errors return per-message results, not application exceptions."""
    result = JsonEventDecoder().decode(_event(value))
    assert isinstance(result, EventDecodeFailure)
    assert result.code == code


@pytest.mark.parametrize(
    "content_type",
    [
        None,
        b"application/json",
        b'Application/JSON; charset="UTF-8"',
        b"application/vnd.acme+json",
        b"text/custom+json",
    ],
)
def test_supported_or_null_content_types(content_type: bytes | None) -> None:
    """Missing/null headers fall back to JSON; custom JSON suffixes work."""
    result = JsonEventDecoder().decode(_event(b"[1]", headers=[("Content-Type", content_type)]))
    assert isinstance(result, EventDecodeSuccess)


@pytest.mark.parametrize(
    ("headers", "code"),
    [
        ([("content-type", b"")], EventFailureCode.malformed_content_type),
        ([("content-type", b"not-a-media-type")], EventFailureCode.malformed_content_type),
        ([("content-type", b"application/json; broken")], EventFailureCode.malformed_content_type),
        ([("content-type", b"\xff")], EventFailureCode.malformed_content_type),
        ([("content-type", b"application/json\r\ninjected:x")], EventFailureCode.malformed_content_type),
        ([("content-type", b"application/json; charset=latin1")], EventFailureCode.unsupported_content_type),
        ([("content-type", b"application/avro")], EventFailureCode.unsupported_content_type),
        (
            [("content-type", b"application/json"), ("Content-Type", b"application/json")],
            EventFailureCode.duplicate_content_type,
        ),
        (
            [("content-type", b"application/json"), ("content-type", b"text/plain")],
            EventFailureCode.duplicate_content_type,
        ),
        ([("content-type", None), ("content-type", None)], EventFailureCode.duplicate_content_type),
    ],
)
def test_header_failures_stop_only_this_message(
    headers: list[tuple[str, bytes | None]], code: EventFailureCode
) -> None:
    """The same decoder remains usable after malformed or ambiguous headers."""
    decoder = JsonEventDecoder()
    result = decoder.decode(_event(b"{}", headers=headers))
    assert isinstance(result, EventDecodeFailure)
    assert result.code == code
    assert isinstance(decoder.decode(_event(b"{}")), EventDecodeSuccess)


def test_schema_validates_payload_without_defaults_or_mutation() -> None:
    """Defaults cannot change the original event or satisfy a missing field."""
    event = _event(b'{"count":2}')
    result = JsonEventDecoder().decode(event)
    assert isinstance(result, EventDecodeSuccess)
    before = encode_envelope(result.envelope)
    schema: dict[str, Any] = {
        "type": "object",
        "required": ["count"],
        "properties": {"count": {"type": "integer"}, "extra": {"default": "never inserted"}},
    }
    schema_before = copy.deepcopy(schema)
    assert validate_payload(result.envelope, schema) is None
    assert encode_envelope(result.envelope) == before
    assert schema == schema_before
    schema["required"] = ["extra"]
    failure = validate_payload(result.envelope, schema)
    assert failure is not None
    assert failure.code == EventFailureCode.schema_mismatch
    assert encode_envelope(result.envelope) == before


@pytest.mark.parametrize(
    ("schema", "code"),
    [
        ({"type": "integer"}, EventFailureCode.schema_mismatch),
        ({"type": "invalid"}, EventFailureCode.invalid_schema),
        ({"$ref": "https://example.com/schema"}, EventFailureCode.invalid_schema),
        ({"$ref": "#/definitions/local"}, EventFailureCode.invalid_schema),
        ({"type": "string", "pattern": "(a+)+$"}, EventFailureCode.invalid_schema),
        ({"patternProperties": {"(a+)+$": {}}}, EventFailureCode.invalid_schema),
    ],
)
def test_schema_failures_are_safe(schema: dict[str, Any], code: EventFailureCode) -> None:
    """Existing definition guards apply without default-filling validation."""
    result = JsonEventDecoder().decode(_event(b'"secret"'), schema=schema)
    assert isinstance(result, EventDecodeFailure)
    assert result.code == code
    assert "secret" not in result.message


@pytest.mark.parametrize("value", [b"null", b"12", b"[1,2]", b'"str"'])
def test_optional_schema_accepts_supported_scalar_and_array_values(value: bytes) -> None:
    """An empty schema permits every root type, not just object wrappers."""
    assert isinstance(JsonEventDecoder().decode(_event(value), schema={}), EventDecodeSuccess)


def test_candidate_raw_value_boundary() -> None:
    """The candidate 256 KiB raw limit is inclusive and configurable."""
    limit = EventStreamLimits.DEFAULT_MAX_VALUE_BYTES
    decoder = JsonEventDecoder()
    assert isinstance(decoder.decode(_event(b'"' + b"x" * (limit - 2) + b'"')), EventDecodeSuccess)
    result = decoder.decode(_event(b'"' + b"x" * (limit - 1) + b'"'))
    assert isinstance(result, EventDecodeFailure)
    assert result.code == EventFailureCode.value_too_large
    assert isinstance(JsonEventDecoder(max_value_bytes=3).decode(_event(b"123")), EventDecodeSuccess)
    assert isinstance(JsonEventDecoder(max_value_bytes=2).decode(_event(b"123")), EventDecodeFailure)


def test_complete_encoded_envelope_boundary() -> None:
    """Sizing includes metadata, binary key, repeated headers, and both payload copies."""
    event = _event(b'{"text":"\\u2603"}', key=b"\xff" * 18, headers=[("x", b"one"), ("x", b"two"), ("x", None)])
    result = JsonEventDecoder().decode(event)
    assert isinstance(result, EventDecodeSuccess)
    size = len(encode_envelope(result.envelope))
    assert result.encoded_envelope_bytes == size == encoded_envelope_size(result.envelope)
    assert isinstance(JsonEventDecoder(max_envelope_bytes=size).decode(event), EventDecodeSuccess)
    failure = JsonEventDecoder(max_envelope_bytes=size - 1).decode(event)
    assert isinstance(failure, EventDecodeFailure)
    assert failure.code == EventFailureCode.envelope_too_large
    assert size > len(event.value or b"")


def test_candidate_one_mib_envelope_boundary_with_large_key() -> None:
    """Large keys count even when the value is tiny; exactly 1 MiB is permitted."""
    limit = EventStreamLimits.DEFAULT_MAX_ENVELOPE_BYTES
    metadata = _metadata()
    baseline = JsonEventDecoder().decode(_event(b"0", key=b"", metadata=metadata))
    assert isinstance(baseline, EventDecodeSuccess)
    padding = (limit - baseline.encoded_envelope_bytes) % 4
    metadata = metadata.model_copy(update={"topic": metadata.topic + "x" * padding})
    key = b"\xff" * ((limit - baseline.encoded_envelope_bytes - padding) // 4 * 3)
    event = _event(b"0", key=key, metadata=metadata)
    result = JsonEventDecoder().decode(event)
    assert isinstance(result, EventDecodeSuccess)
    assert result.encoded_envelope_bytes == limit
    failure = JsonEventDecoder().decode(_event(b"0", key=key + b"x", metadata=metadata))
    assert isinstance(failure, EventDecodeFailure)
    assert failure.code == EventFailureCode.envelope_too_large


def test_parser_capacity_failure_is_sanitized() -> None:
    """No numeric product nesting limit is claimed; parser exhaustion is safe."""
    depth = sys.getrecursionlimit() + 1
    result = JsonEventDecoder().decode(_event(b"[" * depth + b"0" + b"]" * depth))
    assert isinstance(result, EventDecodeFailure)
    assert result.code == EventFailureCode.excessive_nesting


def test_safe_failure_and_model_representations(caplog: pytest.LogCaptureFixture) -> None:
    """No payload, key, headers, schema values, or parser exception text is logged."""
    caplog.set_level(logging.DEBUG)
    private_marker = "CUSTOMER_PRIVATE_MARKER"
    decoder = JsonEventDecoder()
    events = [
        _event(private_marker.encode()),
        _event(b"{}", headers=[("content-type", private_marker.encode())]),
        _event(
            json.dumps(private_marker).encode(),
            key=private_marker.encode(),
            headers=[(private_marker, private_marker.encode())],
        ),
    ]
    for event in events:
        result = decoder.decode(event, schema={"type": "integer"})
        assert isinstance(result, EventDecodeFailure)
        assert private_marker not in result.message
        assert private_marker not in repr(result)
        assert private_marker not in repr(event)
    assert private_marker not in caplog.text
    assert not caplog.records


def test_candidate_settings_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Application settings expose candidate bounds without a transport guarantee."""
    settings = Settings()
    assert settings.event_max_value_bytes == 256 * 1024
    assert settings.event_max_envelope_bytes == 1024 * 1024
    monkeypatch.setenv("APP_EVENT_MAX_VALUE_BYTES", "3")
    monkeypatch.setenv("APP_EVENT_MAX_ENVELOPE_BYTES", "4096")
    settings = Settings()
    decoder = JsonEventDecoder(
        max_value_bytes=settings.event_max_value_bytes,
        max_envelope_bytes=settings.event_max_envelope_bytes,
    )
    assert isinstance(decoder.decode(_event(b"123")), EventDecodeSuccess)
    failure = decoder.decode(_event(b"1234"))
    assert isinstance(failure, EventDecodeFailure)
    assert failure.code == EventFailureCode.value_too_large


@pytest.mark.parametrize("setting", ["APP_EVENT_MAX_VALUE_BYTES", "APP_EVENT_MAX_ENVELOPE_BYTES"])
@pytest.mark.parametrize("value", ["0", "-1"])
def test_candidate_settings_require_positive_values(monkeypatch: pytest.MonkeyPatch, setting: str, value: str) -> None:
    """Zero or negative values cannot silently disable candidate byte limits."""
    monkeypatch.setenv(setting, value)
    with pytest.raises(ValidationError):
        Settings()
