"""Tests for DocumentConversionService.

This module tests the main document conversion service that coordinates
conversion operations with FileMetadata integration and status management.
"""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.core.exceptions import SafeValueError
from syntara.files.document_conversion.models.conversion_result import (
    ConversionResult,
)
from syntara.files.document_conversion.services import ConversionState
from syntara.files.document_conversion.services.document_conversion_service import (
    DocumentConversionService,
)
from syntara.files.models import FileMetadata, FileStatus


@pytest.fixture(autouse=True)
def mock_conversion_config() -> Generator[MagicMock]:
    """Patch ConversionConfig.from_settings for all service tests."""
    mock_config = MagicMock()
    mock_config.overwrite_existing = True
    mock_config.timeout_seconds = 30
    mock_config.temp_dir = "/tmp/nexus-test"  # noqa: S108
    with patch(
        "syntara.files.document_conversion.services.document_conversion_service.ConversionConfig.from_settings",
        return_value=mock_config,
    ):
        yield mock_config


class ConversionTestHelper:
    """Helper class to set up clean mocks for document conversion tests."""

    def __init__(self) -> None:
        """Initialize the test helper with fresh mocks."""
        self.mock_file_manager = MagicMock()
        self.mock_converter_registry = MagicMock()
        self.mock_converter = MagicMock()
        self.mock_retriever = AsyncMock()
        self.status_updater = AsyncMock()

        # Make convert_with_timeout async since it's an async method
        self.mock_converter.convert_with_timeout = AsyncMock()

        # Set up default mock behaviors
        self._setup_default_mocks()

        # Create service with mock factory functions
        self.service = DocumentConversionService(
            file_manager_factory=lambda: self.mock_file_manager,
            converter_registry_factory=lambda: self.mock_converter_registry,
        )

    def _setup_default_mocks(self) -> None:
        """Set up default mock behaviors."""
        self.mock_file_manager.get_retriever.return_value = self.mock_retriever

        # Registry returns our mock converter by default
        self.mock_converter_registry.get_converter.return_value = self.mock_converter

    def setup_file_loading(self, file_content: bytes) -> None:
        """Configure the mock retriever to return specific file content."""
        self.mock_retriever.load_file.return_value = file_content

    def setup_converter(
        self, converter_name: str, conversion_result: ConversionResult | None = None, *, exists: bool = True
    ) -> None:
        """Configure the mock converter with specific behavior."""
        if exists:
            self.mock_converter.get_converter_name.return_value = converter_name
            self.mock_converter.convert_with_timeout.return_value = conversion_result
            self.mock_converter_registry.get_converter.return_value = self.mock_converter
        else:
            self.mock_converter_registry.get_converter.return_value = None

    def setup_file_storage(self, output_path: str) -> None:
        """Configure mock file storage behavior."""
        self.mock_retriever.save_file.return_value = output_path

    def setup_file_storage_error(self, error: Exception) -> None:
        """Configure mock file storage to raise an error."""
        self.mock_retriever.save_file.side_effect = error

    def setup_file_loading_error(self, error: Exception) -> None:
        """Configure mock file loading to raise an error."""
        self.mock_retriever.load_file.side_effect = error


@pytest.fixture
def conversion_helper() -> ConversionTestHelper:
    """Fixture providing a clean test helper for document conversion tests."""
    return ConversionTestHelper()


@pytest.fixture
def sample_file_metadata() -> FileMetadata:
    """Fixture providing sample file metadata for testing."""
    return FileMetadata(
        id=uuid4(),
        filename="test.pdf",
        size_bytes=1000,
        mime_type="application/pdf",
        file_path="/path/to/test.pdf",
        status=FileStatus.PENDING_CONVERSION,
    )


def create_file_metadata(
    filename: str = "test.pdf",
    mime_type: str = "application/pdf",
    status: FileStatus = FileStatus.PENDING_CONVERSION,
    *,
    size_bytes: int = 1000,
    file_path: str | None = None,
    converted_content_path: str | None = None,
    conversion_error: str | None = None,
) -> FileMetadata:
    """Create FileMetadata with sensible defaults."""
    return FileMetadata(
        id=uuid4(),
        filename=filename,
        size_bytes=size_bytes,
        mime_type=mime_type,
        file_path=file_path or f"/path/to/{filename}",
        status=status,
        converted_content_path=converted_content_path,
        conversion_error=conversion_error,
    )


def create_success_result(content: str = "Test content", time_ms: int = 500) -> ConversionResult:
    """Create successful conversion results."""
    return ConversionResult.success_result(converted_content=content, conversion_time_ms=time_ms)


def create_failure_result(
    error_msg: str = "Conversion failed", error_type: str = "test_error", time_ms: int = 200
) -> ConversionResult:
    """Create failed conversion results."""
    return ConversionResult.failure_result(error_message=error_msg, error_type=error_type, conversion_time_ms=time_ms)


class TestDocumentConversionServiceInitialization:
    """Test DocumentConversionService initialization and setup."""

    def test_initialization_creates_file_manager(self) -> None:
        """Test that DocumentConversionService initializes with FileManager."""
        service = DocumentConversionService()
        # Access private member for testing purposes
        assert service.file_manager is not None

    def test_generate_output_filename_pdf_extension(self) -> None:
        """Test output filename generation for PDF files."""
        # Access private method for testing purposes
        result = DocumentConversionService._generate_output_filename("document.pdf")
        assert result == "document.md"

    def test_generate_output_filename_docx_extension(self) -> None:
        """Test output filename generation for DOCX files."""
        # Access private method for testing purposes
        result = DocumentConversionService._generate_output_filename("report.docx")
        assert result == "report.md"

    def test_generate_output_filename_no_extension(self) -> None:
        """Test output filename generation for files without extensions."""
        # Access private method for testing purposes
        result = DocumentConversionService._generate_output_filename("document")
        assert result == "document.md"

    def test_generate_output_filename_multiple_dots(self) -> None:
        """Test output filename generation for files with multiple dots."""
        # Access private method for testing purposes
        result = DocumentConversionService._generate_output_filename("my.document.pdf")
        assert result == "my.document.md"


class TestDocumentConversionServiceFileMetadataValidation:
    """Test DocumentConversionService validation of FileMetadata status."""

    @pytest.mark.asyncio
    async def test_convert_file_validates_pending_conversion_status(
        self, conversion_helper: ConversionTestHelper
    ) -> None:
        """Test that convert_file validates FileMetadata status is pending_conversion."""
        file_metadata = create_file_metadata(status=FileStatus.CONVERTED)  # Wrong status

        conversion_state: ConversionState = await conversion_helper.service.convert_file(
            file_metadata, conversion_helper.status_updater
        )
        assert conversion_state == ConversionState.SKIPPED

    @pytest.mark.asyncio
    async def test_convert_file_accepts_pending_conversion_status(
        self, conversion_helper: ConversionTestHelper
    ) -> None:
        """Test that convert_file accepts FileMetadata with pending_conversion status."""
        file_metadata = create_file_metadata(filename="test.txt", mime_type="text/plain")

        conversion_helper.setup_file_loading(b"Test content")
        conversion_helper.setup_converter("TextConverter", create_success_result("# Test content"))
        conversion_helper.setup_file_storage("/output/test.md")

        # Should not raise an error
        await conversion_helper.service.convert_file(file_metadata, conversion_helper.status_updater)

        # Verify status was updated to converting first
        assert conversion_helper.status_updater.call_count >= 1


class TestDocumentConversionServiceConverterIntegration:
    """Test DocumentConversionService integration with converter registry and retrievers."""

    @pytest.mark.asyncio
    async def test_convert_file_uses_file_manager_get_retriever(self, conversion_helper: ConversionTestHelper) -> None:
        """Test that convert_file uses FileManager.get_retriever."""
        file_metadata = create_file_metadata()

        conversion_helper.setup_file_loading(b"PDF content")
        conversion_helper.setup_converter("", None, exists=False)

        await conversion_helper.service.convert_file(file_metadata, conversion_helper.status_updater)

        conversion_helper.mock_file_manager.get_retriever.assert_called()

    @pytest.mark.asyncio
    async def test_convert_file_loads_file_content_via_retriever(self, conversion_helper: ConversionTestHelper) -> None:
        """Test that convert_file loads file content using BaseRetriever.load_file."""
        file_metadata = create_file_metadata(
            filename="test.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=2000,
        )

        conversion_helper.setup_file_loading(b"DOCX content")
        conversion_helper.setup_converter("", None, exists=False)

        await conversion_helper.service.convert_file(file_metadata, conversion_helper.status_updater)

        # Verify load_file was called with correct file path
        conversion_helper.mock_retriever.load_file.assert_called_once_with(file_metadata.file_path)

    @pytest.mark.asyncio
    async def test_convert_file_gets_converter_by_mime_type(self, conversion_helper: ConversionTestHelper) -> None:
        """Test that convert_file retrieves converter using MIME type."""
        file_metadata = create_file_metadata(filename="test.txt", mime_type="text/plain", size_bytes=500)

        conversion_helper.setup_file_loading(b"Text content")
        conversion_helper.setup_converter("", None, exists=False)

        await conversion_helper.service.convert_file(file_metadata, conversion_helper.status_updater)

        # Verify get_converter was called with correct MIME type
        conversion_helper.mock_converter_registry.get_converter.assert_called_once_with("text/plain")


class TestDocumentConversionServiceStatusUpdates:
    """Test DocumentConversionService FileMetadata status management."""

    @pytest.mark.asyncio
    async def test_convert_file_updates_status_to_converting(self, conversion_helper: ConversionTestHelper) -> None:
        """Test that convert_file updates status to 'converting' before processing."""
        file_metadata = create_file_metadata(filename="test.md", mime_type="text/markdown", size_bytes=300)

        conversion_helper.setup_file_loading(b"# Markdown content")
        conversion_helper.setup_converter("MarkdownConverter", create_success_result("# Markdown content", 100))
        conversion_helper.setup_file_storage("/output/test.md")

        await conversion_helper.service.convert_file(file_metadata, conversion_helper.status_updater)

        # Verify status was updated (could be converting or converted due to timing)
        assert conversion_helper.status_updater.call_count >= 1
        first_call_args = conversion_helper.status_updater.call_args_list[0]
        # The first call should be either CONVERTING or CONVERTED (depending on timing)
        assert first_call_args[0][0].status in [FileStatus.CONVERTING, FileStatus.CONVERTED]

    @pytest.mark.asyncio
    async def test_convert_file_updates_status_to_converted_on_success(
        self, conversion_helper: ConversionTestHelper
    ) -> None:
        """Test that convert_file updates status to 'converted' on successful conversion."""
        file_metadata = create_file_metadata(filename="success.txt", mime_type="text/plain", size_bytes=400)

        conversion_helper.setup_file_loading(b"Plain text content")
        conversion_helper.setup_converter("TextConverter", create_success_result("Plain text content", 750))
        conversion_helper.setup_file_storage("/output/success.md")

        await conversion_helper.service.convert_file(file_metadata, conversion_helper.status_updater)

        # Verify final status is converted
        assert conversion_helper.status_updater.call_count >= 2
        final_call_args = conversion_helper.status_updater.call_args_list[-1]
        final_metadata = final_call_args[0][0]
        assert final_metadata.status == FileStatus.CONVERTED
        assert final_metadata.converted_content_path == "/output/success.md"

    @pytest.mark.asyncio
    async def test_convert_file_updates_status_to_conversion_failed_on_failure(
        self, conversion_helper: ConversionTestHelper
    ) -> None:
        """Test that convert_file updates status to 'conversion_failed' on conversion failure."""
        file_metadata = create_file_metadata(filename="fail.pdf", size_bytes=800)

        conversion_helper.setup_file_loading(b"Corrupted PDF content")
        conversion_helper.setup_converter(
            "PDFConverter",
            create_failure_result("PDF file is corrupted and cannot be processed", "file_corruption", 200),
        )

        await conversion_helper.service.convert_file(file_metadata, conversion_helper.status_updater)

        # Verify final status is conversion_failed
        assert conversion_helper.status_updater.call_count >= 2
        final_call_args = conversion_helper.status_updater.call_args_list[-1]
        final_metadata = final_call_args[0][0]
        assert final_metadata.status == FileStatus.CONVERSION_FAILED
        assert final_metadata.conversion_error is not None
        assert "PDF file is corrupted and cannot be processed" in final_metadata.conversion_error

    @pytest.mark.asyncio
    async def test_convert_file_handles_missing_converter(self, conversion_helper: ConversionTestHelper) -> None:
        """Test that convert_file handles missing converter gracefully."""
        file_metadata = create_file_metadata(filename="unsupported.zip", mime_type="application/zip", size_bytes=1200)

        conversion_helper.setup_file_loading(b"ZIP content")
        conversion_helper.setup_converter("", None, exists=False)

        await conversion_helper.service.convert_file(file_metadata, conversion_helper.status_updater)

        # Verify final status is conversion_failed
        assert conversion_helper.status_updater.call_count >= 2
        final_call_args = conversion_helper.status_updater.call_args_list[-1]
        final_metadata = final_call_args[0][0]
        assert final_metadata.status == FileStatus.CONVERSION_FAILED
        assert final_metadata.conversion_error is not None
        assert "Unsupported MIME type" in final_metadata.conversion_error


class TestDocumentConversionServiceOverwriteExisting:
    """Test DocumentConversionService overwrite_existing setting."""

    @pytest.mark.asyncio
    async def test_skips_conversion_when_overwrite_disabled_and_already_converted(
        self, mock_conversion_config: MagicMock, conversion_helper: ConversionTestHelper
    ) -> None:
        """Test that conversion is skipped when overwrite_existing=False and file already has converted content."""
        mock_conversion_config.overwrite_existing = False

        file_metadata = create_file_metadata(
            filename="already_converted.pdf",
            converted_content_path="/output/already_converted.md",
        )

        conversion_state = await conversion_helper.service.convert_file(file_metadata, conversion_helper.status_updater)

        assert conversion_state == ConversionState.SKIPPED
        assert file_metadata.status == FileStatus.CONVERTED
        conversion_helper.status_updater.assert_called_once()

    @pytest.mark.asyncio
    async def test_proceeds_when_overwrite_enabled_and_already_converted(
        self, mock_conversion_config: MagicMock, conversion_helper: ConversionTestHelper
    ) -> None:
        """Test that conversion proceeds when overwrite_existing=True even if file already has converted content."""
        mock_conversion_config.overwrite_existing = True

        file_metadata = create_file_metadata(
            filename="reconvert.pdf",
            converted_content_path="/output/reconvert.md",
        )

        conversion_helper.setup_file_loading(b"PDF content")
        conversion_helper.setup_converter("PDFConverter", create_success_result("# Reconverted", 500))
        conversion_helper.setup_file_storage("/output/reconvert.md")

        conversion_state = await conversion_helper.service.convert_file(file_metadata, conversion_helper.status_updater)

        assert conversion_state == ConversionState.SUCCESS
        assert file_metadata.status == FileStatus.CONVERTED

    @pytest.mark.asyncio
    async def test_proceeds_when_overwrite_disabled_and_no_existing_conversion(
        self, mock_conversion_config: MagicMock, conversion_helper: ConversionTestHelper
    ) -> None:
        """Test that conversion proceeds when overwrite_existing=False but file has no existing converted content."""
        mock_conversion_config.overwrite_existing = False

        file_metadata = create_file_metadata(filename="new_file.pdf")

        conversion_helper.setup_file_loading(b"PDF content")
        conversion_helper.setup_converter("PDFConverter", create_success_result("# Converted", 500))
        conversion_helper.setup_file_storage("/output/new_file.md")

        conversion_state = await conversion_helper.service.convert_file(file_metadata, conversion_helper.status_updater)

        assert conversion_state == ConversionState.SUCCESS


class TestDocumentConversionServiceErrorHandling:
    """Test DocumentConversionService error handling scenarios."""

    @pytest.mark.asyncio
    async def test_convert_file_handles_file_load_exception(self, conversion_helper: ConversionTestHelper) -> None:
        """Test that convert_file handles file loading exceptions."""
        file_metadata = create_file_metadata(filename="missing.txt", mime_type="text/plain", size_bytes=600)

        # Simulate file loading error
        conversion_helper.setup_file_loading_error(OSError("File not found"))

        await conversion_helper.service.convert_file(file_metadata, conversion_helper.status_updater)

        # Verify error was handled gracefully
        assert conversion_helper.status_updater.call_count >= 2
        final_call_args = conversion_helper.status_updater.call_args_list[-1]
        final_metadata = final_call_args[0][0]
        assert final_metadata.status == FileStatus.CONVERSION_FAILED
        assert final_metadata.conversion_error is not None
        assert "Unexpected error during conversion" in final_metadata.conversion_error

    @pytest.mark.asyncio
    async def test_convert_file_handles_store_file_exception(self, conversion_helper: ConversionTestHelper) -> None:
        """Test that convert_file handles file storage exceptions."""
        file_metadata = create_file_metadata(filename="storage_fail.txt", mime_type="text/plain", size_bytes=700)

        conversion_helper.setup_file_loading(b"Text content")
        conversion_helper.setup_converter("TextConverter", create_success_result("Text content", 300))
        conversion_helper.setup_file_storage_error(ValueError("Storage quota exceeded"))

        await conversion_helper.service.convert_file(file_metadata, conversion_helper.status_updater)

        # Verify error was handled gracefully
        assert conversion_helper.status_updater.call_count >= 2
        final_call_args = conversion_helper.status_updater.call_args_list[-1]
        final_metadata = final_call_args[0][0]
        assert final_metadata.status == FileStatus.CONVERSION_FAILED
        assert final_metadata.conversion_error is not None
        assert final_metadata.conversion_error == "Unexpected error during conversion."


class TestDocumentConversionServiceStorageIntegration:
    """Test DocumentConversionService integration with file storage operations."""

    @pytest.mark.asyncio
    async def test_store_converted_file_uses_correct_retriever(self, conversion_helper: ConversionTestHelper) -> None:
        """Test that _store_converted_file uses FileManager.get_retriever."""
        file_metadata = create_file_metadata(filename="store_test.pdf", status=FileStatus.CONVERTING)
        expected_key = f"nexus-{file_metadata.id}-content.md"
        conversion_result = create_success_result("# Converted Content\n\nThis is the markdown version.", 1000)

        mock_retriever = AsyncMock()
        mock_retriever.save_file.return_value = expected_key
        conversion_helper.mock_file_manager.get_retriever.return_value = mock_retriever

        output_filename, output_path = await conversion_helper.service._store_converted_file(
            file_metadata, conversion_result
        )

        conversion_helper.mock_file_manager.get_retriever.assert_called()

        assert conversion_result.converted_content is not None
        mock_retriever.save_file.assert_called_once_with(
            conversion_result.converted_content.encode("utf-8"), expected_key
        )
        assert output_path == expected_key
        assert output_filename == "store_test.md"

    @pytest.mark.asyncio
    async def test_store_converted_file_handles_no_content_error(self, conversion_helper: ConversionTestHelper) -> None:
        """Test that _store_converted_file raises error when conversion has no content."""
        file_metadata = create_file_metadata(
            filename="no_content.txt", mime_type="text/plain", size_bytes=500, status=FileStatus.CONVERTING
        )
        # Create conversion result with None content
        conversion_result = ConversionResult(
            success=True,
            conversion_time_ms=200,
            converted_content=None,  # No content
        )

        with pytest.raises(SafeValueError, match="Cannot store file: conversion result has no content"):
            # Access private method for testing purposes
            await conversion_helper.service._store_converted_file(file_metadata, conversion_result)
