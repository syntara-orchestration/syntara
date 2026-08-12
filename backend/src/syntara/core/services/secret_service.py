"""SecretService — shared service for managing secret lifecycle.

Wraps the StorageBackend Protocol and SecretEncryptor to provide
a single entry point for creating, retrieving, updating, and deleting
encrypted secret data. Consumers (CredentialService, IdentityProviderService,
future GlobalSettingsService) pass plaintext and receive plaintext —
encryption is an implementation detail.
"""

from typing import Any
from uuid import UUID

import structlog
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import get_encryption_key
from syntara.core.lib.encryption import SecretEncryptor, key_from_string
from syntara.core.models.secret import Secret
from syntara.core.services.storage_backend import DatabaseBackend, StorageBackend

logger = structlog.stdlib.get_logger(__name__)


class SecretService:
    """Manages Secret resource lifecycle and delegates to StorageBackend.

    The Secret table is a routing record (zero secret values).
    Encrypted field data is stored in the backend (encrypted_secrets for GA).
    AAD binding uses secret_id:field_name.
    """

    def __init__(
        self,
        session: AsyncSession,
        encryptor: SecretEncryptor,
        backend: StorageBackend,
    ) -> None:
        """Initialize with database session, encryptor, and storage backend."""
        self._session = session
        self._encryptor = encryptor
        self._backend = backend

    async def create_secret(self, plaintext_fields: dict[str, Any]) -> UUID:
        """Create a Secret routing record and store encrypted data via backend.

        Args:
            plaintext_fields: Dictionary of field_name -> plaintext value.

        Returns:
            The UUID of the newly created Secret record.

        """
        secret = Secret()
        self._session.add(secret)
        await self._session.flush()

        encrypted = self._encryptor.encrypt_fields(plaintext_fields, str(secret.id))
        await self._backend.store(str(secret.id), encrypted)

        logger.info("Secret created", secret_id=str(secret.id))
        return secret.id

    async def retrieve_secret(self, secret_id: UUID) -> dict[str, Any]:
        """Retrieve and decrypt all fields for a secret.

        Args:
            secret_id: UUID of the Secret routing record.

        Returns:
            Dictionary of field_name -> plaintext value.

        Raises:
            KeyError: If the secret does not exist in the backend.

        """
        encrypted = await self._backend.retrieve(str(secret_id))
        return self._encryptor.decrypt_fields(encrypted, str(secret_id))

    async def update_secret(self, secret_id: UUID, plaintext_fields: dict[str, Any]) -> None:
        """Re-encrypt and update stored fields for a secret.

        Args:
            secret_id: UUID of the Secret routing record.
            plaintext_fields: Dictionary of field_name -> new plaintext value.

        Raises:
            KeyError: If the secret does not exist in the backend.

        """
        encrypted = self._encryptor.encrypt_fields(plaintext_fields, str(secret_id))
        await self._backend.update(str(secret_id), encrypted)
        logger.info("Secret updated", secret_id=str(secret_id))

    async def delete_secret(self, secret_id: UUID) -> None:
        """Delete the Secret routing record and its stored data.

        Args:
            secret_id: UUID of the Secret routing record.

        Raises:
            KeyError: If the secret does not exist in the backend.

        """
        # Delete backend data first (EncryptedSecret), then routing record (Secret)
        # to respect FK constraint: encrypted_secrets.secret_id → secrets.id
        await self._backend.delete(str(secret_id))

        stmt = select(Secret).where(Secret.id == secret_id)
        result = await self._session.exec(stmt)
        secret = result.one_or_none()
        if secret:
            await self._session.delete(secret)
        else:
            logger.warning(
                "Secret routing record not found during delete — possible data inconsistency",
                secret_id=str(secret_id),
            )

        await self._session.flush()

        logger.info("Secret deleted", secret_id=str(secret_id))


def create_secret_service(session: AsyncSession) -> SecretService:
    """Create a SecretService with encryptor and backend wired from settings.

    Encapsulates the encryption key lookup, encryptor creation, and backend
    construction so callers don't need to know the internal wiring.
    """
    encryptor = SecretEncryptor(key_from_string(get_encryption_key().get_secret_value()))
    backend = DatabaseBackend(session)
    return SecretService(session, encryptor, backend)
