from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import DateTime
from sqlmodel import Field, SQLModel

from execution_plane.models.execution_target import EP_SCHEMA


class WorkItemStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    DISPATCHED = "dispatched"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkItem(SQLModel, table=True):
    """A unit of work written by the Temporal Worker and consumed by the Task Executor.

    Temporal writes this row (including the activity_handle) before calling POST /schedule.
    The Task Executor polls for PENDING rows, claims them, dispatches, and writes the result.
    """

    __tablename__ = "work_items"
    __table_args__ = {"schema": EP_SCHEMA}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # Opaque reference into public.execution — no declared FK to allow schema separation.
    execution_id: uuid.UUID = Field(index=True)

    # Temporal async completion token. Held by the Task Executor until the terminal event
    # is received from the execution plane.
    activity_handle: str = Field(sa_column=Column(Text, nullable=False))

    status: WorkItemStatus = Field(
        default=WorkItemStatus.PENDING,
        sa_column=Column(sa.String, nullable=False, index=True),
    )

    # Set when a worker claims this item.
    execution_target_id: uuid.UUID | None = Field(default=None, foreign_key=f"{EP_SCHEMA}.execution_targets.id")

    # Activity parameters serialized by the Temporal activity before async handoff.
    payload: dict = Field(default={}, sa_column=Column(JSONB, nullable=False, server_default="{}"))

    # Terminal result persisted before signalling Temporal.
    result: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))

    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    claimed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
