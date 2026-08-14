"""Unit tests for file integrity verification."""

import hashlib
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from syntara.files.exceptions import FileContentNotFoundError, FileIntegrityError
from syntara.files.file_manager import FileManager
from syntara.files.models import FileMetadata, FileStatus


async def _fake_stream(chunks: list[bytes]) -> AsyncGenerator[bytes]:
    for chunk in chunks:
        yield chunk


class TestStreamFileWithIntegrityCheck:
    """Test FileManager.stream_file_with_integrity_check()."""

    @pytest.mark.asyncio
    async def test_streaming_integrity_check_passes(self) -> None:
        """Test that matching hash yields all chunks."""
        chunks = [b"hello ", b"world"]
        full_content = b"".join(chunks)
        content_hash = hashlib.sha256(full_content).hexdigest()

        metadata = FileMetadata(
            id=uuid4(),
            filename="valid.txt",
            mime_type="text/plain",
            size_bytes=len(full_content),
            file_path="/storage/valid.txt",
            content_hash=content_hash,
            status=FileStatus.CONVERTED,
        )

        fm = FileManager()
        mock_retriever = AsyncMock()
        mock_retriever.stream_file = Mock(return_value=_fake_stream(chunks))
        fm._retriever = mock_retriever

        result = b""
        async for chunk in fm.stream_file_with_integrity_check(metadata):
            result += chunk
        assert result == full_content

    @pytest.mark.asyncio
    async def test_streaming_integrity_check_fails_on_mismatch(self) -> None:
        """Test that hash mismatch withholds the last chunk and raises.

        With the buffer-last-chunk approach, the generator yields all chunks
        except the final one before verifying the hash.  On mismatch the
        last chunk is never yielded, making the response shorter than
        Content-Length so the client detects the failure.
        """
        original_content = b"original content"
        tampered_chunks = [b"tampered ", b"content"]
        content_hash = hashlib.sha256(original_content).hexdigest()

        metadata = FileMetadata(
            id=uuid4(),
            filename="tampered.txt",
            mime_type="text/plain",
            size_bytes=len(original_content),
            file_path="/storage/tampered.txt",
            content_hash=content_hash,
            status=FileStatus.CONVERTED,
        )

        fm = FileManager()
        mock_retriever = AsyncMock()
        mock_retriever.stream_file = Mock(return_value=_fake_stream(tampered_chunks))
        fm._retriever = mock_retriever

        received = b""
        with pytest.raises(FileIntegrityError, match="integrity check failed"):
            async for chunk in fm.stream_file_with_integrity_check(metadata):
                received += chunk

        # Only the first chunk was yielded; the last was withheld
        assert received == b"tampered "
        assert received != b"tampered content"

    @pytest.mark.asyncio
    async def test_streaming_integrity_skipped_when_no_hash(self) -> None:
        """Test that files without content_hash skip verification."""
        chunks = [b"legacy ", b"file"]
        full_content = b"".join(chunks)

        metadata = FileMetadata(
            id=uuid4(),
            filename="legacy.txt",
            mime_type="text/plain",
            size_bytes=len(full_content),
            file_path="/storage/legacy.txt",
            content_hash=None,
            status=FileStatus.CONVERTED,
        )

        fm = FileManager()
        mock_retriever = AsyncMock()
        mock_retriever.stream_file = Mock(return_value=_fake_stream(chunks))
        fm._retriever = mock_retriever

        result = b""
        async for chunk in fm.stream_file_with_integrity_check(metadata):
            result += chunk
        assert result == full_content

    @pytest.mark.asyncio
    async def test_streaming_file_not_found_propagates(self) -> None:
        """Test that FileContentNotFoundError from retriever propagates through streaming."""
        metadata = FileMetadata(
            id=uuid4(),
            filename="missing.txt",
            mime_type="text/plain",
            size_bytes=100,
            file_path="/storage/missing.txt",
            status=FileStatus.CONVERTED,
        )

        async def _error_stream() -> AsyncGenerator[bytes]:
            msg = "File not found: /storage/missing.txt"
            raise FileContentNotFoundError(msg)
            yield b""  # type: ignore[unreachable]  # required so Python treats this as an async generator

        fm = FileManager()
        mock_retriever = AsyncMock()
        mock_retriever.stream_file = Mock(return_value=_error_stream())
        fm._retriever = mock_retriever

        with pytest.raises(FileContentNotFoundError):
            async for _ in fm.stream_file_with_integrity_check(metadata):
                pass
