"""Component integration of settings, metadata, decoding, schemas, and encoding."""

import base64
import json
from datetime import UTC, datetime
from uuid import UUID

import pytest

from syntara.core.config.base import get_settings
from syntara.eventstreams.adapters.kafka_metadata import KafkaSourceMetadata, KafkaTimestampType
from syntara.eventstreams.core.envelope import RawEvent, RawEventHeader
from syntara.eventstreams.core.exceptions import EventDecodeFailure, EventFailureCode
from syntara.eventstreams.core.serialization import EventDecodeSuccess, JsonEventDecoder, encode_envelope


@pytest.fixture(autouse=True)
def _seed_authenticated_group() -> None:
    """Override the parent DB seed for a component path without persistence."""


def _record(value: bytes, headers: list[RawEventHeader] | None = None) -> RawEvent:
    return RawEvent(
        value=value,
        key=b"\xff\x00",
        headers=headers or [],
        source_metadata=KafkaSourceMetadata(
            integration_id=UUID(int=1),
            subscription_id=UUID(int=2),
            source_generation=3,
            received_at=datetime(2026, 10, 17, tzinfo=UTC),
            topic="alerts",
            partition=0,
            offset="9007199254740993",
            timestamp_ms=1792195200000,
            timestamp_type=KafkaTimestampType.log_append_time,
        ),
    )


def test_configured_decoder_preserves_complete_workflow_input(monkeypatch: pytest.MonkeyPatch) -> None:
    """Typed source metadata and exact bytes survive payload-only validation."""
    monkeypatch.setenv("APP_EVENT_MAX_VALUE_BYTES", "1024")
    monkeypatch.setenv("APP_EVENT_MAX_ENVELOPE_BYTES", "4096")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        decoder = JsonEventDecoder(
            max_value_bytes=settings.event_max_value_bytes,
            max_envelope_bytes=settings.event_max_envelope_bytes,
        )
        record = _record(
            b' {"count":2} \n',
            [
                RawEventHeader(name="content-type", value=b"application/vnd.acme+json"),
                RawEventHeader(name="trace", value=b"\xff"),
                RawEventHeader(name="trace", value=None),
                RawEventHeader(name="trace", value=b""),
            ],
        )
        before = record.model_copy(deep=True)
        result = decoder.decode(
            record,
            schema={
                "type": "object",
                "required": ["count"],
                "properties": {"count": {"type": "integer"}, "extra": {"default": 99}},
                "additionalProperties": False,
            },
        )
        assert isinstance(result, EventDecodeSuccess)
        encoded = encode_envelope(result.envelope)
        workflow_input = json.loads(encoded)
        assert set(workflow_input) == {"envelope_version", "payload", "original", "cloudevents", "metadata"}
        assert workflow_input["payload"] == {"count": 2}
        assert workflow_input["metadata"]["offset"] == "9007199254740993"
        assert workflow_input["metadata"]["timestamp_type"] == "log_append_time"
        assert workflow_input["metadata"]["source_generation"] == 3
        assert base64.b64decode(workflow_input["original"]["value_base64"]) == record.value
        assert base64.b64decode(workflow_input["original"]["key_base64"]) == record.key
        assert workflow_input["original"]["headers"][1:] == [
            {"name": "trace", "value_base64": "/w=="},
            {"name": "trace", "value_base64": None},
            {"name": "trace", "value_base64": ""},
        ]
        assert len(encoded) == result.encoded_envelope_bytes
        assert record == before
    finally:
        get_settings.cache_clear()


def test_failed_record_remains_available_for_caller_auditing() -> None:
    """A safe failure supplies no commit authority and preserves caller context."""
    decoder = JsonEventDecoder()
    record = _record(
        b'{"private":"CUSTOMER_DATA"}',
        [RawEventHeader(name="content-type", value=b"private/invalid; CUSTOMER_DATA")],
    )
    before = record.model_copy(deep=True)
    result = decoder.decode(record)
    assert isinstance(result, EventDecodeFailure)
    assert result.code == EventFailureCode.malformed_content_type
    assert result.model_dump(mode="json") == {"code": "malformed_content_type"}
    assert "CUSTOMER_DATA" not in result.message
    assert record == before
    assert record.source_metadata.subscription_id == UUID(int=2)
    assert isinstance(decoder.decode(_record(b"null")), EventDecodeSuccess)


@pytest.mark.parametrize(
    ("value", "schema_type"),
    [(b"null", "null"), (b"12", "integer"), (b"true", "boolean"), (b'"text"', "string"), (b"[1]", "array")],
)
def test_payload_schema_does_not_validate_the_envelope(value: bytes, schema_type: str) -> None:
    """Scalar and array schemas validate their payload, not the object wrapper."""
    result = JsonEventDecoder().decode(_record(value), schema={"type": schema_type})
    assert isinstance(result, EventDecodeSuccess)
    assert json.loads(encode_envelope(result.envelope))["payload"] == json.loads(value)
