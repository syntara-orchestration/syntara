"""Verify CloudEvents Publish bytes, validation and generated-header limits."""

from typing import Any

import pytest
from pydantic import ValidationError
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.models.kafka_publish import KafkaPublishParameters, encode_publish_message
from syntara.workflows.workflow_engine.services.kafka_publish_message import compile_publish_message

PARAMETERS: dict[str, Any] = {
    "integration_id": "11111111-1111-4111-8111-111111111111",
    "credential_id": "22222222-2222-4222-8222-222222222222",
    "topic": "automation.outcomes",
    "cloudevents_mode": True,
    "ce_type": "com.example.order.completed",
    "ce_source": "/workflows/order-completion",
    "payload": {"order_id": "order-123", "outcome": "completed"},
}
CONTEXT = {"id": "23a576e8-e9ed-4c04-9a24-3e95802eef1b", "time": "2026-11-25T10:00:00Z"}


def _header(name: str, value: str | None = "value", *, encoding: str = "utf-8") -> dict[str, Any]:
    return {"name": name, "value": None if value is None else {"encoding": encoding, "value": value}}


def test_cloud_event_preserves_data_key_and_ordinary_headers() -> None:
    parameters = KafkaPublishParameters.model_validate(
        {
            **PARAMETERS,
            "key": {"encoding": "base64", "value": "AAEC"},
            "headers": [
                _header("same", None),
                _header("same", ""),
                _header("same", "AAEC", encoding="base64"),
                _header("ce_tenant", "Y2Fmw6k=", encoding="base64"),
            ],
        }
    )

    value, key, headers, _size = compile_publish_message(parameters, cloudevents=CONTEXT)

    assert value == b'{"order_id":"order-123","outcome":"completed"}'
    assert key == b"\x00\x01\x02"
    assert headers[:4] == [("same", None), ("same", b""), ("same", b"\x00\x01\x02"), ("ce_tenant", "café".encode())]
    assert headers[4:] == [
        ("ce_type", b"com.example.order.completed"),
        ("ce_source", b"/workflows/order-completion"),
        ("ce_specversion", b"1.0"),
        ("ce_id", CONTEXT["id"].encode()),
        ("ce_time", CONTEXT["time"].encode()),
        ("content-type", b"application/json"),
    ]
    assert compile_publish_message(parameters, cloudevents=CONTEXT) == (value, key, headers, _size)


@pytest.mark.parametrize("source", ["/workflows/orders", "urn:syntara:workflow:orders", "https://example.com/events"])
def test_absolute_and_relative_sources(source: str) -> None:
    parameters = KafkaPublishParameters.model_validate({**PARAMETERS, "ce_source": source})

    _value, _key, headers, _size = compile_publish_message(parameters, cloudevents=CONTEXT)

    assert ("ce_source", source.encode()) in headers


@pytest.mark.parametrize(
    "patch",
    [
        {"ce_type": None},
        {"ce_type": ""},
        {"ce_type": 42},
        {"ce_type": "event\ninvalid"},
        {"ce_type": "event\x85invalid"},
        {"ce_type": "event\ufdd0invalid"},
        {"ce_source": None},
        {"ce_source": ""},
        {"ce_source": 42},
        {"ce_source": "not a URI"},
        {"cloudevents_mode": "true"},
        {"cloudevents_mode": False},
    ],
)
def test_invalid_cloud_events_configuration(patch: dict[str, Any]) -> None:
    parameters = {**PARAMETERS, **patch}

    with pytest.raises(ValidationError):
        KafkaPublishParameters.model_validate(parameters)


@pytest.mark.parametrize(
    "name",
    [
        "ce_type",
        "CE_SOURCE",
        "ce_specversion",
        "ce_id",
        "ce_time",
        "Content-Type",
        "ce_data",
        "ce_datacontenttype",
        "ce_extensions",
        "CE_tenant",
        "ce_Tenant",
        "ce_bad_name",
        "ce_",
        "ce_é",
    ],
)
def test_reserved_managed_and_invalid_attribute_names(name: str) -> None:
    parameters = {**PARAMETERS, "headers": [_header(name)]}

    with pytest.raises(ValidationError):
        KafkaPublishParameters.model_validate(parameters)


@pytest.mark.parametrize(
    "headers",
    [
        [_header("ce_tenant", None)],
        [_header("ce_tenant", "a"), _header("ce_tenant", "b")],
        [_header("ce_tenant", "/w==", encoding="base64")],
        [_header("ce_tenant", "Cg==", encoding="base64")],
        [_header("ce_subject", "")],
        [_header("ce_dataschema", "/relative")],
    ],
)
def test_invalid_attribute_values(headers: list[dict[str, Any]]) -> None:
    parameters = {**PARAMETERS, "headers": headers}

    with pytest.raises(ValidationError):
        KafkaPublishParameters.model_validate(parameters)


def test_resolved_templates_are_validated_without_rerendering() -> None:
    parameters = KafkaPublishParameters.model_validate(
        {
            **PARAMETERS,
            "ce_type": "${trigger.event_type}",
            "ce_source": "${trigger.source}",
            "headers": "${trigger.headers}",
        }
    )

    with pytest.raises(ApplicationError) as failure:
        compile_publish_message(parameters, cloudevents=CONTEXT)

    assert failure.value.type == "kafka_invalid_message"
    assert failure.value.non_retryable
    assert failure.value.details[0]["output"]["delivery_status"] == "not_sent"


@pytest.mark.parametrize("headers", [[], [_header("x", None)] * 122])
def test_generated_headers_are_included_within_header_limit(headers: list[dict[str, Any]]) -> None:
    parameters = KafkaPublishParameters.model_validate({**PARAMETERS, "headers": headers})

    _value, _key, actual, _size = compile_publish_message(parameters, cloudevents=CONTEXT)

    assert len(actual) == len(headers) + 6


def test_generated_headers_can_exceed_header_limit() -> None:
    parameters = KafkaPublishParameters.model_validate({**PARAMETERS, "headers": [_header("x", None)] * 123})

    with pytest.raises(ApplicationError) as failure:
        compile_publish_message(parameters, cloudevents=CONTEXT)

    assert failure.value.type == "kafka_message_too_large"


def test_generated_headers_count_toward_record_size_limit() -> None:
    plain = {key: value for key, value in PARAMETERS.items() if key not in {"cloudevents_mode", "ce_type", "ce_source"}}
    plain["payload"] = "x" * 1_048_487
    plain_parameters = KafkaPublishParameters.model_validate(plain)
    parameters = KafkaPublishParameters.model_validate({**PARAMETERS, "payload": plain["payload"]})
    assert compile_publish_message(plain_parameters)[3] == 1_048_576

    with pytest.raises(ApplicationError) as failure:
        compile_publish_message(parameters, cloudevents=CONTEXT)

    assert failure.value.type == "kafka_message_too_large"


@pytest.mark.parametrize(
    "context",
    [None, {**CONTEXT, "id": "not-a-uuid"}, {**CONTEXT, "time": "2026-11-25T10:00:00+00:00"}],
)
def test_generated_context_must_be_frozen_and_valid(context: dict[str, str] | None) -> None:
    parameters = KafkaPublishParameters.model_validate(PARAMETERS)

    with pytest.raises(ApplicationError) as failure:
        compile_publish_message(parameters, cloudevents=context)

    assert failure.value.type == "kafka_invalid_message"
    assert failure.value.non_retryable


def test_mode_off_preserves_manual_cloud_event_headers_and_data() -> None:
    parameters = {
        key: value for key, value in PARAMETERS.items() if key not in {"cloudevents_mode", "ce_type", "ce_source"}
    }
    parameters["headers"] = [_header("content-type", "application/cloudevents+json"), _header("ce_custom", None)]
    omitted = KafkaPublishParameters.model_validate(parameters)
    disabled = KafkaPublishParameters.model_validate({**parameters, "cloudevents_mode": False})

    assert encode_publish_message(omitted) == encode_publish_message(disabled)
    assert encode_publish_message(disabled)[2] == [
        ("content-type", b"application/cloudevents+json"),
        ("ce_custom", None),
    ]
