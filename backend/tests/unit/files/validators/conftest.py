"""Shared fixtures for file validator tests."""

from unittest.mock import AsyncMock

import pytest

from syntara.files.file_manager import FileManager


@pytest.fixture(autouse=True)
def _mock_s3_retriever(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject a mock S3 retriever into FileManager instances.

    Validator tests exercise the validation layer, not storage.
    This fixture prevents FileStorageUnavailableError from get_retriever()
    in tests where validation passes and the save path executes.
    """
    original_init = FileManager.__init__

    def patched_init(self: FileManager) -> None:
        original_init(self)
        mock_retriever = AsyncMock()
        mock_retriever.save_file = AsyncMock(return_value="orchestrator-uuid-file.pdf")
        self._retriever = mock_retriever

    monkeypatch.setattr(FileManager, "__init__", patched_init)
