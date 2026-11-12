"""Build a lossless filtering view without changing the workflow envelope."""

import base64
from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field, JsonValue
from sqlmodel import SQLModel

from syntara.eventstreams.core.cloudevents import CloudEventAttributes
from syntara.eventstreams.core.envelope import RawEvent
from syntara.eventstreams.core.results import EventDecodeFailure
from syntara.eventstreams.core.serialization import EventDecodeSuccess


class FilterTextValue(SQLModel):
    """Distinguish strict UTF-8 text, binary bytes and null values."""

    kind: Literal["text", "binary", "null"]
    base64: str | None = Field(repr=False)
    text: str | None = Field(default=None, repr=False)

    @classmethod
    def from_bytes(cls, value: bytes | None) -> "FilterTextValue":
        """Retain exact bytes without guessing the text of binary values."""
        if value is None:
            return cls(kind="null", base64=None)
        encoded = base64.b64encode(value).decode("ascii")
        try:
            text = value.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return cls(kind="binary", base64=encoded)
        return cls(kind="text", text=text, base64=encoded)


class FilterPayload(SQLModel):
    """Keep decoded JSON null distinct from unavailable payload content."""

    state: Literal["not_decoded", "decoded", "decode_error"]
    value: JsonValue = Field(default=None, repr=False)
    error_code: str | None = None


class EventFilterInput(SQLModel):
    """Expose event values to CEL independently of transport-specific rules."""

    headers: dict[str, list[FilterTextValue]] = Field(repr=False)
    key: FilterTextValue = Field(repr=False)
    source_metadata: dict[str, Any] = Field(alias="metadata", repr=False)
    payload: FilterPayload = Field(repr=False)
    cloudevents: CloudEventAttributes | None = Field(default=None, repr=False)

    model_config: ClassVar[ConfigDict] = ConfigDict(  # type: ignore[assignment]
        extra="forbid", populate_by_name=True, serialize_by_alias=True
    )

    @classmethod
    def from_event(
        cls, event: RawEvent, decoded: EventDecodeSuccess | EventDecodeFailure | None = None
    ) -> "EventFilterInput":
        """Group exact header names in occurrence order and attach the payload state."""
        headers: dict[str, list[FilterTextValue]] = {}
        for header in event.headers:
            headers.setdefault(header.name, []).append(FilterTextValue.from_bytes(header.value))
        if isinstance(decoded, EventDecodeSuccess):
            payload = FilterPayload(state="decoded", value=decoded.envelope.payload)
        elif isinstance(decoded, EventDecodeFailure):
            payload = FilterPayload(state="decode_error", error_code=decoded.code.value)
        else:
            payload = FilterPayload(state="not_decoded")
        return cls(
            headers=headers,
            key=FilterTextValue.from_bytes(event.key),
            metadata=event.source_metadata.model_dump(mode="json"),
            payload=payload,
            cloudevents=decoded.envelope.cloudevents if isinstance(decoded, EventDecodeSuccess) else None,
        )
