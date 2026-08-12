"""Tests for DatabaseBackend — real encrypted_secrets table operations."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.core.services.storage_backend import DatabaseBackend
from syntara.core.storage_exceptions import StorageBackendNotFoundError


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
def backend(mock_session: MagicMock) -> DatabaseBackend:
    """Create a DatabaseBackend with mocked session."""
    return DatabaseBackend(mock_session)


class TestStore:
    """Tests for DatabaseBackend.store."""

    @pytest.mark.asyncio
    async def test_inserts_encrypted_secret(
        self,
        backend: DatabaseBackend,
        mock_session: MagicMock,
    ) -> None:
        key = str(uuid4())
        data = {"token": "encrypted-base64-value", "host": "encrypted-host"}

        await backend.store(key, data)

        mock_session.add.assert_called_once()
        added_obj = mock_session.add.call_args[0][0]
        assert str(added_obj.secret_id) == key
        assert added_obj.encrypted_data == data
        mock_session.flush.assert_awaited_once()


class TestRetrieve:
    """Tests for DatabaseBackend.retrieve."""

    @pytest.mark.asyncio
    async def test_returns_encrypted_data(
        self,
        backend: DatabaseBackend,
        mock_session: MagicMock,
    ) -> None:
        key = str(uuid4())
        expected_data = {"token": "encrypted-value"}

        mock_row = MagicMock()
        mock_row.encrypted_data = expected_data
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_row
        mock_session.exec.return_value = mock_result

        result = await backend.retrieve(key)
        assert result == expected_data

    @pytest.mark.asyncio
    async def test_raises_key_error_on_missing(
        self,
        backend: DatabaseBackend,
        mock_session: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.exec.return_value = mock_result

        with pytest.raises(StorageBackendNotFoundError, match="No encrypted data found"):
            await backend.retrieve(str(uuid4()))


class TestUpdate:
    """Tests for DatabaseBackend.update."""

    @pytest.mark.asyncio
    async def test_updates_encrypted_data(
        self,
        backend: DatabaseBackend,
        mock_session: MagicMock,
    ) -> None:
        key = str(uuid4())
        new_data = {"token": "new-encrypted-value"}

        mock_row = MagicMock()
        mock_row.encrypted_data = {"token": "old-value"}
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_row
        mock_session.exec.return_value = mock_result

        await backend.update(key, new_data)

        assert mock_row.encrypted_data == new_data
        mock_session.add.assert_called_once_with(mock_row)
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_key_error_on_missing(
        self,
        backend: DatabaseBackend,
        mock_session: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.exec.return_value = mock_result

        with pytest.raises(StorageBackendNotFoundError, match="No encrypted data found"):
            await backend.update(str(uuid4()), {"token": "value"})


class TestDelete:
    """Tests for DatabaseBackend.delete."""

    @pytest.mark.asyncio
    async def test_deletes_encrypted_secret(
        self,
        backend: DatabaseBackend,
        mock_session: MagicMock,
    ) -> None:
        key = str(uuid4())

        mock_row = MagicMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_row
        mock_session.exec.return_value = mock_result

        await backend.delete(key)

        mock_session.delete.assert_awaited_once_with(mock_row)
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_key_error_on_missing(
        self,
        backend: DatabaseBackend,
        mock_session: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.exec.return_value = mock_result

        with pytest.raises(StorageBackendNotFoundError, match="No encrypted data found"):
            await backend.delete(str(uuid4()))


class TestHealthCheck:
    """Tests for DatabaseBackend.health_check."""

    @pytest.mark.asyncio
    async def test_returns_true_when_db_reachable(self, backend: DatabaseBackend, mock_session: MagicMock) -> None:
        mock_session.exec = AsyncMock()
        result = await backend.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_db_unreachable(self, backend: DatabaseBackend, mock_session: MagicMock) -> None:
        from sqlalchemy.exc import OperationalError

        mock_session.exec = AsyncMock(side_effect=OperationalError("conn refused", {}, Exception("conn refused")))
        result = await backend.health_check()
        assert result is False
