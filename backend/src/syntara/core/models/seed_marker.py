"""Internal history for defaults that must never be recreated after removal."""

from datetime import datetime

from sqlalchemy import DateTime, text
from sqlmodel import Field, SQLModel


class SeedMarker(SQLModel, table=True):
    """A committed marker means its one-time seed completed successfully."""

    __tablename__ = "seed_markers"

    key: str = Field(primary_key=True, max_length=255)
    seeded_at: datetime = Field(
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        sa_column_kwargs={"server_default": text("now()")},
    )
