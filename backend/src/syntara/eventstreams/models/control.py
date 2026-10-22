"""Durable control coordination, independent of activity/Visibility storage.

Runtime participants register before opening a consumer and acknowledge only a
verified stop. Rows have no expiry: a lost worker is never evidence of quiescence.
Recovery requests are consumed by the assigned runner, not the HTTP process.
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
    stopped: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    permanent_content_error: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})

    __table_args__ = (
        CheckConstraint("configuration_revision > 0", name="ck_event_runtime_revision"),
        CheckConstraint("applied_revision IS NULL OR applied_revision > 0", name="ck_event_runtime_applied"),
    )


class EventSubscriptionRecovery(SQLModel, table=True):
    """One revision-checked, authorized request for a source partition."""

    __tablename__ = "event_subscription_recoveries"

    source_id: UUID = Field(foreign_key="event_subscription_sources.id", ondelete="RESTRICT", primary_key=True)
    partition: int = Field(primary_key=True)
    configuration_revision: int = Field(sa_type=BigInteger)
    expected_recovery_revision: int = Field(sa_type=BigInteger)
    policy: str = Field(max_length=32)
    reason: str = Field(max_length=100)
    acknowledge_duplicate_risk: bool = False
    resolve_unscheduled: bool = False
    requested_by: UUID = Field(foreign_key="principals.id", ondelete="RESTRICT")
    completed: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    error_code: str | None = Field(default=None, max_length=100)

    __table_args__ = (
        CheckConstraint("partition >= 0", name="ck_event_recovery_partition"),
        CheckConstraint(
            "configuration_revision > 0 AND expected_recovery_revision >= 0", name="ck_event_recovery_revision"
        ),
        CheckConstraint("policy IN ('retained_beginning', 'current_end')", name="ck_event_recovery_policy"),
    )
