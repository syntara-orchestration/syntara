"""Work item persistence model and lifecycle states."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import DateTime
from sqlmodel import Field, SQLModel

from execution_plane.models.constants import EP_SCHEMA


class WorkItemStatus(StrEnum):
    """Lifecycle states of a dispatched work item."""

    PENDING = "pending"
    CLAIMED = "claimed"
    DISPATCHED = "dispatched"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkItem(SQLModel, table=True):
    """A unit of work written by the Temporal Worker and consumed by the Task Executor."""

    __tablename__ = "work_items"
    __table_args__ = (
        sa.Index("ix_work_items_work_correlation_id", "work_correlation_id"),
        sa.Index("ix_work_items_status", "status"),
        sa.Index("ix_work_items_pending", "created_at", postgresql_where=sa.text("status = 'pending'")),
        {"schema": EP_SCHEMA},
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # Opaque correlation handle supplied by the caller (e.g. Temporal workflow_id).
    # Named generically so non-Temporal callers can use it without confusion with
    # Syntara's own execution_id concept.
    work_correlation_id: uuid.UUID

    # Temporal async completion token. Held by the Task Executor until the terminal event
    # is received from the execution plane.
    activity_handle: str = Field(sa_column=Column(Text, nullable=False))

    status: WorkItemStatus = Field(
        default=WorkItemStatus.PENDING,
        sa_column=Column(sa.String, nullable=False),
    )

    # Set when a worker claims this item.
    execution_target_id: uuid.UUID | None = Field(default=None, foreign_key=f"{EP_SCHEMA}.execution_targets.id")

    # Activity parameters serialized by the Temporal activity before async handoff.
    payload: dict[str, Any] = Field(default={}, sa_column=Column(JSONB, nullable=False, server_default="{}"))

    # Terminal result persisted before signalling Temporal.
    result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))

    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    claimed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    # Set after handle.complete() / handle.fail() returns successfully.
    # NULL means the Temporal signal may not have been delivered — recovery
    # queries use this to retry. See docs/execution-plane/integration.md.
    signaled_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
