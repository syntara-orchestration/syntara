"""Private durable handoff and completion inbox; not an application API model."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


class ActivityCompletion(SQLModel, table=True):
    """One attempt's engine binding and durable terminal result."""

    __tablename__ = "runtime_activity_completions"
    __table_args__ = (UniqueConstraint("engine_run_id", "node_execution_id", "attempt"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    execution_id: UUID = Field(index=True)
    project_id: UUID
    node_execution_id: str
    activity_name: str
    activity_version: int
    engine_workflow_id: str
    engine_run_id: str
    attempt: int
    encrypted_task_token: str = Field(repr=False)
    external_operation_id: str | None = None
    deferred: bool = False
    state: str = Field(default="reserved", index=True)
    output: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    failure: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_column=Column(DateTime(timezone=True), nullable=False)
    )
