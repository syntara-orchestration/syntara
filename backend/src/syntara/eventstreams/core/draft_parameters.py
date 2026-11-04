"""Draft-only bindings; never accepted by runtime or preflight entry points."""

from typing import Any, ClassVar
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator
from sqlmodel import SQLModel


class EventSubscribeDraftParameters(SQLModel):
    """Allow omissions while retaining validation of supplied literal bindings."""

    integration_id: UUID | None = None
    credential_id: UUID | None = None
    topic: str | None = Field(default=None, min_length=1, max_length=1024)
    input_schema: dict[str, Any] | None = None

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]


class KafkaSubscribeDraftParameters(EventSubscribeDraftParameters):
    """Apply Kafka topic rules when a draft has selected a Kafka Integration."""

    topic: str | None = Field(default=None, min_length=1, max_length=249, pattern=r"^[a-zA-Z0-9._-]+$")

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str | None) -> str | None:
        """Reject reserved names even in drafts."""
        if value in {".", ".."}:
            msg = "topic must be one exact Kafka topic"
            raise ValueError(msg)
        return value
