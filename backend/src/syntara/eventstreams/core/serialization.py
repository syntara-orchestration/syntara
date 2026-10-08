"""Payload deserialization.

Deserialization is separate from transport: a message whose body cannot be
parsed is a *no-trigger decision* (the pipeline ACKs it), never a transport
error. JSON is supported today; Avro + schema-registry and the CloudEvents Kafka
binding (ANSTRAT-1934 P3) plug in as additional :class:`Deserializer`
implementations selected by ``content_type``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from syntara.eventstreams.core.exceptions import EventStreamError

if TYPE_CHECKING:
    from syntara.eventstreams.core.envelope import EventEnvelope


class DeserializationError(EventStreamError):
    """Raised when a payload cannot be decoded — treated as a no-trigger decision."""


@runtime_checkable
class Deserializer(Protocol):
    """Decodes raw bytes into a structured payload."""

    def deserialize(self, envelope: EventEnvelope) -> object:
        """Decode the envelope body into a structured payload."""
        ...


class JsonDeserializer:
    """Decodes a UTF-8 JSON body into Python objects."""

    def deserialize(self, envelope: EventEnvelope) -> object:
        """Decode the UTF-8 JSON body, or ``None`` for an empty body."""
        if not envelope.body:
            return None
        try:
            return json.loads(envelope.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            msg = f"payload is not valid JSON: {exc}"
            raise DeserializationError(msg) from exc


class RawBytesDeserializer:
    """Pass-through for arbitrary payloads (no decoding)."""

    def deserialize(self, envelope: EventEnvelope) -> object:
        """Return the raw body bytes unchanged."""
        return envelope.body
