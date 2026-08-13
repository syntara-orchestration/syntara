"""Unit tests for S3FileRetriever.

Tests validate all BaseRetriever methods against moto mock S3,
including happy paths, edge cases, and error handling.
"""

import hashlib
import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from syntara.files.exceptions import FileContentNotFoundError
from syntara.files.retrievers.s3 import S3FileRetriever

BUCKET_NAME = "orchestrator-test-files"
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
        conn.create_bucket(Bucket=BUCKET_NAME)

        retriever = S3FileRetriever(
            endpoint_url=None,
            bucket_name=BUCKET_NAME,
            region_name=REGION,
        )
        yield retriever


# --- save_file + load_file ---


@pytest.mark.asyncio
async def test_save_and_load_file(s3_retriever: S3FileRetriever) -> None:
    """Test round-trip save and load for small files."""
    content = b"Hello from S3FileRetriever!" * 30
    key = "orchestrator-test-uuid-document.txt"

    stored_key = await s3_retriever.save_file(content, key)
    assert stored_key == key

    loaded = await s3_retriever.load_file(key)
    assert loaded == content


@pytest.mark.asyncio
async def test_save_and_load_large_file_multipart(s3_retriever: S3FileRetriever) -> None:
    """Test multipart upload for files exceeding 5MB threshold."""
    content = os.urandom(6 * 1024 * 1024)
    key = "orchestrator-test-uuid-large.bin"

    stored_key = await s3_retriever.save_file(content, key)
    assert stored_key == key

    loaded = await s3_retriever.load_file(key)
    assert loaded == content


# --- file_exists ---


@pytest.mark.asyncio
async def test_file_exists_true(s3_retriever: S3FileRetriever) -> None:
    """Test file_exists returns True for existing file."""
    await s3_retriever.save_file(b"exists test", "orchestrator-test-uuid-exists.txt")
    assert await s3_retriever.file_exists("orchestrator-test-uuid-exists.txt") is True


@pytest.mark.asyncio
async def test_file_exists_false(s3_retriever: S3FileRetriever) -> None:
    """Test file_exists returns False for nonexistent file."""
    assert await s3_retriever.file_exists("nonexistent-key") is False


# --- get_file_metadata ---


@pytest.mark.asyncio
async def test_get_file_metadata(s3_retriever: S3FileRetriever) -> None:
    """Test metadata retrieval for existing file."""
    content = b"metadata test content"
    key = "orchestrator-test-uuid-metadata.txt"

    await s3_retriever.save_file(content, key)
    metadata: dict[str, Any] = await s3_retriever.get_file_metadata(key)

    assert metadata["size"] == len(content)
    assert metadata["exists"] is True
    assert metadata["path"] == key
    assert "modified" in metadata
    assert "etag" in metadata


# --- delete_file ---


@pytest.mark.asyncio
async def test_delete_file(s3_retriever: S3FileRetriever) -> None:
    """Test file deletion removes file from S3."""
    content = b"to be deleted"
    key = "orchestrator-test-uuid-delete.txt"

    await s3_retriever.save_file(content, key)
    assert await s3_retriever.file_exists(key) is True

    result = await s3_retriever.delete_file(key)
    assert result is True
    assert await s3_retriever.file_exists(key) is False


# --- health_check ---


@pytest.mark.asyncio
async def test_health_check_passes(s3_retriever: S3FileRetriever) -> None:
    """Test health_check returns True for valid bucket."""
    assert await s3_retriever.health_check() is True


@pytest.mark.asyncio
async def test_health_check_fails_for_nonexistent_bucket() -> None:
    """Test health_check returns False for nonexistent bucket."""
    with mock_aws():
        retriever = S3FileRetriever(
            endpoint_url=None,
            bucket_name="nonexistent-bucket",
            region_name=REGION,
        )
        assert await retriever.health_check() is False


# --- Content integrity ---


@pytest.mark.asyncio
async def test_content_hash_roundtrip(s3_retriever: S3FileRetriever) -> None:
    """Test SHA-256 hash is preserved across save/load cycle."""
    content = os.urandom(1024)
    key = "orchestrator-test-uuid-hash.bin"
    expected_hash = hashlib.sha256(content).hexdigest()

    await s3_retriever.save_file(content, key)
    loaded = await s3_retriever.load_file(key)
    actual_hash = hashlib.sha256(loaded).hexdigest()

    assert actual_hash == expected_hash


# --- Edge cases ---


@pytest.mark.asyncio
async def test_empty_file(s3_retriever: S3FileRetriever) -> None:
    """Test handling of empty files."""
    key = "orchestrator-test-uuid-empty.txt"

    await s3_retriever.save_file(b"", key)
    loaded = await s3_retriever.load_file(key)
    assert loaded == b""


@pytest.mark.asyncio
async def test_special_characters_in_key(s3_retriever: S3FileRetriever) -> None:
    """Test keys with special characters."""
    content = b"special chars"
    key = "orchestrator-550e8400-file (final).pdf"

    await s3_retriever.save_file(content, key)
    loaded = await s3_retriever.load_file(key)
    assert loaded == content


@pytest.mark.asyncio
async def test_overwrite_existing_file(s3_retriever: S3FileRetriever) -> None:
    """Test that saving to the same key overwrites the previous content."""
    key = "orchestrator-test-uuid-overwrite.txt"

    await s3_retriever.save_file(b"version 1", key)
    await s3_retriever.save_file(b"version 2", key)

    loaded = await s3_retriever.load_file(key)
    assert loaded == b"version 2"


# --- Error paths ---


@pytest.mark.asyncio
async def test_load_nonexistent_file(s3_retriever: S3FileRetriever) -> None:
    """Test loading nonexistent file raises FileNotFoundError."""
    with pytest.raises(FileContentNotFoundError, match="File not found"):
        await s3_retriever.load_file("does-not-exist")


@pytest.mark.asyncio
async def test_get_metadata_nonexistent_file(s3_retriever: S3FileRetriever) -> None:
    """Test get_file_metadata for nonexistent file raises FileNotFoundError."""
    with pytest.raises(FileContentNotFoundError, match="File not found"):
        await s3_retriever.get_file_metadata("does-not-exist")


# --- TLS / verify configuration ---


class TestS3VerifySSL:
    """Tests for S3 TLS verification configuration."""

    def test_default_verify_is_true(self) -> None:
        with mock_aws(), patch("syntara.files.retrievers.s3.boto3.client", wraps=boto3.client) as mock_client:
            S3FileRetriever(endpoint_url=None, bucket_name=BUCKET_NAME, region_name=REGION)
            mock_client.assert_called_once()
            assert mock_client.call_args.kwargs["verify"] is True

    def test_verify_false_passed_through(self) -> None:
        with mock_aws(), patch("syntara.files.retrievers.s3.boto3.client", wraps=boto3.client) as mock_client:
            S3FileRetriever(endpoint_url=None, bucket_name=BUCKET_NAME, region_name=REGION, verify_ssl=False)
            assert mock_client.call_args.kwargs["verify"] is False

    def test_ca_bundle_used_when_verify_ssl_true(self) -> None:
        with mock_aws(), patch("syntara.files.retrievers.s3.boto3.client", wraps=boto3.client) as mock_client:
            S3FileRetriever(
                endpoint_url=None,
                bucket_name=BUCKET_NAME,
                region_name=REGION,
                ca_bundle="/var/run/secrets/ca.crt",
            )
            assert mock_client.call_args.kwargs["verify"] == "/var/run/secrets/ca.crt"

    def test_verify_false_takes_precedence_over_ca_bundle(self) -> None:
        with mock_aws(), patch("syntara.files.retrievers.s3.boto3.client", wraps=boto3.client) as mock_client:
            S3FileRetriever(
                endpoint_url=None,
                bucket_name=BUCKET_NAME,
                region_name=REGION,
                verify_ssl=False,
                ca_bundle="/var/run/secrets/ca.crt",
            )
            assert mock_client.call_args.kwargs["verify"] is False


# --- cleanup_stale_multipart_uploads ---


class TestCleanupStaleMultipartUploads:
    """Tests for cleanup_stale_multipart_uploads method."""

    @pytest.mark.asyncio
    async def test_aborts_stale_uploads(self, s3_retriever: S3FileRetriever) -> None:
        """Stale multipart uploads (older than threshold) are aborted."""
        # Create a multipart upload via the underlying boto3 client
        s3_retriever._client.create_multipart_upload(Bucket=BUCKET_NAME, Key="stale-upload.bin")

        # Use threshold=0 so any upload is considered stale
        aborted = await s3_retriever.cleanup_stale_multipart_uploads(threshold_hours=0)
        assert aborted == 1

        # Verify no multipart uploads remain
        response = s3_retriever._client.list_multipart_uploads(Bucket=BUCKET_NAME)
        assert response.get("Uploads", []) == []

    @pytest.mark.asyncio
    async def test_skips_recent_uploads(self, s3_retriever: S3FileRetriever) -> None:
        """Recent multipart uploads (within threshold) are not aborted."""
        # Mock list_multipart_uploads to return an upload with a recent Initiated time,
        # since moto uses a hardcoded 2010 date that would always appear stale.
        recent_time = datetime.now(tz=UTC) - timedelta(minutes=5)
        with patch.object(
            s3_retriever._client,
            "list_multipart_uploads",
            return_value={
                "Uploads": [
                    {
                        "Key": "recent-upload.bin",
                        "UploadId": "fake-upload-id",
                        "Initiated": recent_time,
                    },
                ],
            },
        ):
            aborted = await s3_retriever.cleanup_stale_multipart_uploads(threshold_hours=1)
        assert aborted == 0

    @pytest.mark.asyncio
    async def test_handles_no_uploads(self, s3_retriever: S3FileRetriever) -> None:
        """Returns 0 when no multipart uploads exist."""
        aborted = await s3_retriever.cleanup_stale_multipart_uploads(threshold_hours=0)
        assert aborted == 0

    @pytest.mark.asyncio
    async def test_handles_list_error_gracefully(self, s3_retriever: S3FileRetriever) -> None:
        """Returns 0 and does not raise when list_multipart_uploads fails."""
        error_response: dict[str, Any] = {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}
        with patch.object(
            s3_retriever._client,
            "list_multipart_uploads",
            side_effect=ClientError(error_response, "ListMultipartUploads"),  # type: ignore[arg-type]
        ):
            aborted = await s3_retriever.cleanup_stale_multipart_uploads(threshold_hours=0)
            assert aborted == 0

    @pytest.mark.asyncio
    async def test_handles_abort_error_continues(self, s3_retriever: S3FileRetriever) -> None:
        """Continues processing when abort fails for one upload."""
        # Create two multipart uploads
        s3_retriever._client.create_multipart_upload(Bucket=BUCKET_NAME, Key="fail-upload.bin")
        s3_retriever._client.create_multipart_upload(Bucket=BUCKET_NAME, Key="succeed-upload.bin")

        original_abort = s3_retriever._client.abort_multipart_upload
        call_count = 0
        error_response: dict[str, Any] = {"Error": {"Code": "InternalError", "Message": "Internal Error"}}

        def abort_side_effect(**kwargs: Any) -> Any:  # noqa: ANN401
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ClientError(error_response, "AbortMultipartUpload")  # type: ignore[arg-type]
            return original_abort(**kwargs)

        with patch.object(
            s3_retriever._client,
            "abort_multipart_upload",
            side_effect=abort_side_effect,
        ):
            aborted = await s3_retriever.cleanup_stale_multipart_uploads(threshold_hours=0)

        # One failed, one succeeded
        assert aborted == 1
