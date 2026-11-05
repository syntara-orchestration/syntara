"""Transport-neutral event contracts without client or persistence imports."""

from typing import Any, ClassVar

from pydantic import ConfigDict, Field, JsonValue
from sqlmodel import SQLModel

from syntara.eventstreams.adapters.source_metadata import SourceMetadata
from syntara.eventstreams.core.cloudevents import CloudEventAttributes


class RawEventHeader(SQLModel):
    """One header; ordered lists preserve repeated names and null values."""

    name: str = Field(repr=False)
    value: bytes | None = Field(repr=False)

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)  # type: ignore[assignment]


class RawEvent(SQLModel):
    """Normalized source bytes; null and empty values remain distinct."""

    value: bytes | None = Field(repr=False)
    key: bytes | None = Field(default=None, repr=False)
    headers: tuple[RawEventHeader, ...] = Field(default_factory=tuple, repr=False)
    source_metadata: SourceMetadata

    model_config: ClassVar[ConfigDict] = ConfigDict(  # type: ignore[assignment]
        extra="forbid", frozen=True, populate_by_name=True, serialize_by_alias=True
    )


class OriginalEventHeader(SQLModel):
    """JSON-safe representation of one original header."""

    name: str = Field(repr=False)
    value_base64: str | None = Field(repr=False)

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)  # type: ignore[assignment]


class OriginalEvent(SQLModel):
    """Exact source bytes without collapsing null and empty values."""

    value_base64: str = Field(repr=False)
    key_base64: str | None = Field(repr=False)
    headers: tuple[OriginalEventHeader, ...] = Field(default_factory=tuple, repr=False)

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)  # type: ignore[assignment]


class WorkflowEventEnvelope(SQLModel):
    """Versioned trigger input independent of the source transport."""

    envelope_version: int = Field(default=1, ge=1, le=1, strict=True)
    payload: JsonValue = Field(repr=False)
    original: OriginalEvent = Field(repr=False)
    cloudevents: CloudEventAttributes | None = Field(default=None, repr=False)
    source_metadata: SourceMetadata = Field(alias="metadata")

    model_config: ClassVar[ConfigDict] = ConfigDict(  # type: ignore[assignment]
        extra="forbid", frozen=True, populate_by_name=True, serialize_by_alias=True
    )

    def dict(self, **kwargs: Any) -> dict[str, Any]:  # noqa: ANN401 - legacy SQLModel keyword compatibility
        """Give legacy converter callers the same JSON wire form as model_dump."""
        kwargs.setdefault("by_alias", True)
        return self.model_dump(mode="json", **kwargs)
