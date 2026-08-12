"""Shared pytest fixtures and test helpers for retriever service tests.

This module provides shared mocks and fixtures to avoid code duplication across
retriever service test files.
"""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.context_manager.retriever_service.retrievers.uploaded_file_retriever import (
    UploadedFileRetriever,
)


async def async_session_generator(session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """Create an async generator for the session factory."""
    yield session


class TestUploadedFileRetriever(UploadedFileRetriever):
    """Test version of UploadedFileRetriever that uses mock FileManager.

    This is a shared mock implementation used across multiple retriever service tests
    to avoid code duplication. It allows injecting a mock FileManager for testing.
    """

    _test_file_manager: MagicMock | None = None

    def __init__(self, file_manager_factory=None, session_factory=None) -> None:
        """Initialize with test mocks."""
        if file_manager_factory is None and TestUploadedFileRetriever._test_file_manager is not None:

            def get_file_manager() -> MagicMock | None:
                return TestUploadedFileRetriever._test_file_manager

            file_manager_factory = get_file_manager

        if session_factory is None:

            async def mock_session_gen() -> AsyncGenerator[Any, None]:
                yield AsyncMock()

            session_factory = mock_session_gen

        super().__init__(file_manager_factory, session_factory)
