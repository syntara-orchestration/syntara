"""Request schemas for invocation API endpoints.

Defines Pydantic models for API request validation with proper field aliasing
to support snake_case API contracts while maintaining backward compatibility.
"""

from uuid import UUID

from pydantic import AliasChoices, Field
from sqlmodel import SQLModel


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
