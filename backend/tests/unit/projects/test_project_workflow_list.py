"""Unit tests for list_project_workflows endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.authz.engine import AllowedProjectsResult
from syntara.projects.router import list_project_workflows


class TestListProjectWorkflows:
    """Tests for the list_project_workflows endpoint."""

    @pytest.mark.asyncio
    async def test_populates_published_version_numbers(self) -> None:
        """Verify endpoint calls populate_published_version_numbers on result."""
        project_id = uuid4()
        mock_service = AsyncMock()
        mock_result = MagicMock()
        mock_result.resources = [MagicMock()]
        mock_service.list_workflows_cursor.return_value = mock_result

        mock_request = MagicMock()
        mock_request.query_params.items.return_value = []

        mock_params = MagicMock()
        mock_params.limit = 10
        mock_params.cursor = None
        mock_params.sort = None
        mock_params.include_total = False

        result = await list_project_workflows(
            project_id=project_id,
            request=mock_request,
            service=mock_service,
            params=mock_params,
        )

        expected_allowed = AllowedProjectsResult(all_projects=False, project_ids=[project_id])
        mock_service.list_workflows_cursor.assert_awaited_once_with(
            limit=10,
            cursor=None,
            sort=None,
            query_params_items=[],
            include_total=False,
            allowed_projects=expected_allowed,
        )
        mock_service.populate_published_version_numbers.assert_awaited_once_with(mock_result.resources)
        assert result is mock_result
