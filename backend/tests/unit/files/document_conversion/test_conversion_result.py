"""Test for ConversionResult model validation and behavior."""

import pytest

from syntara.files.document_conversion.models.conversion_result import (
    ConversionResult,
)


class TestConversionResultValidation:
    """Test ConversionResult validation logic."""

    def test_conversion_time_validation_negative_value_rejected(self) -> None:
        """Test that negative conversion_time_ms raises validation error."""
        with pytest.raises(ValueError, match="Input should be greater than or equal to 0"):
            ConversionResult(success=True, conversion_time_ms=-1, converted_content="Test content")

    def test_conversion_time_validation_zero_value_accepted(self) -> None:
        """Test that zero conversion_time_ms is accepted."""
        result = ConversionResult(success=True, conversion_time_ms=0, converted_content="Test content")
        assert result.conversion_time_ms == 0

    def test_conversion_time_validation_positive_value_accepted(self) -> None:
        """Test that positive conversion_time_ms is accepted."""
        result = ConversionResult(success=True, conversion_time_ms=1500, converted_content="Test content")
        assert result.conversion_time_ms == 1500

    def test_metadata_defaults_to_empty_dict(self) -> None:
        """Test that metadata defaults to empty dictionary when not provided."""
        result = ConversionResult(success=True, conversion_time_ms=1000, converted_content="Test")
        assert result.metadata == {}

    def test_metadata_preserves_provided_values(self) -> None:
        """Test that metadata preserves the provided dictionary values."""
        test_metadata = {"converter": "MSWordConverter", "format": "pdf"}
        result = ConversionResult(
            success=True, conversion_time_ms=1000, converted_content="Test", metadata=test_metadata
        )
        assert result.metadata == test_metadata

    def test_error_fields_default_to_none(self) -> None:
        """Test that error_message and error_type default to None."""
        result = ConversionResult(success=True, conversion_time_ms=1000, converted_content="Test")
        assert result.error_message is None
        assert result.error_type is None

    def test_converted_content_defaults_to_none(self) -> None:
        """Test that converted_content defaults to None when not provided."""
        result = ConversionResult(success=False, conversion_time_ms=500, error_message="Test error")
        assert result.converted_content is None


class TestConversionResultFactoryMethods:
    """Test ConversionResult factory methods for creating success and failure results."""

    def test_success_result_creates_valid_success_instance(self) -> None:
        """Test that success_result creates a valid successful conversion result."""
        converted_content = "# Test Document\n\nThis is converted content."
        conversion_time = 1250
        metadata = {"converter": "MSWordConverter"}

        result = ConversionResult.success_result(
            converted_content=converted_content, conversion_time_ms=conversion_time, metadata=metadata
        )

        assert result.success is True
        assert result.converted_content == converted_content
        assert result.conversion_time_ms == conversion_time
        assert result.metadata == metadata
        assert result.error_message is None
        assert result.error_type is None

    def test_success_result_with_minimal_arguments(self) -> None:
        """Test success_result with only required arguments."""
        result = ConversionResult.success_result(converted_content="Test content", conversion_time_ms=500)

        assert result.success is True
        assert result.converted_content == "Test content"
        assert result.conversion_time_ms == 500
        assert result.metadata == {}

    def test_failure_result_creates_valid_failure_instance(self) -> None:
        """Test that failure_result creates a valid failed conversion result."""
        error_message = "File not found: document.pdf"
        error_type = "file_not_found"
        conversion_time = 300
        metadata = {"attempted_converter": "MSWordConverter"}

        result = ConversionResult.failure_result(
            error_message=error_message, error_type=error_type, conversion_time_ms=conversion_time, metadata=metadata
        )

        assert result.success is False
        assert result.error_message == error_message
        assert result.error_type == error_type
        assert result.conversion_time_ms == conversion_time
        assert result.metadata == metadata
        assert result.converted_content is None

    def test_failure_result_with_minimal_arguments(self) -> None:
        """Test failure_result with only required arguments."""
        result = ConversionResult.failure_result(
            error_message="Conversion failed", error_type="conversion_error", conversion_time_ms=750
        )

        assert result.success is False
        assert result.error_message == "Conversion failed"
        assert result.error_type == "conversion_error"
        assert result.conversion_time_ms == 750
        assert result.metadata == {}


class TestConversionResultDocumentConversionIntegration:
    """Test ConversionResult integration patterns for document conversion scenarios."""

    def test_successful_pdf_conversion_result_structure(self) -> None:
        """Test result structure for successful PDF conversion scenario."""
        result = ConversionResult.success_result(
            converted_content="# Document Title\n\nContent from PDF conversion.",
            conversion_time_ms=2500,
            metadata={"source_format": "application/pdf", "converter": "MSWordConverter", "page_count": 3},
        )

        assert result.success is True
        assert result.converted_content is not None
        assert "Document Title" in result.converted_content
        assert result.metadata["source_format"] == "application/pdf"
        assert result.metadata["page_count"] == 3

    def test_failed_unsupported_format_error_structure(self) -> None:
        """Test result structure for unsupported format conversion failure."""
        result = ConversionResult.failure_result(
            error_message="Unsupported format: application/zip",
            error_type="unsupported_format",
            conversion_time_ms=50,
            metadata={"attempted_format": "application/zip"},
        )

        assert result.success is False
        assert result.error_type == "unsupported_format"
        assert result.error_message is not None
        assert "application/zip" in result.error_message
        assert result.metadata["attempted_format"] == "application/zip"

    def test_failed_file_size_limit_error_structure(self) -> None:
        """Test result structure for file size limit conversion failure."""
        result = ConversionResult.failure_result(
            error_message="File size 15MB exceeds limit of 10MB",
            error_type="file_size_exceeded",
            conversion_time_ms=100,
            metadata={"file_size_bytes": 15 * 1024 * 1024, "limit_bytes": 10 * 1024 * 1024},
        )

        assert result.success is False
        assert result.error_type == "file_size_exceeded"
        assert result.error_message is not None
        assert "15MB exceeds limit" in result.error_message
        assert result.metadata["file_size_bytes"] == 15 * 1024 * 1024
