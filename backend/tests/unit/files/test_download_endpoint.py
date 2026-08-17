"""Unit tests for GET /files/{file_id}/download endpoint."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from syntara.files.exceptions import FileContentNotFoundError, FileIntegrityError
from syntara.files.models import FileMetadata, FileStatus
from syntara.files.router import download_file


def _make_metadata(*, size_bytes: int = 100) -> FileMetadata:
    """Create a FileMetadata for testing."""
    return FileMetadata(
        id=uuid4(),
        filename="test.pdf",
        mime_type="application/pdf",
        size_bytes=size_bytes,
        file_path="orchestrator-abc-test.pdf",
        status=FileStatus.CONVERTED,
    )


async def _async_gen(chunks: list[bytes]) -> AsyncGenerator[bytes]:
    for chunk in chunks:
        yield chunk


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
            file_path="/storage/orchestrator-abc-report.pdf",
            status=FileStatus.CONVERTED,
        )

        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=metadata)
        mock_file_manager.stream_file_with_integrity_check = Mock(
            return_value=_async_gen([file_content]),
        )

        mock_db = AsyncMock()

        response = await download_file(
            file_id=file_id,
            db=mock_db,
            file_manager=mock_file_manager,
        )

        assert response.media_type == "application/pdf"
        assert response.headers["content-disposition"] == 'attachment; filename="report.pdf"'
        assert response.headers["content-length"] == str(len(file_content))

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
    async def test_download_calls_streaming_integrity_check(self) -> None:
        """Test that download uses stream_file_with_integrity_check."""
        metadata = _make_metadata()

        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=metadata)
        mock_file_manager.stream_file_with_integrity_check = Mock(
            return_value=_async_gen([b"hello"]),
        )

        mock_db = AsyncMock()

        response = await download_file(file_id=metadata.id, db=mock_db, file_manager=mock_file_manager)
        assert response.headers["content-length"] == str(metadata.size_bytes)

        async for _ in response.body_iterator:
            pass

        mock_file_manager.stream_file_with_integrity_check.assert_called_once_with(metadata)

    @pytest.mark.asyncio
    async def test_download_streams_multiple_chunks(self) -> None:
        """Test that multiple chunks from the stream are concatenated in the response."""
        chunks = [b"chunk1", b"chunk2", b"chunk3"]
        total_size = sum(len(c) for c in chunks)
        metadata = _make_metadata(size_bytes=total_size)

        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=metadata)
        mock_file_manager.stream_file_with_integrity_check = Mock(
            return_value=_async_gen(chunks),
        )
        mock_db = AsyncMock()

        response = await download_file(file_id=metadata.id, db=mock_db, file_manager=mock_file_manager)

        body = b""
        async for chunk in response.body_iterator:
            body += chunk if isinstance(chunk, bytes) else str(chunk).encode()
        assert body == b"chunk1chunk2chunk3"

    @pytest.mark.asyncio
    async def test_download_dispatches_audit_event(self) -> None:
        """Test that a FileDownloadedEvent is dispatched after streaming completes."""
        file_content = b"audit test"
        metadata = _make_metadata(size_bytes=len(file_content))

        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=metadata)
        mock_file_manager.stream_file_with_integrity_check = Mock(
            return_value=_async_gen([file_content]),
        )
        mock_db = AsyncMock()

        response = await download_file(file_id=metadata.id, db=mock_db, file_manager=mock_file_manager)

        with patch("syntara.files.router.AuditEventDispatcher.dispatch") as mock_dispatch:
            async for _ in response.body_iterator:
                pass

            mock_dispatch.assert_called_once()
            event = mock_dispatch.call_args[0][0]
            assert event.file_id == metadata.id
            assert event.filename == metadata.filename
            assert event.error_type is None

    @pytest.mark.asyncio
    async def test_download_file_not_found_in_storage(self) -> None:
        """Test FileContentNotFoundError propagates when consuming the stream."""
        metadata = _make_metadata()

        async def _error_stream() -> AsyncGenerator[bytes]:
            msg = "File not found"
            raise FileContentNotFoundError(msg)
            yield b""  # type: ignore[unreachable]  # required so Python treats this as an async generator

        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=metadata)
        mock_file_manager.stream_file_with_integrity_check = Mock(
            return_value=_error_stream(),
        )
        mock_db = AsyncMock()

        response = await download_file(file_id=metadata.id, db=mock_db, file_manager=mock_file_manager)

        with pytest.raises(FileContentNotFoundError):
            async for _ in response.body_iterator:
                pass

    @pytest.mark.asyncio
    async def test_download_file_integrity_failure(self) -> None:
        """Test FileIntegrityError propagates when consuming the stream."""
        metadata = _make_metadata()

        async def _error_stream() -> AsyncGenerator[bytes]:
            yield b"partial content"
            msg = "integrity check failed"
            raise FileIntegrityError(msg)

        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=metadata)
        mock_file_manager.stream_file_with_integrity_check = Mock(
            return_value=_error_stream(),
        )
        mock_db = AsyncMock()

        response = await download_file(file_id=metadata.id, db=mock_db, file_manager=mock_file_manager)

        with pytest.raises(FileIntegrityError):
            async for _ in response.body_iterator:
                pass

    @pytest.mark.asyncio
    async def test_download_audit_records_error_type_on_failure(self) -> None:
        """Test that audit event captures error_type when streaming fails."""
        metadata = _make_metadata()

        async def _error_stream() -> AsyncGenerator[bytes]:
            yield b"partial"
            msg = "hash mismatch"
            raise FileIntegrityError(msg)

        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=metadata)
        mock_file_manager.stream_file_with_integrity_check = Mock(
            return_value=_error_stream(),
        )
        mock_db = AsyncMock()

        response = await download_file(file_id=metadata.id, db=mock_db, file_manager=mock_file_manager)

        with patch("syntara.files.router.AuditEventDispatcher.dispatch") as mock_dispatch:
            with pytest.raises(FileIntegrityError):
                async for _ in response.body_iterator:
                    pass

            mock_dispatch.assert_called_once()
            event = mock_dispatch.call_args[0][0]
            assert event.error_type == "FileIntegrityError"

    @pytest.mark.asyncio
    async def test_download_audit_records_incomplete_transfer(self) -> None:
        """Test that incomplete transfer is audited as ClientDisconnect.

        When the stream yields fewer bytes than ``metadata.size_bytes``
        (e.g. because the source stream ended early or the client
        disconnected), the audit wrapper detects it via the
        ``bytes_yielded < size_bytes`` heuristic in ``finally``.
        """
        metadata = _make_metadata(size_bytes=100)

        mock_file_manager = Mock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=metadata)
        mock_file_manager.stream_file_with_integrity_check = Mock(
            return_value=_async_gen([b"partial"]),
        )
        mock_db = AsyncMock()

        response = await download_file(file_id=metadata.id, db=mock_db, file_manager=mock_file_manager)

        with patch("syntara.files.router.AuditEventDispatcher.dispatch") as mock_dispatch:
            async for _ in response.body_iterator:
                pass

            mock_dispatch.assert_called_once()
            event = mock_dispatch.call_args[0][0]
            assert event.error_type == "ClientDisconnect"
