"""Tests for SecretService — secret lifecycle management."""

import os
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.core.lib.encryption import KEY_SIZE, SecretEncryptor
from syntara.core.services.secret_service import SecretService


@pytest.fixture
def encryptor() -> SecretEncryptor:
    """Create an encryptor with a random key."""
    return SecretEncryptor(os.urandom(KEY_SIZE))


@pytest.fixture
def mock_backend() -> MagicMock:
    """Create a mock StorageBackend."""
    backend = MagicMock()
    backend.store = AsyncMock()
    backend.retrieve = AsyncMock()
    backend.update = AsyncMock()
    backend.delete = AsyncMock()
    backend.health_check = AsyncMock(return_value=True)
    return backend


@pytest.fixture
def mock_session() -> MagicMock:
    """Create a mock AsyncSession."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    session.exec = AsyncMock()
    return session


@pytest.fixture
def secret_service(
    mock_session: MagicMock,
    encryptor: SecretEncryptor,
    mock_backend: MagicMock,
) -> SecretService:
    """Create a SecretService with mocked dependencies."""
    return SecretService(mock_session, encryptor, mock_backend)


class TestCreateSecret:
    """Tests for SecretService.create_secret."""

    @pytest.mark.asyncio
    async def test_creates_secret_and_stores_encrypted_data(
        self,
        secret_service: SecretService,
        mock_backend: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        plaintext = {"token": "sk-abc-123", "host": "api.example.com"}
        secret_id = await secret_service.create_secret(plaintext)

        assert secret_id is not None
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited()
        mock_backend.store.assert_awaited_once()

        # Verify encrypted data was passed to backend (not plaintext)
        call_args = mock_backend.store.call_args
        stored_data = call_args[0][1]
        assert set(stored_data.keys()) == {"token", "host"}
        assert stored_data["token"] != "sk-abc-123"  # noqa: S105  # encrypted, not plaintext

    @pytest.mark.asyncio
    async def test_empty_fields(
        self,
        secret_service: SecretService,
        mock_backend: MagicMock,
    ) -> None:
        secret_id = await secret_service.create_secret({})
        assert secret_id is not None
        mock_backend.store.assert_awaited_once()


class TestRetrieveSecret:
    """Tests for SecretService.retrieve_secret."""

    @pytest.mark.asyncio
    async def test_retrieves_and_decrypts(
        self,
        secret_service: SecretService,
        encryptor: SecretEncryptor,
        mock_backend: MagicMock,
    ) -> None:
        secret_id = uuid4()

        # Mock backend returns encrypted data
        encrypted = encryptor.encrypt_fields({"token": "secret-value"}, str(secret_id))
        mock_backend.retrieve.return_value = encrypted

        result = await secret_service.retrieve_secret(secret_id)
        assert result == {"token": "secret-value"}

    @pytest.mark.asyncio
    async def test_raises_on_missing_secret(
        self,
        secret_service: SecretService,
        mock_backend: MagicMock,
    ) -> None:
        mock_backend.retrieve.side_effect = KeyError("No encrypted data found")

        with pytest.raises(KeyError, match="No encrypted data found"):
            await secret_service.retrieve_secret(uuid4())


class TestUpdateSecret:
    """Tests for SecretService.update_secret."""

    @pytest.mark.asyncio
    async def test_re_encrypts_and_updates(
        self,
        secret_service: SecretService,
        mock_backend: MagicMock,
    ) -> None:
        secret_id = uuid4()

        await secret_service.update_secret(secret_id, {"token": "new-value"})

        mock_backend.update.assert_awaited_once()
        call_args = mock_backend.update.call_args
        stored_data = call_args[0][1]
        assert stored_data["token"] != "new-value"  # noqa: S105  # encrypted


class TestDeleteSecret:
    """Tests for SecretService.delete_secret."""

    @pytest.mark.asyncio
    async def test_deletes_backend_data_and_secret_row(
        self,
        secret_service: SecretService,
        mock_backend: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        secret_id = uuid4()

        # Mock the secret exists
        mock_secret = MagicMock()
        mock_secret.id = secret_id
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_secret
        mock_session.exec.return_value = mock_result

        await secret_service.delete_secret(secret_id)

        mock_backend.delete.assert_awaited_once_with(str(secret_id))
        mock_session.delete.assert_awaited_once_with(mock_secret)
        mock_session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_deletes_when_routing_record_missing(
        self,
        secret_service: SecretService,
        mock_backend: MagicMock,
        mock_session: MagicMock,
    ) -> None:
        """Backend data is still deleted even if Secret routing record is gone."""
        secret_id = uuid4()

        # Mock routing record not found
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.exec.return_value = mock_result

        await secret_service.delete_secret(secret_id)

        mock_backend.delete.assert_awaited_once_with(str(secret_id))
        mock_session.delete.assert_not_awaited()  # no row to delete
        mock_session.flush.assert_awaited()


class TestProtocolConformance:
    """Verify DatabaseBackend conforms to StorageBackend Protocol."""

    def test_database_backend_is_storage_backend(self, mock_session: MagicMock) -> None:
        from syntara.core.services.storage_backend import DatabaseBackend, StorageBackend

        backend = DatabaseBackend(mock_session)
        assert isinstance(backend, StorageBackend)


class TestAADBinding:
    """Verify SecretService uses secret_id for AAD, not credential_id."""

    @pytest.mark.asyncio
    async def test_encrypt_decrypt_round_trip_with_secret_id(
        self,
        secret_service: SecretService,
        encryptor: SecretEncryptor,
        mock_backend: MagicMock,
    ) -> None:
        """Data encrypted with secret_id can only be decrypted with same secret_id."""
        # Capture what gets stored and the key used
        stored_key = None
        stored_data = {}

        async def capture_store(key: str, data: dict[str, str]) -> None:
            nonlocal stored_key
            stored_key = key
            stored_data.update(data)

        mock_backend.store.side_effect = capture_store

        await secret_service.create_secret({"token": "test-value"})

        assert stored_key is not None

        # Verify the stored data can be decrypted with the secret_id used during encryption
        decrypted = encryptor.decrypt_fields(stored_data, stored_key)
        assert decrypted == {"token": "test-value"}

        # Verify it CANNOT be decrypted with a different ID
        from syntara.core.lib.encryption import EncryptionError

        with pytest.raises(EncryptionError):
            encryptor.decrypt_fields(stored_data, str(uuid4()))
