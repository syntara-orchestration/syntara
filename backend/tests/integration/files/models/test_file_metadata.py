"""Integration tests for FileMetadata SQLModel.

This file contains comprehensive tests for the FileMetadata model, covering both
ORM (database) usage and Pydantic (schema validation) usage.

Tests cover:
- Database operations (creation, queries)
- FileStatus enum handling
- Field validation and constraints
- Inheritance from BaseResource (id, created_at, updated_at)
"""

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.files.models import FileMetadata, FileStatus


@pytest.mark.asyncio
async def test_file_metadata_create_with_defaults(test_db_session: AsyncSession, test_project_id: str) -> None:
    """Test creating FileMetadata with required fields and default values."""
    file_metadata = FileMetadata(
        filename="document.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        file_path="/storage/orchestrator-abc123-document.pdf",
        project_id=test_project_id,
    )

    test_db_session.add(file_metadata)
    await test_db_session.commit()

    # Verify required fields
    assert file_metadata.id is not None
    assert isinstance(file_metadata.id, UUID)
    assert file_metadata.filename == "document.pdf"
    assert file_metadata.mime_type == "application/pdf"
    assert file_metadata.size_bytes == 1024
    assert file_metadata.file_path == "/storage/orchestrator-abc123-document.pdf"

    # Verify default values
    assert file_metadata.status == FileStatus.PENDING_CONVERSION
    assert file_metadata.converted_content_path is None
    assert file_metadata.conversion_error is None

    # Verify BaseResource fields (auto-generated)
    assert file_metadata.created_at is not None
    assert file_metadata.updated_at is not None
    assert isinstance(file_metadata.created_at, datetime)
    assert isinstance(file_metadata.updated_at, datetime)


@pytest.mark.asyncio
async def test_file_metadata_status_enum_values(test_db_session: AsyncSession, test_project_id: str) -> None:
    """Test FileStatus enum has all expected values."""
    # Verify all expected enum values exist
    assert FileStatus.PENDING_CONVERSION.value == "pending_conversion"
    assert FileStatus.CONVERTING.value == "converting"
    assert FileStatus.CONVERTED.value == "converted"
    assert FileStatus.CONVERSION_FAILED.value == "conversion_failed"

    # Test creating FileMetadata with each status
    for status in FileStatus:
        file_metadata = FileMetadata(
            filename=f"file_{status.value}.txt",
            mime_type="text/plain",
            size_bytes=100,
            file_path=f"/storage/orchestrator-{status.value}-file.txt",
            status=status,
            project_id=test_project_id,
        )
        test_db_session.add(file_metadata)
        await test_db_session.commit()

        assert file_metadata.status == status


@pytest.mark.asyncio
async def test_file_metadata_validates_required_fields(test_db_session: AsyncSession) -> None:
    """Test that required fields are enforced via validation."""
    from pydantic import ValidationError as PydanticValidationError

    # SQLModel with validate_assignment=True raises ValidationError
    # when trying to set a required field to None
    file_metadata = FileMetadata(
        filename="test.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        file_path="/storage/file.pdf",
        project_id=uuid4(),
    )

    # Trying to set a required field to None should raise validation error
    with pytest.raises(PydanticValidationError):
        file_metadata.filename = None  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_file_metadata_inherits_base_resource_fields(test_db_session: AsyncSession, test_project_id: str) -> None:
    """Test that FileMetadata inherits id, created_at, updated_at from BaseResource."""
    file_metadata = FileMetadata(
        filename="test.txt",
        mime_type="text/plain",
        size_bytes=256,
        file_path="/storage/orchestrator-test-test.txt",
        project_id=test_project_id,
    )

    test_db_session.add(file_metadata)
    await test_db_session.commit()

    # id should be auto-generated UUID
    assert file_metadata.id is not None
    assert isinstance(file_metadata.id, UUID)

    # Timestamps should be set automatically
    assert file_metadata.created_at is not None
    assert file_metadata.updated_at is not None

    # Timestamps should have timezone info (UTC)
    assert file_metadata.created_at.tzinfo is not None
    assert file_metadata.updated_at.tzinfo is not None


@pytest.mark.asyncio
async def test_file_metadata_with_converted_content(test_db_session: AsyncSession, test_project_id: str) -> None:
    """Test FileMetadata with converted content path set."""
    file_metadata = FileMetadata(
        filename="document.pdf",
        mime_type="application/pdf",
        size_bytes=2048,
        file_path="/storage/orchestrator-abc123-document.pdf",
        converted_content_path="/storage/orchestrator-abc123-content.md",
        status=FileStatus.CONVERTED,
        project_id=test_project_id,
    )

    test_db_session.add(file_metadata)
    await test_db_session.commit()

    assert file_metadata.status == FileStatus.CONVERTED
    assert file_metadata.converted_content_path == "/storage/orchestrator-abc123-content.md"
    assert file_metadata.conversion_error is None


@pytest.mark.asyncio
async def test_file_metadata_with_conversion_error(test_db_session: AsyncSession, test_project_id: str) -> None:
    """Test FileMetadata with conversion failure and error message."""
    error_message = "Failed to parse PDF: corrupted file"

    file_metadata = FileMetadata(
        filename="corrupted.pdf",
        mime_type="application/pdf",
        size_bytes=512,
        file_path="/storage/orchestrator-xyz789-corrupted.pdf",
        status=FileStatus.CONVERSION_FAILED,
        conversion_error=error_message,
        project_id=test_project_id,
    )

    test_db_session.add(file_metadata)
    await test_db_session.commit()

    assert file_metadata.status == FileStatus.CONVERSION_FAILED
    assert file_metadata.conversion_error == error_message
    assert file_metadata.converted_content_path is None


@pytest.mark.asyncio
async def test_file_metadata_size_bytes_must_be_non_negative(test_db_session: AsyncSession) -> None:
    """Test that size_bytes field must be non-negative (ge=0)."""
    project_id = uuid4()
    with pytest.raises((ValueError, TypeError)):
        FileMetadata(
            filename="test.txt",
            mime_type="text/plain",
            size_bytes=-1,  # Negative size should fail
            file_path="/storage/test.txt",
            project_id=project_id,
        )


@pytest.mark.asyncio
async def test_file_metadata_update_status(test_db_session: AsyncSession, test_project_id: str) -> None:
    """Test updating FileMetadata status after creation."""
    # Create with pending status
    file_metadata = FileMetadata(
        filename="processing.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size_bytes=4096,
        file_path="/storage/orchestrator-proc123-processing.docx",
        status=FileStatus.PENDING_CONVERSION,
        project_id=test_project_id,
    )

    test_db_session.add(file_metadata)
    await test_db_session.commit()

    # Update to converting
    file_metadata.status = FileStatus.CONVERTING
    await test_db_session.commit()

    assert file_metadata.status == FileStatus.CONVERTING

    # Update to converted with content path
    file_metadata.status = FileStatus.CONVERTED
    file_metadata.converted_content_path = "/storage/orchestrator-proc123-content.md"
    await test_db_session.commit()

    assert file_metadata.status == FileStatus.CONVERTED
    assert file_metadata.converted_content_path == "/storage/orchestrator-proc123-content.md"


@pytest.mark.asyncio
async def test_file_metadata_content_hash_nullable(test_db_session: AsyncSession, test_project_id: str) -> None:
    """Test that content_hash defaults to None and accepts a SHA-256 value."""
    file_metadata = FileMetadata(
        filename="test.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        file_path="/storage/orchestrator-abc-test.pdf",
        project_id=test_project_id,
    )
    test_db_session.add(file_metadata)
    await test_db_session.commit()

    assert file_metadata.content_hash is None

    sha256 = "a" * 64
    file_metadata.content_hash = sha256
    await test_db_session.commit()
    assert file_metadata.content_hash == sha256


@pytest.mark.asyncio
async def test_file_metadata_create_with_content_hash(test_db_session: AsyncSession, test_project_id: str) -> None:
    """Test creating FileMetadata with content_hash set."""
    sha256 = "b" * 64

    file_metadata = FileMetadata(
        filename="report.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size_bytes=4096,
        file_path="orchestrator-xyz-report.docx",
        content_hash=sha256,
        project_id=test_project_id,
    )
    test_db_session.add(file_metadata)
    await test_db_session.commit()

    assert file_metadata.content_hash == sha256
