"""Shared capacity-check state; it grants neither claims nor delivery resolution."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, text
from sqlmodel import Field, SQLModel


class EventDeliveryCapacity(SQLModel, table=True):
    """One database-wide latch for retained-row-count backpressure."""

    __tablename__ = "event_delivery_capacity"

    id: int = Field(default=1, primary_key=True)
    paused: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    retained_count: int = Field(default=0, sa_type=BigInteger, sa_column_kwargs={"server_default": text("0")})
    checked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_event_delivery_capacity_singleton"),
        CheckConstraint("retained_count >= 0", name="ck_event_delivery_capacity_count"),
    )
