"""MarkdownConverter - No-op converter for markdown files.

This module provides a passthrough converter for markdown files that are
already in the target format and don't require conversion.
"""

from typing import TYPE_CHECKING

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


class MarkdownConverter(DocumentConverter):
    """No-op converter for markdown files.

    Since markdown files are already in the target format, this converter
    simply passes through the content unchanged.
    """

    def supported_mime_types(self) -> list[str]:
        """Get list of MIME types supported by this converter.

        Returns:
            List containing only the markdown MIME type

        """
        return ["text/markdown"]

    async def convert(
        self,
        file_content: bytes,
        file_metadata: "FileMetadata",
    ) -> ConversionResult:
        r"""Pass through markdown content unchanged.

        Args:
            file_content: Raw bytes content of the markdown file
            file_metadata: Metadata about the source file

        Returns:
            ConversionResult with the original markdown content

        Example:
            converter = MarkdownConverter()
            content = b"# Title\\n\\nMarkdown content"
            result = await converter.convert(content, file_metadata)
            assert result.success is True
            assert result.converted_content == "# Title\\n\\nMarkdown content"

        """
        try:
            # Decode bytes to string and return as-is
            markdown_content = file_content.decode("utf-8")

            return ConversionResult.success_result(
                converted_content=markdown_content,
                conversion_time_ms=0,  # Timing handled by base class
                metadata={
                    "converter": "markdown_passthrough",
                    "mime_type": file_metadata.mime_type,
                    "original_size_bytes": len(file_content),
                },
            )

        except UnicodeDecodeError:
            error_message = "Unexpected error during document conversion. Invalid UTF-8 encoding in markdown file."
            logger.exception(
                error_message,
                filename=file_metadata.filename,
            )
            return ConversionResult.failure_result(
                error_message=error_message,
                error_type="encoding_error",
                conversion_time_ms=0,
            )

        except (OSError, ValueError) as e:
            error_message = "Unexpected error during document conversion. Unexpected error processing markdown."
            logger.exception(
                error_message,
                filename=file_metadata.filename,
            )
            return ConversionResult.failure_result(
                error_message=error_message,
                error_type="conversion_error",
                conversion_time_ms=0,
                metadata={"exception_type": type(e).__name__},
            )
