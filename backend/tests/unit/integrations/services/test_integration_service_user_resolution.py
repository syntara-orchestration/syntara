"""Unit tests for IntegrationService.resolve_user_references."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from syntara.core.models.user_reference import UserReference
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


class TestResolveUserReferences:
    """Tests for resolving UUID audit fields to UserReference objects."""

    @pytest.mark.asyncio
    async def test_resolves_uuids_to_user_references(
        self, service: IntegrationService, mock_session: MagicMock
    ) -> None:
        user_id = uuid4()
        obj = SimpleNamespace(created_by=user_id, updated_by=None)

        # Lookup rows carry principal id, username, first and last name, then SA name.
        mock_session.exec.return_value = [(user_id, "admin", None, None, None)]

        await service.resolve_user_references([obj])

        assert isinstance(obj.created_by, UserReference)
        assert obj.created_by.id == user_id
        assert obj.created_by.name == "admin"

    @pytest.mark.asyncio
    async def test_skips_when_no_user_ids(self, service: IntegrationService, mock_session: MagicMock) -> None:
        obj = SimpleNamespace(created_by=None, updated_by=None)

        await service.resolve_user_references([obj])

        mock_session.exec.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_clears_fields_on_db_error(self, service: IntegrationService, mock_session: MagicMock) -> None:
        user_id = uuid4()
        obj = SimpleNamespace(created_by=user_id, updated_by=None)

        mock_session.exec.side_effect = SQLAlchemyError("connection lost")

        await service.resolve_user_references([obj])

        assert obj.created_by is None

    @pytest.mark.asyncio
    async def test_resolves_multiple_objects(self, service: IntegrationService, mock_session: MagicMock) -> None:
        user_id_1 = uuid4()
        user_id_2 = uuid4()

        obj1 = SimpleNamespace(created_by=user_id_1, updated_by=None)
        obj2 = SimpleNamespace(created_by=user_id_2, updated_by=user_id_1)

        mock_session.exec.return_value = [
            (user_id_1, "alice", None, None, None),
            (user_id_2, "bob", None, None, None),
        ]

        await service.resolve_user_references([obj1, obj2])

        assert isinstance(obj1.created_by, UserReference)
        assert obj1.created_by.name == "alice"
        assert isinstance(obj2.created_by, UserReference)
        assert obj2.created_by.name == "bob"
        assert isinstance(obj2.updated_by, UserReference)
        assert obj2.updated_by.name == "alice"

    @pytest.mark.asyncio
    async def test_empty_objects_list(self, service: IntegrationService, mock_session: MagicMock) -> None:
        await service.resolve_user_references([])

        mock_session.exec.assert_not_awaited()
