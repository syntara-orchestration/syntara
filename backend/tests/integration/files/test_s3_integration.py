"""Integration tests for S3FileRetriever -- end-to-end storage workflows.

Uses moto mock_aws for a realistic S3-compatible backend without
requiring a running MinIO or AWS endpoint.
"""

from __future__ import annotations

import hashlib
import os
from typing import TYPE_CHECKING

import boto3
import pytest
from moto import mock_aws

if TYPE_CHECKING:
    from collections.abc import Generator

from syntara.files.exceptions import FileContentNotFoundError
from syntara.files.retrievers.s3 import S3FileRetriever

BUCKET = "orchestrator-integration-test"
REGION = "us-east-1"


@pytest.fixture(autouse=True)
def _aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


@pytest.fixture
def s3_retriever() -> Generator[S3FileRetriever, None, None]:
    with mock_aws():
        conn = boto3.client("s3", region_name=REGION)
        conn.create_bucket(Bucket=BUCKET)
        retriever = S3FileRetriever(
            endpoint_url=None,
            bucket_name=BUCKET,
            region_name=REGION,
        )
        yield retriever


class TestUploadDownloadRoundTrip:
    """Verify content survives a full save -> load cycle."""

    @pytest.mark.asyncio
    async def test_small_file_round_trip(self, s3_retriever: S3FileRetriever) -> None:
        """Save 1 KB file, load it back, verify byte-for-byte match."""
        content = os.urandom(1024)
        key = "integration/small-file.bin"

        stored_key = await s3_retriever.save_file(content, key)
        assert stored_key == key

        loaded = await s3_retriever.load_file(key)
        assert loaded == content

    @pytest.mark.asyncio
    async def test_large_file_multipart_round_trip(self, s3_retriever: S3FileRetriever) -> None:
        """Save 6 MB file (above 5 MB multipart threshold), verify content and SHA-256."""
        content = os.urandom(6 * 1024 * 1024)
        expected_hash = hashlib.sha256(content).hexdigest()
        key = "integration/large-multipart.bin"

        stored_key = await s3_retriever.save_file(content, key)
        assert stored_key == key

        loaded = await s3_retriever.load_file(key)
        assert loaded == content
        assert hashlib.sha256(loaded).hexdigest() == expected_hash

    @pytest.mark.asyncio
    async def test_binary_content_preserved(self, s3_retriever: S3FileRetriever) -> None:
        """Save random binary content, load back, verify exact match."""
        content = os.urandom(2048)
        key = "integration/binary-blob.dat"

        await s3_retriever.save_file(content, key)
        loaded = await s3_retriever.load_file(key)
        assert loaded == content

    @pytest.mark.asyncio
    async def test_unicode_filename_key(self, s3_retriever: S3FileRetriever) -> None:
        """Save with a key containing unicode chars, load back successfully."""
        content = b"unicode key test"
        key = "integration/élève-résumé-☃.txt"

        await s3_retriever.save_file(content, key)
        loaded = await s3_retriever.load_file(key)
        assert loaded == content


class TestFileLifecycle:
    """Full create -> inspect -> destroy lifecycle."""

    @pytest.mark.asyncio
    async def test_save_exists_metadata_delete(self, s3_retriever: S3FileRetriever) -> None:
        """Full lifecycle: save -> file_exists(True) -> metadata -> delete -> file_exists(False)."""
        content = b"lifecycle test content here"
        key = "integration/lifecycle.txt"

        # Save
        await s3_retriever.save_file(content, key)

        # Exists
        assert await s3_retriever.file_exists(key) is True

        # Metadata
        metadata = await s3_retriever.get_file_metadata(key)
        assert metadata["size"] == len(content)
        assert metadata["exists"] is True
        assert metadata["path"] == key
        assert "etag" in metadata
        assert "content_type" in metadata

        # Delete
        result = await s3_retriever.delete_file(key)
        assert result is True

        # Gone
        assert await s3_retriever.file_exists(key) is False

    @pytest.mark.asyncio
    async def test_delete_nonexistent_is_idempotent(self, s3_retriever: S3FileRetriever) -> None:
        """S3 delete_object is idempotent -- deleting a nonexistent key returns True."""
        result = await s3_retriever.delete_file("integration/does-not-exist.txt")
        assert result is True

    @pytest.mark.asyncio
    async def test_metadata_nonexistent_raises(self, s3_retriever: S3FileRetriever) -> None:
        """get_file_metadata for nonexistent key raises FileContentNotFoundError."""
        with pytest.raises(FileContentNotFoundError, match="File not found"):
            await s3_retriever.get_file_metadata("integration/ghost.txt")

    @pytest.mark.asyncio
    async def test_load_nonexistent_raises(self, s3_retriever: S3FileRetriever) -> None:
        """load_file for nonexistent key raises FileContentNotFoundError."""
        with pytest.raises(FileContentNotFoundError, match="File not found"):
            await s3_retriever.load_file("integration/ghost.txt")


class TestHealthCheck:
    """Bucket reachability probes."""

    @pytest.mark.asyncio
    async def test_health_check_valid_bucket(self, s3_retriever: S3FileRetriever) -> None:
        """health_check returns True when the bucket exists."""
        assert await s3_retriever.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_invalid_bucket(self) -> None:
        """health_check returns False when the bucket does not exist."""
        with mock_aws():
            retriever = S3FileRetriever(
                endpoint_url=None,
                bucket_name="nonexistent-bucket-xyz",
                region_name=REGION,
            )
            assert await retriever.health_check() is False

    @pytest.mark.asyncio
    async def test_multiple_files_independent(self, s3_retriever: S3FileRetriever) -> None:
        """Save 3 different files, load each independently, verify correct content."""
        files = {
            "integration/alpha.txt": b"alpha content",
            "integration/beta.txt": b"beta content -- different",
            "integration/gamma.bin": os.urandom(512),
        }

        for key, content in files.items():
            await s3_retriever.save_file(content, key)

        for key, expected in files.items():
            loaded = await s3_retriever.load_file(key)
            assert loaded == expected, f"Content mismatch for {key}"
