"""Strict JSON decoding and lossless envelopes, independent of the broker."""

import base64
import json
import math
import re
from collections.abc import Iterator
from itertools import pairwise
from typing import Any, NoReturn, cast

import jsonschema
from jsonschema import validators
from pydantic import JsonValue, ValidationError
from referencing.exceptions import Unresolvable
from sqlmodel import SQLModel

from syntara.core.constants import EventStreamLimits
from syntara.eventstreams.adapters.kafka_cloudevents import decode_kafka_cloudevents
from syntara.eventstreams.core.envelope import (
    OriginalEvent,
    OriginalEventHeader,
    RawEvent,
    RawEventHeader,
    WorkflowEventEnvelope,
)
from syntara.eventstreams.core.results import EventDecodeFailure, EventFailureCode
from syntara.workflows.json_schema_validation import NO_REF_REGISTRY, validate_json_schema_definition

_MEDIA_TYPE_ATOM = r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+"
_PARAMETER = (
    rf"[ \t]*;[ \t]*(?P<name>{_MEDIA_TYPE_ATOM})[ \t]*=[ \t]*"
    rf'(?P<value>{_MEDIA_TYPE_ATOM}|"(?:[^"\\\r\n]|\\[^\r\n])*")'
)
_MEDIA_TYPE = re.compile(
    rf"(?P<type>{_MEDIA_TYPE_ATOM})/(?P<subtype>{_MEDIA_TYPE_ATOM})"
    rf"(?P<parameters>(?:{_PARAMETER})*)"
)
_PARAMETERS = re.compile(_PARAMETER)
_REGISTRY_FRAME_PREFIX_BYTES = 5


class EventDecodeSuccess(SQLModel):
    """Decoded content and its encoded size; not durable resolution evidence."""

    envelope: WorkflowEventEnvelope
    encoded_envelope_bytes: int


class _ContentError(ValueError):
    """Internal parser callback signal containing only a safe code."""

    def __init__(self, code: EventFailureCode) -> None:
        self.code = code
        super().__init__(code.value)


def _object_members(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise _ContentError(EventFailureCode.duplicate_member)
        result[key] = value
    return result


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise _ContentError(EventFailureCode.non_finite_number)
    return result


def _reject_constant(_value: str) -> NoReturn:
    raise _ContentError(EventFailureCode.non_finite_number)


def _validate_content_type(headers: tuple[RawEventHeader, ...]) -> str | None:
    values = [header.value for header in headers if header.name.lower() == "content-type"]
    if len(values) > 1:
        raise _ContentError(EventFailureCode.duplicate_content_type)
    if not values or values[0] is None:
        return None
    try:
        text = values[0].decode("ascii").strip(" \t")
    except UnicodeDecodeError:
        raise _ContentError(EventFailureCode.malformed_content_type) from None
    match = _MEDIA_TYPE.fullmatch(text)
    if match is None:
        raise _ContentError(EventFailureCode.malformed_content_type)
    media_type = f"{match['type']}/{match['subtype']}".lower()
    if media_type.startswith("application/cloudevents"):
        raise _ContentError(EventFailureCode.unsupported_cloudevents_mode)
    if media_type != "application/json" and not match["subtype"].lower().endswith("+json"):
        raise _ContentError(EventFailureCode.unsupported_content_type)
    _validate_content_type_parameters(match["parameters"])
    return text


def _validate_content_type_parameters(parameters: str) -> None:
    seen_parameters: set[str] = set()
    for parameter in _PARAMETERS.finditer(parameters):
        name = parameter["name"].lower()
        if name in seen_parameters:
            raise _ContentError(EventFailureCode.malformed_content_type)
        seen_parameters.add(name)
        value = parameter["value"]
        if value.startswith('"'):
            value = re.sub(r"\\(.)", r"\1", value[1:-1])
        if name == "charset" and value.lower() not in {"utf-8", "utf8"}:
            raise _ContentError(EventFailureCode.unsupported_content_type)


def _base64(value: bytes | None) -> str | None:
    return None if value is None else base64.b64encode(value).decode("ascii")


def encode_envelope(envelope: WorkflowEventEnvelope) -> bytes:
    """Match default Temporal JSON bytes; complete start arguments need later sizing."""
    return json.dumps(
        envelope.model_dump(mode="json", by_alias=True),
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def encoded_envelope_size(envelope: WorkflowEventEnvelope) -> int:
    """Count keys, all headers, base64, payload duplication, and source metadata."""
    return len(encode_envelope(envelope))


def _canonical_json_value(value: JsonValue) -> JsonValue:
    """Produce an exact, type-tagged representation for JSON Schema equality."""
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["boolean", value]
    if isinstance(value, (int, float)):
        numerator, denominator = (value, 1) if isinstance(value, int) else value.as_integer_ratio()
        return ["number", str(numerator), str(denominator)]
    if isinstance(value, str):
        return ["string", value]
    if isinstance(value, list):
        return ["array", [_canonical_json_value(item) for item in value]]
    return ["object", [[key, _canonical_json_value(item)] for key, item in sorted(value.items())]]


def _validate_unique_items(
    validator: jsonschema.protocols.Validator,
    unique_items: bool,  # noqa: FBT001 - jsonschema calls keyword validators positionally
    instance: Any,  # noqa: ANN401
    _schema: dict[str, Any],
) -> Iterator[jsonschema.ValidationError]:
    """Sort canonical items instead of using the library's quadratic fallback."""
    if not unique_items or not validator.is_type(instance, "array"):
        return
    canonical_items = sorted(
        json.dumps(_canonical_json_value(item), ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        for item in cast("list[JsonValue]", instance)
    )
    if any(previous == current for previous, current in pairwise(canonical_items)):
        yield jsonschema.ValidationError("Array items must be unique.")


_EventDraft7Validator: type[jsonschema.protocols.Validator] = validators.extend(  # type: ignore[no-untyped-call]
    jsonschema.Draft7Validator,
    {"uniqueItems": _validate_unique_items},
)


def validate_payload(
    envelope: WorkflowEventEnvelope,
    schema: dict[str, Any] | None,
) -> EventDecodeFailure | None:
    """Validate only payload using existing Draft-07 guards, without defaults."""
    if schema is None:
        return None
    try:
        validate_json_schema_definition(schema)
        _EventDraft7Validator(schema, registry=NO_REF_REGISTRY).validate(envelope.payload)
    except (jsonschema.ValidationError, ArithmeticError):
        return EventDecodeFailure(code=EventFailureCode.schema_mismatch)
    except (ValueError, jsonschema.SchemaError, jsonschema.exceptions.UnknownType, RecursionError, Unresolvable):
        return EventDecodeFailure(code=EventFailureCode.invalid_schema)
    return None


class JsonEventDecoder:
    """Build envelopes within configurable candidate limits, with no I/O.

    Callers inject Settings values. Results never discard a record, emit audit
    events, or permit a broker acknowledgement. Numeric nesting and schema
    complexity limits remain deferred; parser-capacity errors are sanitized.
    """

    def __init__(
        self,
        *,
        max_value_bytes: int = EventStreamLimits.DEFAULT_MAX_VALUE_BYTES,
        max_envelope_bytes: int = EventStreamLimits.DEFAULT_MAX_ENVELOPE_BYTES,
        max_headers: int = EventStreamLimits.DEFAULT_MAX_HEADERS,
    ) -> None:
        """Store positive candidate bounds, not validated transport guarantees."""
        if max_value_bytes <= 0 or max_envelope_bytes <= 0 or max_headers <= 0:
            msg = "Candidate event safety limits must be positive."
            raise ValueError(msg)
        self._max_value_bytes = max_value_bytes
        self._max_envelope_bytes = max_envelope_bytes
        self._max_headers = max_headers

    def decode(
        self,
        event: RawEvent,
        *,
        schema: dict[str, Any] | None = None,
    ) -> EventDecodeSuccess | EventDecodeFailure:
        """Return either a complete envelope or a sanitized per-message failure."""
        try:
            return self._decode(event, schema)
        except _ContentError as exc:
            return EventDecodeFailure(code=exc.code)
        except (UnicodeDecodeError, UnicodeEncodeError):
            return EventDecodeFailure(code=EventFailureCode.invalid_utf8)
        except RecursionError:
            return EventDecodeFailure(code=EventFailureCode.excessive_nesting)
        except ValidationError as exc:
            code = (
                EventFailureCode.excessive_nesting
                if any(error["type"] == "recursion_loop" for error in exc.errors(include_input=False))
                else EventFailureCode.invalid_json
            )
            return EventDecodeFailure(code=code)
        except (ValueError, ArithmeticError):
            return EventDecodeFailure(code=EventFailureCode.invalid_json)

    def _decode(
        self,
        event: RawEvent,
        schema: dict[str, Any] | None,
    ) -> EventDecodeSuccess | EventDecodeFailure:
        value = event.value
        if value is None:
            return EventDecodeFailure(code=EventFailureCode.tombstone)
        if len(value) > self._max_value_bytes:
            return EventDecodeFailure(code=EventFailureCode.value_too_large)
        if len(event.headers) > self._max_headers:
            raise _ContentError(EventFailureCode.too_many_headers)
        # Avoid allocating base64 representations that already exceed the limit.
        originals = [value, event.key, *(header.value for header in event.headers)]
        base64_bytes = sum(4 * ((len(item) + 2) // 3) for item in originals if item is not None)
        header_bytes = sum(
            len(header.name.encode("utf-8")) + EventStreamLimits.HEADER_JSON_OVERHEAD_BYTES for header in event.headers
        )
        minimum_encoded_bytes = base64_bytes + header_bytes + max(len(event.headers) - 1, 0)
        if minimum_encoded_bytes > self._max_envelope_bytes:
            return EventDecodeFailure(code=EventFailureCode.envelope_too_large)
        datacontenttype = _validate_content_type(event.headers)
        cloudevents = decode_kafka_cloudevents(event.headers, datacontenttype=datacontenttype)
        if isinstance(cloudevents, EventDecodeFailure):
            raise _ContentError(cloudevents.code)
        # Confluent framing: a zero magic byte followed by a four-byte schema ID.
        if len(value) >= _REGISTRY_FRAME_PREFIX_BYTES and value.startswith(b"\x00"):
            raise _ContentError(EventFailureCode.registry_framing)
        payload = cast(
            "JsonValue",
            json.loads(
                value.decode("utf-8", errors="strict"),
                object_pairs_hook=_object_members,
                parse_float=_finite_float,
                parse_constant=_reject_constant,
            ),
        )
        # Escaped lone surrogates are JSON-decodable but cannot be strict UTF-8.
        json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        envelope = WorkflowEventEnvelope(
            payload=payload,
            cloudevents=cloudevents,
            original=OriginalEvent(
                value_base64=base64.b64encode(value).decode("ascii"),
                key_base64=_base64(event.key),
                headers=tuple(
                    OriginalEventHeader(name=header.name, value_base64=_base64(header.value))
                    for header in event.headers
                ),
            ),
            metadata=event.source_metadata,
        )
        size = encoded_envelope_size(envelope)
        if size > self._max_envelope_bytes:
            return EventDecodeFailure(code=EventFailureCode.envelope_too_large)
        failure = validate_payload(envelope, schema)
        if failure is not None:
            return failure
        return EventDecodeSuccess(envelope=envelope, encoded_envelope_bytes=size)
