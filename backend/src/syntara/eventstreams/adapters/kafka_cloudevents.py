"""Kafka binary-mode CloudEvents header mapping without broker dependencies."""

from syntara.eventstreams.core.cloudevents import CloudEventAttributes, validate_attribute_string
from syntara.eventstreams.core.envelope import RawEventHeader
from syntara.eventstreams.core.results import EventDecodeFailure, EventFailureCode

_REQUIRED_HEADERS = frozenset({"ce_specversion", "ce_id", "ce_source", "ce_type"})
_CORE_ATTRIBUTES = frozenset({"specversion", "id", "source", "type", "subject", "time", "dataschema"})
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
    attributes: dict[str, str] = {}
    extensions: dict[str, str] = {}
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
            if name in _CORE_ATTRIBUTES:
                attributes[name] = value
            else:
                extensions[name] = value
        if not {"specversion", "id", "source", "type"}.issubset(attributes) or any(
            not attributes[name] for name in ("specversion", "id", "source", "type")
        ):
            return EventDecodeFailure(code=EventFailureCode.malformed_cloudevents)
        if attributes["specversion"] != "1.0":
            return EventDecodeFailure(code=EventFailureCode.unsupported_cloudevents_version)
        return CloudEventAttributes.model_validate(
            {**attributes, "datacontenttype": datacontenttype, "extensions": extensions}
        )
    except ValueError:
        return EventDecodeFailure(code=EventFailureCode.malformed_cloudevents)
