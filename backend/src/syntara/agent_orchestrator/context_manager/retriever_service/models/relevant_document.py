"""RelevantDocument model for representing documents with relevancy scoring.

This module provides the RelevantDocument data model used for document retrieval
results with relevancy metadata and file references.
"""

from typing import Any

from pydantic import BaseModel, Field

from syntara.files.models import FileMetadata


class RelevantDocument(BaseModel):
    """Represents a document with relevancy score and metadata for retrieval results.

    This is a transient model (not stored in database) that represents documents
    retrieved from various storage backends with computed relevancy scores.

    Uses Pydantic BaseModel (not SQLModel) since:
    - Not a database table (transient model created on demand)
    - Used for internal service communication, not API requests/responses
    - Contains FileMetadata references from invocation context

    Attributes:
        content: Full document content (no chunking at service level)
        relevancy_score: Numeric score indicating relevance to query (0.0 to 1.0)
        file_metadata: Reference to original file metadata from invocation context
        source_type: Type of storage backend used ("uploaded_file", "database", etc.)
        retrieval_metadata: Additional metadata from retrieval process

    """

    content: str = Field(..., description="Full document content", min_length=1)
    relevancy_score: float = Field(..., description="Numeric score indicating relevance to query", ge=0.0, le=1.0)
    file_metadata: FileMetadata = Field(..., description="Reference to original file metadata from invocation context")
    source_type: str = Field(..., description="Type of storage backend used", min_length=1)
    retrieval_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata from retrieval process"
    )
