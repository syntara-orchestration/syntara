"""Storage backend exceptions for the secret storage layer.

These exceptions replace raw KeyError and SQLAlchemy errors from
DatabaseBackend with structured, user-safe exceptions that map to
RFC 9457 error responses via @fastapi_exception handlers.
"""

from syntara.core.exception_registry import fastapi_exception
from syntara.core.exceptions import SyntaraError


@fastapi_exception(handler="syntara.core.storage_error_handlers.storage_backend_error_handler")
class StorageBackendError(SyntaraError):
    """Base exception for all storage backend failures."""


@fastapi_exception(handler="syntara.core.storage_error_handlers.storage_backend_unavailable_handler")
class StorageBackendUnavailableError(StorageBackendError):
    """Raised when the storage backend is unreachable (DB connection failure, timeout).

    Maps to HTTP 503 with retryable=True.
    """


@fastapi_exception(handler="syntara.core.storage_error_handlers.storage_backend_not_found_handler")
class StorageBackendNotFoundError(StorageBackendError):
    """Raised when requested secret data is not found in the backend.

    Replaces raw KeyError from DatabaseBackend._get_or_raise().
    Maps to HTTP 404 with retryable=False.
    """
