"""Test for DocumentConverter abstract base class."""

import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from syntara.files.document_conversion.converters.document_converter import (
    DocumentConverter,
)
from syntara.files.document_conversion.models.conversion_result import (
    ConversionResult,
)


class MockDocumentConverter(DocumentConverter):
    """Mock implementation of DocumentConverter for testing the abstract base class."""

    def __init__(self, mime_types: list[str] | None = None, convert_result: ConversionResult | None = None) -> None:
        """Initialize test converter with configurable behavior."""
        self._mime_types = mime_types or ["text/plain"]
        self._convert_result = convert_result or ConversionResult.success_result("# Test\n\nConverted content", 100)

    def supported_mime_types(self) -> list[str]:
        """Return configured MIME types."""
        return self._mime_types

    async def convert(self, _file_content: bytes, _file_metadata) -> ConversionResult:
        """Return configured conversion result."""
        return self._convert_result


class SlowTestConverter(DocumentConverter):
    """Test converter that simulates slow conversion for timeout testing."""

    def supported_mime_types(self) -> list[str]:
        """Return slow test MIME types."""
        return ["test/slow"]

    async def convert(self, _file_content: bytes, _file_metadata) -> ConversionResult:
        """Simulate slow conversion with delay."""
        await asyncio.sleep(2)
        return ConversionResult.success_result("Slow conversion result", 2000)


class ErrorTestConverter(DocumentConverter):
    """Test converter that raises errors for error handling testing."""

    def supported_mime_types(self) -> list[str]:
        """Return error test MIME types."""
        return ["test/error"]

    async def convert(self, _file_content: bytes, _file_metadata) -> ConversionResult:
        """Raise test error for error handling validation."""
        msg = "Test conversion error"
        raise ValueError(msg)


class TestDocumentConverterInterface:
    """Test the DocumentConverter abstract base class interface."""

    def test_supports_mime_type_with_supported_type(self) -> None:
        """Test supports_mime_type returns True for supported MIME type."""
        converter = MockDocumentConverter(mime_types=["text/plain", "application/pdf"])

        assert converter.supports_mime_type("text/plain") is True
        assert converter.supports_mime_type("application/pdf") is True

    def test_supports_mime_type_with_unsupported_type(self) -> None:
        """Test supports_mime_type returns False for unsupported MIME type."""
        converter = MockDocumentConverter(mime_types=["text/plain"])

        assert converter.supports_mime_type("application/pdf") is False
        assert converter.supports_mime_type("image/jpeg") is False

    def test_get_converter_name_returns_class_name(self) -> None:
        """Test get_converter_name returns the actual class name."""
        converter = MockDocumentConverter()
        assert converter.get_converter_name() == "MockDocumentConverter"

    @pytest.mark.asyncio
    async def test_convert_with_timing_measures_duration(self) -> None:
        """Test convert_with_timing accurately measures conversion duration."""
        # Use a converter that returns a result with timing set to 100ms
        result = ConversionResult.success_result("Test content", 100)
        converter = MockDocumentConverter(convert_result=result)

        file_metadata = Mock()
        timed_result = await converter.convert_with_timing(b"test content", file_metadata)

        assert timed_result.success is True
        assert timed_result.conversion_time_ms >= 0  # Should be measured and updated


class TestDocumentConverterTimingBehavior:
    """Test timing measurement behavior in DocumentConverter."""

    @pytest.mark.asyncio
    async def test_convert_with_timing_handles_conversion_errors(self) -> None:
        """Test convert_with_timing handles errors and measures timing."""
        converter = ErrorTestConverter()
        file_metadata = Mock()

        result = await converter.convert_with_timing(b"test content", file_metadata)

        assert result.success is False
        assert result.error_type == "unexpected_error"
        assert result.conversion_time_ms >= 0
        assert result.error_message
        assert result.error_message == "Unexpected error during document conversion."
        assert result.metadata["exception_type"] == "ValueError"

    @patch("syntara.files.document_conversion.models.conversion_config.ConversionConfig.from_settings")
    @pytest.mark.asyncio
    async def test_convert_with_timeout_allows_fast_conversions(self, mock_from_settings: AsyncMock) -> None:
        """Test convert_with_timeout allows conversions that complete within timeout."""
        # Mock config with generous timeout
        mock_config = Mock()
        mock_config.timeout_seconds = 30
        mock_from_settings.return_value = mock_config

        converter = MockDocumentConverter()
        file_metadata = Mock()

        result = await converter.convert_with_timeout(b"test content", file_metadata)

        assert result.success is True
        assert result.converted_content is not None


class ThreadedBlockingConverter(DocumentConverter):
    """Test converter that offloads a blocking call to a thread, allowing timeout to fire."""

    def supported_mime_types(self) -> list[str]:
        """Return test MIME types."""
        return ["test/blocking"]

    async def convert(self, _file_content: bytes, _file_metadata) -> ConversionResult:
        """Simulate a blocking conversion offloaded to a thread."""
        return await asyncio.to_thread(self._convert_sync)

    @staticmethod
    def _convert_sync() -> ConversionResult:
        time.sleep(5)
        return ConversionResult.success_result("Blocking conversion result", 5000)


class TestDocumentConverterTimeoutWithBlockingConverter:
    """Test that timeout works when a converter offloads blocking work to a thread."""

    @patch("syntara.files.document_conversion.models.conversion_config.ConversionConfig.from_settings")
    @pytest.mark.asyncio
    async def test_timeout_fires_for_threaded_blocking_conversion(self, mock_from_settings: AsyncMock) -> None:
        """Test that asyncio.wait_for can cancel a blocking conversion running in a thread."""
        mock_config = Mock()
        mock_config.timeout_seconds = 1
        mock_from_settings.return_value = mock_config

        converter = ThreadedBlockingConverter()
        file_metadata = Mock()

        result = await converter.convert_with_timeout(b"test content", file_metadata)

        assert result.success is False
        assert result.error_type == "timeout"
        assert result.conversion_time_ms >= 900


class TestDocumentConverterMimeTypeHandling:
    """Test MIME type support and validation in DocumentConverter."""

    def test_supported_mime_types_with_multiple_types(self) -> None:
        """Test supported_mime_types with multiple MIME types."""
        mime_types = ["application/pdf", "application/msword", "text/plain"]
        converter = MockDocumentConverter(mime_types=mime_types)

        supported = converter.supported_mime_types()
        assert supported == mime_types

    def test_supported_mime_types_with_single_type(self) -> None:
        """Test supported_mime_types with single MIME type."""
        converter = MockDocumentConverter(mime_types=["text/markdown"])

        supported = converter.supported_mime_types()
        assert supported == ["text/markdown"]

    def test_supports_mime_type_case_sensitive_matching(self) -> None:
        """Test supports_mime_type performs case-sensitive MIME type matching."""
        converter = MockDocumentConverter(mime_types=["text/plain"])

        assert converter.supports_mime_type("text/plain") is True
        assert converter.supports_mime_type("TEXT/PLAIN") is False
        assert converter.supports_mime_type("Text/Plain") is False

    def test_supports_mime_type_with_document_conversion_formats(self) -> None:
        """Test supports_mime_type with common document conversion MIME types."""
        document_mime_types = [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
            "text/plain",
            "text/markdown",
        ]
        converter = MockDocumentConverter(mime_types=document_mime_types)

        # Test all supported types
        for mime_type in document_mime_types:
            assert converter.supports_mime_type(mime_type) is True

        # Test unsupported types
        assert converter.supports_mime_type("image/jpeg") is False
        assert converter.supports_mime_type("application/zip") is False
