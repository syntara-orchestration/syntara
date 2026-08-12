"""SQLModel definition for invocations table and related schemas."""

from datetime import datetime
from enum import Enum
from typing import Any, ClassVar
from uuid import UUID

from pydantic import ConfigDict
from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import DateTime
from sqlmodel import Field, SQLModel

from syntara.core.constants import FieldLimits
from syntara.core.models.base import UserOwnedResource
from syntara.core.models.pagination import ResourcesResponse
from syntara.core.utils.sqlmodel import postgres_enum_column


class InvocationStatus(str, Enum):
    """Status enum for invocation lifecycle."""

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


class Invocation(UserOwnedResource, table=True):
    """SQLModel for async workflow invocations."""

    __tablename__ = "invocations"

    # SQLModel configuration is inherited from base classes

    # Define composite indexes
    __table_args__ = (
        Index("ix_invocations_created_by_status", "created_by", "status"),
        Index("ix_invocations_trace_events_gin", "trace_events", postgresql_using="gin"),
    )

    # Define filterable fields for API endpoints - extend base UserOwnedResource fields
    __filterable_fields__: ClassVar[list[str]] = [
        *UserOwnedResource.__filterable_fields__,
        "project_id",
        "status",
        "session_id",
        "started_at",
        "completed_at",
        "prompt",
        "model_name",
    ]

    # Define sortable fields for API endpoints - extend base UserOwnedResource fields
    __sortable_fields__: ClassVar[list[str]] = [
        *UserOwnedResource.__sortable_fields__,
        "started_at",
        "completed_at",
        "status",
        "model_name",
    ]

    project_id: UUID = Field(
        foreign_key="projects.id",
        description="Project namespace for resource isolation",
        index=True,
    )

    # Required fields
    prompt: str = Field(
        min_length=1,
        max_length=10000,
        sa_type=Text(),  # type: ignore[call-overload]
        description="Natural language user request",
    )

    session_id: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Session identifier for multi-tenant isolation",
        index=True,
    )

    status: InvocationStatus = Field(
        default=InvocationStatus.CREATED,
        sa_column=postgres_enum_column(
            InvocationStatus,
            "invocationstatus",
            index=True,
        ),
        description="Current invocation status",
    )

    # Optional timestamp fields
    started_at: datetime | None = Field(
        default=None,
        description="Timestamp when workflow execution started",
        # SQLAlchemy's DateTime() signature expects no args in stubs,
        # but actually supports timezone parameter at runtime
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )

    completed_at: datetime | None = Field(
        default=None,
        description="Timestamp when workflow completed",
        # SQLAlchemy's DateTime() signature expects no args in stubs,
        # but actually supports timezone parameter at runtime
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )

    # JSONB fields
    # Note: context_data may contain:
    # - file_ids: list[str] - File IDs referencing FileMetadata table
    # - Other context fields as needed
    context_data: dict[str, object] = Field(
        default_factory=dict,
        sa_type=JSONB,
        description="Additional context for the request, including file_ids array if files uploaded",
    )

    result: dict[str, object] | None = Field(
        default=None,
        sa_type=JSONB,
        description="Workflow result data",
    )

    checkpoint_data: dict[str, object] | None = Field(
        default=None,
        sa_type=JSONB,
        description="Checkpoint data for pause/resume",
    )

    trace_events: list[dict[str, object]] | None = Field(
        default=None,
        sa_type=JSONB,
        description="Persisted agent trace steps (reasoning, tool calls, tool results, final answer)",
    )

    # Model identification
    model_name: str | None = Field(
        default=None,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="LLM model name used for the invocation",
        index=True,
    )

    # Optional text fields
    error_message: str | None = Field(
        default=None,
        sa_type=Text(),  # type: ignore[call-overload]
        description="Error message if invocation failed",
    )

    def __repr__(self) -> str:
        """Return string representation of Invocation.

        Returns:
            String representation

        """
        return f"<Invocation(id={self.id}, status={self.status})>"


class InvocationListResponse(ResourcesResponse[Invocation]):
    """Paginated list response for invocations."""


class InvocationTraceRead(SQLModel):
    """Read schema for agent execution trace."""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    invocation_id: UUID = Field(description="Invocation UUID")
    status: InvocationStatus = Field(description="Current invocation status")
    agent_trace: dict[str, Any] | None = Field(
        default=None,
        description="Agent execution trace with model, tokens, duration, and steps",
    )
