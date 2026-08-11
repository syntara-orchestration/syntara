"""Tool SQLModel definition for database storage.

This module contains the Tool and related SQLModel classes that extend the Resource base class
with tool-specific fields as defined in the OpenAPI specification.
"""

from datetime import datetime
from enum import Enum
from typing import Any, ClassVar
from uuid import UUID

from pydantic import ConfigDict, field_validator
from sqlalchemy import Column, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import DateTime, Field, Relationship, SQLModel

from syntara.core.constants import FieldLimits
from syntara.core.exceptions import SafeValueError
from syntara.core.models.base import BaseResource
from syntara.core.models.base.named import NamedResource
from syntara.core.models.base.user_owned import UserOwnedResource
from syntara.core.models.pagination import ResourcesResponse
from syntara.core.utils.sqlmodel import postgres_enum_column


class ToolStatus(str, Enum):
    """Status of a tool."""

    AVAILABLE = "available"
    MISSING = "missing"
    ERROR = "error"


class ToolParameterType(str, Enum):
    """Parameter types for tools."""

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"


class ToolParameter(BaseResource, table=True):
    """Tool parameter definition stored in database.

    Represents a parameter that a tool accepts, with its type, validation rules,
    and example values.

    Inherits from BaseResource:
        id: UUID primary key
        created_at: Creation timestamp
        updated_at: Last update timestamp
        labels: Optional key-value metadata
    """

    __tablename__ = "tool_parameters"

    tool_id: UUID = Field(foreign_key="tools.id", ondelete="CASCADE", index=True)

    name: str = Field(
        min_length=1,
        max_length=FieldLimits.PARAMETER_NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.PARAMETER_NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Parameter name",
    )

    type: ToolParameterType = Field(
        sa_column=postgres_enum_column(
            ToolParameterType,
            "tool_parameter_type",
        ),
        description="Parameter type",
    )

    description: str = Field(
        sa_type=Text(),  # type: ignore[call-overload]
        description="Parameter description",
    )

    required: bool = Field(description="Whether this parameter is required")

    default_value: dict[str, Any] | None = Field(
        default=None, sa_type=JSONB, description="Default value for the parameter"
    )

    example_value: dict[str, Any] | None = Field(
        default=None, sa_type=JSONB, description="Example value for the parameter"
    )

    # Relationships
    tool: "Tool" = Relationship(back_populates="parameters")

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",  # Reject unknown fields
    )


class ToolBase(NamedResource, UserOwnedResource):
    """Tool base model.

    Represents a tool provided by an external MCP server integration.
    Extends NamedResource and UserOwnedResource with tool-specific fields.

    Attributes:
        integration_id: UUID of the owning Integration (CASCADE on delete)
        namespaced_name: Unique namespaced name for the tool (max 200 chars)
        enabled: Whether the tool is enabled (default: True)
        status: Current status of the tool (default: available)
        last_executed_at: Timestamp of last execution (nullable)
        last_refreshed_at: Timestamp of last refresh from provider (nullable)
        refresh_error: Error message from last refresh attempt (nullable)

    Inherits from NamedResource + UserOwnedResource:
        id: UUID primary key
        name: Human-readable name (1-255 chars)
        description: Optional detailed description (max 2000 chars)
        created_at: Creation timestamp
        updated_at: Last update timestamp
        created_by: UUID of user who created the resource
        updated_by: Optional UUID of user who last updated the resource
        labels: Optional key-value metadata

    """

    integration_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("integrations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        description="UUID of the owning Integration (mcp_server)",
    )

    namespaced_name: str = Field(
        min_length=1,
        max_length=FieldLimits.NAMESPACED_NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAMESPACED_NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Unique namespaced name for the tool",
        index=True,
    )

    enabled: bool = Field(default=True, description="Whether the tool is enabled", index=True)

    status: ToolStatus = Field(
        default=ToolStatus.AVAILABLE,
        sa_column=postgres_enum_column(
            ToolStatus,
            "tool_status",
            index=True,
        ),
        description="Current status of the tool",
    )

    last_executed_at: datetime | None = Field(
        default=None,
        description="Timestamp of last execution",
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        index=True,
    )

    last_refreshed_at: datetime | None = Field(
        default=None,
        description="Timestamp of last refresh from provider",
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        index=True,
    )

    refresh_error: str | None = Field(
        default=None,
        sa_type=Text(),  # type: ignore[call-overload]
        description="Error message from last refresh attempt",
    )

    FIELD_SCHEMA_EXTRAS: ClassVar[dict[str, Any]] = {
        **NamedResource.FIELD_SCHEMA_EXTRAS,
        **UserOwnedResource.FIELD_SCHEMA_EXTRAS,
    }

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",  # Reject unknown fields
    )  # type: ignore[assignment]


class Tool(ToolBase, table=True):
    """Tool database model."""

    __tablename__ = "tools"

    __filterable_fields__: ClassVar[list[str]] = [
        *NamedResource.__filterable_fields__,
        *UserOwnedResource.__filterable_fields__,
        "enabled",
        "status",
        "integration_id",
        "namespaced_name",
    ]

    __sortable_fields__: ClassVar[list[str]] = [
        *NamedResource.__sortable_fields__,
        *UserOwnedResource.__sortable_fields__,
        "status",
    ]

    # Relationships
    parameters: list["ToolParameter"] = Relationship(back_populates="tool", cascade_delete=True)

    __table_args__ = (
        UniqueConstraint("namespaced_name", name="uq_tools_namespaced_name"),
        # Composite index for pagination queries
        Index("ix_tools_created_at_id", "created_at", "id"),
        # Composite index for integration queries with pagination
        Index("ix_tools_integration_id_created_at_id", "integration_id", "created_at", "id"),
    )

    @field_validator("namespaced_name")
    @classmethod
    def validate_namespaced_name(cls, v: str) -> str:
        """Validate that namespaced_name is not empty."""
        if not v or not v.strip():
            msg = "namespaced_name cannot be empty"
            raise SafeValueError(msg)
        return v.strip()

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",  # Reject unknown fields
    )


# ============================================================================
# API Request/Response Schemas
# ============================================================================


class ToolWithParameters(ToolBase):
    """Schema for Tool response with ToolParameter details."""

    parameters: list[ToolParameter] = Field(..., description="Tool parameters")


class ToolUpdate(SQLModel):
    """Model for updating tool configuration."""

    enabled: bool | None = Field(default=None, description="Whether the tool is enabled")
    status: ToolStatus | None = Field(default=None, description="Current status of the tool")
    refresh_error: str | None = Field(default=None, description="Error message from last refresh attempt")

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",  # Reject unknown fields
    )  # type: ignore[assignment]


# ============================================================================
# List Response
# ============================================================================


class ToolListResponse(ResourcesResponse[ToolWithParameters]):
    """Paginated list response for tools."""
