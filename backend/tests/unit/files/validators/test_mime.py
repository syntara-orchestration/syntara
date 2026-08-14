"""Unit tests for FileManager MIME type validation.

These tests validate:
- FileManager MIME type detection using python-magic for each file
- FileManager raises ValidationError for unsupported formats (e.g., image/png)
- Error message lists supported formats
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from syntara.files.exceptions import FileValidationError

if TYPE_CHECKING:
    from fastapi import UploadFile

from syntara.files.file_manager import FileManager

from .conftest import make_upload_mock


@pytest.mark.asyncio
async def test_validates_mime_type_using_python_magic(
    override_settings: Callable[..., AbstractContextManager[object]],
) -> None:
    """Test that MIME type detection uses python-magic.

    Validates:
    - python-magic is used for MIME detection
    - Content-based detection (not just file extension)
    """
    # Arrange
    mock_file = make_upload_mock("document.pdf", b"PDF content")

    with patch("magic.from_buffer") as mock_magic:
        mock_magic.return_value = "application/pdf"

        with override_settings(file_upload_allowed_mime_types=["application/pdf", "text/plain"]):
            file_manager = FileManager()

            # Act
            result = await file_manager.validate_and_save_files([mock_file], project_id=uuid4())

            # Assert
            # python-magic should have been called
            mock_magic.assert_called()
            assert len(result) == 1


@pytest.mark.asyncio
async def test_rejects_unsupported_mime_types(
    override_settings: Callable[..., AbstractContextManager[object]],
) -> None:
    """Test that unsupported MIME types are rejected.

    Validates:
    - image/png is rejected
    - ValidationError raised for unsupported formats
    """
    # Arrange - PNG image (unsupported)
    mock_file = Mock()
    mock_file.filename = "image.png"
    mock_file.size = 1024
    mock_file.content_type = "image/png"
    mock_file.read = AsyncMock(return_value=b"PNG image data")
    mock_file.seek = AsyncMock()

    with patch("magic.from_buffer") as mock_magic:
        mock_magic.return_value = "image/png"

        with override_settings(
            file_upload_allowed_mime_types=[
                "application/pdf",
                "text/plain",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ]
        ):
            file_manager = FileManager()

            # Act & Assert
            with pytest.raises(FileValidationError) as exc_info:
                await file_manager.validate_and_save_files([mock_file], project_id=uuid4())

            # Error should mention unsupported format and detected MIME type
            error_message = str(exc_info.value)
            assert "Unsupported file format" in error_message
            assert "image/png" in error_message
            assert "Supported formats:" in error_message


@pytest.mark.asyncio
async def test_error_message_lists_supported_formats(
    override_settings: Callable[..., AbstractContextManager[object]],
) -> None:
    """Test that error message lists supported formats.

    Validates:
    - Error message is actionable
    - Shows which formats are supported
    """
    # Arrange - Unsupported format
    mock_file = Mock()
    mock_file.filename = "video.mp4"
    mock_file.size = 1024
    mock_file.content_type = "video/mp4"
    mock_file.read = AsyncMock(return_value=b"video data")
    mock_file.seek = AsyncMock()

    with patch("magic.from_buffer") as mock_magic:
        mock_magic.return_value = "video/mp4"

        with override_settings(file_upload_allowed_mime_types=["application/pdf", "text/plain"]):
            file_manager = FileManager()

            # Act & Assert
            with pytest.raises(FileValidationError) as exc_info:
                await file_manager.validate_and_save_files([mock_file], project_id=uuid4())

            error_message = str(exc_info.value)
            # Should list the supported MIME types
            assert "Unsupported file format" in error_message
            assert "video/mp4" in error_message
            assert "application/pdf" in error_message
            assert "text/plain" in error_message


@pytest.mark.asyncio
async def test_accepts_pdf_mime_type(
    override_settings: Callable[..., AbstractContextManager[object]],
) -> None:
    """Test that application/pdf is accepted.

    Validates:
    - PDF is in allowed MIME types
    - PDF files pass validation
    """
    # Arrange
    mock_file = make_upload_mock("document.pdf", b"PDF content")

    with patch("magic.from_buffer") as mock_magic:
        mock_magic.return_value = "application/pdf"

        with override_settings(file_upload_allowed_mime_types=["application/pdf"]):
            file_manager = FileManager()

            # Act
            result = await file_manager.validate_and_save_files([mock_file], project_id=uuid4())

            # Assert
            assert len(result) == 1
            assert result[0].mime_type == "application/pdf"


@pytest.mark.asyncio
async def test_accepts_docx_mime_type(
    override_settings: Callable[..., AbstractContextManager[object]],
) -> None:
    """Test that DOCX MIME type is accepted.

    Validates:
    - application/vnd.openxmlformats-officedocument.wordprocessingml.document accepted
    """
    # Arrange
    mock_file = make_upload_mock("document.docx", b"DOCX content")

    with patch("magic.from_buffer") as mock_magic:
        mock_magic.return_value = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        with override_settings(
            file_upload_allowed_mime_types=[
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ]
        ):
            file_manager = FileManager()

            # Act
            result = await file_manager.validate_and_save_files([mock_file], project_id=uuid4())

            # Assert
            assert len(result) == 1
            assert "wordprocessing" in result[0].mime_type


@pytest.mark.asyncio
async def test_accepts_text_plain_mime_type(
    override_settings: Callable[..., AbstractContextManager[object]],
) -> None:
    """Test that text/plain is accepted.

    Validates:
    - Plain text files accepted
    - TXT and MD files supported
    """
    # Arrange
    mock_file = make_upload_mock("readme.txt", b"Plain text content", content_type="text/plain")

    with override_settings(file_upload_allowed_mime_types=["text/plain"]):
        file_manager = FileManager()

        # Act
        result = await file_manager.validate_and_save_files([mock_file], project_id=uuid4())

        # Assert
        assert len(result) == 1
        assert result[0].mime_type == "text/plain"


@pytest.mark.asyncio
async def test_validates_mime_type_for_each_file(
    override_settings: Callable[..., AbstractContextManager[object]],
) -> None:
    """Test that MIME type is validated for each file independently.

    Validates:
    - Multiple files each validated
    - One unsupported file fails entire batch
    """
    # Arrange - 2 supported files + 1 unsupported
    # Files 1-2 pass validation and reach streaming — need finite reads
    # File 3 fails MIME validation before streaming — plain Mock is fine
    mock_files: list[Mock] = [
        make_upload_mock("doc.pdf", b"PDF"),
        make_upload_mock("notes.txt", b"text", content_type="text/plain"),
    ]
    mock_file3 = Mock()
    mock_file3.filename = "image.png"
    mock_file3.size = 2048
    mock_file3.content_type = "image/png"
    mock_file3.read = AsyncMock(return_value=b"PNG")
    mock_file3.seek = AsyncMock()
    mock_files.append(mock_file3)

    with patch("magic.from_buffer") as mock_magic:
        # Return different MIME types for different files based on call order
        mock_magic.side_effect = ["text/plain", "text/plain", "image/png"]

        with override_settings(file_upload_allowed_mime_types=["application/pdf", "text/plain"]):
            file_manager = FileManager()

            # Act & Assert
            with pytest.raises(FileValidationError) as exc_info:
                await file_manager.validate_and_save_files(cast("list[UploadFile]", mock_files), project_id=uuid4())

            # Should fail due to image.png with specific error message
            error_message = str(exc_info.value)
            assert "Unsupported file format" in error_message
            assert "image/png" in error_message


@pytest.mark.asyncio
async def test_configurable_allowed_mime_types(
    override_settings: Callable[..., AbstractContextManager[object]],
) -> None:
    """Test that allowed MIME types are configurable.

    Validates:
    - Custom MIME type list can be provided
    - Only configured types accepted
    """
    # Arrange - Only allow PDF
    mock_file = Mock()
    mock_file.filename = "notes.txt"
    mock_file.size = 512
    mock_file.content_type = "text/plain"
    mock_file.read = AsyncMock(return_value=b"text content")
    mock_file.seek = AsyncMock()

    with patch("magic.from_buffer") as mock_magic:
        mock_magic.return_value = "text/plain"

        with override_settings(file_upload_allowed_mime_types=["application/pdf"]):
            file_manager = FileManager()

            # Act & Assert
            with pytest.raises(FileValidationError) as exc_info:
                await file_manager.validate_and_save_files([mock_file], project_id=uuid4())

            # Should reject text/plain and show only PDF is supported
            error_message = str(exc_info.value)
            assert "Unsupported file format" in error_message
            assert "text/plain" in error_message
            assert "application/pdf" in error_message
