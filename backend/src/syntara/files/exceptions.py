"""Exception classes for files domain.

This module contains general file-related exceptions. Domain-specific exceptions
are located in their respective subdomains (e.g., document_conversion/exceptions.py).
"""

from syntara.core.exception_registry import fastapi_exception
from syntara.core.exceptions import SyntaraError


@fastapi_exception(handler="syntara.files.error_handlers.file_error_handler")
class FileError(SyntaraError):
    """Base exception for all file-related errors."""


@fastapi_exception(handler="syntara.files.error_handlers.file_validation_error_handler")
class FileValidationError(FileError):
    """File validation error with actionable messages.

    This exception is raised when file validation fails and should be
    caught by the API layer to return appropriate 400 Bad Request responses.
    """


@fastapi_exception(handler="syntara.files.error_handlers.file_not_found_error_handler")
class FileContentNotFoundError(FileError):
    """Raised when file content is missing from the storage backend."""


@fastapi_exception(handler="syntara.files.error_handlers.file_integrity_error_handler")
class FileIntegrityError(FileError):
    """Raised when file content hash does not match the stored hash."""


@fastapi_exception(handler="syntara.files.error_handlers.file_storage_unavailable_handler")
class FileStorageUnavailableError(FileError):
    """Raised when file storage (S3) is not configured."""
