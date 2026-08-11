"""Document conversion component for agent invocation workflow.

This component provides automatic document conversion to markdown format
when files are uploaded through the agent invocation system.

Key Components:
- DocumentConversionService: Core service for processing conversions
- ConverterRegistry: Registry for managing different converter types
- BaseConverter: Abstract base class for document converters
- ConversionConfig/ConversionResult: Data models for conversion operations

Architecture:
- Files uploaded through FileManager trigger automatic background conversion
- Conversions are processed asynchronously via builtin Temporal workflows
- FileMetadata status tracks conversion progress (pending_conversion → converting → converted/failed)
- Invocation execution is gated until all conversions reach terminal status

Supported Formats:
- PDF documents (via PyMuPDF)
- Word documents (DOC/DOCX via pypandoc)
- Plain text files (simple formatting)
- Markdown files (pass-through)

Usage:
    The conversion process is automatic and transparent to users.
    When files are uploaded via the invoke_agent endpoint, background
    conversion is automatically triggered and results are integrated
    into the invocation context.

Example:
    # User uploads PDF via invoke_agent endpoint
    # → FileManager saves file and creates FileMetadata
    # → Background task converts PDF to markdown
    # → FileMetadata status updated to "converted"
    # → Invocation proceeds with markdown content available

"""

from syntara.files.document_conversion.exceptions import (
    ConversionFailureError,
    DocumentConversionError,
    FileNotReadableError,
    FileSizeExceededError,
    UnsupportedFormatError,
)

# Public API
__all__ = [
    "ConversionFailureError",
    "DocumentConversionError",
    "FileNotReadableError",
    "FileSizeExceededError",
    "UnsupportedFormatError",
]
