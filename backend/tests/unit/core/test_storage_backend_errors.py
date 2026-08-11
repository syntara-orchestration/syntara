"""Tests for graceful storage backend error handling (T083)."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import DatabaseError, OperationalError

from syntara.core.services.storage_backend import DatabaseBackend
from syntara.core.storage_exceptions import StorageBackendNotFoundError, StorageBackendUnavailableError


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


class TestGetOrRaise:
    """Tests for _get_or_raise error wrapping."""

    @pytest.mark.asyncio
    async def test_missing_key_raises_not_found(self, backend: DatabaseBackend, mock_session: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.exec.return_value = mock_result

        with pytest.raises(StorageBackendNotFoundError, match="No encrypted data found"):
            await backend.retrieve(str(uuid4()))

    @pytest.mark.asyncio
    async def test_db_error_raises_unavailable(self, backend: DatabaseBackend, mock_session: MagicMock) -> None:
        mock_session.exec = AsyncMock(
            side_effect=OperationalError("connection refused", {}, Exception("connection refused"))
        )

        with pytest.raises(StorageBackendUnavailableError, match="unavailable during secret lookup"):
            await backend.retrieve(str(uuid4()))


class TestStoreErrors:
    """Tests for store() error wrapping."""

    @pytest.mark.asyncio
    async def test_db_error_on_store_raises_unavailable(
        self, backend: DatabaseBackend, mock_session: MagicMock
    ) -> None:
        mock_session.flush = AsyncMock(side_effect=OperationalError("pool exhausted", {}, Exception("pool exhausted")))

        with pytest.raises(StorageBackendUnavailableError, match="unavailable during secret storage"):
            await backend.store(str(uuid4()), {"token": "value"})

    @pytest.mark.asyncio
    async def test_database_error_on_store_raises_unavailable(
        self, backend: DatabaseBackend, mock_session: MagicMock
    ) -> None:
        mock_session.flush = AsyncMock(side_effect=DatabaseError("disk full", {}, Exception("disk full")))

        with pytest.raises(StorageBackendUnavailableError, match="unavailable during secret storage"):
            await backend.store(str(uuid4()), {"token": "value"})


class TestUpdateErrors:
    """Tests for update() error wrapping."""

    @pytest.mark.asyncio
    async def test_db_error_on_update_raises_unavailable(
        self, backend: DatabaseBackend, mock_session: MagicMock
    ) -> None:
        mock_row = MagicMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_row
        mock_session.exec.return_value = mock_result
        mock_session.flush = AsyncMock(side_effect=OperationalError("timeout", {}, Exception("timeout")))

        with pytest.raises(StorageBackendUnavailableError, match="unavailable during secret update"):
            await backend.update(str(uuid4()), {"token": "new-value"})


class TestDeleteErrors:
    """Tests for delete() error wrapping."""

    @pytest.mark.asyncio
    async def test_db_error_on_delete_raises_unavailable(
        self, backend: DatabaseBackend, mock_session: MagicMock
    ) -> None:
        mock_row = MagicMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_row
        mock_session.exec.return_value = mock_result
        mock_session.delete = AsyncMock(side_effect=OperationalError("conn reset", {}, Exception("conn reset")))

        with pytest.raises(StorageBackendUnavailableError, match="unavailable during secret deletion"):
            await backend.delete(str(uuid4()))


class TestHealthCheck:
    """Tests for health_check() with real DB check."""

    @pytest.mark.asyncio
    async def test_healthy_returns_true(self, backend: DatabaseBackend, mock_session: MagicMock) -> None:
        mock_session.exec = AsyncMock()
        assert await backend.health_check() is True

    @pytest.mark.asyncio
    async def test_unreachable_returns_false(self, backend: DatabaseBackend, mock_session: MagicMock) -> None:
        mock_session.exec = AsyncMock(
            side_effect=OperationalError("connection refused", {}, Exception("connection refused"))
        )
        assert await backend.health_check() is False

    @pytest.mark.asyncio
    async def test_database_error_returns_false(self, backend: DatabaseBackend, mock_session: MagicMock) -> None:
        mock_session.exec = AsyncMock(side_effect=DatabaseError("corrupt", {}, Exception("corrupt")))
        assert await backend.health_check() is False
