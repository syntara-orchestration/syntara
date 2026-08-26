"""Unit tests for DELETE /files/{file_id} and orphan project marker."""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from syntara.core.exceptions import SafeValueError
from syntara.files.models import FileMetadata, FileStatus
from syntara.files.router import delete_file, get_file_details


def _make_metadata(*, project_id=None) -> FileMetadata:
    return FileMetadata(
        id=uuid4(),
        filename="test.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        file_path="file-abc-test.pdf",
        status=FileStatus.CONVERTED,
        project_id=project_id or uuid4(),
    )


class TestDeleteFileEndpoint:
    """Test DELETE /files/{file_id} business logic."""

    @pytest.mark.asyncio
    async def test_delete_file_success(self) -> None:
        metadata = _make_metadata()
        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=metadata)
        mock_file_manager.delete_file = AsyncMock(return_value=metadata)
        mock_db = AsyncMock()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "syntara.files.router.AuditEventDispatcher.dispatch",
                Mock(),
            )
            await delete_file(
                file_id=metadata.id,
                db=mock_db,
                file_manager=mock_file_manager,
            )

        mock_file_manager.delete_file.assert_awaited_once_with(metadata.id, mock_db)

    @pytest.mark.asyncio
    async def test_delete_file_not_found(self) -> None:
        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=None)
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await delete_file(
                file_id=uuid4(),
                db=mock_db,
                file_manager=mock_file_manager,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        mock_file_manager.delete_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_file_race_returns_404(self) -> None:
        metadata = _make_metadata()
        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=metadata)
        mock_file_manager.delete_file = AsyncMock(side_effect=SafeValueError("File not found"))
        mock_db = AsyncMock()

        with (
            pytest.MonkeyPatch.context() as mp,
            pytest.raises(HTTPException) as exc_info,
        ):
            mp.setattr("syntara.files.router.AuditEventDispatcher.dispatch", Mock())
            await delete_file(
                file_id=metadata.id,
                db=mock_db,
                file_manager=mock_file_manager,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


class TestFileDetailOrphanMarker:
    """Test is_project_deleted on GET /files/{file_id}."""

    @pytest.mark.asyncio
    async def test_get_file_details_includes_orphan_marker(self) -> None:
        file_id = uuid4()
        project_id = uuid4()
        metadata = FileMetadata(
            id=file_id,
            filename="report.pdf",
            mime_type="application/pdf",
            size_bytes=524288,
            file_path="/storage/file-abc-report.pdf",
            status=FileStatus.CONVERTED,
            project_id=project_id,
        )

        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=metadata)
        mock_file_manager.is_project_deleted = AsyncMock(return_value=True)
        mock_db = AsyncMock()

        response = await get_file_details(
            file_id=file_id,
            db=mock_db,
            file_manager=mock_file_manager,
        )

        assert response.is_project_deleted is True
        mock_file_manager.is_project_deleted.assert_awaited_once_with(project_id, mock_db)
