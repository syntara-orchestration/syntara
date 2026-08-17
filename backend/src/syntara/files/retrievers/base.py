"""Abstract base retriever for file management.

This module defines the abstract interface for file retrievers, enabling
support for multiple storage backends (local filesystem, cloud storage, etc.).
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

_DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1 MB


class BaseRetriever(ABC):
    """Abstract base class for file retrieval operations.

    This class defines the interface that all file retrievers must implement,
    enabling a pluggable storage architecture that can support local filesystem,
    cloud storage (S3, Google Cloud Storage), or other backends.

    Future implementations might include:
    - GoogleDocsRetriever: Retrieve files from Google Drive
    - DropboxRetriever: Retrieve files from Dropbox
    - AtlassianRetriever: Retrieve files from Confluence/Jira
    """

    @abstractmethod
    async def save_file(
        self,
        file_content: bytes,
        file_path: str,
    ) -> str:
        """Save file content to storage backend.

        Args:
            file_content: Raw file content as bytes
            file_path: Destination path for the file (format depends on backend:
                       relative path for local storage, key for cloud storage)

        Returns:
            Storage-specific identifier for the saved file (S3 object key).

            This identifier is stored in FileMetadata.file_path and used internally
            for file retrieval operations. It is NOT exposed in API responses.

        Raises:
            OSError: If save operation fails (disk full, I/O error)
            PermissionError: If insufficient permissions to write to destination

        Note:
            Implementations should ensure idempotent behavior where possible.
            If the file already exists at the destination, it should be overwritten
            to maintain consistency in retry scenarios.

        """

    @abstractmethod
    async def load_file(self, file_path: str) -> bytes:
        """Load file content from storage location.

        Args:
            file_path: Storage-specific identifier for the file
                      (e.g., absolute path for local storage, s3:// URL for S3)

        Returns:
            Raw file content as bytes

        Raises:
            FileNotFoundError: If file does not exist at the specified path
            OSError: If file cannot be read due to I/O errors
            PermissionError: If insufficient permissions to read the file

        """

    @abstractmethod
    async def stream_file(self, file_path: str, chunk_size: int = _DEFAULT_CHUNK_SIZE) -> AsyncGenerator[bytes]:
        """Stream file content from storage in fixed-size chunks.

        Implementations must yield file content in chunks of at most
        *chunk_size* bytes with constant memory usage.

        Args:
            file_path: Storage-specific identifier for the file
            chunk_size: Maximum bytes per yielded chunk

        Yields:
            File content in chunks of at most *chunk_size* bytes.

        Raises:
            FileNotFoundError: If file does not exist at the specified path
            OSError: If file cannot be read due to I/O errors

        """
        yield b""  # pragma: no cover

    @abstractmethod
    async def save_file_stream(
        self,
        stream: AsyncIterator[bytes],
        file_path: str,
    ) -> tuple[str, int]:
        """Save file content from an async stream to storage.

        Reads chunks from *stream* and writes them to the backend without
        buffering the full file in memory.

        Args:
            stream: Async generator yielding file content chunks
            file_path: Destination path / key for the file

        Returns:
            Tuple of (storage path, total bytes written).

        Raises:
            OSError: If save operation fails
            PermissionError: If insufficient permissions to write

        """

    @abstractmethod
    async def file_exists(self, file_path: str) -> bool:
        """Check if file exists at storage location.

        Args:
            file_path: Storage-specific identifier for the file

        Returns:
            True if file exists, False otherwise

        Note:
            This method should not raise exceptions for normal "file not found"
            conditions. Only raise exceptions for actual errors (permission issues,
            network failures for cloud storage, etc.).

        """

    @abstractmethod
    async def get_file_metadata(self, file_path: str) -> dict[str, Any]:
        """Get file metadata from storage.

        Args:
            file_path: Storage-specific identifier for the file

        Returns:
            Dictionary containing file metadata with at least:
            - 'size': File size in bytes
            - 'modified': Last modified timestamp (ISO 8601 string)
            - Additional backend-specific metadata may be included

        Raises:
            FileNotFoundError: If file does not exist at the specified path
            OSError: If metadata cannot be retrieved due to I/O errors
            PermissionError: If insufficient permissions to access file metadata

        """

    @abstractmethod
    async def delete_file(self, file_path: str) -> bool:
        """Delete file from storage.

        Args:
            file_path: Storage-specific identifier for the file

        Returns:
            True if file was successfully deleted

        Raises:
            FileNotFoundError: If file does not exist at the specified path
            OSError: If deletion fails due to I/O errors

        """

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the storage backend is reachable and operational.

        Returns:
            True if the backend is healthy, False otherwise.
            Should not raise exceptions — returns False on any failure.

        """
