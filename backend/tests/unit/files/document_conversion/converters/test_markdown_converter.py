"""Test for MarkdownConverter functionality."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from syntara.files.document_conversion.converters.markdown_converter import (
    MarkdownConverter,
)
from syntara.files.models import FileMetadata


class TestMarkdownConverterMimeTypeSupport:
    """Test MIME type support in MarkdownConverter."""

    def test_supported_mime_types_includes_only_markdown(self) -> None:
        """Test that supported_mime_types returns only markdown MIME type."""
        converter = MarkdownConverter()
        supported = converter.supported_mime_types()

        assert supported == ["text/markdown"]
        assert len(supported) == 1

    def test_supports_mime_type_returns_true_for_markdown(self) -> None:
        """Test that markdown MIME type is supported."""
        converter = MarkdownConverter()
        assert converter.supports_mime_type("text/markdown") is True

    def test_supports_mime_type_returns_false_for_other_formats(self) -> None:
        """Test that non-markdown MIME types return False."""
        converter = MarkdownConverter()

        unsupported_types = [
            "text/plain",
            "application/pdf",
            "application/msword",
            "image/jpeg",
            "text/html",
            "application/json",
        ]

        for mime_type in unsupported_types:
            assert converter.supports_mime_type(mime_type) is False


class TestMarkdownConverterConversion:
    """Test conversion functionality in MarkdownConverter."""

    @pytest.mark.asyncio
    async def test_successful_markdown_passthrough(self) -> None:
        """Test successful passthrough of markdown content."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/markdown"
        file_metadata.filename = "test.md"

        markdown_content = "# Test Document\n\nThis is **bold** text and _italic_ text."
        content_bytes = markdown_content.encode("utf-8")

        converter = MarkdownConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content == markdown_content
        assert result.metadata["converter"] == "markdown_passthrough"
        assert result.metadata["mime_type"] == "text/markdown"
        assert result.metadata["original_size_bytes"] == len(content_bytes)

    @pytest.mark.asyncio
    async def test_complex_markdown_content_passthrough(self) -> None:
        """Test passthrough of complex markdown with various elements."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/markdown"

        complex_markdown = """# Main Title

## Subtitle

This is a paragraph with **bold** and *italic* text.

### Code Example

```python
def hello_world():
    print("Hello, World!")
```

### List Items

- Item 1
- Item 2
  - Nested item
- Item 3

[Link to example](https://example.com)

> This is a blockquote
> with multiple lines.

| Table | Column |
|-------|--------|
| Data  | Value  |
"""

        content_bytes = complex_markdown.encode("utf-8")

        converter = MarkdownConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content == complex_markdown
        assert "Code Example" in result.converted_content
        assert "```python" in result.converted_content
        assert "| Table | Column |" in result.converted_content

    @pytest.mark.asyncio
    async def test_empty_markdown_content(self) -> None:
        """Test handling of empty markdown content."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/markdown"

        empty_content = ""
        content_bytes = empty_content.encode("utf-8")

        converter = MarkdownConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content == ""
        assert result.metadata["original_size_bytes"] == 0

    @pytest.mark.asyncio
    async def test_markdown_with_unicode_characters(self) -> None:
        """Test handling of markdown with Unicode characters."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/markdown"

        unicode_markdown = "# Título en Español\n\n测试中文内容\n\n🎉 Emojis work too!"
        content_bytes = unicode_markdown.encode("utf-8")

        converter = MarkdownConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content == unicode_markdown
        assert "Título" in result.converted_content
        assert "测试中文" in result.converted_content
        assert "🎉" in result.converted_content

    @pytest.mark.asyncio
    async def test_markdown_with_line_endings(self) -> None:
        """Test handling of different line ending formats."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/markdown"

        # Test with Windows line endings
        windows_markdown = "# Title\r\n\r\nContent with Windows line endings.\r\n"
        content_bytes = windows_markdown.encode("utf-8")

        converter = MarkdownConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content == windows_markdown
        assert "\r\n" in result.converted_content


class TestMarkdownConverterErrorHandling:
    """Test error handling in MarkdownConverter."""

    @pytest.mark.asyncio
    async def test_unicode_decode_error_handling(self) -> None:
        """Test handling of invalid UTF-8 encoding."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/markdown"

        # Invalid UTF-8 bytes
        invalid_content = b"\xff\xfe# Invalid UTF-8 content"

        converter = MarkdownConverter()
        result = await converter.convert(invalid_content, file_metadata)

        assert result.success is False
        assert result.error_type == "encoding_error"
        assert result.error_message
        assert (
            result.error_message
            == "Unexpected error during document conversion. Invalid UTF-8 encoding in markdown file."
        )

    @pytest.mark.asyncio
    async def test_latin1_encoded_content_error(self) -> None:
        """Test handling of content encoded in non-UTF-8 encoding."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/markdown"

        # Latin-1 encoded content that would fail UTF-8 decoding
        latin1_text = "# Café with naïve characters"
        latin1_text.encode("latin-1")

        # Manually create invalid UTF-8 by taking latin-1 bytes
        # This should cause a UnicodeDecodeError when trying to decode as UTF-8
        invalid_utf8_bytes = b"# Caf\xe9 with na\xefve characters"

        converter = MarkdownConverter()
        result = await converter.convert(invalid_utf8_bytes, file_metadata)

        assert result.success is False
        assert result.error_type == "encoding_error"
        assert result.error_message
        assert "Invalid UTF-8 encoding" in result.error_message

    @pytest.mark.asyncio
    async def test_partial_utf8_sequences(self) -> None:
        """Test handling of incomplete UTF-8 byte sequences."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/markdown"

        # Incomplete UTF-8 sequence (missing continuation bytes)
        incomplete_utf8 = b"# Title\n\nContent with incomplete UTF-8: \xc3"

        converter = MarkdownConverter()
        result = await converter.convert(incomplete_utf8, file_metadata)

        assert result.success is False
        assert result.error_type == "encoding_error"
        assert result.error_message
        assert "Invalid UTF-8 encoding" in result.error_message


class TestMarkdownConverterMetadata:
    """Test metadata handling in MarkdownConverter."""

    @pytest.mark.asyncio
    async def test_metadata_includes_expected_fields(self) -> None:
        """Test that result metadata includes all expected fields."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/markdown"
        file_metadata.filename = "test.md"

        content = "# Test\n\nContent"
        content_bytes = content.encode("utf-8")

        converter = MarkdownConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert "converter" in result.metadata
        assert "mime_type" in result.metadata
        assert "original_size_bytes" in result.metadata

        assert result.metadata["converter"] == "markdown_passthrough"
        assert result.metadata["mime_type"] == "text/markdown"
        assert result.metadata["original_size_bytes"] == len(content_bytes)

    @pytest.mark.asyncio
    async def test_original_size_bytes_accuracy(self) -> None:
        """Test that original_size_bytes accurately reflects input size."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/markdown"

        test_cases = [
            "",  # Empty content
            "# Short",  # Short content
            "# " + "Long content " * 100,  # Longer content
            "Unicode: 测试 🎉",  # Unicode content
        ]

        converter = MarkdownConverter()

        for content in test_cases:
            content_bytes = content.encode("utf-8")
            result = await converter.convert(content_bytes, file_metadata)

            assert result.success is True
            assert result.metadata["original_size_bytes"] == len(content_bytes)

    @pytest.mark.asyncio
    async def test_mime_type_preserved_in_metadata(self) -> None:
        """Test that MIME type from file_metadata is preserved in result metadata."""
        content = "# Test content"
        content_bytes = content.encode("utf-8")

        file_metadata = Mock()
        file_metadata.mime_type = "text/markdown"

        converter = MarkdownConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.metadata["mime_type"] == file_metadata.mime_type


class TestMarkdownConverterDocumentConversionIntegration:
    """Test integration patterns with document conversion system."""

    @pytest.mark.asyncio
    async def test_no_op_conversion_behavior(self) -> None:
        """Test that conversion is truly a no-op for markdown files."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/markdown"

        original_content = """# Original Markdown

This markdown file should pass through unchanged.

- Lists should remain as-is
- **Formatting** should be preserved
- `Code` should not be altered

> Blockquotes unchanged
>
> Multiple lines preserved
"""

        content_bytes = original_content.encode("utf-8")

        converter = MarkdownConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content == original_content
        # Content should be byte-for-byte identical when re-encoded
        assert result.converted_content.encode("utf-8") == content_bytes

    @pytest.mark.asyncio
    async def test_conversion_time_not_measured_in_converter(self) -> None:
        """Test that conversion_time_ms is set to 0 (timing handled by base class)."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/markdown"

        content = "# Fast conversion test"
        content_bytes = content.encode("utf-8")

        converter = MarkdownConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.conversion_time_ms == 0

    @pytest.mark.asyncio
    async def test_large_markdown_file_handling(self) -> None:
        """Test handling of larger markdown files."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/markdown"

        # Create a larger markdown document
        large_content = "# Large Document\n\n"
        large_content += "## Section\n\nParagraph content. " * 1000
        large_content += "\n\n### Subsection\n\nMore content. " * 500

        content_bytes = large_content.encode("utf-8")

        converter = MarkdownConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content == large_content
        assert result.metadata["original_size_bytes"] == len(content_bytes)
        assert len(result.converted_content) > 10000  # Sanity check for size

    @pytest.mark.asyncio
    async def test_markdown_with_front_matter_preservation(self) -> None:
        """Test that markdown with YAML front matter is preserved."""
        file_metadata = Mock()
        file_metadata.mime_type = "text/markdown"

        markdown_with_frontmatter = """---
title: "Test Document"
author: "Test Author"
date: 2023-01-01
tags: ["test", "markdown"]
---

# Main Content

This is the main content of the document.
"""

        content_bytes = markdown_with_frontmatter.encode("utf-8")

        converter = MarkdownConverter()
        result = await converter.convert(content_bytes, file_metadata)

        assert result.success is True
        assert result.converted_content == markdown_with_frontmatter
        assert "---" in result.converted_content
        assert "title:" in result.converted_content
        assert "# Main Content" in result.converted_content


class TestMarkdownConverterWithRealFiles:
    """Test MarkdownConverter with actual files from fixtures directory."""

    @pytest.fixture
    def fixtures_dir(self) -> Path:
        from tests.fixtures.files import get_fixtures_dir

        return get_fixtures_dir()

    @pytest.mark.asyncio
    async def test_real_markdown_conversion(self, fixtures_dir: Path) -> None:
        """Test conversion with a real markdown file from fixtures."""
        md_path = fixtures_dir / "sample.md"
        assert md_path.exists(), f"Markdown fixture not found at {md_path}"

        # Read the real markdown file
        with md_path.open("rb") as f:
            md_content = f.read()

        # Create FileMetadata instance
        file_metadata = FileMetadata(
            filename="sample.md",
            size_bytes=len(md_content),
            mime_type="text/markdown",
            file_path=str(md_path),
        )

        converter = MarkdownConverter()
        result = await converter.convert(md_content, file_metadata)

        # Should succeed with passthrough
        assert result.success is True
        assert result.converted_content
        assert isinstance(result.converted_content, str)
        assert len(result.converted_content) > 0

        # Should contain expected metadata
        assert result.metadata["converter"] == "markdown_passthrough"
        assert result.metadata["mime_type"] == "text/markdown"
        assert result.metadata["original_size_bytes"] == len(md_content)

        # Content should be passed through unchanged
        original_text = md_content.decode("utf-8")
        assert result.converted_content == original_text
