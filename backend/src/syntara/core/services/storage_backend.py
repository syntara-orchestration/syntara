"""Pluggable storage backend protocol for sensitive data.

This protocol is generic — designed to serve all sensitive data
(Credentials, application settings, OIDC configs), not just Credentials.
GA implementation: DatabaseBackend stores encrypted data in the
encrypted_secrets PostgreSQL table.
"""

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

import structlog
from sqlalchemy.exc import DatabaseError, OperationalError
from sqlmodel import select, text
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models.secret import EncryptedSecret
from syntara.core.storage_exceptions import StorageBackendNotFoundError, StorageBackendUnavailableError

logger = structlog.stdlib.get_logger(__name__)


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for storing and retrieving encrypted sensitive data.

    Implementations may store data in a database, HashiCorp Vault,
    AWS Secrets Manager, Azure Key Vault, or CyberArk Conjur.
    """

    async def store(self, key: str, data: dict[str, Any]) -> None:
        """Store encrypted data under the given key.

        Args:
            key: Unique identifier (secret_id UUID as string).
            data: Dictionary of field_name -> encrypted value.

        """
        ...

    async def retrieve(self, key: str) -> dict[str, Any]:
        """Retrieve encrypted data by key.

        Args:
            key: Unique identifier (secret_id UUID as string).

        Returns:
            Dictionary of field_name -> encrypted value.

        Raises:
            StorageBackendNotFoundError: If the key does not exist.

        """
        ...

    async def update(self, key: str, data: dict[str, Any]) -> None:
        """Update encrypted data for the given key.

        Args:
            key: Unique identifier (secret_id UUID as string).
            data: Updated dictionary of field_name -> encrypted value.

        Raises:
            StorageBackendNotFoundError: If the key does not exist.

        """
        ...

    async def delete(self, key: str) -> None:
        """Delete encrypted data by key.

        Args:
            key: Unique identifier (secret_id UUID as string).

        Raises:
            StorageBackendNotFoundError: If the key does not exist.

        """
        ...

    async def health_check(self) -> bool:
        """Check if the storage backend is available.

        Returns:
            True if the backend is healthy and reachable.

        """
        ...


class DatabaseBackend:
    """GA storage backend — stores encrypted data in the encrypted_secrets table.

    Each secret's encrypted field values are stored as a JSONB dict
    in the encrypted_secrets table, keyed by secret_id (1:1 with secrets table).
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize with an async database session."""
        self._session = session

    async def _get_or_raise(self, key: str) -> EncryptedSecret:
        """Fetch EncryptedSecret by key or raise StorageBackendNotFoundError."""
        try:
            stmt = select(EncryptedSecret).where(EncryptedSecret.secret_id == UUID(key))
            result = await self._session.exec(stmt)
        except (OperationalError, DatabaseError) as e:
            msg = "Storage backend unavailable during secret lookup"
            raise StorageBackendUnavailableError(msg) from e
        encrypted_secret = result.one_or_none()
        if encrypted_secret is None:
            msg = f"No encrypted data found for key '{key}'"
            raise StorageBackendNotFoundError(msg)
        return encrypted_secret

    async def store(self, key: str, data: dict[str, Any]) -> None:
        """Store encrypted data in encrypted_secrets table."""
        try:
            encrypted_secret = EncryptedSecret(secret_id=UUID(key), encrypted_data=data)
            self._session.add(encrypted_secret)
            await self._session.flush()
        except (OperationalError, DatabaseError) as e:
            msg = "Storage backend unavailable during secret storage"
            raise StorageBackendUnavailableError(msg) from e

    async def retrieve(self, key: str) -> dict[str, Any]:
        """Retrieve encrypted data from encrypted_secrets table."""
        return (await self._get_or_raise(key)).encrypted_data

    async def update(self, key: str, data: dict[str, Any]) -> None:
        """Update encrypted data in encrypted_secrets table."""
        encrypted_secret = await self._get_or_raise(key)
        try:
            # Full dict replacement (not in-place mutation) so SQLAlchemy detects JSONB change
            encrypted_secret.encrypted_data = data
            self._session.add(encrypted_secret)
            await self._session.flush()
        except (OperationalError, DatabaseError) as e:
            msg = "Storage backend unavailable during secret update"
            raise StorageBackendUnavailableError(msg) from e

    async def delete(self, key: str) -> None:
        """Delete encrypted data from encrypted_secrets table."""
        encrypted_secret = await self._get_or_raise(key)
        try:
            await self._session.delete(encrypted_secret)
            await self._session.flush()
        except (OperationalError, DatabaseError) as e:
            msg = "Storage backend unavailable during secret deletion"
            raise StorageBackendUnavailableError(msg) from e

    async def health_check(self) -> bool:
        """Check if the database is reachable via a simple query."""
        try:
            # SECURITY: keep as static literal — never interpolate variables
            await self._session.exec(text("SELECT 1"))  # type: ignore[call-overload]
        except (OperationalError, DatabaseError):
            logger.warning("Storage backend health check failed", exc_info=True)
            return False
        return True
