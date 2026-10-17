"""Transport-neutral event contracts without client or persistence imports."""

from typing import ClassVar
from uuid import UUID

from pydantic import AwareDatetime, ConfigDict, Field, JsonValue, SerializeAsAny
from sqlmodel import SQLModel


class EventSourceMetadata(SQLModel):
    """Common source context, extended by typed transport-specific metadata."""

    integration_id: UUID
    subscription_id: UUID
    source_generation: int = Field(ge=1, strict=True)
    received_at: AwareDatetime

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)  # type: ignore[assignment]


class RawEventHeader(SQLModel):
    """One header; ordered lists preserve repeated names and null values."""

    name: str = Field(repr=False)
    value: bytes | None = Field(repr=False)

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)  # type: ignore[assignment]


class RawEvent(SQLModel):
    """Normalized source bytes; null and empty values remain distinct."""

    value: bytes | None = Field(repr=False)
    key: bytes | None = Field(default=None, repr=False)
    headers: list[RawEventHeader] = Field(default_factory=list, repr=False)
    source_metadata: SerializeAsAny[EventSourceMetadata]

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)  # type: ignore[assignment]


class OriginalEventHeader(SQLModel):
    """JSON-safe representation of one original header."""

    name: str = Field(repr=False)
    value_base64: str | None = Field(repr=False)


class OriginalEvent(SQLModel):
    """Exact source bytes without collapsing null and empty values."""

    value_base64: str = Field(repr=False)
    key_base64: str | None = Field(repr=False)
    headers: list[OriginalEventHeader] = Field(default_factory=list, repr=False)


class WorkflowEventEnvelope(SQLModel):
    """Versioned trigger input independent of the source transport."""

    envelope_version: int = Field(default=1, ge=1, le=1, strict=True)
    payload: JsonValue = Field(repr=False)
    original: OriginalEvent = Field(repr=False)
    cloudevents: None = None
    source_metadata: SerializeAsAny[EventSourceMetadata] = Field(alias="metadata")

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)  # type: ignore[assignment]
