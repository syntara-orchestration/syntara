"""Draft-only bindings; never accepted by runtime or preflight entry points."""

from typing import Any, ClassVar
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator
from sqlmodel import SQLModel

from syntara.eventstreams.models.filter_configuration import FilterConfiguration, normalize_filter


class EventSubscribeDraftParameters(SQLModel):
    """Allow omissions while retaining validation of supplied literal bindings."""

    integration_id: UUID | None = None
    credential_id: UUID | None = None
    topic: str | None = Field(default=None, min_length=1, max_length=1024)
    input_schema: dict[str, Any] | None = None
    filter: FilterConfiguration | None = None

    _normalize_filter = field_validator("filter")(normalize_filter)

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]
