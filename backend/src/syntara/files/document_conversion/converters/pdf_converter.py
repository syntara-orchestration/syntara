"""PDF Converter - PDF document conversion using pypdf.

This module provides document conversion for PDF files to mark-down format
using the pypdf library for text extraction.
"""

import asyncio
from io import BytesIO
from typing import TYPE_CHECKING

from pypdf import PdfReader

from syntara.files.document_conversion.converters.document_converter import (
    DocumentConverter,
)
from syntara.files.document_conversion.models.conversion_result import (
    ConversionResult,
)

if TYPE_CHECKING:
    from syntara.files.models import FileMetadata


class PDFConverter(DocumentConverter):
    """Converter for PDF documents using pypdf.

    Handles conversion of PDF files to markdown format using pypdf
    for text extraction.
    """

    def supported_mime_types(self) -> list[str]:
        """Get list of MIME types supported by this converter.

        Returns:
            List of supported MIME types for PDF documents

        """
        return ["application/pdf"]

    def _convert_sync(self, file_content: bytes, mime_type: str) -> ConversionResult:
        """Run the blocking pypdf extraction in a thread-safe manner.

        Args:
            file_content: Raw bytes content of the PDF document
            mime_type: MIME type of the source file

        Returns:
            ConversionResult with converted markdown content

        """
        if mime_type != "application/pdf":
            return ConversionResult.failure_result(
                error_message=f"Unsupported MIME type: {mime_type}",
                error_type="unsupported_format",
                conversion_time_ms=0,
            )

        try:
            reader = PdfReader(BytesIO(file_content))
            page_count = len(reader.pages)
            markdown_content = self._extract_text_as_markdown(reader)

            if not markdown_content.strip():
                return ConversionResult.failure_result(
                    error_message="PDF appears to contain no extractable text (may be scanned images)",
                    error_type="no_text_content",
                    conversion_time_ms=0,
                )

            return ConversionResult.success_result(
                converted_content=markdown_content,
                conversion_time_ms=0,
                metadata={
                    "input_format": "pdf",
                    "converter": "pypdf",
                    "mime_type": mime_type,
                    "page_count": page_count,
                },
            )

        except (OSError, ValueError, RuntimeError) as e:
            error_message = str(e)
            error_type = self._classify_pdf_error(error_message)

            return ConversionResult.failure_result(
                error_message=error_message,
                error_type=error_type,
                conversion_time_ms=0,
                metadata={"exception_type": type(e).__name__},
            )

    async def convert(
        self,
        file_content: bytes,
        file_metadata: "FileMetadata",
    ) -> ConversionResult:
        """Convert PDF document content to markdown.

        Runs pypdf in a thread pool so the event loop stays responsive
        and asyncio.wait_for() can enforce timeouts.

        Args:
            file_content: Raw bytes content of the PDF document
            file_metadata: Metadata about the source file

        Returns:
            ConversionResult with converted markdown content

        Example:
            converter = PDFConverter()
            with open("/tmp/document.pdf", "rb") as f:
                content = f.read()
            result = await converter.convert(content, file_metadata)
            assert result.success is True
            assert result.converted_content

        """
        return await asyncio.to_thread(self._convert_sync, file_content, file_metadata.mime_type)

    def _extract_text_as_markdown(self, reader: PdfReader) -> str:
        """Extract text from PDF document and format as markdown.

        Args:
            reader: pypdf PdfReader object

        Returns:
            Markdown-formatted text content

        """
        markdown_lines = []

        for page_num, page in enumerate(reader.pages):
            # Add page separator for multipage documents
            if page_num > 0:
                markdown_lines.append("\n---\n")

            text = page.extract_text()
            if text:
                markdown_lines.append(text)

        return self._clean_markdown_content(markdown_lines)

    def _clean_markdown_content(self, markdown_lines: list[str]) -> str:
        """Clean up markdown content by removing excess whitespace.

        Args:
            markdown_lines: List of mark-down text lines

        Returns:
            Cleaned markdown content

        """
        content = "\n".join(markdown_lines)
        # Remove excessive blank lines
        while "\n\n\n" in content:
            content = content.replace("\n\n\n", "\n\n")

        return content.strip()

    def _classify_pdf_error(self, error_message: str) -> str:
        """Classify PDF processing error for appropriate error type.

        Args:
            error_message: Error message from pypdf

        Returns:
            Classified error type string

        """
        error_lower = error_message.lower()

        if "corrupted" in error_lower or "invalid" in error_lower or "damaged" in error_lower:
            return "corruption"
        if "password" in error_lower or "encrypted" in error_lower:
            return "password_protected"
        if "memory" in error_lower:
            return "memory_exhausted"
        return "conversion_error"
