"""Immutable record coordinates without broker clients or persistence."""

from typing import ClassVar

from pydantic import ConfigDict
from sqlmodel import SQLModel


class EventRecordIdentity(SQLModel):
    """Base for adapter-supplied coordinates; never contains message contents."""

    transport: str

    model_config: ClassVar[ConfigDict] = ConfigDict(  # type: ignore[assignment]
        extra="forbid", frozen=True
    )
