"""FileMetadata SQLModel for file upload metadata.

This module provides the FileMetadata SQLModel table for storing
file upload metadata independently of invocations.

Files are first-class entities with their own lifecycle, managed
by FileManager. File content is stored on the filesystem, with
only paths stored in the database (protects against DB bloat).
"""

from enum import Enum
from typing import ClassVar
from uuid import UUID

from pydantic import ConfigDict
from sqlmodel import Field

from syntara.core.models.base.base_resource import BaseResource


class FileStatus(str, Enum):
    """Status enum for file conversion lifecycle.

    States:
        PENDING_CONVERSION: File uploaded, waiting for conversion
        CONVERTING: Conversion in progress
        CONVERTED: Successfully converted to text/markdown
        CONVERSION_FAILED: Conversion failed with error
    """

    PENDING_CONVERSION = "pending_conversion"
    CONVERTING = "converting"
    CONVERTED = "converted"
    CONVERSION_FAILED = "conversion_failed"


FILE_TERMINAL_STATUSES: frozenset[FileStatus] = frozenset(
    {
        FileStatus.CONVERTED,
        FileStatus.CONVERSION_FAILED,
    }
)


class FileMetadata(BaseResource, table=True):
    """SQLModel for uploaded file metadata.

    Files are first-class entities with their own lifecycle,
    independent of invocations. This model stores metadata about
    uploaded files while the actual content is stored on the filesystem.

    Storage Strategy:
        - Original file bytes stored on filesystem via BaseRetriever
        - Converted text content stored on filesystem via BaseRetriever
        - Only paths stored in database (protects against DB bloat)

    Security Note:
        file_path and converted_content_path contain internal filesystem paths
        and should NEVER be exposed in API responses. Use file_id (the UUID
        primary key inherited from BaseResource) for public references.

    Attributes:
        id: UUID primary key (inherited from BaseResource, used as file_id)
        filename: Sanitize filename from original filename from upload
        mime_type: Detected MIME type of the file
        size_bytes: File size in bytes
        file_path: Internal storage path (pattern: orchestrator-{file_id}-{filename})
        converted_content_path: Path to converted markdown (optional)
        status: Conversion lifecycle status
        conversion_error: Error message if conversion failed
        created_at: Timestamp when file was uploaded (inherited from BaseResource)
        updated_at: Timestamp when metadata was last updated (inherited from BaseResource)
        labels: Key-value pairs for metadata (inherited from BaseResource)

    """

    __tablename__ = "file_metadata"

    # Project isolation
    project_id: UUID = Field(
        foreign_key="projects.id",
        description="Project namespace for resource isolation",
        index=True,
    )

    # File identification
    filename: str = Field(
        max_length=255,
        description="Original filename from upload",
        index=True,
    )
    mime_type: str = Field(
        max_length=100,
        description="Detected MIME type of the file",
    )
    size_bytes: int = Field(
        ge=0,
        description="File size in bytes",
    )

    # Storage paths (internal only - not exposed in API)
    file_path: str = Field(
        max_length=500,
        description="Internal storage path: orchestrator-{file_id}-{filename}",
    )
    converted_content_path: str | None = Field(
        default=None,
        max_length=500,
        description="Path to converted markdown: orchestrator-{file_id}-content.md",
    )

    # Integrity
    content_hash: str | None = Field(
        default=None,
        max_length=128,
        description="SHA-256 hash of file content, computed on upload",
    )

    # Conversion status
    status: FileStatus = Field(
        default=FileStatus.PENDING_CONVERSION,
        description="Conversion lifecycle status",
        index=True,
    )
    conversion_error: str | None = Field(
        default=None,
        description="Error message if conversion failed",
    )

    # Extend filterable and sortable fields from BaseResource
    __filterable_fields__: ClassVar[list[str]] = [
        *BaseResource.__filterable_fields__,
        "filename",
        "mime_type",
        "status",
        "project_id",
    ]

    __sortable_fields__: ClassVar[list[str]] = [
        *BaseResource.__sortable_fields__,
        "filename",
        "size_bytes",
        "project_id",
    ]

    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,
        validate_by_name=True,
        validate_assignment=True,
        extra="forbid",
    )


__all__ = [
    "FileMetadata",
    "FileStatus",
]
