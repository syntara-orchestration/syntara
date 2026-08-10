"""MSWordConverter - Microsoft Word document conversion using pypandoc.

This module provides document conversion for Microsoft Word documents
using the pypandoc library with pandoc backend.
"""

import asyncio
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

import pypandoc  # type: ignore[import-untyped]
import structlog

from syntara.files.document_conversion.converters.document_converter import (
    DocumentConverter,
)
from syntara.files.document_conversion.models.conversion_result import (
    ConversionResult,
)

if TYPE_CHECKING:
    from syntara.files.models import FileMetadata

logger = structlog.stdlib.get_logger(__name__)


class MSWordConverter(DocumentConverter):
    """Converter for Microsoft Word documents using pypandoc.

    Handles conversion of Microsoft Word documents (.doc, .docx)
    to markdown format using pypandoc and pandoc.
    """

    def supported_mime_types(self) -> list[str]:
        """Get list of MIME types supported by this converter.

        Returns:
            List of supported MIME types for Word documents

        """
        return [
            "application/msword",  # .doc files
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx files
        ]

    def _convert_sync(self, file_content: bytes, mime_type: str, filename: str) -> ConversionResult:
        """Run the blocking pypandoc conversion in a thread-safe manner.

        Args:
            file_content: Raw bytes content of the document
            mime_type: MIME type of the source file
            filename: Original filename for logging

        Returns:
            ConversionResult with converted markdown content

        """
        input_format = self._get_pandoc_format(mime_type)
        if not input_format:
            return ConversionResult.failure_result(
                error_message=f"Unsupported MIME type: {mime_type}",
                error_type="unsupported_format",
                conversion_time_ms=0,
            )

        temp_input_path = None
        try:
            file_extension = self._get_file_extension(mime_type)
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                temp_file.write(file_content)
                temp_input_path = temp_file.name

            converted_content = pypandoc.convert_file(
                temp_input_path,
                "markdown",
                format=input_format,
                extra_args=["--wrap=none"],
            )

            return ConversionResult.success_result(
                converted_content=converted_content,
                conversion_time_ms=0,
                metadata={"input_format": input_format, "converter": "pypandoc", "mime_type": mime_type},
            )

        except RuntimeError as e:
            error_message = str(e)
            error_type = self._classify_pypandoc_error(error_message)

            return ConversionResult.failure_result(
                error_message=error_message,
                error_type=error_type,
                conversion_time_ms=0,
            )

        except MemoryError:
            return ConversionResult.failure_result(
                error_message="Insufficient memory to process document",
                error_type="memory_exhausted",
                conversion_time_ms=0,
            )

        except (OSError, ValueError) as e:
            error_message = "Unexpected error during document conversion."
            logger.exception(
                error_message,
                filename=filename,
            )
            return ConversionResult.failure_result(
                error_message=error_message,
                error_type="conversion_error",
                conversion_time_ms=0,
                metadata={"exception_type": type(e).__name__},
            )

        finally:
            if temp_input_path and Path(temp_input_path).exists():
                with suppress(OSError):
                    Path(temp_input_path).unlink()

    async def convert(
        self,
        file_content: bytes,
        file_metadata: "FileMetadata",
    ) -> ConversionResult:
        """Convert Word document content to markdown.

        Runs pypandoc in a thread pool so the event loop stays responsive
        and asyncio.wait_for() can enforce timeouts.

        Args:
            file_content: Raw bytes content of the document
            file_metadata: Metadata about the source file

        Returns:
            ConversionResult with converted markdown content

        Example:
            converter = MSWordConverter()
            with open("/tmp/document.docx", "rb") as f:
                content = f.read()
            result = await converter.convert(content, file_metadata)
            assert result.success is True
            assert result.converted_content.startswith("#")

        """
        return await asyncio.to_thread(
            self._convert_sync, file_content, file_metadata.mime_type, file_metadata.filename
        )

    def _get_pandoc_format(self, mime_type: str) -> str:
        """Determine pandoc input format from MIME type.

        Args:
            mime_type: MIME type of the input file

        Returns:
            Pandoc format string, or empty string if unsupported

        """
        format_map = {
            "application/msword": "doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        }

        return format_map.get(mime_type, "")

    def _get_file_extension(self, mime_type: str) -> str:
        """Get file extension for temporary file creation.

        Args:
            mime_type: MIME type of the input file

        Returns:
            File extension including the dot

        """
        extension_map = {
            "application/msword": ".doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        }

        return extension_map.get(mime_type, ".tmp")

    def _classify_pypandoc_error(self, error_message: str) -> str:
        """Classify pypandoc error for appropriate error type.

        Args:
            error_message: Error message from pypandoc

        Returns:
            Classified error type string

        """
        error_lower = error_message.lower()

        if "corrupted" in error_lower or "invalid" in error_lower:
            return "corruption"
        if "password" in error_lower or "encrypted" in error_lower:
            return "password_protected"
        if "not found" in error_lower:
            return "dependency_missing"
        if "unsupported" in error_lower or "version" in error_lower:
            return "unsupported_version"
        return "conversion_error"
