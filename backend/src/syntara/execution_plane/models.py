"""AO-owned persistence for EP dispatch bindings and callback events."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class ExecutionPlaneActivityBinding(SQLModel, table=True):
    """AO's durable Temporal-token binding for one logical EP request."""

    __tablename__ = "execution_plane_activity_bindings"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_ep_activity_bindings_request_id"),
        Index("ix_ep_activity_bindings_status_updated", "status", "updated_at"),
        Index(
            "ix_ep_activity_bindings_cancel_delivery",
            "cancel_delivered_at",
            "cancel_next_attempt_at",
            "cancel_lease_expires_at",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    request_id: str = Field(sa_column=Column(String(64), nullable=False))
    client_id: str = Field(sa_column=Column(String(128), nullable=False))
    project_id: uuid.UUID
    temporal_workflow_id: str = Field(sa_column=Column(String(255), nullable=False))
    temporal_run_id: str = Field(sa_column=Column(String(255), nullable=False))
    temporal_activity_id: str = Field(sa_column=Column(String(255), nullable=False))
    activity_attempt: int = Field(sa_column=Column(Integer, nullable=False))
    task_token_ciphertext: str = Field(sa_column=Column(Text, nullable=False), repr=False)
    request_payload_ciphertext: str = Field(sa_column=Column(Text, nullable=False), repr=False)
    work_item_id: uuid.UUID | None = Field(default=None)
    status: str = Field(default="submitting", sa_column=Column(String(32), nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    last_status_check_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    cancel_requested_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    cancel_delivered_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    cancel_next_attempt_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    cancel_lease_expires_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    cancel_attempts: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    cancel_last_error: str | None = Field(default=None, sa_column=Column(String(1000), nullable=True))


class ExecutionPlaneCompletionInbox(SQLModel, table=True):
    """AO's durable, deduplicated inbox for authenticated EP result events."""

    __tablename__ = "execution_plane_completion_inbox"
    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "project_id",
            "request_id",
            "state_revision",
            name="uq_ep_completion_inbox_request_revision",
        ),
        Index("ix_ep_completion_inbox_delivery", "processed_at", "next_attempt_at", "lease_expires_at"),
    )

    event_id: uuid.UUID = Field(primary_key=True)
    client_id: str = Field(sa_column=Column(String(128), nullable=False))
    project_id: uuid.UUID
    work_item_id: uuid.UUID
    request_id: str = Field(sa_column=Column(String(64), nullable=False))
    state_revision: int = Field(sa_column=Column(Integer, nullable=False))
    status: str = Field(sa_column=Column(String(32), nullable=False))
    result: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    completed_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    received_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    processed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    attempts: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    next_attempt_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    lease_expires_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    last_error: str | None = Field(default=None, sa_column=Column(String(1000), nullable=True))
