"""Test for TextConverter functionality."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from syntara.files.document_conversion.converters.text_converter import (
    TextConverter,
)
from syntara.files.models import FileMetadata


class TestTextConverterMimeTypeSupport:
    """Test MIME type support in TextConverter."""

    def test_supported_mime_types_includes_only_text_plain(self) -> None:
        """Test that supported_mime_types returns only text/plain MIME type."""
        converter = TextConverter()
        supported = converter.supported_mime_types()

        assert supported == ["text/plain"]
        assert len(supported) == 1

    def test_supports_mime_type_returns_true_for_text_plain(self) -> None:
        """Test that text/plain MIME type is supported."""
        converter = TextConverter()
        assert converter.supports_mime_type("text/plain") is True

    def test_supports_mime_type_returns_false_for_other_formats(self) -> None:
        """Test that non-text-plain MIME types return False."""
        converter = TextConverter()

        unsupported_types = [
            "text/markdown",
            "application/pdf",
            "application/msword",
            "image/jpeg",
            "text/html",
            "application/json",
            "text/csv",
        ]

        for mime_type in unsupported_types:
            assert converter.supports_mime_type(mime_type) is False


class TestTextConverterBasicConversion:
    """Test basic text to markdown conversion functionality."""

    @pytest.mark.asyncio
    async def test_simple_text_conversion(self) -> None:
        """Test conversion of simple plain text."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"
        file_metadata.filename = "test.txt"

        text_content = "Hello World\n\nThis is a simple text file."
        content_bytes = text_content.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content
        assert "Hello World" in result.converted_content
        assert "This is a simple text file" in result.converted_content
        assert result.metadata["converter"] == "text_to_markdown"
        assert result.metadata["mime_type"] == "text/plain"
        assert result.metadata["original_size_bytes"] == len(content_bytes)

    @pytest.mark.asyncio
    async def test_single_paragraph_text(self) -> None:
        """Test conversion of single paragraph text."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        text_content = "This is a single paragraph of text without line breaks."
        content_bytes = text_content.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        # Periods are escaped in markdown conversion
        expected_content = "This is a single paragraph of text without line breaks\\."
        assert result.converted_content
        assert result.converted_content == expected_content
        assert result.metadata["converted_size_chars"] == len(result.converted_content)

    @pytest.mark.asyncio
    async def test_multiple_paragraphs_conversion(self) -> None:
        """Test conversion of text with multiple paragraphs."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        text_content = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        content_bytes = text_content.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        # Periods are escaped in markdown conversion
        assert result.converted_content
        assert "First paragraph\\." in result.converted_content
        assert "Second paragraph\\." in result.converted_content
        assert "Third paragraph\\." in result.converted_content
        # Should maintain paragraph separation
        assert result.converted_content.count("\n\n") == 2

    @pytest.mark.asyncio
    async def test_empty_text_conversion(self) -> None:
        """Test conversion of empty text content."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        empty_content = ""
        content_bytes = empty_content.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content is not None
        assert result.converted_content == ""
        assert result.metadata["original_size_bytes"] == 0
        assert result.metadata["converted_size_chars"] == 0

    @pytest.mark.asyncio
    async def test_whitespace_only_text_conversion(self) -> None:
        """Test conversion of whitespace-only text."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        whitespace_content = "   \n\n   \n   "
        content_bytes = whitespace_content.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        # Whitespace-only paragraphs should be filtered out
        assert result.converted_content == ""


class TestTextConverterMarkdownEscaping:
    """Test markdown character escaping in TextConverter."""

    @pytest.mark.asyncio
    async def test_asterisk_escaping(self) -> None:
        """Test that asterisks are properly escaped."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        text_content = "This text has *asterisks* that should be escaped."
        content_bytes = text_content.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content
        assert r"\*asterisks\*" in result.converted_content
        assert "*asterisks*" not in result.converted_content

    @pytest.mark.asyncio
    async def test_underscore_escaping(self) -> None:
        """Test that underscores are properly escaped."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        text_content = "Text with _underscores_ for emphasis."
        content_bytes = text_content.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content
        assert r"\_underscores\_" in result.converted_content

    @pytest.mark.asyncio
    async def test_hash_symbol_escaping(self) -> None:
        """Test that hash symbols are properly escaped."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        text_content = "# This looks like a header but should be escaped."
        content_bytes = text_content.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content
        assert r"\# This looks like a header" in result.converted_content

    @pytest.mark.asyncio
    async def test_backtick_escaping(self) -> None:
        """Test that backticks are properly escaped."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        text_content = "Code like `print('hello')` should be escaped."
        content_bytes = text_content.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content
        assert r"\`print\('hello'\)\`" in result.converted_content

    @pytest.mark.asyncio
    async def test_bracket_escaping(self) -> None:
        """Test that brackets are properly escaped."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        text_content = "Links like [example](http://example.com) should be escaped."
        content_bytes = text_content.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content
        assert r"\[example\]\(http://example\.com\)" in result.converted_content

    @pytest.mark.asyncio
    async def test_multiple_special_characters_escaping(self) -> None:
        """Test escaping of multiple markdown special characters."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        text_content = "Text with *bold*, _italic_, `code`, [link], #header, >quote, and ~strikethrough~."
        content_bytes = text_content.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        # Verify all special characters are escaped
        assert result.converted_content
        assert r"\*bold\*" in result.converted_content
        assert r"\_italic\_" in result.converted_content
        assert r"\`code\`" in result.converted_content
        assert r"\[link\]" in result.converted_content
        assert r"\#header" in result.converted_content
        assert r"\>quote" in result.converted_content
        assert r"\~strikethrough\~" in result.converted_content


class TestTextConverterEncodingHandling:
    """Test text encoding detection and handling."""

    @pytest.mark.asyncio
    async def test_utf8_encoding_detection(self) -> None:
        """Test proper handling of UTF-8 encoded text."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        # UTF-8 text with Unicode characters
        unicode_text = "Hello 世界! This is UTF-8 text with émojis 🎉."
        content_bytes = unicode_text.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content
        assert "世界" in result.converted_content
        assert "émojis" in result.converted_content
        assert "🎉" in result.converted_content

    @pytest.mark.asyncio
    async def test_latin1_encoding_fallback(self) -> None:
        """Test fallback to Latin-1 encoding when UTF-8 fails."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        # Latin-1 encoded text that would fail UTF-8 decoding
        latin1_text = "Café with naïve characters"
        content_bytes = latin1_text.encode("latin-1")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content
        assert "Café" in result.converted_content
        assert "naïve" in result.converted_content

    @pytest.mark.asyncio
    async def test_cp1252_encoding_fallback(self) -> None:
        """Test fallback to CP1252 encoding."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        # CP1252 text with Windows-specific characters
        cp1252_text = "Smart quotes and em-dashes"
        content_bytes = cp1252_text.encode("cp1252")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content

    @pytest.mark.asyncio
    async def test_invalid_encoding_error_replacement(self) -> None:
        """Test handling of completely invalid byte sequences."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        # Random bytes that don't form valid text in any encoding
        invalid_bytes = bytes([0xFF, 0xFE, 0x00, 0x00, 0x80, 0x81])

        converter = TextConverter()
        result = await converter.convert(invalid_bytes, file_metadata)

        # Should still succeed with replacement characters
        assert result.success is True
        assert result.converted_content


class TestTextConverterLineEndingHandling:
    """Test handling of different line ending formats."""

    @pytest.mark.asyncio
    async def test_windows_line_endings_normalization(self) -> None:
        """Test normalization of Windows (CRLF) line endings."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        windows_text = "Line one\r\n\r\nLine two\r\n"
        content_bytes = windows_text.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content
        assert "\r\n" not in result.converted_content
        assert "Line one\n\nLine two" in result.converted_content

    @pytest.mark.asyncio
    async def test_mac_line_endings_normalization(self) -> None:
        """Test normalization of classic Mac (CR) line endings."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        mac_text = "Line one\r\rLine two\r"
        content_bytes = mac_text.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content
        assert "\r" not in result.converted_content
        assert "Line one\n\nLine two" in result.converted_content

    @pytest.mark.asyncio
    async def test_mixed_line_endings_normalization(self) -> None:
        """Test normalization of mixed line ending formats."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        mixed_text = "Unix line\n\nWindows line\r\n\rMac line\r"
        content_bytes = mixed_text.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        # All should be normalized to Unix line endings
        assert result.converted_content
        assert "\r\n" not in result.converted_content
        assert "\r" not in result.converted_content


class TestTextConverterErrorHandling:
    """Test error handling in TextConverter."""

    @pytest.mark.asyncio
    @patch("syntara.files.document_conversion.converters.text_converter.TextConverter._decode_text_content")
    async def test_memory_error_handling(self, mock_decode) -> None:
        """Test handling of MemoryError during conversion."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        # Mock the _decode_text_content method to raise MemoryError
        mock_decode.side_effect = MemoryError("Out of memory")

        converter = TextConverter()
        result = await converter.convert(b"test content", file_metadata)

        assert result.success is False
        assert result.error_type == "memory_exhausted"
        assert result.error_message
        assert "File too large to process" in result.error_message

    @pytest.mark.asyncio
    @patch("syntara.files.document_conversion.converters.text_converter.TextConverter._convert_to_markdown")
    async def test_os_error_handling(self, mock_convert) -> None:
        """Test handling of OSError during conversion."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        # Mock the _convert_to_markdown method to raise OSError
        mock_convert.side_effect = OSError("Disk full")

        converter = TextConverter()
        result = await converter.convert(b"test content", file_metadata)

        assert result.success is False
        assert result.error_type == "conversion_error"
        assert result.error_message
        assert result.error_message == "Unexpected error during document conversion."
        assert result.metadata["exception_type"] == "OSError"

    @pytest.mark.asyncio
    @patch("syntara.files.document_conversion.converters.text_converter.TextConverter._convert_to_markdown")
    async def test_value_error_handling(self, mock_convert) -> None:
        """Test handling of ValueError during conversion."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        # Mock the _convert_to_markdown method to raise ValueError
        mock_convert.side_effect = ValueError("Invalid input")

        converter = TextConverter()
        result = await converter.convert(b"test content", file_metadata)

        assert result.success is False
        assert result.error_type == "conversion_error"
        assert result.error_message
        assert result.error_message == "Unexpected error during document conversion."
        assert result.metadata["exception_type"] == "ValueError"


class TestTextConverterMetadata:
    """Test metadata handling in TextConverter."""

    @pytest.mark.asyncio
    async def test_metadata_includes_expected_fields(self) -> None:
        """Test that result metadata includes all expected fields."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"
        file_metadata.filename = "test.txt"

        content = "Test content"
        content_bytes = content.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.metadata
        assert result.converted_content
        assert "converter" in result.metadata
        assert "mime_type" in result.metadata
        assert "original_size_bytes" in result.metadata
        assert "converted_size_chars" in result.metadata

        assert result.metadata["converter"] == "text_to_markdown"
        assert result.metadata["mime_type"] == "text/plain"
        assert result.metadata["original_size_bytes"] == len(content_bytes)
        assert result.metadata["converted_size_chars"] == len(result.converted_content)

    @pytest.mark.asyncio
    async def test_size_metadata_accuracy(self) -> None:
        """Test accuracy of size measurements in metadata."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        test_cases = [
            "",  # Empty
            "Short text",  # Short
            "Much longer text content with multiple words",  # Longer
            "Unicode: 测试 🎉 with émojis",  # Unicode
        ]

        converter = TextConverter()

        for content in test_cases:
            content_bytes = content.encode("utf-8")
            result = await converter.convert(content_bytes, file_metadata)

            assert result.success is True
            assert result.converted_content is not None
            assert result.metadata["original_size_bytes"] == len(content_bytes)
            assert result.metadata["converted_size_chars"] == len(result.converted_content)


class TestTextConverterDocumentConversionIntegration:
    """Test integration patterns with document conversion system."""

    @pytest.mark.asyncio
    async def test_conversion_time_not_measured_in_converter(self) -> None:
        """Test that conversion_time_ms is set to 0 (timing handled by base class)."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        content = "Test conversion timing"
        content_bytes = content.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.conversion_time_ms == 0

    @pytest.mark.asyncio
    async def test_large_text_file_handling(self) -> None:
        """Test handling of larger text files."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        # Create a larger text document
        large_content = "This is a paragraph.\n\n" * 1000
        large_content += "Final paragraph with special characters: *bold* and _italic_."

        content_bytes = large_content.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content
        assert len(result.converted_content) > 10000  # Sanity check for size
        assert result.metadata["original_size_bytes"] == len(content_bytes)
        # Should have escaped special characters
        assert r"\*bold\*" in result.converted_content
        assert r"\_italic\_" in result.converted_content

    @pytest.mark.asyncio
    async def test_code_snippet_preservation(self) -> None:
        """Test that code snippets in text are properly escaped."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        code_text = """Here is some code:

def hello_world():
    print("Hello, World!")
    return True

The function uses *args and **kwargs parameters."""

        content_bytes = code_text.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        # Code structure should be preserved but special chars escaped
        assert result.converted_content
        assert r"def hello\_world\(\):" in result.converted_content
        assert r"\*args and \*\*kwargs" in result.converted_content
        assert "print" in result.converted_content

    @pytest.mark.asyncio
    async def test_configuration_file_content_handling(self) -> None:
        """Test handling of configuration file-like content."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/plain"

        config_text = """# Configuration file
server.port=8080
database.url=postgresql://localhost:5432/mydb
features.enabled=[feature1, feature2]

# Comments should be preserved
debug.mode=true"""

        content_bytes = config_text.encode("utf-8")

        converter = TextConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        # Comments and config syntax should be escaped
        assert result.converted_content
        assert r"\# Configuration file" in result.converted_content
        assert r"server\.port=8080" in result.converted_content
        assert r"\[feature1, feature2\]" in result.converted_content


class TestTextConverterWithRealFiles:
    """Test TextConverter with actual files from fixtures directory."""

    @pytest.fixture
    def fixtures_dir(self) -> Path:
        from tests.fixtures.files import get_fixtures_dir

        return get_fixtures_dir()

    @pytest.mark.asyncio
    async def test_real_text_conversion(self, fixtures_dir: Path) -> None:
        """Test conversion with a real text file from fixtures."""
        txt_path = fixtures_dir / "sample.txt"
        assert txt_path.exists(), f"Text fixture not found at {txt_path}"

        # Read the real text file
        with txt_path.open("rb") as f:
            txt_content = f.read()

        # Create FileMetadata instance
        file_metadata = FileMetadata(
            filename="sample.txt",
            size_bytes=len(txt_content),
            mime_type="text/plain",
            file_path=str(txt_path),
        )

        converter = TextConverter()
        result = await converter.convert(txt_content, file_metadata)

        # Should succeed with conversion
        assert result.success is True
        assert result.converted_content
        assert isinstance(result.converted_content, str)
        assert len(result.converted_content) > 0

        # Should contain expected metadata
        assert result.metadata["converter"] == "text_to_markdown"
        assert result.metadata["mime_type"] == "text/plain"
        assert result.metadata["original_size_bytes"] == len(txt_content)
        assert result.metadata["converted_size_chars"] == len(result.converted_content)

        # Content should be converted from text to markdown
        original_text = txt_content.decode("utf-8", errors="replace")
        assert len(result.converted_content) >= len(original_text)  # May be longer due to escaping
