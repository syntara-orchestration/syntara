"""Tests for DocumentConversionTask.

This module tests the background task execution for document conversion
using FileManager for all FileMetadata operations.

The task is decoupled from invocation execution - it only handles file
conversion and updates FileMetadata status in the database via FileManager.
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from syntara.files.document_conversion.services.types import ConversionState
from syntara.files.document_conversion.tasks import (
    DocumentConversionTask,
    get_document_conversion_task,
)
from syntara.files.models import FileMetadata, FileStatus


class TestDocumentConversionTaskInit:
    """Test DocumentConversionTask initialization."""

    def test_init_with_default_factories(self) -> None:
        """Test initialization with default factories."""
        task = get_document_conversion_task()
        assert task.file_manager is not None
        assert task.service is not None
        assert task.session_factory is not None
        assert task.get_async_session_context is not None

    def test_init_with_custom_session_factory(self) -> None:
        """Test initialization with custom session factory."""

        async def custom_session_factory() -> AsyncGenerator[AsyncMock, None]:
            yield AsyncMock()

        task = get_document_conversion_task(session_factory=custom_session_factory)
        assert task.session_factory == custom_session_factory


class TestDocumentConversionTaskConvert:
    """Test DocumentConversionTask.convert() method."""

    @pytest.fixture
    def sample_file_id(self) -> UUID:
        """Sample file ID for testing."""
        return uuid4()

    @pytest.fixture
    def sample_file_metadata(self, sample_file_id: UUID) -> FileMetadata:
        """Sample FileMetadata for testing."""
        return FileMetadata(
            id=sample_file_id,
            filename="test.pdf",
            file_path=f"/uploads/nexus-{sample_file_id}-test.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            status=FileStatus.PENDING_CONVERSION,
        )

    @pytest.mark.asyncio
    async def test_convert_file_not_found(self, sample_file_id: UUID, mock_session_factory) -> None:
        """Test convert returns FAILED when file not found in database."""
        # Create mock file manager that returns None
        mock_file_manager = MagicMock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=None)
        mock_file_manager.update_file_status = AsyncMock()

        with patch(
            "syntara.files.document_conversion.tasks.document_conversion_task.get_file_manager",
            return_value=mock_file_manager,
        ):
            task = DocumentConversionTask(
                file_manager_factory=lambda: mock_file_manager,
                session_factory=mock_session_factory,
            )

            result = await task.convert(sample_file_id)

            assert result == ConversionState.FAILED
            mock_file_manager.get_file_metadata.assert_called_once()

    @pytest.mark.asyncio
    async def test_convert_skips_already_converted(
        self, sample_file_id: UUID, sample_file_metadata: FileMetadata, mock_session_factory
    ) -> None:
        """Test convert returns SKIPPED when file is not pending conversion."""
        # Set status to already converted
        sample_file_metadata.status = FileStatus.CONVERTED

        # Create mock file manager
        mock_file_manager = MagicMock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=sample_file_metadata)
        mock_file_manager.update_file_status = AsyncMock()

        task = DocumentConversionTask(
            file_manager_factory=lambda: mock_file_manager,
            session_factory=mock_session_factory,
        )

        result = await task.convert(sample_file_id)

        assert result == ConversionState.SKIPPED
        mock_file_manager.get_file_metadata.assert_called_once()
        # Should not attempt to update status since it was skipped
        mock_file_manager.update_file_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_convert_success(
        self, sample_file_id: UUID, sample_file_metadata: FileMetadata, mock_session_factory
    ) -> None:
        """Test successful file conversion."""
        # Create mock file manager
        mock_file_manager = MagicMock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=sample_file_metadata)
        mock_file_manager.update_file_status = AsyncMock()

        # Create mock conversion service
        mock_service = MagicMock()
        mock_service.convert_file = AsyncMock(return_value=ConversionState.SUCCESS)

        task = DocumentConversionTask(
            file_manager_factory=lambda: mock_file_manager,
            session_factory=mock_session_factory,
        )
        task.service = mock_service

        result = await task.convert(sample_file_id)

        assert result == ConversionState.SUCCESS
        mock_file_manager.get_file_metadata.assert_called_once()
        mock_service.convert_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_convert_handles_exception(
        self, sample_file_id: UUID, sample_file_metadata: FileMetadata, mock_session_factory
    ) -> None:
        """Test convert handles exceptions gracefully."""
        # Create mock file manager
        mock_file_manager = MagicMock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=sample_file_metadata)
        mock_file_manager.update_file_status = AsyncMock()

        # Create mock conversion service that raises an exception
        mock_service = MagicMock()
        mock_service.convert_file = AsyncMock(side_effect=Exception("Conversion failed"))

        task = DocumentConversionTask(
            file_manager_factory=lambda: mock_file_manager,
            session_factory=mock_session_factory,
        )
        task.service = mock_service

        result = await task.convert(sample_file_id)

        assert result == ConversionState.FAILED
        # Should attempt to update status to FAILED
        mock_file_manager.update_file_status.assert_called()

    @pytest.mark.asyncio
    async def test_convert_with_uuid(self, sample_file_metadata: FileMetadata, mock_session_factory) -> None:
        """Test convert works with UUID file_id."""
        file_uuid = sample_file_metadata.id

        # Create mock file manager
        mock_file_manager = MagicMock()
        mock_file_manager.get_file_metadata = AsyncMock(return_value=sample_file_metadata)
        mock_file_manager.update_file_status = AsyncMock()

        # Create mock conversion service
        mock_service = MagicMock()
        mock_service.convert_file = AsyncMock(return_value=ConversionState.SUCCESS)

        task = DocumentConversionTask(
            file_manager_factory=lambda: mock_file_manager,
            session_factory=mock_session_factory,
        )
        task.service = mock_service

        result = await task.convert(file_uuid)

        assert result == ConversionState.SUCCESS


class TestGetDocumentConversionTask:
    """Test get_document_conversion_task factory function."""

    def test_returns_document_conversion_task(self) -> None:
        """Test factory returns DocumentConversionTask instance."""
        task = get_document_conversion_task()
        assert isinstance(task, DocumentConversionTask)

    def test_with_custom_session_factory(self) -> None:
        """Test factory with custom session factory."""

        async def custom_factory() -> AsyncGenerator[AsyncMock, None]:
            yield AsyncMock()

        task = get_document_conversion_task(session_factory=custom_factory)
        assert task.session_factory == custom_factory
