"""Shared fixtures for file validator tests."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, Mock

import pytest

from syntara.files.file_manager import FileManager


def make_upload_mock(filename: str, content: bytes, content_type: str = "application/pdf") -> Mock:
    """Create a mock UploadFile with a finite read cursor for streaming.

    The mock supports:
    - ``get_file_size``: via ``seek(0, 2)`` / ``tell()``
    - ``validate_single_file``: header read via ``read(N)``
    - ``_stream_upload_file``: remaining reads until EOF (``b""``)
    """
    mock_file = Mock()
    mock_file.filename = filename
    mock_file.size = len(content)
    mock_file.content_type = content_type

    pos = 0

    async def _read(size: int = -1) -> bytes:
        nonlocal pos
        if size == -1:
            chunk = content[pos:]
            pos = len(content)
        else:
            chunk = content[pos : pos + size]
            pos += len(chunk)
        return chunk

    async def _seek(offset: int, whence: int = 0) -> int:
        nonlocal pos
        if whence == 2:
            pos = len(content)
        elif whence == 0:
            pos = offset
        return pos

    def _tell() -> int:
        return pos

    mock_file.read = _read
    mock_file.seek = _seek
    mock_file.tell = _tell
    return mock_file


async def _consume_and_save(stream: AsyncGenerator[bytes], path: str) -> tuple[str, int]:
    """Mock save_file_stream that consumes the async stream."""
    total = 0
    async for chunk in stream:
        total += len(chunk)
    return "orchestrator-uuid-file.pdf", total


@pytest.fixture(autouse=True)
def _mock_s3_retriever(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject a mock S3 retriever into FileManager instances.

    Validator tests exercise the validation layer, not storage.
    This fixture prevents FileStorageUnavailableError from get_retriever()
    in tests where validation passes and the save path executes.

    Only the S3 retriever is mocked — validate_single_file runs real
    validation so MIME/size tests exercise actual behavior.
    """
    original_init = FileManager.__init__

    def patched_init(self: FileManager) -> None:
        original_init(self)
        mock_retriever = AsyncMock()
        mock_retriever.save_file = AsyncMock(return_value="orchestrator-uuid-file.pdf")
        mock_retriever.save_file_stream = AsyncMock(side_effect=_consume_and_save)
        self._retriever = mock_retriever

    monkeypatch.setattr(FileManager, "__init__", patched_init)
