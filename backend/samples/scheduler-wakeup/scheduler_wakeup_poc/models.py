"""Database records owned exclusively by the scheduler wake-up sample."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Index, JSON, String, UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Normalise SQLite's timezone-naive reads for the sample test backend."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class POCExecution(SQLModel, table=True):
    __tablename__ = "poc_execution"
    __table_args__ = (
        UniqueConstraint("queue", "idempotency_key", name="uq_poc_execution_queue_key"),
        Index("ix_poc_execution_eligible", "queue", "next_attempt_at", "created_at", "id"),
        Index("ix_poc_execution_active_lease", "lease_expires_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    queue: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    idempotency_key: str = Field(sa_column=Column(String(255), nullable=False))
    request_hash: str = Field(sa_column=Column(String(64), nullable=False))
    task: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    state: str = Field(default="queued", sa_column=Column(String(32), nullable=False, index=True))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    next_attempt_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    deadline: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    current_owner_id: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    current_attempt_id: UUID | None = Field(default=None, nullable=True)
    current_fencing_token: int = Field(default=0, nullable=False)
    lease_expires_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    transition_reason: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))


class POCAttempt(SQLModel, table=True):
    __tablename__ = "poc_attempt"
    __table_args__ = (
        UniqueConstraint("execution_id", "fencing_token", name="uq_poc_attempt_execution_fence"),
        Index("ix_poc_attempt_unfinished", "execution_id", "finished_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    execution_id: UUID = Field(foreign_key="poc_execution.id", nullable=False, index=True)
    fencing_token: int = Field(nullable=False)
    owner_id: str = Field(sa_column=Column(String(255), nullable=False))
    started_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    lease_expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    terminal_reason: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))


class POCWakeOutbox(SQLModel, table=True):
    __tablename__ = "poc_wake_outbox"
    __table_args__ = (Index("ix_poc_wake_outbox_due", "publication_state", "next_publication_at"),)

    event_id: UUID = Field(default_factory=uuid4, primary_key=True)
    queue: str = Field(sa_column=Column(String(255), nullable=False, index=True))
    execution_id: UUID | None = Field(default=None, foreign_key="poc_execution.id")
    not_before: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    publication_state: str = Field(default="pending", sa_column=Column(String(32), nullable=False))
    publication_lease_owner: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    publication_lease_token: int = Field(default=0, nullable=False)
    publication_lease_expires_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    tries: int = Field(default=0, nullable=False)
    next_publication_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    accepted_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    last_safe_error: str | None = Field(default=None, sa_column=Column(String(2048), nullable=True))


class POCPool(SQLModel, table=True):
    __tablename__ = "poc_pool"
    __table_args__ = (UniqueConstraint("queue", name="uq_poc_pool_queue"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    queue: str = Field(sa_column=Column(String(255), nullable=False))
    capacity_limit: int | None = Field(default=None, nullable=True)
    reserved_count: int = Field(default=0, nullable=False)


class POCReservation(SQLModel, table=True):
    __tablename__ = "poc_reservation"
    __table_args__ = (Index("ix_poc_reservation_active", "attempt_id", "released_at"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    attempt_id: UUID = Field(foreign_key="poc_attempt.id", nullable=False, index=True)
    pool_id: UUID = Field(foreign_key="poc_pool.id", nullable=False, index=True)
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    released_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
