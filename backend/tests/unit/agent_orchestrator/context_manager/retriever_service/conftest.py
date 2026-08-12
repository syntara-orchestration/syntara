"""Shared pytest fixtures for retriever service tests.

This module provides shared mocks and fixtures to avoid code duplication across
retriever service test files.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from syntara.files.models import FileMetadata


@pytest.fixture
def mock_file_manager() -> MagicMock:
    """Create a mock FileManager for tests.

    This fixture provides a mock FileManager with a file metadata store
    that tests can populate. The mock supports:
    - get_files_metadata: Returns metadata from the store based on file IDs
    - get_retriever: Returns a mock retriever that loads files from disk
    - _test_file_metadata_store: Dictionary to populate with test data

    Usage:
        mock_file_manager._test_file_metadata_store[(file_id1, file_id2)] = [metadata1, metadata2]
    """
    file_metadata_store: dict[tuple[UUID, ...], list[FileMetadata]] = {}

    mock_file_manager = MagicMock()

    async def mock_get_files_metadata(file_ids: list[UUID], session) -> list[FileMetadata]:
        return file_metadata_store.get(tuple(file_ids), [])

    mock_file_manager.get_files_metadata = AsyncMock(side_effect=mock_get_files_metadata)

    mock_retriever = MagicMock()

    async def mock_load_file(path: str) -> bytes:
        return Path(path).read_bytes()

    mock_retriever.load_file = AsyncMock(side_effect=mock_load_file)
    mock_file_manager.get_retriever = MagicMock(return_value=mock_retriever)

    mock_file_manager._test_file_metadata_store = file_metadata_store

    return mock_file_manager
