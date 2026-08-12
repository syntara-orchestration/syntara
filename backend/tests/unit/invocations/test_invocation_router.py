"""Unit tests for the invocation router list_invocations endpoint.

Verifies that the VisibilityFilter result is correctly forwarded to
the InvocationService.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from syntara.invocations.router import list_invocations


class TestListInvocationsVisibility:
    """Verify list_invocations passes allowed_projects from visibility to service."""

    @pytest.mark.asyncio
    async def test_allowed_projects_forwarded_to_service(self) -> None:
        mock_service = AsyncMock()
        mock_service.list_invocations.return_value = MagicMock()

        mock_request = MagicMock()
        mock_request.query_params.items.return_value = []

        mock_params = MagicMock()
        mock_params.limit = 10
        mock_params.cursor = None
        mock_params.sort = None
        mock_params.include_total = False

        mock_allowed = MagicMock()
        mock_visibility = MagicMock()
        mock_visibility.to_allowed_projects.return_value = mock_allowed

        result = await list_invocations(
            request=mock_request,
            service=mock_service,
            params=mock_params,
            visibility=mock_visibility,
        )

        mock_visibility.to_allowed_projects.assert_called_once()
        mock_service.list_invocations.assert_awaited_once_with(
            limit=10,
            cursor=None,
            sort=None,
            query_params_items=[],
            include_total=False,
            allowed_projects=mock_allowed,
        )
        assert result is mock_service.list_invocations.return_value

    @pytest.mark.asyncio
    async def test_none_visibility_forwarded_when_unrestricted(self) -> None:
        mock_service = AsyncMock()
        mock_service.list_invocations.return_value = MagicMock()

        mock_request = MagicMock()
        mock_request.query_params.items.return_value = []

        mock_params = MagicMock()
        mock_params.limit = 20
        mock_params.cursor = "abc"
        mock_params.sort = "-created_at"
        mock_params.include_total = True

        mock_visibility = MagicMock()
        mock_visibility.to_allowed_projects.return_value = None

        await list_invocations(
            request=mock_request,
            service=mock_service,
            params=mock_params,
            visibility=mock_visibility,
        )

        mock_service.list_invocations.assert_awaited_once_with(
            limit=20,
            cursor="abc",
            sort="-created_at",
            query_params_items=[],
            include_total=True,
            allowed_projects=None,
        )
