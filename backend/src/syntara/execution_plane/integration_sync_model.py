"""AO-owned durable outbox for desired integration state sent to EP."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class ExecutionPlaneIntegrationSync(SQLModel, table=True):
    """One AO transaction's intent to create, update, or delete an EP resource."""

    __tablename__ = "execution_plane_integration_sync"
    __table_args__ = (
        UniqueConstraint("integration_id", "source_revision", name="uq_ep_integration_sync_revision"),
        Index("ix_ep_integration_sync_delivery", "processed_at", "next_attempt_at", "lease_expires_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    integration_id: uuid.UUID
    source_revision: int = Field(sa_column=Column(Integer, nullable=False))
    operation: str = Field(sa_column=Column(String(16), nullable=False))
    name: str = Field(sa_column=Column(String(255), nullable=False))
    endpoint: str = Field(sa_column=Column(String(2048), nullable=False))
    namespace: str = Field(sa_column=Column(String(63), nullable=False))
    attempts: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    processed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    next_attempt_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    lease_expires_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    last_error: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
