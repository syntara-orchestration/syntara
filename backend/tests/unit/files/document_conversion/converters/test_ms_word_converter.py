"""Test for MSWordConverter functionality."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from syntara.files.document_conversion.converters.ms_word_converter import (
    MSWordConverter,
)
from syntara.files.document_conversion.models.conversion_result import (
    ConversionResult,
)
from syntara.files.models import FileMetadata


class TestMSWordConverterMimeTypeSupport:
    """Test MIME type support in MSWordConverter."""

    def test_supported_mime_types_includes_expected_formats(self) -> None:
        """Test that supported_mime_types returns expected document formats."""
        converter = MSWordConverter()
        supported = converter.supported_mime_types()

        expected_types = [
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]

        assert all(mime_type in supported for mime_type in expected_types)
        assert len(supported) == 2

    def test_supports_mime_type_returns_false_for_pdf(self) -> None:
        """Test that PDF MIME type is NOT supported (handled by separate PDF converter)."""
        converter = MSWordConverter()
        assert converter.supports_mime_type("application/pdf") is False

    def test_supports_mime_type_returns_true_for_doc(self) -> None:
        """Test that DOC MIME type is supported."""
        converter = MSWordConverter()
        assert converter.supports_mime_type("application/msword") is True

    def test_supports_mime_type_returns_true_for_docx(self) -> None:
        """Test that DOCX MIME type is supported."""
        converter = MSWordConverter()
        docx_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert converter.supports_mime_type(docx_type) is True

    def test_supports_mime_type_returns_false_for_unsupported_formats(self) -> None:
        """Test that unsupported MIME types return False."""
        converter = MSWordConverter()

        unsupported_types = [
            "application/pdf",
            "image/jpeg",
            "text/plain",
            "application/zip",
            "video/mp4",
            "text/markdown",
        ]

        for mime_type in unsupported_types:
            assert converter.supports_mime_type(mime_type) is False


class TestMSWordConverterThreadOffloading:
    """Test that MSWordConverter offloads blocking work to a thread pool."""

    @pytest.mark.asyncio
    @patch("syntara.files.document_conversion.converters.ms_word_converter.asyncio.to_thread")
    async def test_convert_runs_in_thread_pool(self, mock_to_thread: AsyncMock) -> None:
        """Test that convert() offloads sync work via asyncio.to_thread."""
        file_metadata = Mock()
        file_metadata.mime_type = "application/msword"
        file_metadata.filename = "test.doc"

        mock_to_thread.return_value = ConversionResult.success_result("# Test", 0)

        converter = MSWordConverter()
        result = await converter.convert(b"test content", file_metadata)

        mock_to_thread.assert_called_once_with(
            converter._convert_sync, b"test content", "application/msword", "test.doc"
        )
        assert result.success is True


class TestMSWordConverterConversion:
    """Test conversion functionality in MSWordConverter."""

    @pytest.mark.asyncio
    @patch("syntara.files.document_conversion.converters.ms_word_converter.pypandoc.convert_file")
    @patch("syntara.files.document_conversion.converters.ms_word_converter.tempfile.NamedTemporaryFile")
    async def test_successful_docx_conversion(self, mock_tempfile, mock_convert_file) -> None:
        """Test successful DOCX to markdown conversion."""
        file_metadata = Mock()
        file_metadata.mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        file_metadata.filename = "test.docx"

        temp_dir = tempfile.gettempdir()
        mock_temp_file = Mock()
        mock_temp_file.name = f"{temp_dir}/test.docx"
        mock_tempfile.return_value.__enter__ = Mock(return_value=mock_temp_file)
        mock_tempfile.return_value.__exit__ = Mock(return_value=None)

        expected_markdown = "# Word Document\n\nConverted from DOCX."
        mock_convert_file.return_value = expected_markdown

        converter = MSWordConverter()
        result = await converter.convert(b"fake docx content", file_metadata)

        assert result.success is True
        assert result.converted_content == expected_markdown
        assert result.metadata["input_format"] == "docx"

    @pytest.mark.asyncio
    async def test_unsupported_mime_type_returns_failure(self) -> None:
        """Test that unsupported MIME types return failure result."""
        file_metadata = Mock()
        file_metadata.mime_type = "image/jpeg"

        converter = MSWordConverter()
        result = await converter.convert(b"fake image content", file_metadata)

        assert result.success is False
        assert result.error_type == "unsupported_format"
        assert result.error_message
        assert result.error_message is not None
        assert "Unsupported MIME type: image/jpeg" in result.error_message

    @pytest.mark.asyncio
    @patch("syntara.files.document_conversion.converters.ms_word_converter.pypandoc.convert_file")
    @patch("syntara.files.document_conversion.converters.ms_word_converter.tempfile.NamedTemporaryFile")
    async def test_runtime_error_handling(self, mock_tempfile, mock_convert_file) -> None:
        """Test handling of pypandoc RuntimeError exceptions."""
        file_metadata = Mock()
        file_metadata.mime_type = "application/msword"

        temp_dir = tempfile.gettempdir()
        mock_temp_file = Mock()
        mock_temp_file.name = f"{temp_dir}/test.doc"
        mock_tempfile.return_value.__enter__ = Mock(return_value=mock_temp_file)
        mock_tempfile.return_value.__exit__ = Mock(return_value=None)

        # Mock pypandoc raising RuntimeError
        mock_convert_file.side_effect = RuntimeError("The file appears to be corrupted")

        converter = MSWordConverter()
        result = await converter.convert(b"corrupted content", file_metadata)

        assert result.success is False
        assert result.error_type == "corruption"
        assert result.error_message
        assert result.error_message is not None
        assert "The file appears to be corrupted" in result.error_message

    @pytest.mark.asyncio
    @patch("syntara.files.document_conversion.converters.ms_word_converter.pypandoc.convert_file")
    @patch("syntara.files.document_conversion.converters.ms_word_converter.tempfile.NamedTemporaryFile")
    async def test_memory_error_handling(self, mock_tempfile, mock_convert_file) -> None:
        """Test handling of MemoryError exceptions."""
        file_metadata = Mock()
        file_metadata.mime_type = "application/msword"

        temp_dir = tempfile.gettempdir()
        mock_temp_file = Mock()
        mock_temp_file.name = f"{temp_dir}/test.doc"
        mock_tempfile.return_value.__enter__ = Mock(return_value=mock_temp_file)
        mock_tempfile.return_value.__exit__ = Mock(return_value=None)

        # Mock pypandoc raising MemoryError
        mock_convert_file.side_effect = MemoryError()

        converter = MSWordConverter()
        result = await converter.convert(b"large content", file_metadata)

        assert result.success is False
        assert result.error_type == "memory_exhausted"
        assert result.error_message
        assert result.error_message is not None
        assert "Insufficient memory to process document" in result.error_message

    @pytest.mark.asyncio
    @patch("syntara.files.document_conversion.converters.ms_word_converter.pypandoc.convert_file")
    @patch("syntara.files.document_conversion.converters.ms_word_converter.tempfile.NamedTemporaryFile")
    async def test_os_error_handling(self, mock_tempfile, mock_convert_file) -> None:
        """Test handling of OSError exceptions."""
        file_metadata = Mock()
        file_metadata.mime_type = "application/msword"

        temp_dir = tempfile.gettempdir()
        mock_temp_file = Mock()
        mock_temp_file.name = f"{temp_dir}/test.doc"
        mock_tempfile.return_value.__enter__ = Mock(return_value=mock_temp_file)
        mock_tempfile.return_value.__exit__ = Mock(return_value=None)

        # Mock pypandoc raising OSError
        mock_convert_file.side_effect = OSError("Disk full")

        converter = MSWordConverter()
        result = await converter.convert(b"test content", file_metadata)

        assert result.success is False
        assert result.error_type == "conversion_error"
        assert result.error_message
        assert result.error_message is not None
        assert result.error_message == "Unexpected error during document conversion."
        assert result.metadata["exception_type"] == "OSError"

    @pytest.mark.asyncio
    @patch("syntara.files.document_conversion.converters.ms_word_converter.Path.unlink")
    @patch("syntara.files.document_conversion.converters.ms_word_converter.Path.exists")
    @patch("syntara.files.document_conversion.converters.ms_word_converter.pypandoc.convert_file")
    @patch("syntara.files.document_conversion.converters.ms_word_converter.tempfile.NamedTemporaryFile")
    async def test_temporary_file_cleanup(self, mock_tempfile, mock_convert_file, mock_exists, mock_unlink) -> None:
        """Test that temporary files are cleaned up after conversion."""
        file_metadata = Mock()
        file_metadata.mime_type = "application/msword"

        temp_dir = tempfile.gettempdir()
        mock_temp_file = Mock()
        mock_temp_file.name = f"{temp_dir}/test.doc"
        mock_tempfile.return_value.__enter__ = Mock(return_value=mock_temp_file)
        mock_tempfile.return_value.__exit__ = Mock(return_value=None)

        mock_convert_file.return_value = "# Test"
        mock_exists.return_value = True

        converter = MSWordConverter()
        result = await converter.convert(b"test content", file_metadata)

        assert result.success is True
        mock_unlink.assert_called_once()

    @pytest.mark.asyncio
    @patch("syntara.files.document_conversion.converters.ms_word_converter.Path.unlink")
    @patch("syntara.files.document_conversion.converters.ms_word_converter.Path.exists")
    @patch("syntara.files.document_conversion.converters.ms_word_converter.pypandoc.convert_file")
    @patch("syntara.files.document_conversion.converters.ms_word_converter.tempfile.NamedTemporaryFile")
    async def test_cleanup_handles_missing_temp_file_gracefully(
        self, mock_tempfile, mock_convert_file, mock_exists, mock_unlink
    ) -> None:
        """Test that cleanup handles missing temporary files gracefully."""
        file_metadata = Mock()
        file_metadata.mime_type = "application/msword"

        temp_dir = tempfile.gettempdir()
        mock_temp_file = Mock()
        mock_temp_file.name = f"{temp_dir}/test.doc"
        mock_tempfile.return_value.__enter__ = Mock(return_value=mock_temp_file)
        mock_tempfile.return_value.__exit__ = Mock(return_value=None)

        mock_convert_file.return_value = "# Test"
        mock_exists.return_value = False  # File already gone

        converter = MSWordConverter()
        result = await converter.convert(b"test content", file_metadata)

        assert result.success is True
        mock_unlink.assert_not_called()


class TestMSWordConverterDocumentFormatHandling:
    """Test handling of specific document format scenarios."""

    @pytest.mark.asyncio
    async def test_doc_format_support(self) -> None:
        """Test support for legacy DOC format."""
        file_metadata = Mock()
        file_metadata.mime_type = "application/msword"

        converter = MSWordConverter()

        # Should recognize format
        assert converter.supports_mime_type(file_metadata.mime_type) is True

    @pytest.mark.asyncio
    async def test_docx_format_handling(self) -> None:
        """Test comprehensive DOCX format handling."""
        docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        file_metadata = Mock()
        file_metadata.mime_type = docx_mime

        converter = MSWordConverter()

        # Should handle full DOCX MIME type correctly
        assert converter.supports_mime_type(docx_mime) is True

    @pytest.mark.asyncio
    @patch("syntara.files.document_conversion.converters.ms_word_converter.pypandoc.convert_file")
    @patch("syntara.files.document_conversion.converters.ms_word_converter.tempfile.NamedTemporaryFile")
    async def test_password_protected_document_handling(self, mock_tempfile, mock_convert_file) -> None:
        """Test handling of password-protected documents."""
        file_metadata = Mock()
        file_metadata.mime_type = "application/msword"

        temp_dir = tempfile.gettempdir()
        mock_temp_file = Mock()
        mock_temp_file.name = f"{temp_dir}/test.doc"
        mock_tempfile.return_value.__enter__ = Mock(return_value=mock_temp_file)
        mock_tempfile.return_value.__exit__ = Mock(return_value=None)

        # Mock pypandoc error for password protection
        mock_convert_file.side_effect = RuntimeError("Document is password protected")

        converter = MSWordConverter()
        result = await converter.convert(b"protected content", file_metadata)

        assert result.success is False
        assert result.error_type == "password_protected"
        assert result.error_message
        assert result.error_message is not None
        assert "password protected" in result.error_message.lower()

    @pytest.mark.asyncio
    @patch("syntara.files.document_conversion.converters.ms_word_converter.pypandoc.convert_file")
    @patch("syntara.files.document_conversion.converters.ms_word_converter.tempfile.NamedTemporaryFile")
    async def test_pandoc_not_installed_handling(self, mock_tempfile, mock_convert_file) -> None:
        """Test handling when pandoc is not installed."""
        file_metadata = Mock()
        file_metadata.mime_type = "application/msword"

        temp_dir = tempfile.gettempdir()
        mock_temp_file = Mock()
        mock_temp_file.name = f"{temp_dir}/test.doc"
        mock_tempfile.return_value.__enter__ = Mock(return_value=mock_temp_file)
        mock_tempfile.return_value.__exit__ = Mock(return_value=None)

        # Mock pypandoc error for missing dependency
        mock_convert_file.side_effect = RuntimeError("pandoc not found in PATH")

        converter = MSWordConverter()
        result = await converter.convert(b"test content", file_metadata)

        assert result.success is False
        assert result.error_type == "dependency_missing"
        assert result.error_message
        assert result.error_message is not None
        assert "not found" in result.error_message.lower()


class TestMSWordConverterWithRealFiles:
    """Test MSWordConverter with actual files from fixtures directory."""

    @pytest.fixture
    def fixtures_dir(self) -> Path:
        from tests.fixtures.files import get_fixtures_dir

        return get_fixtures_dir()

    @pytest.mark.asyncio
    async def test_real_docx_conversion(self, fixtures_dir: Path) -> None:
        """Test conversion with a real DOCX file from fixtures."""
        docx_path = fixtures_dir / "sample.docx"
        assert docx_path.exists(), f"DOCX fixture not found at {docx_path}"

        # Read the real DOCX file
        with docx_path.open("rb") as f:
            docx_content = f.read()

        # Create FileMetadata instance
        file_metadata = FileMetadata(
            filename="sample.docx",
            size_bytes=len(docx_content),
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            file_path=str(docx_path),
        )

        converter = MSWordConverter()
        result = await converter.convert(docx_content, file_metadata)

        # Should succeed with actual conversion
        assert result.success is True
        assert result.converted_content
        assert isinstance(result.converted_content, str)
        assert len(result.converted_content) > 0

        # Should contain expected metadata
        assert result.metadata["input_format"] == "docx"
        assert result.metadata["converter"] == "pypandoc"
        assert result.metadata["mime_type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        # Converted content should be markdown format
        # At minimum should not be empty and should have some text
        assert len(result.converted_content.strip()) > 0
