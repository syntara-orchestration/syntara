"""Durable control coordination, independent of activity/Visibility storage.

Runtime participants register before opening a consumer and acknowledge only a
verified stop. Rows have no expiry: a lost worker is never evidence of quiescence.
"""

from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, text
from sqlmodel import Field, SQLModel


class EventSubscriptionRuntime(SQLModel, table=True):
    """A consumer's durable participation in a source lifecycle fence."""

    __tablename__ = "event_subscription_runtimes"

    source_id: UUID = Field(foreign_key="event_subscription_sources.id", ondelete="RESTRICT", primary_key=True)
    worker_id: str = Field(max_length=255, primary_key=True)
    configuration_revision: int = Field(sa_type=BigInteger)
    applied_revision: int | None = Field(default=None, sa_type=BigInteger)
    applied_published_version_id: UUID | None = None
    runtime_state: str = Field(
        default="starting", max_length=32, sa_column_kwargs={"server_default": text("'starting'")}
    )
    stopped: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    permanent_content_error: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})

    __table_args__ = (
        CheckConstraint("configuration_revision > 0", name="ck_event_runtime_revision"),
        CheckConstraint("applied_revision IS NULL OR applied_revision > 0", name="ck_event_runtime_applied"),
    )
