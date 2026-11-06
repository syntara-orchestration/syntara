"""Kafka binary-mode CloudEvents header mapping without broker dependencies."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import JsonValue

    from syntara.eventstreams.core.envelope import RawEventHeader

from syntara.eventstreams.core.cloudevents import (
    CloudEventAttributes,
    normalize_cloudevents,
    validate_attribute_string,
)
from syntara.eventstreams.core.results import EventDecodeFailure, EventFailureCode

_REQUIRED_HEADERS = frozenset({"ce_specversion", "ce_id", "ce_source", "ce_type"})
_RESERVED_HEADERS = frozenset({"ce_datacontenttype", "ce_data", "ce_extensions"})


def decode_kafka_cloudevents(
    headers: tuple[RawEventHeader, ...], *, datacontenttype: str | None
) -> CloudEventAttributes | EventDecodeFailure | None:
    """Return attributes, a safe failure, or None for an ordinary JSON record.

    Any required header identifies a candidate, even with incorrect casing.
    Candidates require canonical lowercase names, unique attributes, and all
    required values. Extension-only headers do not identify a CloudEvent.
    """
    if not any(header.name.lower() in _REQUIRED_HEADERS for header in headers):
        return None
    attributes: dict[str, JsonValue] = {}
    seen: set[str] = set()
    try:
        for header in headers:
            if not header.name.lower().startswith("ce_"):
                continue
            name = header.name.removeprefix("ce_")
            if (
                header.name != header.name.lower()
                or header.name in _RESERVED_HEADERS
                or name in seen
                or header.value is None
            ):
                return EventDecodeFailure(code=EventFailureCode.malformed_cloudevents)
            seen.add(name)
            value = validate_attribute_string(header.value.decode("utf-8", errors="strict"))
            attributes[name] = value
        return normalize_cloudevents({**attributes, "datacontenttype": datacontenttype})
    except ValueError:
        return EventDecodeFailure(code=EventFailureCode.malformed_cloudevents)
