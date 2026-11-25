"""CloudEvents validation and frozen context for Kafka Publish."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import UUID4, StrictStr, field_validator
from rfc3339_validator import validate_rfc3339  # type: ignore[import-untyped]
from sqlmodel import SQLModel

from syntara.eventstreams.core.cloudevents import (
    CloudEventAttributes,
    normalize_cloudevents,
    validate_attribute_string,
)

if TYPE_CHECKING:
    from pydantic import JsonValue

    from syntara.workflows.workflow_engine.models.kafka_publish import KafkaPublishHeader

KAFKA_CLOUDEVENTS_MANAGED_HEADERS = frozenset(
    {"ce_type", "ce_source", "ce_specversion", "ce_id", "ce_time", "content-type"}
)
KAFKA_CLOUDEVENTS_HEADER_COUNT = len(KAFKA_CLOUDEVENTS_MANAGED_HEADERS)
_RESERVED_HEADERS = frozenset({"ce_data", "ce_datacontenttype", "ce_extensions"})
_HEADER_NAME = re.compile(r"ce_[a-z0-9]+")
_TEMPLATE = re.compile(r"\$\{[^}]+\}")


class KafkaPublishCloudEventContext(SQLModel):
    """Generated once by the workflow and persisted in Temporal activity inputs."""

    model_config = {"extra": "forbid", "frozen": True}
    id: UUID4
    time: StrictStr

    @field_validator("time")
    @classmethod
    def utc_timestamp(cls, value: str) -> str:
        """Require the UTC representation used for generated Publish events."""
        if not value.endswith("Z") or not validate_rfc3339(value):
            msg = "CloudEvents time must be an RFC 3339 UTC timestamp ending in Z"
            raise ValueError(msg)
        return value


def _attribute(value: str | None, *, source: bool, allow_templates: bool) -> str:
    if not value:
        msg = "CloudEvents mode requires a non-empty event type and source"
        raise ValueError(msg)
    validate_attribute_string(value)
    if allow_templates and _TEMPLATE.search(value):
        return "/" if source else "validation"
    return value


def _custom_attributes(headers: list[KafkaPublishHeader] | str, *, allow_templates: bool) -> dict[str, JsonValue]:
    if isinstance(headers, str):
        if allow_templates:
            return {}
        msg = "Header template must resolve to an ordered list"
        raise ValueError(msg)
    attributes: dict[str, JsonValue] = {}
    seen: set[str] = set()
    for header in headers:
        if allow_templates and _TEMPLATE.search(header.name):
            continue
        name = header.name.lower()
        if name in KAFKA_CLOUDEVENTS_MANAGED_HEADERS:
            msg = "This header is managed by CloudEvents mode"
            raise ValueError(msg)
        if not name.startswith("ce_"):
            continue
        if _HEADER_NAME.fullmatch(header.name) is None or name in _RESERVED_HEADERS or name in seen:
            msg = "CloudEvents headers require unique canonical attribute names"
            raise ValueError(msg)
        seen.add(name)
        if header.value is None:
            msg = "CloudEvents headers require non-null UTF-8 text values"
            raise ValueError(msg)
        if allow_templates and _TEMPLATE.search(header.value.value):
            continue
        attributes[name.removeprefix("ce_")] = validate_attribute_string(
            header.value.decode().decode("utf-8", errors="strict")
        )
    return attributes


def validate_publish_cloudevents(
    event_type: str | None,
    source: str | None,
    headers: list[KafkaPublishHeader] | str,
    *,
    allow_templates: bool = False,
    context: KafkaPublishCloudEventContext | None = None,
) -> CloudEventAttributes:
    """Validate literal fields at design time and the full resolved event at runtime."""
    attributes: dict[str, JsonValue] = {
        "specversion": "1.0",
        "id": str(context.id) if context else "validation",
        "type": _attribute(event_type, source=False, allow_templates=allow_templates),
        "source": _attribute(source, source=True, allow_templates=allow_templates),
        "datacontenttype": "application/json",
        **_custom_attributes(headers, allow_templates=allow_templates),
    }
    if context is not None:
        attributes["time"] = context.time
    normalized = normalize_cloudevents(attributes)
    if isinstance(normalized, CloudEventAttributes):
        return normalized
    msg = "CloudEvents attributes are invalid"
    raise ValueError(msg)
