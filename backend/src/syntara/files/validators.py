"""File validation logic for file uploads.

This module provides validation functions for file uploads including:
- File count validation
- File size validation
- MIME type validation
"""

import os
from typing import Protocol, cast

import magic
import structlog
from fastapi import UploadFile

from syntara.core.config.base import Settings
from syntara.core.constants import MIME_TYPE_DETECTION_MIN_BYTES
from syntara.files.exceptions import FileValidationError

logger = structlog.stdlib.get_logger(__name__)


class SeekableFile(Protocol):
    """Protocol for files that support async seek/tell operations.

    This protocol defines the interface for file-like objects that support
    seeking to positions and getting the current position. UploadFile implements
    this interface at runtime but doesn't have type stubs for these methods.
    """

    async def seek(self, offset: int, whence: int = 0) -> int:
        """Seek to a position in the file."""
        ...

    def tell(self) -> int:
        """Get current file position."""
        ...

    async def read(self, size: int = -1) -> bytes:
        """Read bytes from the file."""
        ...


async def get_file_size(file: UploadFile) -> int:
    """Get file size without loading entire file into memory.

    Uses efficient methods to determine file size:
    - For regular files: uses os.fstat() on file descriptor
    - Fallback: seeks to end and gets position

    Args:
        file: Uploaded file to check

    Returns:
        File size in bytes

    """
    # Try to use fstat for efficiency (works for regular files)
    if hasattr(file.file, "fileno"):
        try:
            file_no = file.file.fileno()
            # Ensure we got a valid file descriptor (int), not a Mock or other object
            if isinstance(file_no, int):
                return os.fstat(file_no).st_size
        except (AttributeError, OSError, TypeError):
            pass

    # Fallback: seek to end to get size
    # UploadFile implements SeekableFile protocol at runtime
    try:
        seekable = cast("SeekableFile", file)
        await seekable.seek(0, 2)  # SEEK_END
        size = seekable.tell()
        await seekable.seek(0)  # Reset to beginning

        # Ensure we got a valid int (for test compatibility with mocks)
        if isinstance(size, int):
            return size
    except (AttributeError, TypeError):
        pass

    # Last resort: read the file to get size (for compatibility with mocks in tests)
    # This is the fallback path when file doesn't support seek/tell or tell() returns non-int
    seekable_for_read = cast("SeekableFile", file)
    content = await seekable_for_read.read()
    await seekable_for_read.seek(0)  # Reset to beginning
    return len(content)


async def validate_file_count(
    files: list[UploadFile],
    max_files: int,
) -> None:
    """Validate that file count does not exceed maximum.

    Args:
        files: List of uploaded files
        max_files: Maximum allowed number of files

    Raises:
        FileValidationError: If file count exceeds maximum

    """
    if len(files) > max_files:
        msg = f"Too many files uploaded. Maximum allowed is {max_files} files, but received {len(files)} files."
        logger.warning(msg)
        raise FileValidationError(msg)


async def validate_file_size(
    file: UploadFile,
    max_size_mb: int,
) -> None:
    """Validate file size without loading entire file into memory.

    Args:
        file: Uploaded file to validate
        max_size_mb: Maximum allowed file size in megabytes

    Raises:
        FileValidationError: If file is empty or exceeds maximum size

    """
    # Get file size efficiently without reading into memory
    file_size_bytes = await get_file_size(file)
    filename = file.filename or "unknown"

    # Reject empty files
    if file_size_bytes == 0:
        msg = f"File '{filename}' is empty (0 bytes). Empty files are not allowed."
        logger.warning(msg)
        raise FileValidationError(msg)

    # Check maximum size
    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size_bytes > max_size_bytes:
        file_size_mb = file_size_bytes / (1024 * 1024)
        msg = (
            f"File '{filename}' is too large. Maximum allowed size is {max_size_mb}MB, "
            f"but file is {file_size_mb:.2f}MB."
        )
        logger.warning(msg)
        raise FileValidationError(msg)


def validate_mime_type_from_bytes(
    file_content: bytes,
    filename: str,
    allowed_mime_types: list[str],
) -> str:
    """Validate file MIME type using python-magic.

    Args:
        file_content: File content as bytes
        filename: Original filename (for error messages)
        allowed_mime_types: List of allowed MIME types

    Returns:
        Detected MIME type string

    Raises:
        FileValidationError: If MIME type is not in allowed list

    Note:
        MIME detection requires sufficient bytes for accuracy. Files smaller
        than MIME_TYPE_DETECTION_MIN_BYTES may have unreliable detection.

    """
    # Warn about small files that may have unreliable MIME detection
    if len(file_content) < MIME_TYPE_DETECTION_MIN_BYTES:
        logger.warning(
            "Small file may cause MIME detection issues. Detection requires sufficient bytes for reliability.",
            filename=filename,
            file_size_bytes=len(file_content),
            required_min_bytes=MIME_TYPE_DETECTION_MIN_BYTES,
        )

    # Detect MIME type using python-magic
    mime_type = str(magic.from_buffer(file_content, mime=True))

    if mime_type not in allowed_mime_types:
        msg = (
            f"Unsupported file format for '{filename}'. "
            f"Detected MIME type '{mime_type}' is not supported. "
            f"Supported formats: {', '.join(allowed_mime_types)}."
        )
        logger.warning(msg)
        raise FileValidationError(msg)

    logger.debug(
        "MIME type validated",
        filename=filename,
        mime_type=mime_type,
    )

    return mime_type


_MIME_HEADER_SIZE = 8192  # 8 KB — enough for reliable MIME detection


async def validate_single_file(
    file: UploadFile,
    settings: Settings,
) -> tuple[bytes, str]:
    """Validate a single file and return header bytes with detected MIME type.

    Validates size without buffering, then reads only the first 8 KB for
    MIME type detection.  The caller is responsible for streaming the
    remainder of the file content.

    Args:
        file: Uploaded file to validate
        settings: Application settings with validation limits

    Returns:
        Tuple of (header_bytes, mime_type).  header_bytes contains at most
        8 KB — enough for MIME detection.  The UploadFile position is left
        at the end of the header; callers should continue reading from
        that position for the remaining content.

    Raises:
        FileValidationError: If size or MIME type validation fails

    """
    await validate_file_size(file, settings.file_upload_max_size_mb)

    header = await file.read(_MIME_HEADER_SIZE)
    filename = file.filename or "unknown"

    mime_type = validate_mime_type_from_bytes(
        header,
        filename,
        settings.file_upload_allowed_mime_types,
    )

    return header, mime_type
