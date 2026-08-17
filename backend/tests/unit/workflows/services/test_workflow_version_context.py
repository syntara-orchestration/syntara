"""Unit tests for version context population.

Covers list_workflow_versions_cursor inner callbacks (populate_version_context,
convert_version), the IDOR-prevention merge logic, and the batch population of
published_version_number on WorkflowRead objects.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from syntara.workflows.models.workflow import WorkflowRead
from syntara.workflows.models.workflow_publish_event import PublishAction
from syntara.workflows.services.workflow_service import WorkflowService

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def mock_service() -> WorkflowService:
    """Create a WorkflowService with mocked session and user."""
    session = AsyncMock()
    session.add = MagicMock()
    user = MagicMock()
    user.id = uuid4()
    service = WorkflowService.__new__(WorkflowService)
    service.session = session
    service.user = user
    return service


def _make_workflow_read(**overrides: object) -> WorkflowRead:
    """Build a WorkflowRead with sensible defaults, overridable by keyword."""
    defaults: dict[str, object] = {
        "id": uuid4(),
        "name": "wf",
        "labels": {},
        "current_version": 1,
        "is_builtin": False,
        "is_enabled": True,
        "has_validation_issues": False,
        "published_version_id": None,
        "created_by": uuid4(),
        "project_id": uuid4(),
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }
    defaults.update(overrides)
    return WorkflowRead(**defaults)


async def _capture_callbacks(
    mock_service: WorkflowService,
    workflow_id: UUID,
    published_version_id: UUID | None = None,
    query_params_items: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Invoke list_workflow_versions_cursor and capture the callbacks."""
    mock_workflow = MagicMock()
    mock_workflow.id = workflow_id
    mock_workflow.published_version_id = published_version_id

    captured: dict[str, Any] = {}

    async def capture_list_resources(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return MagicMock()

    mock_list = AsyncMock(side_effect=capture_list_resources)

    call_kwargs: dict[str, Any] = {"workflow_id": workflow_id}
    if query_params_items is not None:
        call_kwargs["query_params_items"] = query_params_items

    with (
        patch.object(mock_service, "get_workflow_by_id", new_callable=AsyncMock, return_value=mock_workflow),
        patch.object(WorkflowService, "list_resources", mock_list),
    ):
        await mock_service.list_workflow_versions_cursor(**call_kwargs)

    return captured


class TestListWorkflowVersionsCursor:
    """Tests for query-param merging and IDOR prevention."""

    @pytest.mark.asyncio
    async def test_merges_query_params_strips_workflow_id(self, mock_service: WorkflowService) -> None:
        """Attacker-supplied workflow_id in query_params is stripped to prevent IDOR."""
        workflow_id = uuid4()
        attacker_id = uuid4()

        captured = await _capture_callbacks(
            mock_service,
            workflow_id,
            query_params_items=[("workflow_id", str(attacker_id)), ("status", "draft")],
        )

        params = captured["query_params_items"]
        wf_ids = [v for k, v in params if k == "workflow_id"]
        assert wf_ids == [str(workflow_id)], "Only the path-level workflow_id should survive"
        assert ("status", "draft") in params, "Non-workflow_id params should pass through"

    @pytest.mark.asyncio
    async def test_empty_versions_callback_returns_early(self, mock_service: WorkflowService) -> None:
        """populate_version_context with an empty list should not query the DB."""
        workflow_id = uuid4()
        captured = await _capture_callbacks(mock_service, workflow_id)

        callback: Callable[..., Any] = captured["post_query_callback"]

        mock_exec = AsyncMock()
        with patch.object(mock_service.session, "exec", mock_exec):
            await callback([])

        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_populate_callback_queries_usernames(self, mock_service: WorkflowService) -> None:
        """populate_version_context queries User for usernames used by convert_version."""
        workflow_id = uuid4()
        user_id_1 = uuid4()
        user_id_2 = uuid4()

        captured = await _capture_callbacks(mock_service, workflow_id)
        callback: Callable[..., Any] = captured["post_query_callback"]

        v1 = MagicMock()
        v1.id = uuid4()
        v1.created_by = user_id_1

        v2 = MagicMock()
        v2.id = uuid4()
        v2.created_by = user_id_2

        user_rows = MagicMock()
        user_rows.__iter__ = MagicMock(return_value=iter([(user_id_1, "alice"), (user_id_2, "bob")]))

        event_rows = MagicMock()
        event_rows.__iter__ = MagicMock(return_value=iter([]))

        call_count = 0

        async def exec_side_effect(stmt: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return user_rows
            return event_rows

        with patch.object(mock_service.session, "exec", side_effect=exec_side_effect):
            await callback([v1, v2])

        # Now invoke convert_version; usernames should be mapped
        converter: Callable[..., Any] = captured["response_type_converter"]
        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.workflow_id = workflow_id
        mock_version.version = 1
        mock_version.schema_version = "2.0.0"
        mock_version.workflow_definition = {"nodes": []}
        mock_version.change_description = None
        mock_version.name = None
        mock_version.created_by = user_id_1
        mock_version.created_at = MagicMock()
        mock_version.updated_at = MagicMock()
        mock_version.deleted_at = None
        mock_version.deleted_by = None

        result = converter(mock_version)
        assert result.created_by_username == "alice"

    @pytest.mark.asyncio
    async def test_populate_callback_queries_publish_events(self, mock_service: WorkflowService) -> None:
        """populate_version_context queries events to build ever_published_ids and publish_ts."""
        workflow_id = uuid4()
        version_id = uuid4()
        pub_ts = datetime(2024, 6, 1, tzinfo=UTC)
        unpub_ts = datetime(2024, 6, 2, tzinfo=UTC)

        captured = await _capture_callbacks(mock_service, workflow_id)
        callback: Callable[..., Any] = captured["post_query_callback"]

        user_id = uuid4()
        v = MagicMock()
        v.id = version_id
        v.created_by = user_id

        user_rows = MagicMock()
        user_rows.__iter__ = MagicMock(return_value=iter([(user_id, "tester")]))

        event_rows = MagicMock()
        event_rows.__iter__ = MagicMock(
            return_value=iter(
                [
                    (version_id, PublishAction.PUBLISHED, pub_ts),
                    (version_id, PublishAction.UNPUBLISHED, unpub_ts),
                ]
            )
        )

        call_count = 0

        async def exec_side_effect(stmt: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return user_rows
            return event_rows

        with patch.object(mock_service.session, "exec", side_effect=exec_side_effect):
            await callback([v])

        # Verify via convert_version: the version should have status
        # "previously_published" (it has a publish event but
        # published_version_id is None so it is not currently published)
        converter: Callable[..., Any] = captured["response_type_converter"]
        mock_version = MagicMock()
        mock_version.id = version_id
        mock_version.workflow_id = workflow_id
        mock_version.version = 1
        mock_version.schema_version = "2.0.0"
        mock_version.workflow_definition = {}
        mock_version.change_description = None
        mock_version.name = None
        mock_version.created_by = uuid4()
        mock_version.created_at = MagicMock()
        mock_version.updated_at = MagicMock()
        mock_version.deleted_at = None
        mock_version.deleted_by = None

        result = converter(mock_version)
        assert result.status == "previously_published"
        assert result.last_published_at == pub_ts
        assert result.last_unpublished_at == unpub_ts

    @pytest.mark.asyncio
    async def test_convert_version_calls_deserialize(self, mock_service: WorkflowService) -> None:
        """convert_version delegates to deserialize_workflow_version."""
        from syntara.workflows.models import WorkflowVersionRead

        workflow_id = uuid4()
        pub_id = uuid4()

        captured = await _capture_callbacks(mock_service, workflow_id, published_version_id=pub_id)
        converter: Callable[..., Any] = captured["response_type_converter"]

        mock_version = MagicMock()
        mock_version.id = pub_id
        mock_version.workflow_id = workflow_id
        mock_version.version = 3
        mock_version.schema_version = "2.0.0"
        mock_version.workflow_definition = {"nodes": []}
        mock_version.change_description = "Initial"
        mock_version.name = "v3"
        mock_version.created_by = uuid4()
        mock_version.created_at = MagicMock()
        mock_version.updated_at = MagicMock()
        mock_version.deleted_at = None
        mock_version.deleted_by = None

        result = converter(mock_version)

        assert isinstance(result, WorkflowVersionRead)
        assert result.version == 3
        assert result.workflow_id == workflow_id
        # published_version_id matches version.id -> status is "published"
        assert result.status == "published"

    @pytest.mark.asyncio
    async def test_convert_version_sets_username(self, mock_service: WorkflowService) -> None:
        """convert_version sets created_by_username from the username_map."""
        workflow_id = uuid4()
        user_id = uuid4()

        captured = await _capture_callbacks(mock_service, workflow_id)
        callback: Callable[..., Any] = captured["post_query_callback"]

        v = MagicMock()
        v.id = uuid4()
        v.created_by = user_id

        user_rows = MagicMock()
        user_rows.__iter__ = MagicMock(return_value=iter([(user_id, "charlie")]))

        event_rows = MagicMock()
        event_rows.__iter__ = MagicMock(return_value=iter([]))

        call_count = 0

        async def exec_side_effect(stmt: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return user_rows
            return event_rows

        with patch.object(mock_service.session, "exec", side_effect=exec_side_effect):
            await callback([v])

        converter: Callable[..., Any] = captured["response_type_converter"]
        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.workflow_id = workflow_id
        mock_version.version = 1
        mock_version.schema_version = "2.0.0"
        mock_version.workflow_definition = {}
        mock_version.change_description = None
        mock_version.name = None
        mock_version.created_by = user_id
        mock_version.created_at = MagicMock()
        mock_version.updated_at = MagicMock()
        mock_version.deleted_at = None
        mock_version.deleted_by = None

        result = converter(mock_version)
        assert result.created_by_username == "charlie"

    @pytest.mark.asyncio
    async def test_convert_version_username_none_when_missing(self, mock_service: WorkflowService) -> None:
        """created_by_username is None when user ID not in username_map."""
        workflow_id = uuid4()
        unknown_user_id = uuid4()

        captured = await _capture_callbacks(mock_service, workflow_id)
        converter: Callable[..., Any] = captured["response_type_converter"]

        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.workflow_id = workflow_id
        mock_version.version = 1
        mock_version.schema_version = "2.0.0"
        mock_version.workflow_definition = {}
        mock_version.change_description = None
        mock_version.name = None
        mock_version.created_by = unknown_user_id
        mock_version.created_at = MagicMock()
        mock_version.updated_at = MagicMock()
        mock_version.deleted_at = None
        mock_version.deleted_by = None

        result = converter(mock_version)
        assert result.created_by_username is None


class TestPopulatePublishedVersionNumbers:
    """Tests for batch-populating published_version_number."""

    @pytest.mark.asyncio
    async def test_no_published_versions_returns_early_empty_list(self, mock_service: WorkflowService) -> None:
        """An empty workflow list should not query the DB."""
        mock_exec = AsyncMock()
        with patch.object(mock_service.session, "exec", mock_exec):
            await mock_service.populate_published_version_numbers([])
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_published_versions_returns_early_all_none(self, mock_service: WorkflowService) -> None:
        """Workflows with no published_version_id should not query the DB."""
        w1 = _make_workflow_read(published_version_id=None)
        w2 = _make_workflow_read(published_version_id=None)

        mock_exec = AsyncMock()
        with patch.object(mock_service.session, "exec", mock_exec):
            await mock_service.populate_published_version_numbers([w1, w2])

        mock_exec.assert_not_called()
        assert w1.published_version_number is None
        assert w2.published_version_number is None

    @pytest.mark.asyncio
    async def test_sets_version_numbers_from_query(self, mock_service: WorkflowService) -> None:
        """Normal case: version numbers are populated from DB results."""
        pub_id_a = uuid4()
        pub_id_b = uuid4()

        w1 = _make_workflow_read(name="w1", published_version_id=pub_id_a)
        w2 = _make_workflow_read(name="w2", published_version_id=pub_id_b)

        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([(pub_id_a, 3), (pub_id_b, 7)]))
        mock_exec = AsyncMock(return_value=mock_result)

        with patch.object(mock_service.session, "exec", mock_exec):
            await mock_service.populate_published_version_numbers([w1, w2])

        assert w1.published_version_number == 3
        assert w2.published_version_number == 7

    @pytest.mark.asyncio
    async def test_handles_missing_version_ids(self, mock_service: WorkflowService) -> None:
        """published_version_number remains None when version ID not in query results."""
        pub_id = uuid4()
        w = _make_workflow_read(published_version_id=pub_id)

        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([]))
        mock_exec = AsyncMock(return_value=mock_result)

        with patch.object(mock_service.session, "exec", mock_exec):
            await mock_service.populate_published_version_numbers([w])

        assert w.published_version_number is None

    @pytest.mark.asyncio
    async def test_mixed_published_and_unpublished(self, mock_service: WorkflowService) -> None:
        """Only workflows with published_version_id get numbers set."""
        pub_id = uuid4()
        w_pub = _make_workflow_read(name="published", published_version_id=pub_id)
        w_unpub = _make_workflow_read(name="unpublished", published_version_id=None)

        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([(pub_id, 5)]))
        mock_exec = AsyncMock(return_value=mock_result)

        with patch.object(mock_service.session, "exec", mock_exec):
            await mock_service.populate_published_version_numbers([w_pub, w_unpub])

        assert w_pub.published_version_number == 5
        assert w_unpub.published_version_number is None
