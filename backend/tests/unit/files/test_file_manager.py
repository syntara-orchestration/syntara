"""Unit tests for FileManager.

Tests validate S3-only file management: upload, integrity check,
metadata queries, status updates, and graceful degradation when
S3 is not configured.
"""

import asyncio
import hashlib
from collections.abc import Callable
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


@pytest.mark.asyncio
async def test_validate_and_save_files_success() -> None:
    """Test successful file save via mocked S3 retriever."""
    file_content = b"PDF content"
    mock_file = Mock()
    mock_file.filename = "test.pdf"
    mock_file.size = len(file_content)
    mock_file.content_type = "application/pdf"
    mock_file.read = AsyncMock(return_value=file_content)
    mock_file.seek = AsyncMock()

    fm = FileManager()
    mock_retriever = AsyncMock()
    mock_retriever.save_file = AsyncMock(return_value="nexus-uuid-test.pdf")
    fm._retriever = mock_retriever

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
    mock_file = Mock()
    mock_file.filename = "test.pdf"
    mock_file.size = 100
    mock_file.content_type = "application/pdf"
    mock_file.read = AsyncMock(return_value=b"content")
    mock_file.seek = AsyncMock()

    fm = FileManager()
    project_id = uuid4()
    with pytest.raises(FileStorageUnavailableError, match="File storage is not configured"):
        await fm.validate_and_save_files([mock_file], project_id=project_id)


@pytest.mark.asyncio
async def test_upload_sets_content_hash() -> None:
    """Upload populates content_hash with SHA-256."""
    file_content = b"hash me"
    mock_file = Mock()
    mock_file.filename = "hash_test.txt"
    mock_file.size = len(file_content)
    mock_file.content_type = "text/plain"
    mock_file.read = AsyncMock(return_value=file_content)
    mock_file.seek = AsyncMock()

    fm = FileManager()
    mock_retriever = AsyncMock()
    mock_retriever.save_file = AsyncMock(return_value="nexus-uuid-hash_test.txt")
    fm._retriever = mock_retriever

    result = await fm.validate_and_save_files([mock_file], project_id=uuid4())
    metadata = result[0]

    expected_hash = hashlib.sha256(file_content).hexdigest()
    assert metadata.content_hash == expected_hash


@pytest.mark.asyncio
async def test_multiple_files_saved_successfully() -> None:
    """Multiple files processed correctly with unique paths."""
    mock_files = []
    for i in range(3):
        mock_file = Mock()
        mock_file.filename = f"file{i}.pdf"
        mock_file.size = 1024 * (i + 1)
        mock_file.content_type = "application/pdf"
        mock_file.read = AsyncMock(return_value=f"content{i}".encode())
        mock_file.seek = AsyncMock()
        mock_files.append(mock_file)

    fm = FileManager()
    call_count = 0

    async def unique_save(content: bytes, path: str) -> str:
        nonlocal call_count
        call_count += 1
        return f"nexus-{call_count}-file.pdf"

    mock_retriever = AsyncMock()
    mock_retriever.save_file = AsyncMock(side_effect=unique_save)
    fm._retriever = mock_retriever

    result = await fm.validate_and_save_files(cast("list[UploadFile]", mock_files), project_id=uuid4())

    assert len(result) == 3
    assert all(m.status == FileStatus.PENDING_CONVERSION for m in result)


@pytest.mark.asyncio
async def test_storage_failure_cleans_up_saved_files() -> None:
    """Storage failure on second file cleans up first file."""
    files = []
    for i in range(2):
        mock_file = Mock()
        mock_file.filename = f"file{i}.pdf"
        mock_file.size = 100
        mock_file.content_type = "application/pdf"
        mock_file.read = AsyncMock(return_value=f"content{i}".encode())
        mock_file.seek = AsyncMock()
        files.append(mock_file)

    fm = FileManager()
    call_count = 0

    async def fail_on_second(content: bytes, path: str) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            msg = "Disk full"
            raise OSError(msg)
        return "nexus-1-file0.pdf"

    mock_retriever = AsyncMock()
    mock_retriever.save_file = AsyncMock(side_effect=fail_on_second)
    mock_retriever.delete_file = AsyncMock()
    fm._retriever = mock_retriever

    project_id = uuid4()
    with pytest.raises(OSError, match="Disk full"):
        await fm.validate_and_save_files(cast("list[UploadFile]", files), project_id=project_id)

    mock_retriever.delete_file.assert_called_once_with("nexus-1-file0.pdf")


@pytest.mark.asyncio
async def test_file_upload_events_logged() -> None:
    """File upload events are logged with metadata."""
    mock_file = Mock()
    mock_file.filename = "logged.pdf"
    mock_file.size = 1024
    mock_file.content_type = "application/pdf"
    mock_file.read = AsyncMock(return_value=b"content")
    mock_file.seek = AsyncMock()

    with patch("syntara.files.file_manager.logger") as mock_logger:
        fm = FileManager()
        mock_retriever = AsyncMock()
        mock_retriever.save_file = AsyncMock(return_value="nexus-uuid-logged.pdf")
        fm._retriever = mock_retriever

        await fm.validate_and_save_files([mock_file], project_id=uuid4())

        assert mock_logger.info.called


@pytest.mark.asyncio
async def test_async_io_used_for_file_operations() -> None:
    """File operations complete without blocking."""
    mock_file = Mock()
    mock_file.filename = "async_test.pdf"
    mock_file.size = 512
    mock_file.content_type = "application/pdf"
    mock_file.read = AsyncMock(return_value=b"async content")
    mock_file.seek = AsyncMock()

    fm = FileManager()
    mock_retriever = AsyncMock()
    mock_retriever.save_file = AsyncMock(return_value="nexus-uuid-async_test.pdf")
    fm._retriever = mock_retriever

    result = await asyncio.wait_for(fm.validate_and_save_files([mock_file], project_id=uuid4()), timeout=5.0)
    assert len(result) == 1


# =============================================================================
# load_file_with_integrity_check
# =============================================================================


@pytest.mark.asyncio
async def test_load_file_with_integrity_check_success() -> None:
    """Successful load with matching content hash."""
    file_content = b"integrity check content"
    content_hash = hashlib.sha256(file_content).hexdigest()

    fm = FileManager()
    mock_retriever = AsyncMock()
    mock_retriever.load_file = AsyncMock(return_value=file_content)
    fm._retriever = mock_retriever

    mock_metadata = Mock()
    mock_metadata.file_path = "nexus-uuid-integrity-check.txt"
    mock_metadata.content_hash = content_hash
    mock_metadata.id = "test-id"
    mock_metadata.filename = "integrity-check.txt"

    result = await fm.load_file_with_integrity_check(mock_metadata)
    assert result == file_content


@pytest.mark.asyncio
async def test_load_file_with_integrity_check_no_hash() -> None:
    """Load skips integrity check when content_hash is None (legacy files)."""
    file_content = b"legacy file"

    fm = FileManager()
    mock_retriever = AsyncMock()
    mock_retriever.load_file = AsyncMock(return_value=file_content)
    fm._retriever = mock_retriever

    mock_metadata = Mock()
    mock_metadata.file_path = "nexus-uuid-legacy.txt"
    mock_metadata.content_hash = None

    result = await fm.load_file_with_integrity_check(mock_metadata)
    assert result == file_content


@pytest.mark.asyncio
async def test_load_file_with_integrity_check_hash_mismatch() -> None:
    """Load raises FileIntegrityError when hash doesn't match."""
    from syntara.files.exceptions import FileIntegrityError

    file_content = b"tampered content"

    fm = FileManager()
    mock_retriever = AsyncMock()
    mock_retriever.load_file = AsyncMock(return_value=file_content)
    fm._retriever = mock_retriever

    mock_metadata = Mock()
    mock_metadata.file_path = "nexus-uuid-tampered.txt"
    mock_metadata.content_hash = "0" * 64
    mock_metadata.id = "test-id"
    mock_metadata.filename = "tampered.txt"

    with pytest.raises(FileIntegrityError, match="File integrity check failed"):
        await fm.load_file_with_integrity_check(mock_metadata)


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

    mock_file = Mock()
    mock_file.filename = "empty.pdf"
    mock_file.size = 0
    mock_file.content_type = "application/pdf"
    mock_file.read = AsyncMock(return_value=b"")
    mock_file.seek = AsyncMock()

    with (
        patch("syntara.files.file_manager.AuditEventDispatcher.dispatch") as mock_dispatch,
        patch(
            "syntara.files.file_manager.validators.validate_files",
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
    mock_file = Mock()
    mock_file.filename = "audit.txt"
    mock_file.size = len(file_content)
    mock_file.content_type = "text/plain"
    mock_file.read = AsyncMock(return_value=file_content)
    mock_file.seek = AsyncMock()

    fm = FileManager()
    mock_retriever = AsyncMock()
    mock_retriever.save_file = AsyncMock(return_value="nexus-uuid-audit.txt")
    fm._retriever = mock_retriever

    with patch("syntara.files.file_manager.AuditEventDispatcher.dispatch") as mock_dispatch:
        await fm.validate_and_save_files([mock_file], project_id=uuid4())

        # The success audit event has file_details with storage_backend
        calls = mock_dispatch.call_args_list
        success_event = calls[-1][0][0]  # last call, first positional arg
        assert success_event.file_details[0]["storage_backend"] == "s3"
