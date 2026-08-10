"""Unit tests for FileManager file count validation.

These tests validate:
- FileManager raises FileValidationError when file count exceeds limit (10 files default)
- Error message includes actual count and max count
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from fastapi import UploadFile

from syntara.files.exceptions import FileValidationError
from syntara.files.file_manager import FileManager


@pytest.mark.asyncio
async def test_rejects_files_exceeding_count_limit() -> None:
    """Test that FileManager raises FileValidationError for too many files.

    Validates:
    - Raises FileValidationError when count > max_files
    - Default limit is 10 files
    """
    # Arrange - 11 files (exceeds default limit of 10)
    mock_files = []
    for i in range(11):
        mock_file = Mock()
        mock_file.filename = f"file{i}.pdf"
        mock_file.size = 1024
        mock_file.content_type = "application/pdf"
        mock_file.read = AsyncMock(return_value=b"content")
        mock_files.append(mock_file)

    file_manager = FileManager()

    # Act & Assert
    with pytest.raises(FileValidationError) as exc_info:
        await file_manager.validate_and_save_files(cast("list[UploadFile]", mock_files), project_id=uuid4())

    # Error message should mention too many files
    error_message = str(exc_info.value)
    assert "Too many files" in error_message


@pytest.mark.asyncio
async def test_error_message_includes_actual_and_max_count() -> None:
    """Test that error message includes actual count and max count.

    Validates:
    - Error message is actionable
    - Includes both actual and maximum allowed counts
    """
    # Arrange - 15 files
    mock_files = []
    for i in range(15):
        mock_file = Mock()
        mock_file.filename = f"file{i}.pdf"
        mock_file.size = 512
        mock_file.content_type = "application/pdf"
        mock_file.read = AsyncMock(return_value=b"content")
        mock_files.append(mock_file)

    file_manager = FileManager()

    # Act & Assert
    with pytest.raises(FileValidationError) as exc_info:
        await file_manager.validate_and_save_files(cast("list[UploadFile]", mock_files), project_id=uuid4())

    error_message = str(exc_info.value)
    # Should mention both 15 (actual) and 10 (max)
    assert "15" in error_message
    assert "10" in error_message


@pytest.mark.asyncio
async def test_accepts_files_at_exact_limit() -> None:
    """Test that exactly max_files count is accepted.

    Validates:
    - 10 files (at limit) succeeds
    - Boundary condition handled correctly
    """
    # Arrange - Exactly 10 files
    mock_files = []
    for i in range(10):
        mock_file = Mock()
        mock_file.filename = f"file{i}.pdf"
        mock_file.size = 1024
        mock_file.content_type = "application/pdf"
        mock_file.read = AsyncMock(return_value=b"content")
        mock_file.seek = AsyncMock()
        mock_files.append(mock_file)

    file_manager = FileManager()

    # Act
    result = await file_manager.validate_and_save_files(cast("list[UploadFile]", mock_files), project_id=uuid4())

    # Assert
    assert len(result) == 10


@pytest.mark.asyncio
async def test_accepts_files_below_limit() -> None:
    """Test that file count below limit is accepted.

    Validates:
    - Fewer files than limit succeeds
    - No validation error for valid count
    """
    # Arrange - 5 files (below limit)
    mock_files = []
    for i in range(5):
        mock_file = Mock()
        mock_file.filename = f"file{i}.pdf"
        mock_file.size = 1024
        mock_file.content_type = "application/pdf"
        mock_file.read = AsyncMock(return_value=b"content")
        mock_file.seek = AsyncMock()
        mock_files.append(mock_file)

    file_manager = FileManager()

    # Act
    result = await file_manager.validate_and_save_files(cast("list[UploadFile]", mock_files), project_id=uuid4())

    # Assert
    assert len(result) == 5


@pytest.mark.asyncio
async def test_configurable_max_files_limit(
    override_settings: Callable[..., AbstractContextManager[object]],
) -> None:
    """Test that max_files limit is configurable.

    Validates:
    - Custom limit can be set
    - Validation uses configured limit
    """
    # Arrange - 6 files with custom limit of 5
    mock_files = []
    for i in range(6):
        mock_file = Mock()
        mock_file.filename = f"file{i}.pdf"
        mock_file.size = 1024
        mock_file.content_type = "application/pdf"
        mock_file.read = AsyncMock(return_value=b"content")
        mock_files.append(mock_file)

    with override_settings(file_upload_max_files=5):
        file_manager = FileManager()

        # Act & Assert
        with pytest.raises(FileValidationError) as exc_info:
            await file_manager.validate_and_save_files(cast("list[UploadFile]", mock_files), project_id=uuid4())

        # Should validate against custom limit (5)
        error_message = str(exc_info.value)
        assert "5" in error_message
        assert "6" in error_message


@pytest.mark.asyncio
async def test_single_file_accepted() -> None:
    """Test that single file upload is accepted.

    Validates:
    - Minimum case (1 file) works
    """
    # Arrange - 1 file
    mock_file = Mock()
    mock_file.filename = "single.pdf"
    mock_file.size = 1024
    mock_file.content_type = "application/pdf"
    mock_file.read = AsyncMock(return_value=b"content")
    mock_file.seek = AsyncMock()

    file_manager = FileManager()

    # Act
    result = await file_manager.validate_and_save_files([mock_file], project_id=uuid4())

    # Assert
    assert len(result) == 1
