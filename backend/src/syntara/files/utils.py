"""Utility functions for file manager operations."""

from pathlib import Path

import structlog

logger = structlog.stdlib.get_logger(__name__)


async def cleanup_files(file_paths: list[str], context: str = "") -> None:
    """Cleanup files from storage (best effort).

    This function attempts to delete files from the filesystem without
    raising exceptions. It's used for cleanup after errors or cancellations.

    Args:
        file_paths: List of absolute file paths to delete
        context: Optional context string for logging (e.g., "after validation failure")

    """
    for file_path in file_paths:
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                context_msg = f" {context}" if context else ""
                logger.info("Cleaned up file", context=context_msg, file_path=file_path)
        except Exception:
            # Don't fail cleanup if individual file deletion fails
            logger.exception("Failed to cleanup file", file_path=file_path)
