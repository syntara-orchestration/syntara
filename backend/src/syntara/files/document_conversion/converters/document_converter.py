"""Abstract base class for document converters.

This module provides the DocumentConverter base class that defines the interface
and common functionality for all document format converters.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import structlog

from syntara.files.document_conversion.models.conversion_config import (
    ConversionConfig,
)
from syntara.files.document_conversion.models.conversion_result import (
    ConversionResult,
)

if TYPE_CHECKING:
    from syntara.files.models import FileMetadata

logger = structlog.stdlib.get_logger(__name__)


class DocumentConverter(ABC):
    """Abstract base class for document converters.

    Provides the common interface and timing functionality that all converters
    must implement. Each converter handles specific MIME types and formats.
    """

    @abstractmethod
    def supported_mime_types(self) -> list[str]:
        """Get list of MIME types supported by this converter.

        Returns:
            List of MIME types this converter can handle

        Example:
            converter = MSWordConverter()
            types = converter.supported_mime_types()
            assert "application/pdf" in types
            assert "application/msword" in types

        """

    def supports_mime_type(self, mime_type: str) -> bool:
        """Check if this converter supports the given MIME type.

        Args:
            mime_type: MIME type to check for support

        Returns:
            True if converter can handle this MIME type

        Example:
            converter = MSWordConverter()
            assert converter.supports_mime_type("application/pdf") is True
            assert converter.supports_mime_type("image/jpeg") is False

        """
        return mime_type in self.supported_mime_types()

    @abstractmethod
    async def convert(self, file_content: bytes, file_metadata: "FileMetadata") -> ConversionResult:
        """Convert document content to markdown.

        Args:
            file_content: Raw bytes content of the document
            file_metadata: Metadata about the source file

        Returns:
            ConversionResult with converted markdown content and metadata

        Example:
            converter = MSWordConverter()
            with open("/tmp/doc.pdf", "rb") as f:
                content = f.read()
            result = await converter.convert(content, file_metadata)
            assert result.success is True
            assert isinstance(result.converted_content, str)

        """

    async def convert_with_timing(self, file_content: bytes, file_metadata: "FileMetadata") -> ConversionResult:
        """Convert document with accurate timing measurement.

        This method wraps the convert() implementation with precise timing
        to ensure accurate performance metrics for all converters.

        Args:
            file_content: Raw bytes content of the document
            file_metadata: Metadata about the source file

        Returns:
            ConversionResult with accurate timing information

        Example:
            converter = MSWordConverter()
            result = await converter.convert_with_timing(content, file_metadata)
            assert result.conversion_time_ms > 0

        """
        start_time = time.time()

        try:
            # Call the actual converter implementation
            result = await self.convert(file_content, file_metadata)

            # Calculate timing and update result
            end_time = time.time()
            conversion_time_ms = int((end_time - start_time) * 1000)

            # Update the result with accurate timing
            result.conversion_time_ms = conversion_time_ms

            return result

        except (OSError, ValueError, RuntimeError) as e:
            # Handle unexpected errors with timing
            end_time = time.time()
            conversion_time_ms = int((end_time - start_time) * 1000)

            error_message = "Unexpected error during document conversion."
            logger.exception(
                error_message,
                filename=file_metadata.filename,
            )

            return ConversionResult.failure_result(
                error_message=error_message,
                error_type="unexpected_error",
                conversion_time_ms=conversion_time_ms,
                metadata={"exception_type": type(e).__name__},
            )

    async def convert_with_timeout(self, file_content: bytes, file_metadata: "FileMetadata") -> ConversionResult:
        """Convert document with timeout enforcement.

        This method ensures conversions don't exceed the configured timeout,
        supporting NFR-001 compliance.

        Args:
            file_content: Raw bytes content of the document
            file_metadata: Metadata about the source file

        Returns:
            ConversionResult, with timeout error if exceeded

        Example:
            converter = MSWordConverter()
            result = await converter.convert_with_timeout(content, file_metadata)
            if not result.success and result.error_type == "timeout":
                print("Conversion timed out")

        """
        config = await ConversionConfig.from_settings()
        start_time = time.time()

        try:
            # Run conversion with timeout
            return await asyncio.wait_for(
                self.convert_with_timing(file_content, file_metadata), timeout=config.timeout_seconds
            )

        except TimeoutError:
            # Handle timeout
            end_time = time.time()
            conversion_time_ms = int((end_time - start_time) * 1000)

            return ConversionResult.failure_result(
                error_message=f"Conversion timed out after {config.timeout_seconds} seconds",
                error_type="timeout",
                conversion_time_ms=conversion_time_ms,
                metadata={"timeout_seconds": config.timeout_seconds},
            )

    def get_converter_name(self) -> str:
        """Get the name of this converter for logging and identification.

        Returns:
            Name of the converter class

        Example:
            converter = MSWordConverter()
            assert converter.get_converter_name() == "MSWordConverter"

        """
        return self.__class__.__name__
