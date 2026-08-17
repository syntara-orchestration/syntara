"""Exception classes for document conversion subdomain.

This module contains all custom exceptions specific to document conversion operations,
including format validation, size limits, and conversion failures.
"""

from syntara.files.exceptions import FileError


class DocumentConversionError(FileError):
    """Base exception for document conversion errors."""


class UnsupportedFormatError(DocumentConversionError):
    """Raised when attempting to convert an unsupported file format."""

    def __init__(self, format_type: str, supported_formats: list[str]) -> None:
        """Initialize with format details."""
        self.format_type = format_type
        self.supported_formats = supported_formats
        message = f"Unsupported format '{format_type}'. Supported formats: {', '.join(supported_formats)}"
        super().__init__(message)


class FileSizeExceededError(DocumentConversionError):
    """Raised when a file exceeds the configured size limit."""

    def __init__(self, file_size: int, max_size: int, file_path: str) -> None:
        """Initialize with file size details."""
        self.file_size = file_size
        self.max_size = max_size
        self.file_path = file_path
        message = f"File '{file_path}' size ({file_size:,} bytes) exceeds limit ({max_size:,} bytes)"
        super().__init__(message)


class FileNotReadableError(DocumentConversionError):
    """Raised when a source file cannot be read."""

    def __init__(self, file_path: str, reason: str = "File is not readable") -> None:
        """Initialize with file path and reason."""
        self.file_path = file_path
        self.reason = reason
        message = f"Cannot read file '{file_path}': {reason}"
        super().__init__(message)


class ConversionFailureError(DocumentConversionError):
    """Raised when document conversion fails due to library or processing errors."""

    def __init__(self, file_path: str, format_type: str, cause: str) -> None:
        """Initialize with conversion failure details."""
        self.file_path = file_path
        self.format_type = format_type
        self.cause = cause
        message = f"Failed to convert '{format_type}' file '{file_path}': {cause}"
        super().__init__(message)
