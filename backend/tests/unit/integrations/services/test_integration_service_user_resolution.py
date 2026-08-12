"""Unit tests for BaseService._resolve_user_fields via IntegrationService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from syntara.integrations.services.integration_service import IntegrationService


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    session.exec = AsyncMock()
    return session


@pytest.fixture
def mock_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    return user


@pytest.fixture
def service(mock_session: MagicMock, mock_user: MagicMock) -> IntegrationService:
    return IntegrationService(mock_session, mock_user)


class TestResolveUserFields:
    """Tests for BaseService._resolve_user_fields via IntegrationService."""

    @pytest.mark.asyncio
    async def test_resolves_uuids_to_usernames(self, service: IntegrationService, mock_session: MagicMock) -> None:
        user_id = uuid4()
        obj = MagicMock()
        obj.created_by = user_id
        obj.updated_by = None

        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([(user_id, "admin")]))
        mock_session.exec.return_value = mock_result

        await service._resolve_user_fields([obj])

        assert obj.created_by == "admin"

    @pytest.mark.asyncio
    async def test_skips_when_no_user_ids(self, service: IntegrationService, mock_session: MagicMock) -> None:
        obj = MagicMock()
        obj.created_by = None
        obj.updated_by = None

        await service._resolve_user_fields([obj])

        mock_session.exec.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_leaves_uuids_on_db_error(self, service: IntegrationService, mock_session: MagicMock) -> None:
        user_id = uuid4()
        obj = MagicMock()
        obj.created_by = user_id
        obj.updated_by = None

        mock_session.exec.side_effect = SQLAlchemyError("connection lost")

        await service._resolve_user_fields([obj])

        assert obj.created_by == user_id

    @pytest.mark.asyncio
    async def test_resolves_multiple_objects(self, service: IntegrationService, mock_session: MagicMock) -> None:
        user_id_1 = uuid4()
        user_id_2 = uuid4()

        obj1 = MagicMock()
        obj1.created_by = user_id_1
        obj1.updated_by = None
        obj2 = MagicMock()
        obj2.created_by = user_id_2
        obj2.updated_by = user_id_1

        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([(user_id_1, "alice"), (user_id_2, "bob")]))
        mock_session.exec.return_value = mock_result

        await service._resolve_user_fields([obj1, obj2])

        assert obj1.created_by == "alice"
        assert obj2.created_by == "bob"
        assert obj2.updated_by == "alice"

    @pytest.mark.asyncio
    async def test_empty_objects_list(self, service: IntegrationService, mock_session: MagicMock) -> None:
        await service._resolve_user_fields([])

        mock_session.exec.assert_not_awaited()
