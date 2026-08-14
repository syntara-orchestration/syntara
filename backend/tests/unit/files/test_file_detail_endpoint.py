"""Unit tests for GET /files/{file_id} endpoint."""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from syntara.files.models import FileMetadata, FileStatus
from syntara.files.router import get_file_details


def _make_metadata(
    *,
    file_status: FileStatus = FileStatus.CONVERTED,
    conversion_error: str | None = None,
) -> FileMetadata:
    """Create a FileMetadata for testing."""
    return FileMetadata(
        id=uuid4(),
        filename="test.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        file_path="orchestrator-abc-test.pdf",
        status=file_status,
        conversion_error=conversion_error,
    )


class TestFileDetailEndpoint:
    """Test file detail endpoint business logic."""

    @pytest.mark.asyncio
    async def test_get_file_details_success(self) -> None:
        """Test successful file detail retrieval."""
        file_id = uuid4()
        metadata = FileMetadata(
            id=file_id,
            filename="report.pdf",
            mime_type="application/pdf",
            size_bytes=524288,
            file_path="/storage/orchestrator-abc-report.pdf",
            status=FileStatus.CONVERTED,
        )

        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=metadata)
        mock_db = AsyncMock()

        response = await get_file_details(
            file_id=file_id,
            db=mock_db,
            file_manager=mock_file_manager,
        )

        assert response.file_id == file_id
        assert response.filename == "report.pdf"
        assert response.mime_type == "application/pdf"
        assert response.size_bytes == 524288
        assert response.status == FileStatus.CONVERTED
        assert response.conversion_error is None

    @pytest.mark.asyncio
    async def test_get_file_details_not_found(self) -> None:
        """Test 404 when file_id doesn't exist."""
        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=None)
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_file_details(
                file_id=uuid4(),
                db=mock_db,
                file_manager=mock_file_manager,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_file_details_includes_conversion_error(self) -> None:
        """Test that conversion_error is included when conversion failed."""
        file_id = uuid4()
        metadata = FileMetadata(
            id=file_id,
            filename="bad.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=1024,
            file_path="/storage/orchestrator-abc-bad.docx",
            status=FileStatus.CONVERSION_FAILED,
            conversion_error="The file appears to be corrupted",
        )

        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=metadata)
        mock_db = AsyncMock()

        response = await get_file_details(
            file_id=file_id,
            db=mock_db,
            file_manager=mock_file_manager,
        )

        assert response.status == FileStatus.CONVERSION_FAILED
        assert response.conversion_error == "The file appears to be corrupted"

    @pytest.mark.asyncio
    async def test_get_file_details_pending_conversion(self) -> None:
        """Test response for a file still pending conversion."""
        file_id = uuid4()
        metadata = FileMetadata(
            id=file_id,
            filename="uploading.pdf",
            mime_type="application/pdf",
            size_bytes=2048,
            file_path="/storage/orchestrator-abc-uploading.pdf",
            status=FileStatus.PENDING_CONVERSION,
        )

        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=metadata)
        mock_db = AsyncMock()

        response = await get_file_details(
            file_id=file_id,
            db=mock_db,
            file_manager=mock_file_manager,
        )

        assert response.status == FileStatus.PENDING_CONVERSION
        assert response.conversion_error is None
