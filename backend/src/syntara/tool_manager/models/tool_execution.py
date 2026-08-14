"""Tool execution model for database storage."""

from datetime import datetime
from enum import Enum
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import DateTime, Field

from syntara.core.constants import FieldLimits
from syntara.core.models.base.user_owned import UserOwnedResource


class ToolExecutionStatus(str, Enum):
    """Status of a tool execution."""

    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class ToolExecution(UserOwnedResource, table=True):
    """Tool execution records stored in database.

    Records individual Tool executions for performance monitoring and analysis.

    Inherits from UserOwnedResource:
        id: UUID primary key
        created_at: Creation timestamp
        updated_at: Last update timestamp
        created_by: UUID of user who created the resource
        updated_by: Optional UUID of user who last updated the resource
        labels: Optional key-value metadata
    """

    __tablename__ = "tool_executions"

    __filterable_fields__: ClassVar[list[str]] = [
        *UserOwnedResource.__filterable_fields__,
        "tool_id",
        "integration_id",
        "user_id",
        "status",
    ]

    __sortable_fields__: ClassVar[list[str]] = [
        *UserOwnedResource.__sortable_fields__,
        "execution_start",
        "duration_ms",
    ]

    tool_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("tools.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        description="Foreign key to Tool",
    )

    integration_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("integrations.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        description="Foreign key to Integration (denormalized from tool)",
    )

    user_id: UUID = Field(description="Identifier of executing user/agent", index=True)

    execution_start: datetime = Field(
        description="Execution start timestamp",
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        index=True,
    )

    execution_end: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="Execution completion timestamp",
    )

    duration_ms: int | None = Field(default=None, ge=0, description="Execution duration in milliseconds")

    status: ToolExecutionStatus = Field(description="Execution status")

    input_parameters: dict[str, Any] = Field(sa_type=JSONB, description="Tool input parameters")

    output_data: dict[str, Any] | None = Field(default=None, sa_type=JSONB, description="Tool output data")

    error_message: str | None = Field(
        default=None,
        sa_type=Text(),  # type: ignore[call-overload]
        description="Error description for failed executions",
    )

    error_code: str | None = Field(
        default=None,
        max_length=FieldLimits.ERROR_CODE_MAX_LENGTH,
        sa_type=String(FieldLimits.ERROR_CODE_MAX_LENGTH),  # type: ignore[call-overload]
        description="Structured error code",
    )
