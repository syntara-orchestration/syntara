"""Unit tests for file integrity verification."""

import hashlib
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from syntara.files.exceptions import FileContentNotFoundError, FileIntegrityError
from syntara.files.file_manager import FileManager
from syntara.files.models import FileMetadata, FileStatus


class TestLoadFileWithIntegrityCheck:
    """Test FileManager.load_file_with_integrity_check()."""

    @pytest.mark.asyncio
    async def test_integrity_check_passes(self) -> None:
        """Test that matching hash returns file content."""
        content = b"valid file content"
        content_hash = hashlib.sha256(content).hexdigest()

        metadata = FileMetadata(
            id=uuid4(),
            filename="valid.txt",
            mime_type="text/plain",
            size_bytes=len(content),
            file_path="/storage/valid.txt",
            content_hash=content_hash,
            status=FileStatus.CONVERTED,
        )

        fm = FileManager()
        mock_retriever = AsyncMock()
        mock_retriever.load_file = AsyncMock(return_value=content)
        fm._retriever = mock_retriever

        result = await fm.load_file_with_integrity_check(metadata)
        assert result == content

    @pytest.mark.asyncio
    async def test_integrity_check_fails_on_mismatch(self) -> None:
        """Test that hash mismatch raises FileIntegrityError."""
        original_content = b"original content"
        tampered_content = b"tampered content"
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
        mock_retriever.load_file = AsyncMock(return_value=tampered_content)
        fm._retriever = mock_retriever

        with pytest.raises(FileIntegrityError, match="integrity check failed"):
            await fm.load_file_with_integrity_check(metadata)

    @pytest.mark.asyncio
    async def test_integrity_check_skipped_when_no_hash(self) -> None:
        """Test that files without content_hash skip verification."""
        content = b"legacy file without hash"

        metadata = FileMetadata(
            id=uuid4(),
            filename="legacy.txt",
            mime_type="text/plain",
            size_bytes=len(content),
            file_path="/storage/legacy.txt",
            content_hash=None,
            status=FileStatus.CONVERTED,
        )

        fm = FileManager()
        mock_retriever = AsyncMock()
        mock_retriever.load_file = AsyncMock(return_value=content)
        fm._retriever = mock_retriever

        result = await fm.load_file_with_integrity_check(metadata)
        assert result == content

    @pytest.mark.asyncio
    async def test_file_not_found_propagates(self) -> None:
        """Test that FileContentNotFoundError from retriever propagates."""
        metadata = FileMetadata(
            id=uuid4(),
            filename="missing.txt",
            mime_type="text/plain",
            size_bytes=100,
            file_path="/storage/missing.txt",
            status=FileStatus.CONVERTED,
        )

        fm = FileManager()
        mock_retriever = AsyncMock()
        mock_retriever.load_file = AsyncMock(
            side_effect=FileContentNotFoundError("File not found: /storage/missing.txt"),
        )
        fm._retriever = mock_retriever

        with pytest.raises(FileContentNotFoundError):
            await fm.load_file_with_integrity_check(metadata)
