"""Request schemas for invocation API endpoints.

Defines Pydantic models for API request validation with proper field aliasing
to support snake_case API contracts while maintaining backward compatibility.
"""

from enum import Enum
from uuid import UUID

from fastapi import UploadFile
from pydantic import AliasChoices, Field
from sqlmodel import SQLModel


class CancellationResult(Enum):
    """Result enum for invocation cancellation operations."""

    SUCCESS = "success"
    NOT_FOUND = "not_found"
    NOT_CANCELLABLE = "not_cancellable"


class InvocationCreateRequest(SQLModel, populate_by_name=True):
    """Request schema for creating a new invocation.

    Supports multiple field name formats:
    - snake_case (API contract): session_id, context_data
    - camelCase (backward compatibility): sessionId, contextData

    Note: created_by is automatically set from authenticated user context.
    """

    prompt: str = Field(
        min_length=1,
        max_length=10000,
        description="Natural language request describing desired automation task",
    )

    session_id: str = Field(
        validation_alias=AliasChoices("sessionId", "session_id"),
        serialization_alias="session_id",
        description="Session identifier for grouping related invocations",
    )

    context_data: dict[str, object] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("contextData", "context_data"),
        serialization_alias="context_data",
        description=(
            "Optional additional context for the request. "
            "Use 'file_ids' (array of UUID strings) to reference uploaded files."
        ),
    )

    project_id: UUID = Field(
        validation_alias=AliasChoices("projectId", "project_id"),
        serialization_alias="project_id",
        description="Project to associate this invocation with",
    )


class InvocationRequestWithFile(SQLModel):
    """Multipart form body for POST /invocations/chat (file upload path)."""

    prompt: str | None = None
    session_id: str | None = None
    context_data: str | None = None
    files: list[UploadFile] | None = None
    project_id: str


class InvocationCancelRequest(SQLModel, populate_by_name=True):
    """Request schema for cancelling an invocation.

    Supports multiple field name formats:
    - camelCase (API contract): reason
    - snake_case (internal): reason
    """

    reason: str = Field(
        default="User cancelled",
        max_length=500,
        description="Optional reason for cancellation",
    )


class InvocationCancelResponse(SQLModel, populate_by_name=True):
    """Response schema for invocation cancellation.

    Indicates whether the cancellation was successful or failed.
    """

    success: bool = Field(description="True if cancellation was successful, False otherwise")

    message: str = Field(description="Human-readable message describing the cancellation result")
