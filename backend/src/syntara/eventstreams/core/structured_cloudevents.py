"""Decode a single structured CloudEvents JSON object into the shared contract."""

from pydantic import JsonValue

from syntara.eventstreams.core.cloudevents import CloudEventAttributes, normalize_cloudevents
from syntara.eventstreams.core.results import EventDecodeFailure, EventFailureCode


def decode_structured_cloudevents(
    value: JsonValue,
) -> tuple[JsonValue, CloudEventAttributes] | EventDecodeFailure:
    """Extract data without reparsing JSON strings or merging transport headers."""
    if not isinstance(value, dict) or ("data" in value and "data_base64" in value):
        return EventDecodeFailure(code=EventFailureCode.malformed_cloudevents)
    attributes = normalize_cloudevents(
        {name: item for name, item in value.items() if name not in {"data", "data_base64"}}
    )
    if isinstance(attributes, EventDecodeFailure):
        return attributes
    if "data_base64" in value:
        return EventDecodeFailure(code=EventFailureCode.unsupported_cloudevents_data)
    return value.get("data"), attributes
