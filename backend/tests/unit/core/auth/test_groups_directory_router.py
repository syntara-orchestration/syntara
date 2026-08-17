"""Unit tests for groups directory endpoint."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.users.groups_directory_router import (
    GroupDirectoryEntry,
    GroupDirectoryListResponse,
    _GroupDirectoryService,
    list_groups_directory,
)


class TestListGroupsDirectory:
    """Tests for GET /groups/directory."""

    @pytest.mark.asyncio
    async def test_returns_lightweight_entries(self) -> None:
        gid1 = uuid4()
        gid2 = uuid4()
        expected = GroupDirectoryListResponse(
            resources=[
                GroupDirectoryEntry(id=gid1, name="admins"),
                GroupDirectoryEntry(id=gid2, name="engineers"),
            ],
            next=None,
            prev=None,
            total=None,
        )

        service = AsyncMock(spec=_GroupDirectoryService)
        service.list_directory = AsyncMock(return_value=expected)

        request = MagicMock()
        request.query_params.items.return_value = []

        params = MagicMock()
        params.limit = 20
        params.cursor = None
        params.sort = None
        params.include_total = False

        result = await list_groups_directory(request, service, params)

        assert len(result.resources) == 2
        assert result.resources[0].name == "admins"
        assert result.resources[1].name == "engineers"
        service.list_directory.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_pagination_params(self) -> None:
        expected = GroupDirectoryListResponse(resources=[], next=None, prev=None, total=3)
        service = AsyncMock(spec=_GroupDirectoryService)
        service.list_directory = AsyncMock(return_value=expected)

        request = MagicMock()
        request.query_params.items.return_value = [("name[contains]", "admin")]

        params = MagicMock()
        params.limit = 5
        params.cursor = "xyz"
        params.sort = "name"
        params.include_total = True

        result = await list_groups_directory(request, service, params)

        service.list_directory.assert_called_once_with(
            limit=5,
            cursor="xyz",
            sort="name",
            query_params_items=[("name[contains]", "admin")],
            include_total=True,
        )
        assert result.total == 3

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        expected = GroupDirectoryListResponse(resources=[], next=None, prev=None, total=0)
        service = AsyncMock(spec=_GroupDirectoryService)
        service.list_directory = AsyncMock(return_value=expected)

        request = MagicMock()
        request.query_params.items.return_value = []

        params = MagicMock()
        params.limit = 20
        params.cursor = None
        params.sort = None
        params.include_total = True

        result = await list_groups_directory(request, service, params)

        assert result.resources == []
        assert result.total == 0


class TestGroupDirectoryEntry:
    """Tests for the GroupDirectoryEntry schema."""

    def test_fields(self) -> None:
        gid = uuid4()
        entry = GroupDirectoryEntry(id=gid, name="admins")
        assert entry.id == gid
        assert entry.name == "admins"
