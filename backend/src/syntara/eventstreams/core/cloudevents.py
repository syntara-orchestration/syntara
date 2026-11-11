"""Supported CloudEvents context attributes, independent of transport and data."""

import re
from collections.abc import Mapping
from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, JsonValue, ValidationError, field_validator
from rfc3339_validator import validate_rfc3339  # type: ignore[import-untyped]
from rfc3986_validator import validate_rfc3986  # type: ignore[import-untyped]
from sqlmodel import SQLModel

from syntara.eventstreams.core.results import EventDecodeFailure, EventFailureCode

_ATTRIBUTE_NAME = re.compile(r"[a-z0-9]+")
_FORBIDDEN_STRING_CHARACTERS = re.compile("[\x00-\x1f\x7f-\x9f\ud800-\udfff\ufdd0-\ufdef]")
_RESERVED_NAMES = frozenset(
    {"specversion", "id", "source", "type", "subject", "time", "dataschema", "datacontenttype", "data", "extensions"}
)


def validate_attribute_string(value: str) -> str:
    """Reject characters forbidden by the CloudEvents String type."""
    if _FORBIDDEN_STRING_CHARACTERS.search(value) or any(ord(char) & 0xFFFF in {0xFFFE, 0xFFFF} for char in value):
        msg = "CloudEvents attributes contain a forbidden character."
        raise ValueError(msg)
    return value


class CloudEventAttributes(SQLModel):
    """CloudEvents 1.0 attributes; data lives only in the envelope payload.

    Unknown extension values retain their UTF-8 strings without type inference.
    URI and timestamp strings are validated without fetching schemas or URLs.
    """

    specversion: Literal["1.0"]
    id: str = Field(min_length=1, repr=False)
    source: str = Field(min_length=1, repr=False)
    type: str = Field(min_length=1, repr=False)
    subject: str | None = Field(default=None, min_length=1, repr=False)
    time: str | None = Field(default=None, repr=False)
    dataschema: str | None = Field(default=None, min_length=1, repr=False)
    datacontenttype: str | None = Field(default=None, repr=False)
    extensions: dict[str, str] = Field(default_factory=dict, repr=False)

    model_config: ClassVar[ConfigDict] = ConfigDict(  # type: ignore[assignment]
        extra="forbid", frozen=True, strict=True
    )

    @field_validator("id", "source", "type", "subject", "time", "dataschema", "datacontenttype")
    @classmethod
    def validate_string(cls, value: str | None) -> str | None:
        """Validate all supported String encodings without trimming values."""
        return None if value is None else validate_attribute_string(value)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        """Accept absolute and relative URI-references without normalization."""
        if not validate_rfc3986(value, rule="URI_reference"):
            msg = "CloudEvents source must be a URI-reference."
            raise ValueError(msg)
        return value

    @field_validator("dataschema")
    @classmethod
    def validate_dataschema(cls, value: str | None) -> str | None:
        """Require an absolute URI when a data schema is supplied."""
        if value is not None and not validate_rfc3986(value, rule="URI"):
            msg = "CloudEvents dataschema must be an absolute URI."
            raise ValueError(msg)
        return value

    @field_validator("time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        """Preserve timestamp precision and offset while checking RFC 3339."""
        if value is not None and not validate_rfc3339(value.upper()):
            msg = "CloudEvents time must be a supported RFC 3339 timestamp."
            raise ValueError(msg)
        return value

    @field_validator("extensions")
    @classmethod
    def validate_extensions(cls, value: dict[str, str]) -> dict[str, str]:
        """Keep extension names distinct from core attributes and event data."""
        for name, text in value.items():
            if _ATTRIBUTE_NAME.fullmatch(name) is None or name in _RESERVED_NAMES:
                msg = "CloudEvents extension names must be distinct lowercase alphanumeric names."
                raise ValueError(msg)
            validate_attribute_string(text)
        return value


_REQUIRED_ATTRIBUTES = frozenset({"specversion", "id", "source", "type"})
_STANDARD_ATTRIBUTES = frozenset(CloudEventAttributes.model_fields) - {"extensions"}
_MIN_EXTENSION_INTEGER = -(2**31)
_MAX_EXTENSION_INTEGER = 2**31 - 1


def _canonical_extension(value: JsonValue) -> str:
    """Normalize supported extension types to the binary binding's string form."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and _MIN_EXTENSION_INTEGER <= value <= _MAX_EXTENSION_INTEGER:
        return str(value)
    msg = "CloudEvents extensions require a string, Boolean, or signed 32-bit integer."
    raise ValueError(msg)


def normalize_cloudevents(attributes: Mapping[str, JsonValue]) -> CloudEventAttributes | EventDecodeFailure:
    """Validate attributes from either binding without inferring event data.

    JSON null attributes are unset. Both modes share required/optional attribute
    validation and extension names; binary strings retain their exact values.
    """
    if any(not isinstance(attributes.get(name), str) or not attributes[name] for name in _REQUIRED_ATTRIBUTES):
        return EventDecodeFailure(code=EventFailureCode.malformed_cloudevents)
    try:
        version = attributes["specversion"]
        if not isinstance(version, str):
            return EventDecodeFailure(code=EventFailureCode.malformed_cloudevents)
        validate_attribute_string(version)
        if version != "1.0":
            return EventDecodeFailure(code=EventFailureCode.unsupported_cloudevents_version)
        standard = {
            name: value for name, value in attributes.items() if name in _STANDARD_ATTRIBUTES and value is not None
        }
        extensions = {
            name: _canonical_extension(value)
            for name, value in attributes.items()
            if name not in _STANDARD_ATTRIBUTES and value is not None
        }
        return CloudEventAttributes.model_validate({**standard, "extensions": extensions})
    except ValidationError:
        return EventDecodeFailure(code=EventFailureCode.malformed_cloudevents)
    except ValueError:
        return EventDecodeFailure(code=EventFailureCode.malformed_cloudevents)
