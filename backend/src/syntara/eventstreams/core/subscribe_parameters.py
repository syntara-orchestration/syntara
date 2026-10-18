"""Transport-neutral, literal bindings for event Subscribe definitions."""

from typing import Any, ClassVar
from uuid import UUID

from pydantic import ConfigDict
from sqlmodel import SQLModel


class EventSubscribeParameters(SQLModel):
    """Resource references fixed before an event execution exists."""

    integration_id: UUID
    credential_id: UUID
    transport: str
    input_schema: dict[str, Any] | None = None

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]
