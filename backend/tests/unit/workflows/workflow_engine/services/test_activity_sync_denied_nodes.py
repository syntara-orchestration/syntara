"""Unit tests for persisting denied nodes from the sync service (ANSTRAT-1750).

A denied node never starts a Temporal activity, so its ActivityExecution row is
only ever moved to the terminal DENIED status by this path.
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.workflow_engine.services.activity_sync_service import ActivitySyncService
from tests.unit.workflows.workflow_engine.services.test_activity_sync_service import create_test_metadata

DENIED_QUERY_RESULT = {"denied_node": {"kind": "script", "denied_by": "no-scripts"}}


class TestSyncDeniedNodes:
    """_sync_denied_nodes writes DENIED and never raises."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.execution_id = uuid4()
        self.mock_session_factory = Mock()
        self.service = ActivitySyncService(Mock(), self.mock_session_factory, AsyncMock())

    def _activity(self, name: str) -> Mock:
        activity = Mock()
        activity.activity_name = name
        activity.status = ActivityStatus.PENDING
        activity.started_at = None
        activity.completed_at = None
        activity.error_details = None
        activity.updated_at = None
        activity.output_data = None
        activity.iteration = None
        return activity

    def _mock_session(self, activities: list[Mock]) -> Mock:
        result = Mock()
        result.all.return_value = activities
        session = Mock()
        session.exec = AsyncMock(return_value=result)
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        self.mock_session_factory.return_value = session
        return session

    @pytest.mark.asyncio
    async def test_denied_node_marked_denied_with_error_details(self) -> None:
        activity = self._activity("denied_node")
        self._mock_session([activity])
        metadata = create_test_metadata(execution_id=self.execution_id, activity_index_map={"denied_node": 1})
        handle = AsyncMock()
        handle.query = AsyncMock(return_value=DENIED_QUERY_RESULT)

        with patch.object(self.service, "_publish_activity_patches", new_callable=AsyncMock):
            await self.service._sync_denied_nodes(metadata, handle)

        handle.query.assert_awaited_once_with("get_denied_nodes")
        assert activity.status == ActivityStatus.DENIED
        assert activity.completed_at is not None
        assert "node_execute_denied" in activity.error_details
        assert "no-scripts" in activity.error_details

    @pytest.mark.asyncio
    async def test_activity_is_never_marked_started(self) -> None:
        activity = self._activity("denied_node")
        self._mock_session([activity])
        metadata = create_test_metadata(execution_id=self.execution_id, activity_index_map={"denied_node": 1})
        handle = AsyncMock()
        handle.query = AsyncMock(return_value=DENIED_QUERY_RESULT)

        with patch.object(self.service, "_publish_activity_patches", new_callable=AsyncMock):
            await self.service._sync_denied_nodes(metadata, handle)

        assert activity.started_at is None

    @pytest.mark.asyncio
    async def test_no_denied_nodes_is_a_noop(self) -> None:
        metadata = create_test_metadata(execution_id=self.execution_id)
        handle = AsyncMock()
        handle.query = AsyncMock(return_value={})

        await self.service._sync_denied_nodes(metadata, handle)

        self.mock_session_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_failure_does_not_propagate(self) -> None:
        metadata = create_test_metadata(execution_id=self.execution_id)
        handle = AsyncMock()
        handle.query = AsyncMock(side_effect=RuntimeError("workflow not reachable"))

        await self.service._sync_denied_nodes(metadata, handle)

        self.mock_session_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_already_terminal_activity_is_left_alone(self) -> None:
        activity = self._activity("denied_node")
        activity.status = ActivityStatus.COMPLETED
        self._mock_session([activity])
        metadata = create_test_metadata(execution_id=self.execution_id, activity_index_map={"denied_node": 1})
        handle = AsyncMock()
        handle.query = AsyncMock(return_value=DENIED_QUERY_RESULT)

        await self.service._sync_denied_nodes(metadata, handle)

        assert activity.status == ActivityStatus.COMPLETED


class TestDenialOnlyErrorDetails:
    """A completed_with_errors run caused only by denials still reports a reason."""

    def test_denied_activities_used_when_nothing_failed(self) -> None:
        detail = ActivitySyncService._extract_failed_activity_errors(
            {"failed_activities": {}, "denied_activities": {"denied_node": "node_execute_denied: ..."}}
        )
        assert detail == "denied_node: node_execute_denied: ..."

    def test_failed_activities_take_precedence(self) -> None:
        detail = ActivitySyncService._extract_failed_activity_errors(
            {"failed_activities": {"boom": "kaboom"}, "denied_activities": {"denied_node": "denied"}}
        )
        assert detail == "boom: kaboom"

    def test_generic_fallback_when_neither_is_present(self) -> None:
        assert ActivitySyncService._extract_failed_activity_errors({}) == "One or more workflow activities failed"
