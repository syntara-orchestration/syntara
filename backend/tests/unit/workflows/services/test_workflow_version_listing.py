"""Unit tests for workflow version listing and published_version_number population."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

if TYPE_CHECKING:
    from collections.abc import Callable

import pytest

from syntara.workflows.models.workflow import WorkflowRead
from syntara.workflows.router import _populate_published_version_number
from syntara.workflows.services.workflow_service import WorkflowService


@pytest.fixture
def mock_service() -> WorkflowService:
    """Create a WorkflowService with mocked dependencies."""
    session = AsyncMock()
    user = MagicMock()
    user.id = uuid4()
    service = WorkflowService.__new__(WorkflowService)
    service.session = session
    service.user = user
    return service


class TestPopulatePublishedVersionNumbers:
    """Tests for batch-populating published_version_number on WorkflowRead objects."""

    @pytest.mark.asyncio
    async def test_populates_version_numbers(self, mock_service: WorkflowService) -> None:
        pub_id_1 = uuid4()
        pub_id_2 = uuid4()

        w1 = WorkflowRead(
            id=uuid4(),
            name="w1",
            labels={},
            current_version=3,
            is_builtin=False,
            is_enabled=True,
            has_validation_issues=False,
            published_version_id=pub_id_1,
            created_by=uuid4(),
            project_id=uuid4(),
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        w2 = WorkflowRead(
            id=uuid4(),
            name="w2",
            labels={},
            current_version=5,
            is_builtin=False,
            is_enabled=True,
            has_validation_issues=False,
            published_version_id=pub_id_2,
            created_by=uuid4(),
            project_id=uuid4(),
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([(pub_id_1, 2), (pub_id_2, 4)]))
        mock_exec = AsyncMock(return_value=mock_result)

        with patch.object(mock_service.session, "exec", mock_exec):
            await mock_service.populate_published_version_numbers([w1, w2])

        assert w1.published_version_number == 2
        assert w2.published_version_number == 4

    @pytest.mark.asyncio
    async def test_skips_unpublished_workflows(self, mock_service: WorkflowService) -> None:
        w = WorkflowRead(
            id=uuid4(),
            name="unpub",
            labels={},
            current_version=1,
            is_builtin=False,
            is_enabled=False,
            has_validation_issues=False,
            published_version_id=None,
            created_by=uuid4(),
            project_id=uuid4(),
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

        mock_exec = AsyncMock()
        with patch.object(mock_service.session, "exec", mock_exec):
            await mock_service.populate_published_version_numbers([w])

        assert w.published_version_number is None
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_empty_list(self, mock_service: WorkflowService) -> None:
        mock_exec = AsyncMock()
        with patch.object(mock_service.session, "exec", mock_exec):
            await mock_service.populate_published_version_numbers([])
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_missing_version_record(self, mock_service: WorkflowService) -> None:
        pub_id = uuid4()
        w = WorkflowRead(
            id=uuid4(),
            name="missing",
            labels={},
            current_version=2,
            is_builtin=False,
            is_enabled=True,
            has_validation_issues=False,
            published_version_id=pub_id,
            created_by=uuid4(),
            project_id=uuid4(),
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([]))
        mock_exec = AsyncMock(return_value=mock_result)

        with patch.object(mock_service.session, "exec", mock_exec):
            await mock_service.populate_published_version_numbers([w])

        assert w.published_version_number is None


class TestPopulatePublishedVersionNumberSingle:
    """Tests for _populate_published_version_number router helper."""

    @pytest.mark.asyncio
    async def test_sets_number_when_current_is_published(self) -> None:
        version_id = uuid4()
        mock_session = AsyncMock()
        workflow = MagicMock()
        workflow.published_version_id = version_id
        version = MagicMock()
        version.id = version_id
        version.version = 3

        workflow_read = MagicMock(spec=WorkflowRead)
        await _populate_published_version_number(workflow_read, workflow, version, mock_session)

        assert workflow_read.published_version_number == 3

    @pytest.mark.asyncio
    async def test_skips_when_version_not_published(self) -> None:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_session.exec = AsyncMock(return_value=mock_result)
        workflow = MagicMock()
        workflow.published_version_id = uuid4()
        version = MagicMock()
        version.id = uuid4()

        workflow_read = MagicMock(spec=WorkflowRead)
        workflow_read.published_version_number = None
        await _populate_published_version_number(workflow_read, workflow, version, mock_session)

        assert workflow_read.published_version_number is None

    @pytest.mark.asyncio
    async def test_skips_when_unpublished(self) -> None:
        mock_session = AsyncMock()
        workflow = MagicMock()
        workflow.published_version_id = None
        version = MagicMock()

        workflow_read = MagicMock(spec=WorkflowRead)
        workflow_read.published_version_number = None
        await _populate_published_version_number(workflow_read, workflow, version, mock_session)

        assert workflow_read.published_version_number is None


class TestListWorkflowVersionsCursorCallbacks:
    """Tests for the inner callbacks used by list_workflow_versions_cursor."""

    @pytest.mark.asyncio
    async def test_populate_usernames_callback(self, mock_service: WorkflowService) -> None:
        workflow_id = uuid4()
        user_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.published_version_id = None

        captured: dict[str, Any] = {}

        async def capture_list_resources(**kwargs: Any) -> MagicMock:  # noqa: ANN401
            captured["post_query_callback"] = kwargs.get("post_query_callback")
            return MagicMock()

        mock_list = AsyncMock(side_effect=capture_list_resources)

        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([(user_id, "testuser")]))
        mock_exec = AsyncMock(return_value=mock_result)

        with (
            patch.object(mock_service, "get_workflow_by_id", new_callable=AsyncMock, return_value=mock_workflow),
            patch.object(WorkflowService, "list_resources", mock_list),
        ):
            await mock_service.list_workflow_versions_cursor(workflow_id=workflow_id)

        callback: Callable[..., Any] = captured["post_query_callback"]
        mock_version = MagicMock()
        mock_version.created_by = user_id
        with patch.object(mock_service.session, "exec", mock_exec):
            await callback([mock_version])
        mock_exec.assert_called()

    @pytest.mark.asyncio
    async def test_populate_usernames_skips_empty(self, mock_service: WorkflowService) -> None:
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.published_version_id = None

        captured: dict[str, Any] = {}

        async def capture_list_resources(**kwargs: Any) -> MagicMock:  # noqa: ANN401
            captured["post_query_callback"] = kwargs.get("post_query_callback")
            return MagicMock()

        mock_list = AsyncMock(side_effect=capture_list_resources)

        with (
            patch.object(mock_service, "get_workflow_by_id", new_callable=AsyncMock, return_value=mock_workflow),
            patch.object(WorkflowService, "list_resources", mock_list),
        ):
            await mock_service.list_workflow_versions_cursor(workflow_id=workflow_id)

        callback: Callable[..., Any] = captured["post_query_callback"]
        mock_exec = AsyncMock()
        with patch.object(mock_service.session, "exec", mock_exec):
            await callback([])
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_convert_version_callback(self, mock_service: WorkflowService) -> None:
        workflow_id = uuid4()
        pub_version_id = uuid4()
        user_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.published_version_id = pub_version_id

        captured: dict[str, Any] = {}

        async def capture_list_resources(**kwargs: Any) -> MagicMock:  # noqa: ANN401
            captured["response_type_converter"] = kwargs.get("response_type_converter")
            return MagicMock()

        mock_list = AsyncMock(side_effect=capture_list_resources)

        with (
            patch.object(mock_service, "get_workflow_by_id", new_callable=AsyncMock, return_value=mock_workflow),
            patch.object(WorkflowService, "list_resources", mock_list),
        ):
            await mock_service.list_workflow_versions_cursor(workflow_id=workflow_id)

        converter: Callable[..., Any] = captured["response_type_converter"]
        mock_version = MagicMock()
        mock_version.id = pub_version_id
        mock_version.workflow_id = workflow_id
        mock_version.version = 1
        mock_version.schema_version = "2.0.0"
        mock_version.workflow_definition = {"nodes": []}
        mock_version.change_description = None
        mock_version.name = None
        mock_version.created_by = user_id
        mock_version.created_at = MagicMock()
        mock_version.updated_at = MagicMock()
        mock_version.deleted_at = None
        mock_version.deleted_by = None

        result = converter(mock_version)
        assert result is not None

    @pytest.mark.asyncio
    async def test_merges_extra_query_params(self, mock_service: WorkflowService) -> None:
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.published_version_id = None

        mock_list = AsyncMock(return_value=MagicMock())

        with (
            patch.object(mock_service, "get_workflow_by_id", new_callable=AsyncMock, return_value=mock_workflow),
            patch.object(WorkflowService, "list_resources", mock_list),
        ):
            await mock_service.list_workflow_versions_cursor(
                workflow_id=workflow_id,
                query_params_items=[("status", "published")],
            )

        call_kwargs = mock_list.call_args
        query_params = call_kwargs.kwargs["query_params_items"]
        assert ("workflow_id", str(workflow_id)) in query_params
        assert ("status", "published") in query_params


class TestListWorkflowVersionsCursor:
    """Tests for list_workflow_versions_cursor service method."""

    @pytest.mark.asyncio
    async def test_delegates_to_list_resources(self, mock_service: WorkflowService) -> None:
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.published_version_id = uuid4()

        expected_response = MagicMock()
        mock_list = AsyncMock(return_value=expected_response)

        with (
            patch.object(mock_service, "get_workflow_by_id", new_callable=AsyncMock, return_value=mock_workflow),
            patch.object(WorkflowService, "list_resources", mock_list),
        ):
            result = await mock_service.list_workflow_versions_cursor(
                workflow_id=workflow_id,
                limit=10,
                sort="-created_at",
            )

        assert result is expected_response
        mock_list.assert_called_once()
        call_kwargs = mock_list.call_args
        assert call_kwargs.kwargs["limit"] == 10
        assert call_kwargs.kwargs["sort"] == "-created_at"

    @pytest.mark.asyncio
    async def test_injects_workflow_id_filter(self, mock_service: WorkflowService) -> None:
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.published_version_id = None

        mock_list = AsyncMock(return_value=MagicMock())

        with (
            patch.object(mock_service, "get_workflow_by_id", new_callable=AsyncMock, return_value=mock_workflow),
            patch.object(WorkflowService, "list_resources", mock_list),
        ):
            await mock_service.list_workflow_versions_cursor(workflow_id=workflow_id)

        call_kwargs = mock_list.call_args
        query_params = call_kwargs.kwargs["query_params_items"]
        assert ("workflow_id", str(workflow_id)) in query_params

    @pytest.mark.asyncio
    async def test_defaults_sort_to_created_at_desc(self, mock_service: WorkflowService) -> None:
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.published_version_id = None

        mock_list = AsyncMock(return_value=MagicMock())

        with (
            patch.object(mock_service, "get_workflow_by_id", new_callable=AsyncMock, return_value=mock_workflow),
            patch.object(WorkflowService, "list_resources", mock_list),
        ):
            await mock_service.list_workflow_versions_cursor(workflow_id=workflow_id)

        call_kwargs = mock_list.call_args
        assert call_kwargs.kwargs["sort"] == "-created_at"
