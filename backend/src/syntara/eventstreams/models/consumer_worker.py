"""Operational membership of event consumer process incarnations.

This registry has no resource ownership or recovery-evidence relationships.
Removing stale membership cannot delete subscriptions, sources or deliveries.
Membership/placement services own database-time heartbeat and lease operations.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, text
from sqlmodel import Field, SQLModel


class EventConsumerWorker(SQLModel, table=True):
    """A process incarnation in the persisted installation namespace."""

    __tablename__ = "event_consumer_workers"

    worker_id: UUID = Field(default_factory=uuid4, primary_key=True)
    deployment_id: UUID = Field(description="Persisted Installation.id; never a per-process namespace")
    heartbeat_until: datetime = Field(
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="Database-time membership deadline; renewal belongs to the placement service",
    )
    draining: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    started_at: datetime = Field(
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        sa_column_kwargs={"server_default": text("now()")},
        description="Database-recorded process registration time",
    )

    __table_args__ = (
        Index("ix_event_consumer_workers_live_membership", "deployment_id", "draining", "heartbeat_until"),
    )
