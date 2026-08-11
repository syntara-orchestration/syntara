"""Test for PDFConverter functionality."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from syntara.files.document_conversion.converters.pdf_converter import (
    PDFConverter,
)
from syntara.files.document_conversion.models.conversion_result import (
    ConversionResult,
)
from syntara.files.models import FileMetadata


class TestPDFConverterMimeTypeSupport:
    """Test MIME type support in PDFConverter."""

    def test_supported_mime_types_includes_pdf(self) -> None:
        """Test that supported_mime_types returns PDF format."""
        converter = PDFConverter()
        supported = converter.supported_mime_types()

        assert "application/pdf" in supported
        assert len(supported) == 1

    def test_supports_mime_type_returns_true_for_pdf(self) -> None:
        """Test that PDF MIME type is supported."""
        converter = PDFConverter()
        assert converter.supports_mime_type("application/pdf") is True

    def test_supports_mime_type_returns_false_for_unsupported_formats(self) -> None:
        """Test that unsupported MIME types return False."""
        converter = PDFConverter()

        unsupported_types = [
            "image/jpeg",
            "text/plain",
            "application/zip",
            "video/mp4",
            "text/markdown",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]

        for mime_type in unsupported_types:
            assert converter.supports_mime_type(mime_type) is False


class TestPDFConverterThreadOffloading:
    """Test that PDFConverter offloads blocking work to a thread pool."""

    @pytest.mark.asyncio
    @patch("syntara.files.document_conversion.converters.pdf_converter.asyncio.to_thread")
    async def test_convert_runs_in_thread_pool(self, mock_to_thread: AsyncMock) -> None:
        """Test that convert() offloads sync work via asyncio.to_thread."""
        file_metadata = Mock()
        file_metadata.mime_type = "application/pdf"

        mock_to_thread.return_value = ConversionResult.success_result("# PDF content", 0)

        converter = PDFConverter()
        result = await converter.convert(b"pdf content", file_metadata)

        mock_to_thread.assert_called_once_with(converter._convert_sync, b"pdf content", "application/pdf")
        assert result.success is True


class TestPDFConverterConversion:
    """Test conversion functionality in PDFConverter."""

    @pytest.mark.asyncio
    async def test_unsupported_mime_type_returns_failure(self) -> None:
        """Test that unsupported MIME types return failure result."""
        file_metadata = Mock()
        file_metadata.mime_type = "image/jpeg"

        converter = PDFConverter()
        result = await converter.convert(b"fake image content", file_metadata)

        assert result.success is False
        assert result.error_type == "unsupported_format"
        assert result.error_message
        assert result.error_message is not None
        assert "Unsupported MIME type: image/jpeg" in result.error_message


class TestPDFConverterWithRealFiles:
    """Test PDFConverter with actual files from fixtures directory."""

    @pytest.fixture
    def fixtures_dir(self) -> Path:
        from tests.fixtures.files import get_fixtures_dir

        return get_fixtures_dir()

    @pytest.mark.asyncio
    async def test_real_pdf_conversion(self, fixtures_dir: Path) -> None:
        """Test conversion with a real PDF file from fixtures."""
        pdf_path = fixtures_dir / "sample.pdf"
        assert pdf_path.exists(), f"PDF fixture not found at {pdf_path}"

        # Read the real PDF file
        with pdf_path.open("rb") as f:
            pdf_content = f.read()

        # Create FileMetadata instance
        file_metadata = FileMetadata(
            filename="sample.pdf",
            size_bytes=len(pdf_content),
            mime_type="application/pdf",
            file_path=str(pdf_path),
        )

        converter = PDFConverter()
        result = await converter.convert(pdf_content, file_metadata)

        # Should succeed with actual conversion
        assert result.success is True
        assert result.converted_content
        assert isinstance(result.converted_content, str)
        assert len(result.converted_content) > 0

        # Should contain expected metadata
        assert result.metadata["input_format"] == "pdf"
        assert result.metadata["converter"] == "pypdf"
        assert result.metadata["mime_type"] == "application/pdf"
        assert result.metadata["page_count"] == 1

        # Should contain some recognizable content from the PDF
        content_lower = result.converted_content.lower()
        assert "sample" in content_lower or "pdf" in content_lower
