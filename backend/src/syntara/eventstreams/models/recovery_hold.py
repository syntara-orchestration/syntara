"""Durable evidence reservations shared by recovery and terminal cleanup."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, text
from sqlmodel import Field, SQLModel


class EventDeliveryRecoveryHold(SQLModel, table=True):
    """Protect all retained evidence for a source until explicitly released."""

    __tablename__ = "event_delivery_recovery_holds"

    token: UUID = Field(default_factory=uuid4, primary_key=True)
    source_id: UUID = Field(foreign_key="event_subscription_sources.id", ondelete="RESTRICT")
    created_at: datetime = Field(
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        sa_column_kwargs={"server_default": text("clock_timestamp()")},
    )
    released_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]

    __table_args__ = (
        Index(
            "ix_event_delivery_recovery_holds_active_source",
            "source_id",
            postgresql_where=text("released_at IS NULL"),
        ),
    )
