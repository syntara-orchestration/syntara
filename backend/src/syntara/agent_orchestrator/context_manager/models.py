"""Data models for context management.

Defines Pydantic data models for context packages and related components.

Note: ContextPackage is an in-memory model only (FR-020) - no database persistence.
"""

from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid4())


class ContextPackage(BaseModel):
    """Context package returned by the Context Manager.

    Represents the final assembled context with all metadata
    and grounding information for LLM consumption.

    Note: This is an in-memory model only (FR-020). Context packages are
    ephemeral and rebuilt on demand, not persisted to database.
    """

    id: str = Field(
        default_factory=generate_uuid,
        description="Unique identifier for this context package",
    )
    invocation_id: UUID | None = Field(
        default=None,
        description="Reference to the agent invocation ID (in-memory reference, not a foreign key)",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Assembled document content from RelevantDocuments",
    )
    grounding_score: float = Field(
        default=0.0,
        description="Simple average of relevancy_score from RelevantDocuments",
        ge=0.0,
        le=1.0,
    )
    citations: list[str] = Field(
        default_factory=list,
        description="File IDs extracted from RelevantDocument.file_metadata.file_id attributes",
    )
    package_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Timing, token counts, compression status, compression_retry_count",
    )
