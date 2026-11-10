"""Kafka Publish parameters shared by validation and execution.

This module deliberately has no Kafka client dependency: workflow definitions
and the deterministic workflow sandbox only need the message contract.
"""

import base64
import binascii
import json
import re
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, StrictStr, field_validator
from sqlmodel import SQLModel

KAFKA_PUBLISH_MAX_RECORD_BYTES = 1_048_576
KAFKA_PUBLISH_MAX_HEADERS = 128
KAFKA_PUBLISH_BUDGET_SECONDS = 180
KAFKA_PUBLISH_HEARTBEAT_SECONDS = 2
KAFKA_PUBLISH_HEARTBEAT_TIMEOUT_SECONDS = 10
KAFKA_PUBLISH_IDLE_SECONDS = 300
KAFKA_PUBLISH_REQUEST_TIMEOUT_MS = 10_000

_TOPIC = re.compile(r"^[a-zA-Z0-9._-]{1,249}$")
_UUID_PATTERN = r"^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$"


class KafkaEncodedValue(SQLModel):
    """Explicit text or binary representation; empty bytes remain distinct from null."""

    model_config = {"extra": "forbid"}
    encoding: Literal["utf-8", "base64"]
    value: StrictStr

    def decode(self) -> bytes:
        """Validate and decode without repairing or guessing an encoding."""
        if self.encoding == "utf-8":
            return self.value.encode("utf-8")
        try:
            return base64.b64decode(self.value, validate=True)
        except (binascii.Error, ValueError) as exc:
            msg = "Kafka binary values must use valid standard Base64"
            raise ValueError(msg) from exc


class KafkaPublishHeader(SQLModel):
    """One ordered header; duplicate names and null values are intentional."""

    model_config = {"extra": "forbid"}
    name: StrictStr
    value: KafkaEncodedValue | None


class KafkaPublishParameters(SQLModel):
    """Fixed destination and a templated JSON message, with no producer overrides."""

    model_config = {"extra": "forbid"}
    integration_id: StrictStr = Field(pattern=_UUID_PATTERN)
    credential_id: StrictStr = Field(pattern=_UUID_PATTERN, description="Required runtime Kafka credential reference")
    topic: StrictStr = Field(
        min_length=1, max_length=249, pattern=r"^[a-zA-Z0-9._-]+$", json_schema_extra={"not": {"enum": [".", ".."]}}
    )
    payload: Any = Field(..., description="Required JSON value; explicit null publishes JSON null, not a tombstone")
    key: KafkaEncodedValue | None = None
    headers: list[KafkaPublishHeader] | StrictStr = Field(default_factory=list)

    @field_validator("integration_id", "credential_id")
    @classmethod
    def fixed_reference(cls, value: str) -> str:
        """Reject templated references chosen by workflow data."""
        UUID(value)
        return value

    @field_validator("topic")
    @classmethod
    def fixed_topic(cls, value: str) -> str:
        """Match Subscribe's Kafka naming rules and reject templated destinations."""
        if not _TOPIC.fullmatch(value) or value in {".", ".."}:
            msg = "topic must be one literal Kafka topic name"
            raise ValueError(msg)
        return value

    @field_validator("headers")
    @classmethod
    def header_template(cls, value: list[KafkaPublishHeader] | str) -> list[KafkaPublishHeader] | str:
        """Only a full-value template may stand in for the ordered header list."""
        if isinstance(value, str) and not (value.startswith("${") and value.endswith("}")):
            msg = "headers must be an ordered list or a full-value template"
            raise ValueError(msg)
        return value


def _check_json(value: Any) -> None:  # noqa: ANN401
    """Reject implicit Python conversions, including non-string object keys."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return
    if isinstance(value, list):
        for item in value:
            _check_json(item)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _check_json(item)
        return
    msg = "Payload must be a valid JSON value"
    raise TypeError(msg)


def encode_publish_message(
    parameters: KafkaPublishParameters,
) -> tuple[bytes, bytes | None, list[tuple[str, bytes | None]]]:
    """Encode resolved data once, preserving JSON/native and Kafka byte semantics."""
    _check_json(parameters.payload)
    value = json.dumps(
        parameters.payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if isinstance(parameters.headers, str):
        msg = "Header template must resolve to an ordered list"
        raise TypeError(msg)
    if len(parameters.headers) > KAFKA_PUBLISH_MAX_HEADERS:
        msg = "Kafka Publish supports at most 128 header entries"
        raise ValueError(msg)
    headers: list[tuple[str, bytes | None]] = []
    for header in parameters.headers:
        header.name.encode("utf-8")
        headers.append((header.name, header.value.decode() if header.value is not None else None))
    return value, parameters.key.decode() if parameters.key is not None else None, headers
