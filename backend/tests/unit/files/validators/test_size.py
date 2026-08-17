"""Unit tests for FileManager file size validation.

These tests validate:
- FileManager raises FileValidationError when any file exceeds size limit (10MB default per file)
- Error message includes actual and max size
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from fastapi import UploadFile

from syntara.files.exceptions import FileValidationError
from syntara.files.file_manager import FileManager

from .conftest import make_upload_mock


@pytest.mark.asyncio
async def test_rejects_file_exceeding_size_limit() -> None:
    """Test that FileManager raises FileValidationError for oversized files.

    Validates:
    - Raises FileValidationError when file size > max_size_mb
    - Default limit is 10MB per file
    """
    # Arrange - 11MB file (exceeds default 10MB limit)
    large_content = b"0" * (11 * 1024 * 1024)  # 11MB
    mock_file = Mock()
    mock_file.filename = "large.pdf"
    mock_file.size = len(large_content)
    mock_file.content_type = "application/pdf"
    mock_file.read = AsyncMock(return_value=large_content)
    mock_file.seek = AsyncMock()

    file_manager = FileManager()

    # Act & Assert
    with pytest.raises(FileValidationError) as exc_info:
        await file_manager.validate_and_save_files([mock_file], project_id=uuid4())

    # Error message should mention file is too large
    error_message = str(exc_info.value)
    assert "too large" in error_message


@pytest.mark.asyncio
async def test_error_message_includes_actual_and_max_size() -> None:
    """Test that error message includes actual size and max size.

    Validates:
    - Error message is actionable
    - Shows file size in bytes and limit
    """
    # Arrange - 15MB file
    size_bytes = 15 * 1024 * 1024  # 15MB
    large_content = b"0" * size_bytes
    mock_file = Mock()
    mock_file.filename = "oversized.pdf"
    mock_file.size = size_bytes
    mock_file.content_type = "application/pdf"
    mock_file.read = AsyncMock(return_value=large_content)
    mock_file.seek = AsyncMock()

    file_manager = FileManager()

    # Act & Assert
    with pytest.raises(FileValidationError) as exc_info:
        await file_manager.validate_and_save_files([mock_file], project_id=uuid4())

    error_message = str(exc_info.value)
    # Should mention actual and max size in MB
    assert "too large" in error_message
    assert "10MB" in error_message  # Max size
    assert "15" in error_message  # Actual size (15.00MB)


@pytest.mark.asyncio
async def test_accepts_file_at_exact_size_limit() -> None:
    """Test that file at exact size limit is accepted.

    Validates:
    - 10MB file (at limit) succeeds
    - Boundary condition handled correctly
    """
    # Arrange - Exactly 10MB
    content = b"0" * (10 * 1024 * 1024)
    mock_file = make_upload_mock("exact_limit.pdf", content)

    with patch("magic.from_buffer") as mock_magic:
        mock_magic.return_value = "application/pdf"

        file_manager = FileManager()

        # Act
        result = await file_manager.validate_and_save_files([mock_file], project_id=uuid4())

        # Assert
        assert len(result) == 1
        assert result[0].size_bytes == len(content)


@pytest.mark.asyncio
async def test_accepts_file_below_size_limit() -> None:
    """Test that file below size limit is accepted.

    Validates:
    - Smaller files pass validation
    - No error for valid sizes
    """
    # Arrange - 5MB file (below limit)
    content = b"0" * (5 * 1024 * 1024)
    mock_file = make_upload_mock("small.pdf", content)

    with patch("magic.from_buffer") as mock_magic:
        mock_magic.return_value = "application/pdf"

        file_manager = FileManager()

        # Act
        result = await file_manager.validate_and_save_files([mock_file], project_id=uuid4())

        # Assert
        assert len(result) == 1
        assert result[0].size_bytes == len(content)


@pytest.mark.asyncio
async def test_validates_each_file_size_independently() -> None:
    """Test that each file is validated independently for size.

    Validates:
    - Multiple files each checked against limit
    - One oversized file fails entire batch
    """
    # Arrange - 2 small files + 1 large file
    # Files 1-2 pass validation and reach streaming — need finite reads
    # File 3 fails size validation before streaming — plain Mock is fine
    mock_files: list[Mock] = [
        make_upload_mock("small1.pdf", b"0" * (1 * 1024 * 1024)),
        make_upload_mock("small2.pdf", b"0" * (2 * 1024 * 1024)),
    ]
    mock_file3 = Mock()
    mock_file3.filename = "large.pdf"
    mock_file3.size = 11 * 1024 * 1024  # 11MB
    mock_file3.content_type = "application/pdf"
    mock_file3.read = AsyncMock(return_value=b"0" * mock_file3.size)
    mock_file3.seek = AsyncMock()
    mock_files.append(mock_file3)

    file_manager = FileManager()

    # Act & Assert
    with pytest.raises(FileValidationError) as exc_info:
        await file_manager.validate_and_save_files(cast("list[UploadFile]", mock_files), project_id=uuid4())

    # Should fail due to large.pdf being too large
    error_message = str(exc_info.value)
    assert "too large" in error_message
    assert "large.pdf" in error_message


@pytest.mark.asyncio
async def test_configurable_max_size_limit(
    override_settings: Callable[..., AbstractContextManager[object]],
) -> None:
    """Test that max_size_mb limit is configurable.

    Validates:
    - Custom size limit can be set
    - Validation uses configured limit
    """
    # Arrange - 6MB file with custom limit of 5MB
    size_bytes = 6 * 1024 * 1024  # 6MB
    content = b"0" * size_bytes
    mock_file = Mock()
    mock_file.filename = "custom_limit_test.pdf"
    mock_file.size = size_bytes
    mock_file.content_type = "application/pdf"
    mock_file.read = AsyncMock(return_value=content)
    mock_file.seek = AsyncMock()

    with override_settings(file_upload_max_size_mb=5):
        file_manager = FileManager()

        # Act & Assert
        with pytest.raises(FileValidationError) as exc_info:
            await file_manager.validate_and_save_files([mock_file], project_id=uuid4())

        # Should validate against custom limit (5MB)
        error_message = str(exc_info.value)
        assert "5" in error_message
        assert "6" in error_message


@pytest.mark.asyncio
async def test_very_small_file_accepted() -> None:
    """Test that very small files are accepted.

    Validates:
    - Minimum file sizes work (1KB)
    """
    # Arrange - 1KB file
    content = b"0" * 1024
    mock_file = make_upload_mock("tiny.txt", content, content_type="text/plain")

    file_manager = FileManager()

    # Act
    result = await file_manager.validate_and_save_files([mock_file], project_id=uuid4())

    # Assert
    assert len(result) == 1
    assert result[0].size_bytes == len(content)
