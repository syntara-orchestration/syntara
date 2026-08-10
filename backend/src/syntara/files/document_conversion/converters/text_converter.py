"""TextConverter - Plain text to markdown conversion.

This module provides conversion for plain text files to markdown format
with basic formatting improvements.
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


class TextConverter(DocumentConverter):
    """Converter for plain text files to markdown.

    Converts plain text files to markdown format while preserving
    paragraph structure and escaping markdown special characters.
    """

    def supported_mime_types(self) -> list[str]:
        """Get list of MIME types supported by this converter.

        Returns:
            List containing only the plain text MIME type

        """
        return ["text/plain"]

    async def convert(
        self,
        file_content: bytes,
        file_metadata: "FileMetadata",
    ) -> ConversionResult:
        r"""Convert plain text content to markdown.

        Args:
            file_content: Raw bytes content of the text file
            file_metadata: Metadata about the source file

        Returns:
            ConversionResult with converted markdown content

        Example:
            converter = TextConverter()
            content = b"Hello World\\n\\nThis is text."
            result = await converter.convert(content, file_metadata)
            assert result.success is True
            assert "Hello World" in result.converted_content

        """
        try:
            # Decode bytes to string with encoding detection fallback
            text_content = self._decode_text_content(file_content)

            # Convert to markdown format
            markdown_content = self._convert_to_markdown(text_content)

            return ConversionResult.success_result(
                converted_content=markdown_content,
                conversion_time_ms=0,  # Timing handled by base class
                metadata={
                    "converter": "text_to_markdown",
                    "mime_type": file_metadata.mime_type,
                    "original_size_bytes": len(file_content),
                    "converted_size_chars": len(markdown_content),
                },
            )

        except UnicodeDecodeError:
            error_message = "Unexpected error during document conversion. Unable to decode text file."
            logger.exception(
                error_message,
                filename=file_metadata.filename,
            )
            return ConversionResult.failure_result(
                error_message=error_message, error_type="encoding_error", conversion_time_ms=0
            )

        except MemoryError:
            error_message = "Unexpected error during document conversion. File too large to process."
            logger.exception(
                error_message,
                filename=file_metadata.filename,
            )
            return ConversionResult.failure_result(
                error_message=error_message, error_type="memory_exhausted", conversion_time_ms=0
            )

        except (OSError, ValueError) as e:
            error_message = "Unexpected error during document conversion."
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

    def _decode_text_content(self, file_content: bytes) -> str:
        """Decode bytes to text with fallback encoding detection.

        Args:
            file_content: Raw file bytes

        Returns:
            Decoded text content

        Raises:
            UnicodeDecodeError: If content cannot be decoded as text

        """
        # Try UTF-8 first
        try:
            return file_content.decode("utf-8")
        except UnicodeDecodeError:
            pass

        # Try common encodings as fallback
        fallback_encodings = ["latin-1", "cp1252", "iso-8859-1"]

        for encoding in fallback_encodings:
            try:
                return file_content.decode(encoding)
            except UnicodeDecodeError:
                continue

        # If all else fails, decode with error handling
        return file_content.decode("utf-8", errors="replace")

    def _convert_to_markdown(self, text_content: str) -> str:
        """Convert plain text to markdown format.

        Args:
            text_content: Plain text content

        Returns:
            Converted markdown content

        """
        # Normalize line endings
        text_content = text_content.replace("\r\n", "\n").replace("\r", "\n")

        # Escape markdown special characters to preserve literal meaning
        text_content = self._escape_markdown_characters(text_content)

        # Split into paragraphs and rejoin with proper markdown spacing
        paragraphs = text_content.split("\n\n")

        # Filter empty paragraphs and normalize whitespace
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        # Join paragraphs with double newlines for proper markdown formatting
        return "\n\n".join(paragraphs)

    def _escape_markdown_characters(self, text: str) -> str:
        """Escape markdown special characters to preserve literal meaning.

        Args:
            text: Text content to escape

        Returns:
            Text with markdown characters escaped

        """
        # Characters that have special meaning in markdown
        escape_chars = {
            "*": r"\*",
            "_": r"\_",
            "`": r"\`",
            "[": r"\[",
            "]": r"\]",
            "(": r"\(",
            ")": r"\)",
            "#": r"\#",
            "+": r"\+",
            "-": r"\-",
            ".": r"\.",
            "!": r"\!",
            "{": r"\{",
            "}": r"\}",
            "|": r"\|",
            ">": r"\>",
            "~": r"\~",
            "^": r"\^",
        }

        for char, escaped in escape_chars.items():
            text = text.replace(char, escaped)

        return text
