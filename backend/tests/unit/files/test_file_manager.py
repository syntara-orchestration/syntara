"""Unit tests for FileManager.

Tests validate S3-only file management: upload, integrity check,
metadata queries, status updates, and graceful degradation when
S3 is not configured.
"""

import asyncio
import hashlib
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from fastapi import UploadFile

from syntara.core.exceptions import SafeValueError
from syntara.files.exceptions import FileStorageUnavailableError
from syntara.files.file_manager import FileManager
from syntara.files.models import FileMetadata, FileStatus

# =============================================================================
# S3 configuration and graceful degradation
# =============================================================================


def test_file_manager_unconfigured_when_no_s3_env() -> None:
    """FileManager initializes without a retriever when S3 is not configured."""
    fm = FileManager()
    assert fm.s3_configured is False
    assert fm._retriever is None


def test_file_manager_configured_when_s3_set(
    override_settings: Callable[..., AbstractContextManager[object]],
) -> None:
    """FileManager registers S3 retriever when endpoint is configured."""
    with override_settings(
        s3_endpoint_url="http://localhost:9000",
        s3_bucket_name="test-bucket",
    ):
        fm = FileManager()
        assert fm.s3_configured is True
        assert fm._retriever is not None


def test_get_retriever_raises_when_unconfigured() -> None:
    """get_retriever() raises FileStorageUnavailableError (503) when S3 is not configured."""
    fm = FileManager()
    with pytest.raises(FileStorageUnavailableError, match="File storage is not configured"):
        fm.get_retriever()


# =============================================================================
# validate_and_save_files
# =============================================================================


async def _consuming_save(stream: AsyncGenerator[bytes], path: str) -> tuple[str, int]:
    """Mock save_file_stream that consumes the stream to drive the hasher."""
    total = 0
    async for chunk in stream:
        total += len(chunk)
    return f"orchestrator-uuid-{path}", total


def _make_mock_file(filename: str, content: bytes) -> Mock:
    """Create a mock UploadFile that supports streaming reads.

    The mock returns content on the first read() call (header), then
    remaining content on the second call, then b"" on subsequent calls
    — matching how the streaming upload reads files.
    """
    mock_file = Mock()
    mock_file.filename = filename
    mock_file.size = len(content)
    mock_file.content_type = "application/pdf"

    read_position = 0

    async def _read(size: int = -1) -> bytes:
        nonlocal read_position
        if size == -1:
            chunk = content[read_position:]
            read_position = len(content)
        else:
            chunk = content[read_position : read_position + size]
            read_position += len(chunk)
        return chunk

    mock_file.read = _read
    mock_file.seek = AsyncMock()
    mock_file.file = Mock()
    mock_file.file.fileno = Mock(side_effect=OSError)
    return mock_file


@pytest.mark.asyncio
async def test_validate_and_save_files_success() -> None:
    """Test successful file save via streaming to mocked S3 retriever."""
    file_content = b"PDF content here"
    mock_file = _make_mock_file("test.pdf", file_content)

    fm = FileManager()
    mock_retriever = AsyncMock()
    mock_retriever.save_file_stream = AsyncMock(side_effect=_consuming_save)
    fm._retriever = mock_retriever

    with patch(
        "syntara.files.file_manager.validators.validate_single_file",
        new_callable=AsyncMock,
        return_value=(b"", "application/pdf"),
    ):
        result = await fm.validate_and_save_files([mock_file], project_id=uuid4())

    assert len(result) == 1
    metadata = result[0]
    assert metadata.filename == "test.pdf"
    assert metadata.size_bytes == len(file_content)
    assert metadata.status == FileStatus.PENDING_CONVERSION
    assert metadata.content_hash is not None
    assert len(metadata.content_hash) == 64


@pytest.mark.asyncio
async def test_validate_and_save_raises_when_unconfigured() -> None:
    """File upload raises FileStorageUnavailableError (503) when S3 is not configured."""
    mock_file = _make_mock_file("test.pdf", b"content")

    fm = FileManager()
    project_id = uuid4()
    with pytest.raises(FileStorageUnavailableError, match="File storage is not configured"):
        await fm.validate_and_save_files([mock_file], project_id=project_id)


@pytest.mark.asyncio
async def test_upload_sets_content_hash() -> None:
    """Upload populates content_hash with SHA-256 computed incrementally."""
    file_content = b"hash me"
    mock_file = _make_mock_file("hash_test.txt", file_content)

    fm = FileManager()
    mock_retriever = AsyncMock()
    mock_retriever.save_file_stream = AsyncMock(side_effect=_consuming_save)
    fm._retriever = mock_retriever

    with patch(
        "syntara.files.file_manager.validators.validate_single_file",
        new_callable=AsyncMock,
        return_value=(b"", "text/plain"),
    ):
        result = await fm.validate_and_save_files([mock_file], project_id=uuid4())

    metadata = result[0]
    expected_hash = hashlib.sha256(file_content).hexdigest()
    assert metadata.content_hash == expected_hash


@pytest.mark.asyncio
async def test_multiple_files_saved_successfully() -> None:
    """Multiple files processed correctly with unique paths."""
    mock_files = []
    for i in range(3):
        mock_files.append(_make_mock_file(f"file{i}.pdf", f"content{i}".encode()))

    fm = FileManager()
    call_count = 0

    async def unique_save(stream: AsyncGenerator[bytes], path: str) -> tuple[str, int]:
        nonlocal call_count
        call_count += 1
        total = 0
        async for _chunk in stream:
            total += len(_chunk)
        return f"orchestrator-{call_count}-file.pdf", total

    mock_retriever = AsyncMock()
    mock_retriever.save_file_stream = AsyncMock(side_effect=unique_save)
    fm._retriever = mock_retriever

    with patch(
        "syntara.files.file_manager.validators.validate_single_file",
        new_callable=AsyncMock,
        side_effect=[(b"", "application/pdf")] * 3,
    ):
        result = await fm.validate_and_save_files(cast("list[UploadFile]", mock_files), project_id=uuid4())

    assert len(result) == 3
    assert all(m.status == FileStatus.PENDING_CONVERSION for m in result)


@pytest.mark.asyncio
async def test_storage_failure_cleans_up_saved_files() -> None:
    """Storage failure on second file cleans up first file."""
    files = [_make_mock_file(f"file{i}.pdf", f"content{i}".encode()) for i in range(2)]

    fm = FileManager()
    call_count = 0

    async def fail_on_second(stream: AsyncGenerator[bytes], path: str) -> tuple[str, int]:
        nonlocal call_count
        call_count += 1
        async for _chunk in stream:
            pass
        if call_count == 2:
            msg = "Disk full"
            raise OSError(msg)
        return "orchestrator-1-file0.pdf", 8

    mock_retriever = AsyncMock()
    mock_retriever.save_file_stream = AsyncMock(side_effect=fail_on_second)
    mock_retriever.delete_file = AsyncMock()
    fm._retriever = mock_retriever

    project_id = uuid4()
    with (
        patch(
            "syntara.files.file_manager.validators.validate_single_file",
            new_callable=AsyncMock,
            side_effect=[(b"", "application/pdf")] * 2,
        ),
        pytest.raises(OSError, match="Disk full"),
    ):
        await fm.validate_and_save_files(cast("list[UploadFile]", files), project_id=project_id)

    mock_retriever.delete_file.assert_called_once_with("orchestrator-1-file0.pdf")


@pytest.mark.asyncio
async def test_validation_failure_cleans_up_saved_files() -> None:
    """Validation failure on second file cleans up first file from S3."""
    from syntara.files.exceptions import FileValidationError

    files = [_make_mock_file(f"file{i}.pdf", f"content{i}".encode()) for i in range(2)]

    fm = FileManager()
    mock_retriever = AsyncMock()
    mock_retriever.save_file_stream = AsyncMock(side_effect=_consuming_save)
    mock_retriever.delete_file = AsyncMock()
    fm._retriever = mock_retriever

    call_count = 0

    async def _pass_then_fail(file: object, settings: object) -> tuple[bytes, str]:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            msg = "Bad MIME type"
            raise FileValidationError(msg)
        return b"", "application/pdf"

    project_id = uuid4()
    with (
        patch(
            "syntara.files.file_manager.validators.validate_single_file",
            new_callable=AsyncMock,
            side_effect=_pass_then_fail,
        ),
        pytest.raises(FileValidationError),
    ):
        await fm.validate_and_save_files(cast("list[UploadFile]", files), project_id=project_id)

    mock_retriever.delete_file.assert_called_once()


@pytest.mark.asyncio
async def test_cancelled_error_cleans_up_saved_files() -> None:
    """CancelledError during file 2 cleans up file 1 from S3.

    asyncio.CancelledError is a BaseException, not Exception, so it
    bypasses the except (OSError, FileError) handler.  The finally
    block must still delete already-saved objects.
    """
    import asyncio

    files = [_make_mock_file(f"file{i}.pdf", f"content{i}".encode()) for i in range(2)]

    fm = FileManager()
    call_count = 0

    async def cancel_on_second(stream: AsyncGenerator[bytes], path: str) -> tuple[str, int]:
        nonlocal call_count
        call_count += 1
        async for _chunk in stream:
            pass
        if call_count == 2:
            raise asyncio.CancelledError
        return "orchestrator-1-file0.pdf", 8

    mock_retriever = AsyncMock()
    mock_retriever.save_file_stream = AsyncMock(side_effect=cancel_on_second)
    mock_retriever.delete_file = AsyncMock()
    fm._retriever = mock_retriever

    project_id = uuid4()
    with (
        patch(
            "syntara.files.file_manager.validators.validate_single_file",
            new_callable=AsyncMock,
            side_effect=[(b"", "application/pdf")] * 2,
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await fm.validate_and_save_files(cast("list[UploadFile]", files), project_id=project_id)

    mock_retriever.delete_file.assert_called_once_with("orchestrator-1-file0.pdf")


@pytest.mark.asyncio
async def test_file_upload_events_logged() -> None:
    """File upload events are logged with metadata."""
    mock_file = _make_mock_file("logged.pdf", b"content")

    with patch("syntara.files.file_manager.logger") as mock_logger:
        fm = FileManager()
        mock_retriever = AsyncMock()
        mock_retriever.save_file_stream = AsyncMock(side_effect=_consuming_save)
        fm._retriever = mock_retriever

        with patch(
            "syntara.files.file_manager.validators.validate_single_file",
            new_callable=AsyncMock,
            return_value=(b"", "application/pdf"),
        ):
            await fm.validate_and_save_files([mock_file], project_id=uuid4())

        assert mock_logger.info.called


@pytest.mark.asyncio
async def test_async_io_used_for_file_operations() -> None:
    """File operations complete without blocking."""
    mock_file = _make_mock_file("async_test.pdf", b"async content")

    fm = FileManager()
    mock_retriever = AsyncMock()
    mock_retriever.save_file_stream = AsyncMock(side_effect=_consuming_save)
    fm._retriever = mock_retriever

    with patch(
        "syntara.files.file_manager.validators.validate_single_file",
        new_callable=AsyncMock,
        return_value=(b"", "application/pdf"),
    ):
        result = await asyncio.wait_for(fm.validate_and_save_files([mock_file], project_id=uuid4()), timeout=5.0)
    assert len(result) == 1


# =============================================================================
# get_file_metadata (DB query) tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_file_metadata_returns_result() -> None:
    """get_file_metadata delegates to session.get."""
    from uuid import uuid4

    fm = FileManager()
    file_id = uuid4()

    mock_session = AsyncMock()
    mock_file = Mock()
    mock_session.get.return_value = mock_file

    result = await fm.get_file_metadata(file_id, mock_session)
    assert result is mock_file
    mock_session.get.assert_called_once_with(FileMetadata, file_id)


@pytest.mark.asyncio
async def test_get_file_metadata_returns_none_when_not_found() -> None:
    """get_file_metadata returns None for missing file."""
    from uuid import uuid4

    fm = FileManager()
    file_id = uuid4()

    mock_session = AsyncMock()
    mock_session.get.return_value = None

    result = await fm.get_file_metadata(file_id, mock_session)
    assert result is None


# =============================================================================
# get_files_metadata tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_files_metadata_empty_list() -> None:
    """get_files_metadata returns empty list for empty input."""
    fm = FileManager()
    mock_session = AsyncMock()

    result = await fm.get_files_metadata([], mock_session)
    assert result == []
    mock_session.exec.assert_not_called()


@pytest.mark.asyncio
async def test_get_files_metadata_with_ids() -> None:
    """get_files_metadata queries database with file IDs."""
    from uuid import uuid4

    fm = FileManager()
    file_ids = [uuid4(), uuid4()]

    mock_file1 = Mock()
    mock_file2 = Mock()

    mock_result = Mock()
    mock_result.all.return_value = [mock_file1, mock_file2]
    mock_session = AsyncMock()
    mock_session.exec.return_value = mock_result

    result = await fm.get_files_metadata(file_ids, mock_session)
    assert len(result) == 2
    assert result[0] is mock_file1
    assert result[1] is mock_file2
    mock_session.exec.assert_called_once()


# =============================================================================
# update_file_status tests
# =============================================================================


@pytest.mark.asyncio
async def test_update_file_status_success() -> None:
    """update_file_status updates status and commits."""
    from uuid import uuid4

    fm = FileManager()
    file_id = uuid4()

    mock_file = Mock()
    mock_file.status = FileStatus.PENDING_CONVERSION
    mock_file.converted_content_path = None
    mock_file.conversion_error = None

    mock_session = AsyncMock()
    mock_session.get.return_value = mock_file
    mock_session.add = Mock()

    result = await fm.update_file_status(
        file_id,
        FileStatus.CONVERTED,
        mock_session,
        converted_content_path="/path/to/content.md",
    )

    assert result is mock_file
    assert mock_file.status == FileStatus.CONVERTED
    assert mock_file.converted_content_path == "/path/to/content.md"
    mock_session.add.assert_called_once_with(mock_file)
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_file_status_with_error() -> None:
    """update_file_status sets conversion_error on failure."""
    from uuid import uuid4

    fm = FileManager()
    file_id = uuid4()

    mock_file = Mock()
    mock_file.status = FileStatus.CONVERTING

    mock_session = AsyncMock()
    mock_session.get.return_value = mock_file
    mock_session.add = Mock()

    result = await fm.update_file_status(
        file_id,
        FileStatus.CONVERSION_FAILED,
        mock_session,
        conversion_error="Conversion timeout",
    )

    assert result is mock_file
    assert mock_file.status == FileStatus.CONVERSION_FAILED
    assert mock_file.conversion_error == "Conversion timeout"


@pytest.mark.asyncio
async def test_update_file_status_not_found_raises() -> None:
    """update_file_status raises SafeValueError when file not found."""
    from uuid import uuid4

    fm = FileManager()
    file_id = uuid4()

    mock_session = AsyncMock()
    mock_session.get.return_value = None

    with pytest.raises(SafeValueError, match="File not found"):
        await fm.update_file_status(file_id, FileStatus.CONVERTED, mock_session)


# =============================================================================
# get_file_manager factory tests
# =============================================================================


def test_get_file_manager_returns_singleton() -> None:
    """get_file_manager returns a FileManager instance."""
    from syntara.files.file_manager import get_file_manager

    fm = get_file_manager()
    assert isinstance(fm, FileManager)


def test_get_file_manager_returns_same_instance() -> None:
    """get_file_manager returns the same cached instance."""
    from syntara.files.file_manager import get_file_manager

    fm1 = get_file_manager()
    fm2 = get_file_manager()
    assert fm1 is fm2


# =============================================================================
# validate_and_save_files — audit dispatch
# =============================================================================


@pytest.mark.asyncio
async def test_validate_and_save_files_validation_error_dispatches_audit() -> None:
    """Validation errors dispatch an audit event before raising."""
    from syntara.files.exceptions import FileValidationError

    fm = FileManager()
    mock_retriever = AsyncMock()
    fm._retriever = mock_retriever

    mock_file = _make_mock_file("empty.pdf", b"")

    with (
        patch("syntara.files.file_manager.AuditEventDispatcher.dispatch") as mock_dispatch,
        patch(
            "syntara.files.file_manager.validators.validate_single_file",
            new_callable=AsyncMock,
            side_effect=FileValidationError("File too small"),
        ),
    ):
        with pytest.raises(FileValidationError):
            await fm.validate_and_save_files([mock_file], project_id=uuid4())

        mock_dispatch.assert_called_once()


@pytest.mark.asyncio
async def test_audit_event_storage_backend_is_s3() -> None:
    """Audit event file_details includes storage_backend='s3'."""
    file_content = b"audit test"
    mock_file = _make_mock_file("audit.txt", file_content)

    fm = FileManager()
    mock_retriever = AsyncMock()
    mock_retriever.save_file_stream = AsyncMock(side_effect=_consuming_save)
    fm._retriever = mock_retriever

    with (
        patch("syntara.files.file_manager.AuditEventDispatcher.dispatch") as mock_dispatch,
        patch(
            "syntara.files.file_manager.validators.validate_single_file",
            new_callable=AsyncMock,
            return_value=(b"", "text/plain"),
        ),
    ):
        await fm.validate_and_save_files([mock_file], project_id=uuid4())

        calls = mock_dispatch.call_args_list
        success_event = calls[-1][0][0]
        assert success_event.file_details[0]["storage_backend"] == "s3"
