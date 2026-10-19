"""Transport-neutral event source configuration without broker client imports."""

from typing import ClassVar

from pydantic import ConfigDict
from sqlmodel import SQLModel


class EventSourceConfiguration(SQLModel):
    """Source address shared by supported event sources; immutable per generation.

    Concrete transports narrow ``transport`` to a literal and add their own
    addressing fields in the adapter layer. No secrets or event payloads.
    """

    transport: str

    model_config: ClassVar[ConfigDict] = ConfigDict(  # type: ignore[assignment]
        extra="forbid", frozen=True
    )
