"""Unit tests for GET /files/{file_id}/download endpoint."""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from syntara.files.exceptions import FileContentNotFoundError, FileIntegrityError
from syntara.files.models import FileMetadata, FileStatus
from syntara.files.router import download_file


def _make_metadata() -> FileMetadata:
    """Create a FileMetadata for testing."""
    return FileMetadata(
        id=uuid4(),
        filename="test.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        file_path="nexus-abc-test.pdf",
        status=FileStatus.CONVERTED,
    )


class TestDownloadEndpoint:
    """Test file download endpoint business logic."""

    @pytest.mark.asyncio
    async def test_download_file_success(self) -> None:
        """Test successful file download returns streaming response."""
        file_id = uuid4()
        file_content = b"file content bytes"

        metadata = FileMetadata(
            id=file_id,
            filename="report.pdf",
            mime_type="application/pdf",
            size_bytes=len(file_content),
            file_path="/storage/nexus-abc-report.pdf",
            status=FileStatus.CONVERTED,
        )

        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=metadata)
        mock_file_manager.load_file_with_integrity_check = AsyncMock(return_value=file_content)

        mock_db = AsyncMock()

        response = await download_file(
            file_id=file_id,
            db=mock_db,
            file_manager=mock_file_manager,
        )

        assert response.media_type == "application/pdf"
        assert response.headers["content-disposition"] == 'attachment; filename="report.pdf"'

        body = b""
        async for chunk in response.body_iterator:
            body += chunk if isinstance(chunk, bytes) else str(chunk).encode()
        assert body == file_content

    @pytest.mark.asyncio
    async def test_download_file_not_found_in_db(self) -> None:
        """Test 404 when file_id doesn't exist in database."""
        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=None)
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await download_file(
                file_id=uuid4(),
                db=mock_db,
                file_manager=mock_file_manager,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_download_file_not_found_in_storage(self) -> None:
        """Test FileNotFoundError propagates when file exists in DB but not in storage."""
        metadata = _make_metadata()

        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=metadata)
        mock_file_manager.load_file_with_integrity_check = AsyncMock(
            side_effect=FileContentNotFoundError("File not found"),
        )

        mock_db = AsyncMock()

        with pytest.raises(FileContentNotFoundError):
            await download_file(file_id=metadata.id, db=mock_db, file_manager=mock_file_manager)

    @pytest.mark.asyncio
    async def test_download_file_integrity_failure(self) -> None:
        """Test FileIntegrityError propagates when integrity check fails."""
        metadata = _make_metadata()

        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=metadata)
        mock_file_manager.load_file_with_integrity_check = AsyncMock(
            side_effect=FileIntegrityError("integrity check failed"),
        )

        mock_db = AsyncMock()

        with pytest.raises(FileIntegrityError):
            await download_file(file_id=metadata.id, db=mock_db, file_manager=mock_file_manager)

    @pytest.mark.asyncio
    async def test_download_calls_integrity_check(self) -> None:
        """Test that download uses load_file_with_integrity_check."""
        metadata = _make_metadata()

        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=metadata)
        mock_file_manager.load_file_with_integrity_check = AsyncMock(return_value=b"hello")

        mock_db = AsyncMock()

        await download_file(file_id=metadata.id, db=mock_db, file_manager=mock_file_manager)

        mock_file_manager.load_file_with_integrity_check.assert_called_once_with(metadata)
