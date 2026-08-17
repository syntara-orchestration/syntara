"""File storage operations.

This module provides file storage operations using the retriever pattern
for pluggable storage backends.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import structlog

from syntara.files.retrievers.base import BaseRetriever

logger = structlog.stdlib.get_logger(__name__)


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """Sanitize filename to prevent path traversal and filesystem issues.

    Args:
        filename: Original filename from user upload
        max_length: Maximum allowed filename length (default 200)

    Returns:
        Sanitized filename safe for filesystem storage

    Note:
        Files are saved with pattern: orchestrator-{36-char-uuid}-{filename}
        Total prefix length is ~50 chars, so we limit filename to 200 chars
        to ensure total path stays well under the 255-byte filesystem limit.

    """
    # Remove path components, keep only basename
    safe_name = Path(filename).name

    # Remove dangerous characters, keep only alphanumeric and .-_
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in ".-_")

    # Remove leading/trailing dots, dashes, underscores (filesystem edge cases)
    safe_name = safe_name.strip(".-_")

    # Ensure non-empty after sanitization
    if not safe_name:
        return "unnamed"

    # Enforce length limit (filesystem typically limits to 255 bytes)
    # Extension preservation is nice-to-have but not critical since we validate via MIME type
    if len(safe_name) > max_length:
        safe_name = safe_name[:max_length]

    return safe_name


async def save_file(
    file_content: bytes,
    safe_filename: str,
    file_id: str,
    retriever: BaseRetriever,
) -> str:
    """Save uploaded file to storage using the configured retriever.

    Files are saved with the naming pattern: orchestrator-{file_id}-{sanitized_filename}

    Args:
        file_content: File content as bytes
        safe_filename: Sanitize filename from original filename from upload
        file_id: Unique file identifier (UUID) for file naming
        retriever: Storage retriever to use for saving file

    Returns:
        Absolute path where file was saved

    Raises:
        OSError: If save operation fails (disk full, permission denied)
        PermissionError: If insufficient permissions to write
        IOError: If I/O operation fails

    """
    # Sanitize filename to prevent path traversal
    # Defence-in-depth. Callers may not have sanitized filename.
    safe_filename = sanitize_filename(safe_filename)

    # Generate file path with naming pattern
    file_path = f"orchestrator-{file_id}-{safe_filename}"

    # Save using retriever
    try:
        saved_path = await retriever.save_file(file_content, file_path)

        logger.info(
            "File saved to storage",
            filename=safe_filename,
            file_id=file_id,
            size_bytes=len(file_content),
        )

        return saved_path

    except (OSError, PermissionError):
        # Log detailed error information (not exposed to client)
        logger.exception(
            "Storage failure",
            filename=safe_filename,
            file_id=file_id,
            path=file_path,
            size_bytes=len(file_content),
        )
        # Re-raise for caller to handle
        raise


async def save_file_stream(
    stream: AsyncIterator[bytes],
    safe_filename: str,
    file_id: str,
    retriever: BaseRetriever,
) -> tuple[str, int]:
    """Save uploaded file to storage by streaming chunks.

    Files are saved with the naming pattern: orchestrator-{file_id}-{sanitized_filename}

    Args:
        stream: Async generator yielding file content chunks
        safe_filename: Sanitized filename from original upload
        file_id: Unique file identifier (UUID) for file naming
        retriever: Storage retriever to use for saving file

    Returns:
        Tuple of (saved path, total bytes written)

    """
    safe_filename = sanitize_filename(safe_filename)
    file_path = f"orchestrator-{file_id}-{safe_filename}"

    try:
        saved_path, total_bytes = await retriever.save_file_stream(stream, file_path)

        logger.info(
            "File saved to storage via streaming",
            filename=safe_filename,
            file_id=file_id,
            size_bytes=total_bytes,
        )

        return saved_path, total_bytes

    except (OSError, PermissionError):
        logger.exception(
            "Storage failure during streaming save",
            filename=safe_filename,
            file_id=file_id,
            path=file_path,
        )
        raise
