"""Unit tests for ActivitySyncService."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest
from temporalio.api.enums.v1 import EventType

from syntara.core.exceptions import SafeValueError
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.workflow_engine.activities.internal import register_activity_monitoring
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, NodeType
from syntara.workflows.workflow_engine.services.activity_sync_service import (
    _PENDING_ACTIVITY_STATE_STARTED as STARTED_STATE,
)
from syntara.workflows.workflow_engine.services.activity_sync_service import (
    ActivitySyncService,
    ExecutionMonitorMetadata,
    SyntheticActivityStarted,
    SyntheticPartialOutput,
)
from syntara.workflows.workflow_engine.utils.timeout_messages import (
    build_timeout_error_message,
    format_timeout_friendly,
)


def create_test_metadata(
    execution_id: UUID | None = None,
    last_processed_event_id: int = 0,
    activity_definitions_map: dict[str, dict[str, Any]] | None = None,
    activity_index_map: dict[str, int] | None = None,
    pending_activity_updates: dict[int, dict[str, Any]] | None = None,
    pending_sync_event_ids: set[int] | None = None,
    iteration_counters: dict[str, int] | None = None,
    next_activity_index: int | None = None,
) -> ExecutionMonitorMetadata:
    """Create ExecutionMonitorMetadata for testing with sensible defaults."""
    updates = pending_activity_updates or {}
    index_map = activity_index_map or {}
    return ExecutionMonitorMetadata(
        execution_id=execution_id or uuid4(),
        last_processed_event_id=last_processed_event_id,
        activity_definitions_map=activity_definitions_map or {},
        activity_index_map=index_map,
        next_activity_index=next_activity_index if next_activity_index is not None else len(index_map),
        pending_activity_updates=updates,
        pending_sync_event_ids=pending_sync_event_ids if pending_sync_event_ids is not None else set(updates.keys()),
        iteration_counters=iteration_counters or {},
    )


class TestActivitySyncService:
    """Test ActivitySyncService class."""

    def test_init(self, mock_session_factory) -> None:
        """Test service initialization."""
        mock_client = Mock()

        service = ActivitySyncService(
            temporal_client=mock_client,
            session_factory=mock_session_factory,
        )

        assert service.temporal_client is mock_client
        assert service.session_factory is mock_session_factory
        assert service._sync_tasks == {}
        assert service._shutdown is False

    def test_is_monitoring_execution_returns_false_when_not_monitoring(self, mock_session_factory) -> None:
        """Test is_monitoring_execution returns False when execution not monitored."""
        mock_client = Mock()
        service = ActivitySyncService(mock_client, mock_session_factory)

        execution_id = uuid4()

        assert service.is_monitoring_execution(execution_id) is False

    def test_is_monitoring_execution_returns_true_when_monitoring(self, mock_session_factory) -> None:
        """Test is_monitoring_execution returns True when execution is monitored."""
        mock_client = Mock()
        service = ActivitySyncService(mock_client, mock_session_factory)

        execution_id = uuid4()
        mock_task = Mock(spec=asyncio.Task)
        service._sync_tasks[str(execution_id)] = mock_task

        assert service.is_monitoring_execution(execution_id) is True

    @pytest.mark.asyncio
    async def test_start_monitoring_execution_stores_task(self, mock_session_factory) -> None:
        """Test start_monitoring_execution stores monitoring task."""
        mock_client = Mock()
        service = ActivitySyncService(mock_client, mock_session_factory)

        execution_id = uuid4()
        temporal_workflow_id = "workflow-123"
        task_key = str(execution_id)

        async def long_running_monitor(exec_id, workflow_id, request_id) -> None:
            await asyncio.sleep(10)

        with patch.object(service, "_monitor_execution", side_effect=long_running_monitor):
            service.start_monitoring_execution(execution_id, temporal_workflow_id)

            await asyncio.sleep(0.01)

            assert task_key in service._sync_tasks
            assert isinstance(service._sync_tasks[task_key], asyncio.Task)
            assert not service._sync_tasks[task_key].done()

            # Cancel and clean up the task
            task = service._sync_tasks[task_key]
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    @pytest.mark.asyncio
    async def test_start_monitoring_execution_skips_if_already_monitoring(self, mock_session_factory) -> None:
        """Test start_monitoring_execution skips if already monitoring."""
        mock_client = Mock()
        service = ActivitySyncService(mock_client, mock_session_factory)

        execution_id = uuid4()
        temporal_workflow_id = "workflow-123"

        mock_task = Mock(spec=asyncio.Task)
        service._sync_tasks[str(execution_id)] = mock_task

        with patch.object(service, "_monitor_execution", new_callable=AsyncMock) as mock_monitor:
            service.start_monitoring_execution(execution_id, temporal_workflow_id)

            mock_monitor.assert_not_called()

    @pytest.mark.asyncio
    async def test_shutdown_cancels_all_tasks(self, mock_session_factory) -> None:
        """Test shutdown cancels all monitoring tasks."""
        mock_client = Mock()
        service = ActivitySyncService(mock_client, mock_session_factory)

        task1 = asyncio.create_task(asyncio.sleep(100))
        task2 = asyncio.create_task(asyncio.sleep(100))

        service._sync_tasks["exec1"] = task1
        service._sync_tasks["exec2"] = task2

        await service.shutdown()

        assert service._shutdown is True
        assert task1.cancelled()
        assert task2.cancelled()
        assert service._sync_tasks == {}


class TestPublishHelpersTreatRedisFailureAsNonFatal:
    """_publish_snapshot/_publish_execution_patch must swallow publisher failures.

    ActivityUpdatePublisher raises on Redis failure (it does not degrade
    internally) specifically so this outer layer is the single place that
    decides publishing is best-effort. These tests pin that contract: a
    RedisConnectionError from the publisher must not propagate, and the
    success-path "Published ..." log must not fire when nothing was
    actually published.
    """

    def _make_service(self, mock_session_factory) -> tuple[ActivitySyncService, AsyncMock]:
        mock_publisher = AsyncMock()
        service = ActivitySyncService(Mock(), mock_session_factory, mock_publisher)
        return service, mock_publisher

    @pytest.mark.asyncio
    async def test_publish_snapshot_swallows_redis_failure(self, mock_session_factory) -> None:
        from redis.exceptions import ConnectionError as RedisConnectionError

        service, mock_publisher = self._make_service(mock_session_factory)
        mock_publisher.publish_snapshot.side_effect = RedisConnectionError("pool exhausted")
        execution = Execution(
            id=uuid4(),
            workflow_id=uuid4(),
            workflow_version_id=uuid4(),
            temporal_workflow_id="temporal-exec",
            status=ExecutionStatus.RUNNING,
            created_by=uuid4(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            updated_by=uuid4(),
            input_data={},
            labels={},
            project_id=uuid4(),
        )
        execution.activities = []

        with patch("syntara.workflows.workflow_engine.services.activity_sync_service.logger") as mock_logger:
            await service._publish_snapshot(execution, "initial_snapshot")  # does not raise

        mock_logger.exception.assert_called_once()
        assert mock_logger.exception.call_args.args[0] == "Failed to publish snapshot (non-fatal)"
        assert not any(
            call.args and call.args[0] == "Published snapshot for execution"
            for call in mock_logger.debug.call_args_list
        )

    @pytest.mark.asyncio
    async def test_publish_execution_patch_swallows_redis_failure(self, mock_session_factory) -> None:
        from redis.exceptions import ConnectionError as RedisConnectionError

        service, mock_publisher = self._make_service(mock_session_factory)
        mock_publisher.publish_execution_patch.side_effect = RedisConnectionError("pool exhausted")

        with patch("syntara.workflows.workflow_engine.services.activity_sync_service.logger") as mock_logger:
            await service._publish_execution_patch(uuid4(), [])  # does not raise

        mock_logger.exception.assert_called_once()
        assert mock_logger.exception.call_args.args[0] == "Failed to publish execution patch (non-fatal)"


class TestRegisterActivityMonitoring:
    """Test register_activity_monitoring activity function."""

    @pytest.mark.asyncio
    async def test_register_monitoring_success_on_first_attempt(self) -> None:
        """Test successful registration on first attempt."""
        execution_id = str(uuid4())
        temporal_workflow_id = "workflow-123"

        mock_sync_service = Mock()
        mock_sync_service.is_monitoring_execution.return_value = False
        mock_sync_service.start_monitoring_execution = Mock()

        mock_execution = Mock(spec=Execution)
        mock_execution.id = UUID(execution_id)

        mock_result = Mock()
        mock_result.one_or_none.return_value = mock_execution

        mock_session = Mock()
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.internal.activity_monitoring.get_activity_sync_service",
                return_value=mock_sync_service,
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.internal.activity_monitoring.AsyncSessionLocal",
                return_value=mock_session,
            ),
        ):
            await register_activity_monitoring(execution_id, temporal_workflow_id)

            mock_sync_service.start_monitoring_execution.assert_called_once_with(
                UUID(execution_id), temporal_workflow_id, request_id=None
            )

    @pytest.mark.asyncio
    async def test_register_monitoring_skips_if_already_monitoring(self) -> None:
        """Test registration skips if already monitoring."""
        execution_id = str(uuid4())
        temporal_workflow_id = "workflow-123"

        mock_sync_service = Mock()
        mock_sync_service.is_monitoring_execution.return_value = True
        mock_sync_service.start_monitoring_execution = Mock()

        with patch(
            "syntara.workflows.workflow_engine.activities.internal.activity_monitoring.get_activity_sync_service",
            return_value=mock_sync_service,
        ):
            await register_activity_monitoring(execution_id, temporal_workflow_id)

            mock_sync_service.start_monitoring_execution.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_monitoring_retries_when_execution_not_found(self) -> None:
        """Test registration retries with exponential backoff when execution not found."""
        execution_id = str(uuid4())
        temporal_workflow_id = "workflow-123"

        mock_sync_service = Mock()
        mock_sync_service.is_monitoring_execution.return_value = False
        mock_sync_service.start_monitoring_execution = Mock()

        mock_execution = Mock(spec=Execution)
        mock_execution.id = UUID(execution_id)

        mock_result_not_found = Mock()
        mock_result_not_found.one_or_none.return_value = None

        mock_result_found = Mock()
        mock_result_found.one_or_none.return_value = mock_execution

        mock_session = Mock()
        mock_session.exec = AsyncMock(side_effect=[mock_result_not_found, mock_result_found])
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.internal.activity_monitoring.get_activity_sync_service",
                return_value=mock_sync_service,
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.internal.activity_monitoring.AsyncSessionLocal",
                return_value=mock_session,
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.internal.activity_monitoring.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await register_activity_monitoring(execution_id, temporal_workflow_id)

            assert mock_session.exec.await_count == 2
            mock_sync_service.start_monitoring_execution.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_monitoring_raises_after_max_retries(self) -> None:
        """Test registration raises RuntimeError after max retries exhausted."""
        execution_id = str(uuid4())
        temporal_workflow_id = "workflow-123"

        mock_sync_service = Mock()
        mock_sync_service.is_monitoring_execution.return_value = False

        mock_result = Mock()
        mock_result.one_or_none.return_value = None

        mock_session = Mock()
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.internal.activity_monitoring.get_activity_sync_service",
                return_value=mock_sync_service,
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.internal.activity_monitoring.AsyncSessionLocal",
                return_value=mock_session,
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.internal.activity_monitoring.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            with pytest.raises(RuntimeError, match="not found in database after 5 retries"):
                await register_activity_monitoring(execution_id, temporal_workflow_id)

            assert mock_session.exec.await_count == 5

    @pytest.mark.asyncio
    async def test_register_monitoring_raises_when_sync_service_not_available(self) -> None:
        """Test registration raises RuntimeError when sync service not available."""
        execution_id = str(uuid4())
        temporal_workflow_id = "workflow-123"

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.internal.activity_monitoring.get_activity_sync_service",
                return_value=None,
            ),
            pytest.raises(RuntimeError, match="Activity sync service not available"),
        ):
            await register_activity_monitoring(execution_id, temporal_workflow_id)


class TestActivityEventProcessing:
    """Test activity event processing methods."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = ActivitySyncService(Mock(), Mock())
        self.metadata = create_test_metadata()

    def _create_mock_event(
        self,
        event_type: int,
        event_id: int,
        scheduled_event_id: int | None = None,
        activity_id: str = "test-activity",
        attempt: int = 1,
        failure_message: str | None = None,
    ) -> Mock:
        """Create a mock Temporal history event."""
        event = Mock()
        event.event_type = event_type
        event.event_id = event_id
        event.event_time = datetime.now(UTC)

        if event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
            attrs = Mock()
            attrs.activity_id = activity_id
            attrs.start_to_close_timeout = None
            event.activity_task_scheduled_event_attributes = attrs

        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED:
            attrs = Mock()
            attrs.scheduled_event_id = scheduled_event_id
            attrs.attempt = attempt
            attrs.last_failure = None
            event.activity_task_started_event_attributes = attrs

        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED:
            attrs = Mock()
            attrs.scheduled_event_id = scheduled_event_id
            event.activity_task_completed_event_attributes = attrs

        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_FAILED:
            attrs = Mock()
            attrs.scheduled_event_id = scheduled_event_id
            attrs.failure = Mock(message=failure_message) if failure_message else None
            event.activity_task_failed_event_attributes = attrs

        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_TIMED_OUT:
            attrs = Mock()
            attrs.scheduled_event_id = scheduled_event_id
            attrs.failure = Mock(message=failure_message) if failure_message else None
            event.activity_task_timed_out_event_attributes = attrs

        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_CANCELED:
            attrs = Mock()
            attrs.scheduled_event_id = scheduled_event_id
            event.activity_task_canceled_event_attributes = attrs

        return event

    def test_process_activity_scheduled(self) -> None:
        """Test processing ACTIVITY_TASK_SCHEDULED event sets status to PENDING."""
        event = self._create_mock_event(
            EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED,
            event_id=1,
            activity_id="my-activity",
        )

        self.service._process_activity_scheduled(event, self.metadata)

        assert 1 in self.metadata.pending_activity_updates
        assert self.metadata.pending_activity_updates[1]["activity_id"] == "my-activity"
        assert self.metadata.pending_activity_updates[1]["status"] == ActivityStatus.PENDING
        assert self.metadata.pending_activity_updates[1]["started_at"] is None
        assert self.metadata.pending_activity_updates[1]["completed_at"] is None
        assert self.metadata.pending_activity_updates[1]["error_details"] is None
        assert self.metadata.pending_activity_updates[1]["retry_count"] == 0

    def test_process_activity_scheduled_skips_internal_activities(self) -> None:
        """Test processing ACTIVITY_TASK_SCHEDULED skips internal activities."""
        event = self._create_mock_event(
            EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED,
            event_id=1,
            activity_id="__internal__register_monitoring",
        )

        self.service._process_activity_scheduled(event, self.metadata)

        assert 1 not in self.metadata.pending_activity_updates

    def test_process_activity_scheduled_sets_loop_flags_for_iter_suffix(self) -> None:
        """An activity with _iter_N suffix is recognized as a loop iteration control node."""
        event = self._create_mock_event(
            EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED,
            event_id=2,
            activity_id="loop-node_iter_0",
        )

        self.service._process_activity_scheduled(event, self.metadata)

        update = self.metadata.pending_activity_updates[2]
        assert update["activity_id"] == "loop-node"
        assert update["_is_loop_iteration"] is True
        assert update["_is_loop_control"] is True
        assert update["iteration"] == 0

    def test_process_activity_scheduled_extracts_iteration_number(self) -> None:
        """The iteration number is extracted from the _iter_N suffix."""
        event = self._create_mock_event(
            EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED,
            event_id=5,
            activity_id="loop-node_iter_3",
        )

        self.service._process_activity_scheduled(event, self.metadata)

        update = self.metadata.pending_activity_updates[5]
        assert update["iteration"] == 3

    def test_process_activity_scheduled_no_loop_flags_for_plain_activity(self) -> None:
        """A plain activity without iter suffix and not in terminal_activity_ids gets no loop flags."""
        event = self._create_mock_event(
            EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED,
            event_id=3,
            activity_id="action-1",
        )

        self.service._process_activity_scheduled(event, self.metadata)

        update = self.metadata.pending_activity_updates[3]
        assert update["activity_id"] == "action-1"
        assert update["_is_loop_iteration"] is False
        assert update["_is_loop_control"] is False
        assert update["iteration"] is None

    def test_process_activity_scheduled_loop_iteration_for_re_executed_body_node(self) -> None:
        """A body node re-scheduled after terminal is a loop iteration but not a control node."""
        self.metadata.terminal_activity_ids.add("body-node")

        event = self._create_mock_event(
            EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED,
            event_id=4,
            activity_id="body-node",
        )

        self.service._process_activity_scheduled(event, self.metadata)

        update = self.metadata.pending_activity_updates[4]
        assert update["activity_id"] == "body-node"
        assert update["_is_loop_iteration"] is True
        assert update["_is_loop_control"] is False

    @pytest.mark.parametrize(
        ("attempt", "expected_retry_count", "expected_status"),
        [
            (1, 0, ActivityStatus.RUNNING),
            (2, 1, ActivityStatus.RETRYING),
            (3, 2, ActivityStatus.RETRYING),
        ],
    )
    def test_process_activity_started(
        self, attempt: int, expected_retry_count: int, expected_status: ActivityStatus
    ) -> None:
        """Test processing ACTIVITY_TASK_STARTED event sets status to RUNNING or RETRYING based on attempt."""
        self.metadata.pending_activity_updates[1] = {
            "activity_id": "test-activity",
            "status": ActivityStatus.PENDING,
            "started_at": None,
            "retry_count": 0,
        }

        event = self._create_mock_event(
            EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED,
            event_id=2,
            scheduled_event_id=1,
            attempt=attempt,
        )

        self.service._process_activity_started(event, self.metadata)

        assert self.metadata.pending_activity_updates[1]["status"] == expected_status
        assert self.metadata.pending_activity_updates[1]["started_at"] is not None
        assert self.metadata.pending_activity_updates[1]["retry_count"] == expected_retry_count

    @pytest.mark.parametrize(
        ("failure_message", "expected_error"),
        [
            ("Connection timeout", "Connection timeout"),
            (None, None),
        ],
    )
    def test_process_activity_failed(self, failure_message: str | None, expected_error: str | None) -> None:
        """Test processing ACTIVITY_TASK_FAILED event sets status to FAILED."""
        self.metadata.pending_activity_updates[1] = {
            "activity_id": "test-activity",
            "status": ActivityStatus.RUNNING,
            "completed_at": None,
            "error_details": None,
        }

        event = self._create_mock_event(
            EventType.EVENT_TYPE_ACTIVITY_TASK_FAILED,
            event_id=3,
            scheduled_event_id=1,
            failure_message=failure_message,
        )

        self.service._process_activity_failed(event, self.metadata)

        assert self.metadata.pending_activity_updates[1]["status"] == ActivityStatus.FAILED
        assert self.metadata.pending_activity_updates[1]["completed_at"] is not None
        assert self.metadata.pending_activity_updates[1]["error_details"] == expected_error

    @pytest.mark.parametrize(
        ("event_type", "expected_status", "expected_error", "failure_message"),
        [
            (EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED, ActivityStatus.COMPLETED, None, None),
            (
                EventType.EVENT_TYPE_ACTIVITY_TASK_TIMED_OUT,
                ActivityStatus.FAILED,
                'The step "test-activity" did not finish within',
                "Activity timeout",
            ),
            (EventType.EVENT_TYPE_ACTIVITY_TASK_CANCELED, ActivityStatus.CANCELLED, "Activity was canceled", None),
        ],
    )
    def test_process_activity_terminal_events(
        self,
        event_type: int,
        expected_status: ActivityStatus,
        expected_error: str | None,
        failure_message: str | None,
    ) -> None:
        """Test processing terminal activity events (completed, timed_out, canceled)."""
        self.metadata.pending_activity_updates[1] = {
            "activity_id": "test-activity",
            "status": ActivityStatus.RUNNING,
            "completed_at": None,
            "error_details": None,
        }

        event = self._create_mock_event(
            event_type,
            event_id=3,
            scheduled_event_id=1,
            failure_message=failure_message,
        )

        # Call the appropriate processor based on event type
        if event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED:
            self.service._process_activity_completed(event, self.metadata)
        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_TIMED_OUT:
            self.service._process_activity_timed_out(event, self.metadata)
        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_CANCELED:
            self.service._process_activity_canceled(event, self.metadata)

        assert self.metadata.pending_activity_updates[1]["status"] == expected_status
        assert self.metadata.pending_activity_updates[1]["completed_at"] is not None
        if expected_error:
            assert expected_error in self.metadata.pending_activity_updates[1]["error_details"]

    def test_process_activity_completed_sets_completed_for_approval_nodes(self) -> None:
        """Test that approval activities get COMPLETED status on ACTIVITY_TASK_COMPLETED."""
        self.metadata.activity_definitions_map = {
            "approval-node": {"id": "approval-node", "type": "approval", "parameters": {}},
        }
        self.metadata.pending_activity_updates[1] = {
            "activity_id": "approval-node",
            "status": ActivityStatus.RUNNING,
            "completed_at": None,
            "error_details": None,
        }

        event = self._create_mock_event(
            EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED,
            event_id=3,
            scheduled_event_id=1,
        )

        self.service._process_activity_completed(event, self.metadata)

        assert self.metadata.pending_activity_updates[1]["status"] == ActivityStatus.COMPLETED
        assert self.metadata.pending_activity_updates[1]["completed_at"] is not None

    def test_process_activity_completed_sets_completed_for_non_approval_nodes(self) -> None:
        """Test that non-approval activities still get COMPLETED status."""
        self.metadata.activity_definitions_map = {
            "script-node": {"id": "script-node", "type": "script", "parameters": {}},
        }
        self.metadata.pending_activity_updates[1] = {
            "activity_id": "script-node",
            "status": ActivityStatus.RUNNING,
            "completed_at": None,
            "error_details": None,
        }

        event = self._create_mock_event(
            EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED,
            event_id=3,
            scheduled_event_id=1,
        )

        self.service._process_activity_completed(event, self.metadata)

        assert self.metadata.pending_activity_updates[1]["status"] == ActivityStatus.COMPLETED
        assert self.metadata.pending_activity_updates[1]["completed_at"] is not None

    def test_process_activity_event_delegates_to_correct_handler(self) -> None:
        """Test _process_activity_event delegates to the correct handler method."""
        test_cases = [
            (EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED, "_process_activity_scheduled"),
            (EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED, "_process_activity_started"),
            (EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED, "_process_activity_completed"),
            (EventType.EVENT_TYPE_ACTIVITY_TASK_FAILED, "_process_activity_failed"),
            (EventType.EVENT_TYPE_ACTIVITY_TASK_TIMED_OUT, "_process_activity_timed_out"),
            (EventType.EVENT_TYPE_ACTIVITY_TASK_CANCELED, "_process_activity_canceled"),
        ]

        for event_type, handler_name in test_cases:
            metadata = create_test_metadata()
            event = self._create_mock_event(event_type, event_id=1, scheduled_event_id=1)

            with patch.object(self.service, handler_name) as mock_handler:
                self.service._process_activity_event(event, metadata)
                mock_handler.assert_called_once_with(event, metadata)


# ---------------------------------------------------------------------------
# AAP-87135: User-facing timeout messages must not expose Temporal jargon
# ---------------------------------------------------------------------------


class TestUserFacingTimeoutMessages:
    """Regression tests for AAP-87135: no Temporal jargon in timeout messages."""

    def test_format_timeout_friendly_seconds(self) -> None:
        assert format_timeout_friendly(30) == "30 seconds"
        assert format_timeout_friendly(1) == "1 second"

    def test_format_timeout_friendly_minutes(self) -> None:
        assert format_timeout_friendly(120) == "2 minutes"
        assert format_timeout_friendly(60) == "1 minute"

    def test_format_timeout_friendly_minutes_and_seconds(self) -> None:
        assert format_timeout_friendly(90) == "1 minute 30 seconds"
        assert format_timeout_friendly(121) == "2 minutes 1 second"

    def test_format_timeout_friendly_none(self) -> None:
        assert format_timeout_friendly(None) == "the configured timeout"
        assert format_timeout_friendly(0) == "the configured timeout"

    def test_timeout_message_includes_step_name(self) -> None:
        msg = build_timeout_error_message(
            step_name="Fetch Users",
            is_agentic=False,
            timeout_seconds=300,
        )
        assert '"Fetch Users"' in msg
        assert "5 minutes" in msg

    def test_timeout_message_falls_back_to_activity_id(self) -> None:
        msg = build_timeout_error_message(step_name="fetch_data", is_agentic=False, timeout_seconds=60)
        assert '"fetch_data"' in msg

    def test_timeout_message_no_temporal_jargon(self) -> None:
        msg = build_timeout_error_message(step_name="my_step", is_agentic=False, timeout_seconds=300)
        assert "Temporal" not in msg
        assert "StartToClose" not in msg
        assert "start_to_close" not in msg

    def test_agentic_node_gets_ai_agent_label(self) -> None:
        msg = build_timeout_error_message(
            step_name="Analyze Code",
            is_agentic=True,
            timeout_seconds=600,
        )
        assert 'The AI Agent step "Analyze Code"' in msg
        assert "simplify the prompt" in msg
        assert "agent may still be running" in msg

    def test_non_agentic_node_gets_generic_label(self) -> None:
        msg = build_timeout_error_message(
            step_name="Fetch Data",
            is_agentic=False,
            timeout_seconds=300,
        )
        assert 'The step "Fetch Data"' in msg
        assert "AI Agent" not in msg

    def test_timeout_message_includes_guidance(self) -> None:
        msg = build_timeout_error_message(step_name="step1", is_agentic=False, timeout_seconds=120)
        assert "Timeout setting" in msg
        assert "Increase the timeout" in msg


class TestHandleEventPostProcessing:
    """Test _handle_event_post_processing sync trigger logic."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = ActivitySyncService(Mock(), Mock())
        self.execution_id = uuid4()
        self.metadata = create_test_metadata(
            execution_id=self.execution_id,
            activity_index_map={"test-activity": 0},
            pending_activity_updates={
                1: {
                    "activity_id": "test-activity",
                    "status": ActivityStatus.RUNNING,
                }
            },
        )
        self.mock_handle = Mock()

    def _create_mock_event(
        self,
        event_type: int,
        event_id: int,
        scheduled_event_id: int | None = None,
    ) -> Mock:
        """Create a mock Temporal history event."""
        event = Mock()
        event.event_type = event_type
        event.event_id = event_id
        event.event_time = datetime.now(UTC)

        if event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
            attrs = Mock()
            attrs.activity_id = "test-activity"
            attrs.start_to_close_timeout = None
            event.activity_task_scheduled_event_attributes = attrs

        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED:
            attrs = Mock()
            attrs.scheduled_event_id = scheduled_event_id or 1
            attrs.attempt = 1
            attrs.last_failure = None
            event.activity_task_started_event_attributes = attrs

        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED:
            attrs = Mock()
            attrs.scheduled_event_id = scheduled_event_id or 1
            event.activity_task_completed_event_attributes = attrs

        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_FAILED:
            attrs = Mock()
            attrs.scheduled_event_id = scheduled_event_id or 1
            attrs.failure = None
            event.activity_task_failed_event_attributes = attrs

        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_TIMED_OUT:
            attrs = Mock()
            attrs.scheduled_event_id = scheduled_event_id or 1
            attrs.failure = None
            event.activity_task_timed_out_event_attributes = attrs

        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_CANCELED:
            attrs = Mock()
            attrs.scheduled_event_id = scheduled_event_id or 1
            event.activity_task_canceled_event_attributes = attrs

        return event

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "event_type",
        [
            EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED,
            EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED,
            EventType.EVENT_TYPE_ACTIVITY_TASK_FAILED,
            EventType.EVENT_TYPE_ACTIVITY_TASK_TIMED_OUT,
            EventType.EVENT_TYPE_ACTIVITY_TASK_CANCELED,
        ],
    )
    async def test_sync_triggered_for_started_and_terminal_events(self, event_type: int) -> None:
        """Test that STARTED and terminal events trigger database sync."""
        event = self._create_mock_event(event_type, event_id=5)

        with patch.object(self.service, "_sync_activities_to_db", new_callable=AsyncMock) as mock_sync:
            result = await self.service._handle_event_post_processing(
                event,
                self.metadata,
                self.mock_handle,
            )

            mock_sync.assert_called_once_with(
                self.metadata,
                self.mock_handle,
            )
            # Verify metadata was updated with event ID
            assert self.metadata.last_processed_event_id == event.event_id
            assert result == event.event_id

    @pytest.mark.asyncio
    async def test_sync_not_triggered_for_scheduled_event(self) -> None:
        """Test that SCHEDULED events do NOT trigger database sync."""
        event = self._create_mock_event(EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED, event_id=5)

        with patch.object(self.service, "_sync_activities_to_db", new_callable=AsyncMock) as mock_sync:
            result = await self.service._handle_event_post_processing(
                event,
                self.metadata,
                self.mock_handle,
            )

            mock_sync.assert_not_called()
            assert result is None

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_no_modulo_based_sync(self) -> None:
        """Test that events at multiples of 10 do NOT automatically trigger sync (modulo check removed)."""
        # Create a non-sync event (SCHEDULED) at event_id 10 (multiple of 10)
        event = self._create_mock_event(EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED, event_id=10)

        with patch.object(self.service, "_sync_activities_to_db", new_callable=AsyncMock) as mock_sync:
            result = await self.service._handle_event_post_processing(
                event,
                self.metadata,
                self.mock_handle,
            )

            # Should NOT sync just because event_id is 10
            mock_sync.assert_not_called()
            assert result is None

    @pytest.mark.asyncio
    async def test_sync_triggered_for_scheduled_loop_iteration(self) -> None:
        """SCHEDULED events flagged as loop iterations should trigger sync."""
        event = self._create_mock_event(EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED, event_id=7)

        self.metadata.pending_activity_updates[7] = {
            "activity_id": "script-1",
            "status": ActivityStatus.PENDING,
            "_is_loop_iteration": True,
        }

        with patch.object(self.service, "_sync_activities_to_db", new_callable=AsyncMock) as mock_sync:
            result = await self.service._handle_event_post_processing(
                event,
                self.metadata,
                self.mock_handle,
            )

            mock_sync.assert_called_once_with(self.metadata, self.mock_handle)
            assert self.metadata.last_processed_event_id == 7
            assert result == 7

    @pytest.mark.asyncio
    async def test_sync_not_triggered_for_scheduled_non_loop_iteration(self) -> None:
        """SCHEDULED events without _is_loop_iteration flag should not trigger sync."""
        event = self._create_mock_event(EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED, event_id=7)

        self.metadata.pending_activity_updates[7] = {
            "activity_id": "script-1",
            "status": ActivityStatus.PENDING,
        }

        with patch.object(self.service, "_sync_activities_to_db", new_callable=AsyncMock) as mock_sync:
            result = await self.service._handle_event_post_processing(
                event,
                self.metadata,
                self.mock_handle,
            )

            mock_sync.assert_not_called()
            assert result is None


class TestControlNodeSyncTrigger:
    """Test that control node completions trigger _sync_skipped_nodes."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = ActivitySyncService(Mock(), Mock())
        self.mock_handle = Mock()

    def _create_completed_event(self, scheduled_event_id: int = 1, event_id: int = 5) -> Mock:
        event = Mock()
        event.event_type = EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED
        event.event_id = event_id
        attrs = Mock()
        attrs.scheduled_event_id = scheduled_event_id
        event.activity_task_completed_event_attributes = attrs
        return event

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "node_type",
        [NodeType.CONDITION, NodeType.APPROVAL, NodeType.CONVERGE],
    )
    async def test_sync_skipped_after_control_node_completes(self, node_type: str) -> None:
        """Completing a control node (condition, approval, converge) syncs skipped nodes."""
        metadata = create_test_metadata(
            activity_definitions_map={"ctrl_node": {"type": node_type}},
            pending_activity_updates={1: {"activity_id": "ctrl_node", "status": ActivityStatus.RUNNING}},
        )
        event = self._create_completed_event()

        with (
            patch.object(self.service, "_sync_skipped_nodes", new_callable=AsyncMock) as mock_skipped,
            patch.object(self.service, "_sync_activities_to_db", new_callable=AsyncMock),
        ):
            await self.service._handle_event_post_processing(event, metadata, self.mock_handle)
            mock_skipped.assert_called_once_with(metadata, self.mock_handle)

    @pytest.mark.asyncio
    async def test_no_sync_skipped_for_script_node(self) -> None:
        """Completing a non-control node (script) does NOT sync skipped nodes."""
        metadata = create_test_metadata(
            activity_definitions_map={"script_node": {"type": NodeType.SCRIPT}},
            pending_activity_updates={1: {"activity_id": "script_node", "status": ActivityStatus.RUNNING}},
        )
        event = self._create_completed_event()

        with (
            patch.object(self.service, "_sync_skipped_nodes", new_callable=AsyncMock) as mock_skipped,
            patch.object(self.service, "_sync_activities_to_db", new_callable=AsyncMock),
        ):
            await self.service._handle_event_post_processing(event, metadata, self.mock_handle)
            mock_skipped.assert_not_called()


class TestWorkflowEventExtraction:
    """Test workflow completion event extraction."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = ActivitySyncService(Mock(), Mock())

    def _create_workflow_event(
        self,
        event_type: int,
        event_id: int = 100,
        failure_message: str | None = None,
    ) -> Mock:
        """Create a mock workflow completion event."""
        event = Mock()
        event.event_type = event_type
        event.event_id = event_id
        event.event_time = datetime(2025, 1, 20, 12, 0, 0, tzinfo=UTC)

        if event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED:
            attrs = Mock()
            event.workflow_execution_started_event_attributes = attrs

        elif event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED:
            attrs = Mock()
            event.workflow_execution_completed_event_attributes = attrs

        elif event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED:
            attrs = Mock()
            attrs.failure = Mock(message=failure_message) if failure_message else None
            event.workflow_execution_failed_event_attributes = attrs

        elif event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_CANCELED:
            attrs = Mock()
            event.workflow_execution_canceled_event_attributes = attrs

        elif event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_TIMED_OUT:
            attrs = Mock()
            attrs.failure = Mock(message=failure_message) if failure_message else None
            event.workflow_execution_timed_out_event_attributes = attrs

        elif event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_TERMINATED:
            attrs = Mock()
            event.workflow_execution_terminated_event_attributes = attrs

        return event

    @pytest.mark.parametrize(
        ("event_type", "expected_status", "expected_error"),
        [
            (EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED, "completed", None),
            (EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED, "failed", None),
            (EventType.EVENT_TYPE_WORKFLOW_EXECUTION_CANCELED, "cancelled", None),
            (EventType.EVENT_TYPE_WORKFLOW_EXECUTION_TIMED_OUT, "failed", "Workflow execution timed out"),
            (EventType.EVENT_TYPE_WORKFLOW_EXECUTION_TERMINATED, "cancelled", "Workflow was forcibly terminated"),
        ],
    )
    def test_extract_execution_status_from_event(
        self, event_type: int, expected_status: str, expected_error: str | None
    ) -> None:
        """Test extracting execution status from workflow completion events."""
        event = self._create_workflow_event(event_type)

        status, completed_at, error_details = self.service._extract_execution_status_from_event(event)

        assert status.value == expected_status
        assert completed_at == datetime(2025, 1, 20, 12, 0, 0, tzinfo=UTC)
        assert error_details == expected_error

    def test_extract_execution_status_with_failure_message(self) -> None:
        """Test extracting status from FAILED event includes error message."""
        from syntara.workflows.models.execution import ExecutionStatus

        event = self._create_workflow_event(
            EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED, failure_message="Database connection failed"
        )

        status, _completed_at, error_details = self.service._extract_execution_status_from_event(event)

        assert status == ExecutionStatus.FAILED
        assert error_details == "Database connection failed"

    def test_extract_execution_status_with_timeout_uses_default_message(self) -> None:
        """Test extracting status from TIMED_OUT event uses default message (not custom)."""
        from syntara.workflows.models.execution import ExecutionStatus

        event = self._create_workflow_event(
            EventType.EVENT_TYPE_WORKFLOW_EXECUTION_TIMED_OUT, failure_message="Workflow exceeded 5 minute timeout"
        )

        status, _completed_at, error_details = self.service._extract_execution_status_from_event(event)

        assert status == ExecutionStatus.FAILED
        # Implementation uses default message, not custom failure message
        assert error_details == "Workflow execution timed out"

    def test_extract_execution_status_raises_on_invalid_event(self) -> None:
        """Test extraction raises SafeValueError for non-completion events."""
        # Use an activity event instead of a workflow event
        event = self._create_workflow_event(EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED)

        with pytest.raises(SafeValueError, match="is not a workflow completion event"):
            self.service._extract_execution_status_from_event(event)

    def test_extract_execution_status_completed_with_errors_from_result_payload(self) -> None:
        """COMPLETED event with inner status 'completed_with_errors' maps to COMPLETED_WITH_ERRORS."""
        import json

        from syntara.workflows.models.execution import ExecutionStatus

        event = self._create_workflow_event(EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED)
        payload = Mock()
        payload.data = json.dumps(
            {
                "status": "completed_with_errors",
                "execution_id": "exec-1",
                "failed_activities": {"node_2": "Script exited with code 1"},
            }
        ).encode()
        event.workflow_execution_completed_event_attributes.result.payloads = [payload]

        status, _completed_at, error_details = self.service._extract_execution_status_from_event(event)

        assert status == ExecutionStatus.COMPLETED_WITH_ERRORS
        assert error_details is not None
        assert "node_2" in error_details

    def test_extract_execution_status_completed_with_inner_failed_status(self) -> None:
        """COMPLETED event with inner status 'failed' maps to FAILED (existing behaviour preserved)."""
        import json

        from syntara.workflows.models.execution import ExecutionStatus

        event = self._create_workflow_event(EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED)
        payload = Mock()
        payload.data = json.dumps(
            {
                "status": "failed",
                "execution_id": "exec-1",
                "failed_activities": {"node_2": "Unhandled error"},
            }
        ).encode()
        event.workflow_execution_completed_event_attributes.result.payloads = [payload]

        status, _completed_at, error_details = self.service._extract_execution_status_from_event(event)

        assert status == ExecutionStatus.FAILED
        assert error_details is not None


class TestExecutionStatusUpdates:
    """Test execution status updates during monitoring."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.mock_session_factory = Mock()
        self.mock_activity_publisher = AsyncMock()
        self.service = ActivitySyncService(Mock(), self.mock_session_factory, self.mock_activity_publisher)
        self.execution_id = uuid4()

    def _create_mock_execution(
        self,
        execution_id: UUID,
        status: str = "PENDING",
        created_at: datetime | None = None,
    ) -> Mock:
        """Create a mock Execution object."""
        from syntara.workflows.models.execution import ExecutionStatus

        execution = Mock(spec=Execution)
        execution.id = execution_id
        execution.status = ExecutionStatus[status]
        execution.temporal_workflow_id = f"exec-{execution_id}"
        execution.created_at = created_at or datetime(2025, 1, 20, 10, 0, 0, tzinfo=UTC)
        execution.updated_at = execution.created_at
        execution.completed_at = None
        execution.error_details = None
        execution.activities = []
        return execution

    def _create_workflow_event(
        self,
        event_type: int,
        event_id: int = 1,
        event_time: datetime | None = None,
        failure_message: str | None = None,
    ) -> Mock:
        """Create a mock workflow event."""
        event = Mock()
        event.event_type = event_type
        event.event_id = event_id
        event.event_time = event_time or datetime(2025, 1, 20, 12, 0, 0, tzinfo=UTC)

        if event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED:
            attrs = Mock()
            attrs.workflow_run_timeout = None
            event.workflow_execution_started_event_attributes = attrs

        elif event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED:
            attrs = Mock()
            attrs.failure = Mock(message=failure_message) if failure_message else None
            event.workflow_execution_failed_event_attributes = attrs

        elif event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED:
            attrs = Mock()
            event.workflow_execution_completed_event_attributes = attrs

        return event

    @pytest.mark.asyncio
    async def test_update_execution_to_running_from_pending(self) -> None:
        """Test updating execution status from PENDING to RUNNING."""
        from syntara.workflows.models.execution import ExecutionStatus

        execution = self._create_mock_execution(self.execution_id, status="PENDING")

        # Mock session
        mock_result = Mock()
        mock_result.one_or_none.return_value = execution
        mock_session = Mock()
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        self.mock_session_factory.return_value = mock_session

        event = self._create_workflow_event(EventType.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED, event_id=5)

        # Create metadata
        metadata = create_test_metadata(execution_id=self.execution_id)

        # Execute
        await self.service._update_execution_to_running(metadata, event)

        # Verify status changed to RUNNING
        assert execution.status == ExecutionStatus.RUNNING
        assert execution.last_processed_event_id == 5
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_execution_to_running_skips_if_already_running(self) -> None:
        """Test updating to RUNNING is idempotent (service restart scenario)."""
        from syntara.workflows.models.execution import ExecutionStatus

        execution = self._create_mock_execution(self.execution_id, status="RUNNING")
        original_status = execution.status

        # Mock session
        mock_result = Mock()
        mock_result.one_or_none.return_value = execution
        mock_session = Mock()
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        self.mock_session_factory.return_value = mock_session

        event = self._create_workflow_event(EventType.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED)

        # Create metadata
        metadata = create_test_metadata(execution_id=self.execution_id)

        # Execute
        await self.service._update_execution_to_running(metadata, event)

        # Verify status unchanged (idempotent)
        assert execution.status == original_status
        assert execution.status == ExecutionStatus.RUNNING
        # Commit should not be called since no changes
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_execution_to_running_skips_if_terminal_state(self) -> None:
        """Test updating to RUNNING skips if execution already in terminal state."""
        from syntara.workflows.models.execution import ExecutionStatus

        execution = self._create_mock_execution(self.execution_id, status="COMPLETED")
        original_status = execution.status

        # Mock session
        mock_result = Mock()
        mock_result.one_or_none.return_value = execution
        mock_session = Mock()
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        self.mock_session_factory.return_value = mock_session

        event = self._create_workflow_event(EventType.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED)

        # Create metadata
        metadata = create_test_metadata(execution_id=self.execution_id)

        # Execute
        await self.service._update_execution_to_running(metadata, event)

        # Verify status unchanged
        assert execution.status == original_status
        assert execution.status == ExecutionStatus.COMPLETED
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_execution_status_on_completion(self) -> None:
        """Test updating execution status to COMPLETED when workflow completes."""
        from syntara.workflows.models.execution import ExecutionStatus

        execution = self._create_mock_execution(self.execution_id, status="RUNNING")

        # Mock session
        mock_result = Mock()
        mock_result.one_or_none.return_value = execution
        mock_session = Mock()
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        self.mock_session_factory.return_value = mock_session

        event_time = datetime(2025, 1, 20, 12, 30, 0, tzinfo=UTC)
        event = self._create_workflow_event(
            EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED, event_id=100, event_time=event_time
        )

        # Create metadata
        metadata = create_test_metadata(execution_id=self.execution_id)

        # Execute
        await self.service._update_execution_status_from_event(metadata, event)

        # Verify status changed to COMPLETED
        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.completed_at == event_time
        assert execution.last_processed_event_id == 100
        assert execution.error_details is None
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_execution_status_on_failure_with_error(self) -> None:
        """Test updating execution status to FAILED with error message."""
        from syntara.workflows.models.execution import ExecutionStatus

        execution = self._create_mock_execution(self.execution_id, status="RUNNING")

        # Mock session
        mock_result = Mock()
        mock_result.one_or_none.return_value = execution
        mock_session = Mock()
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        self.mock_session_factory.return_value = mock_session

        event = self._create_workflow_event(
            EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED,
            event_id=100,
            failure_message="Database connection timeout",
        )

        # Create metadata
        metadata = create_test_metadata(execution_id=self.execution_id)

        # Execute
        await self.service._update_execution_status_from_event(metadata, event)

        # Verify status changed to FAILED with error
        assert execution.status == ExecutionStatus.FAILED
        assert execution.completed_at is not None
        assert execution.error_details == "Database connection timeout"
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_execution_status_skips_if_already_terminal(self) -> None:
        """Test updating status is idempotent (service restart after completion)."""
        from syntara.workflows.models.execution import ExecutionStatus

        execution = self._create_mock_execution(self.execution_id, status="COMPLETED")
        execution.completed_at = datetime(2025, 1, 20, 12, 0, 0, tzinfo=UTC)
        original_status = execution.status
        original_completed_at = execution.completed_at

        # Mock session
        mock_result = Mock()
        mock_result.one_or_none.return_value = execution
        mock_session = Mock()
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        self.mock_session_factory.return_value = mock_session

        event = self._create_workflow_event(EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED)

        # Create metadata
        metadata = create_test_metadata(execution_id=self.execution_id)

        # Execute
        await self.service._update_execution_status_from_event(metadata, event)

        # Verify execution not modified (idempotent)
        assert execution.status == original_status
        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.completed_at == original_completed_at
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_execution_status_adjusts_timestamp_if_before_created_at(self) -> None:
        """Test completion timestamp is adjusted if before created_at (database constraint)."""
        from syntara.workflows.models.execution import ExecutionStatus

        created_at = datetime(2025, 1, 20, 12, 0, 0, tzinfo=UTC)
        execution = self._create_mock_execution(self.execution_id, status="RUNNING", created_at=created_at)

        # Mock session
        mock_result = Mock()
        mock_result.one_or_none.return_value = execution
        mock_session = Mock()
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        self.mock_session_factory.return_value = mock_session

        # Completion time before creation time (edge case)
        event_time = datetime(2025, 1, 20, 11, 0, 0, tzinfo=UTC)
        event = self._create_workflow_event(EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED, event_time=event_time)

        # Create metadata
        metadata = create_test_metadata(execution_id=self.execution_id)

        # Execute
        await self.service._update_execution_status_from_event(metadata, event)

        # Verify completed_at was adjusted to be after created_at
        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.completed_at > created_at
        # Should be created_at + 1 microsecond
        assert execution.completed_at == created_at + datetime.resolution
        mock_session.commit.assert_awaited_once()


class TestAgenticActivityFinalizationOnWorkflowCompletion:
    """Test that RUNNING agentic activities are finalized when the workflow completes."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        from syntara.workflows.models.execution import ExecutionStatus

        self.mock_session_factory = Mock()
        self.mock_activity_publisher = AsyncMock()
        self.service = ActivitySyncService(Mock(), self.mock_session_factory, self.mock_activity_publisher)
        self.execution_id = uuid4()
        self.ExecutionStatus = ExecutionStatus

    def _create_mock_execution(self, status: str = "RUNNING", activities: list[Mock] | None = None) -> Mock:
        execution = Mock(spec=Execution)
        execution.id = self.execution_id
        execution.status = self.ExecutionStatus[status]
        execution.temporal_workflow_id = f"exec-{self.execution_id}"
        execution.created_at = datetime(2025, 1, 20, 10, 0, 0, tzinfo=UTC)
        execution.updated_at = execution.created_at
        execution.completed_at = None
        execution.error_details = None
        execution.activities = activities or []
        return execution

    def _create_mock_activity(self, status: ActivityStatus, executor: str = "agentic") -> Mock:
        # NOTE: Accepts strings for node_type in tests for backward compatibility.
        # Production code uses NodeType enum. Tracked for migration in ANSTRAT-1845.
        act = Mock()
        act.id = uuid4()
        act.activity_name = "test-activity"
        act.temporal_activity_id = "test-activity"
        act.status = status
        act.completed_at = None
        act.error_details = None
        act.output_data = None
        act.node_type = executor
        return act

    def _create_workflow_event(self, event_type: int, failure_message: str | None = None) -> Mock:
        event = Mock()
        event.event_type = event_type
        event.event_id = 100
        event.event_time = datetime(2025, 1, 20, 12, 30, 0, tzinfo=UTC)

        if event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED:
            attrs = Mock()
            attrs.result = Mock(payloads=[])
            event.workflow_execution_completed_event_attributes = attrs
        elif event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED:
            attrs = Mock()
            attrs.failure = Mock(message=failure_message) if failure_message else None
            event.workflow_execution_failed_event_attributes = attrs

        return event

    def _mock_session(self, execution: Mock) -> Mock:
        mock_result = Mock()
        mock_result.one_or_none.return_value = execution
        mock_session = Mock()
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        self.mock_session_factory.return_value = mock_session
        return mock_session

    @staticmethod
    def _mock_handle(output_data: dict[str, object] | None = None) -> Mock:
        """Create a mock workflow handle that returns output_data for queries."""
        handle = AsyncMock()
        handle.query = AsyncMock(return_value=output_data)
        return handle


class TestIsAgenticActivity:
    """Test _is_agentic_activity with v1 and v2 formats."""

    @pytest.mark.parametrize(
        ("activity_def", "expected"),
        [
            ({"type": "agentic"}, True),
            ({"type": "script"}, False),
            ({"type": "aap_job_template"}, False),
            ({}, False),
        ],
        ids=["agentic", "script", "aap", "empty"],
    )
    def test_is_agentic_activity(self, activity_def: dict[str, object], expected: bool) -> None:  # noqa: FBT001
        """Test agentic detection for activity definitions."""
        assert ActivitySyncService._is_agentic_activity(activity_def) == expected


class TestExtractTriggerActivityType:
    """Test _extract_trigger_activity_type static method."""

    @pytest.mark.parametrize(
        ("activity_definitions_map", "expected"),
        [
            ({"trigger-1": {"type": "manual_trigger"}}, "manual_trigger"),
            ({"trigger-1": {"type": "scheduled_trigger"}}, "scheduled_trigger"),
            ({"trigger-1": {"type": "webhook_trigger"}}, "webhook_trigger"),
            ({"trigger-1": {"type": "eda_trigger"}}, "eda_trigger"),
            (
                {
                    "node-1": {"type": "script"},
                    "trigger-1": {"type": "manual_trigger"},
                    "node-2": {"type": "condition"},
                },
                "manual_trigger",
            ),
            ({"node-1": {"type": "script"}, "node-2": {"type": "agentic"}}, None),
            ({}, None),
            ({"node-1": {"type": 123}}, None),
            ({"node-1": {"name": "test"}}, None),
            ({"node-1": {}}, None),
            ({"trigger-1": {"type": "unknown_trigger"}}, None),
        ],
        ids=[
            "manual_trigger",
            "scheduled_trigger",
            "webhook_trigger",
            "eda_trigger",
            "mixed_nodes_with_trigger",
            "no_trigger_nodes",
            "empty_map",
            "non_string_type",
            "missing_type_key",
            "empty_definition",
            "unknown_trigger_type_not_matched",
        ],
    )
    def test_extract_trigger_activity_type(
        self, activity_definitions_map: dict[str, dict[str, Any]], expected: ActivityName | None
    ) -> None:
        """Test trigger type extraction from various activity definition maps."""
        assert ActivitySyncService._extract_trigger_activity_type(activity_definitions_map) == expected


class TestActivitySyncTerminalCleanup:
    """Test terminal activity cleanup logic in _sync_activities_to_db."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.execution_id = uuid4()
        self.mock_session_factory = Mock()
        self.mock_activity_publisher = AsyncMock()
        self.service = ActivitySyncService(Mock(), self.mock_session_factory, self.mock_activity_publisher)

    def _create_mock_activity_execution(
        self,
        activity_name: str = "approval-node",
        status: ActivityStatus = ActivityStatus.PENDING,
    ) -> Mock:
        """Create a mock ActivityExecution database record."""
        activity = Mock()
        activity.activity_name = activity_name
        activity.status = status
        activity.started_at = None
        activity.completed_at = None
        activity.error_details = None
        activity.retry_count = 0
        activity.input_data = {}
        activity.output_data = None
        activity.updated_at = None
        return activity

    def _mock_session_with_activities(self, activities: list[Mock]) -> Mock:
        """Create a mock session that returns the given activities and a mock execution."""
        from syntara.workflows.models.execution import Execution

        # Mock for the activity query
        mock_activity_result = Mock()
        mock_activity_result.all.return_value = activities

        # Mock for the execution query (used to update last_processed_event_id)
        mock_execution = Mock(spec=Execution)
        mock_execution.id = self.execution_id
        mock_execution.last_processed_event_id = 0
        mock_execution_result = Mock()
        mock_execution_result.one_or_none.return_value = mock_execution

        mock_session = Mock()
        mock_session.exec = AsyncMock(side_effect=[mock_activity_result, mock_execution_result])
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        self.mock_session_factory.return_value = mock_session
        return mock_session

    def _create_mock_handle(
        self,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
    ) -> AsyncMock:
        """Create a mock workflow handle that returns given data for queries."""
        handle = AsyncMock()

        async def mock_query(query_name: str, activity_id: str) -> dict[str, object] | None:
            if query_name == "get_activity_input":
                return input_data or {}
            if query_name == "get_activity_output":
                return output_data
            return None

        handle.query = AsyncMock(side_effect=mock_query)
        return handle

    @pytest.mark.asyncio
    async def test_completed_activity_cleared_from_pending(self) -> None:
        """A completed activity with output_data is cleared from pending_activity_updates."""
        activity = self._create_mock_activity_execution(activity_name="script-node")
        self._mock_session_with_activities([activity])

        handle = self._create_mock_handle(output_data={"stdout": "hello", "exit_code": 0})

        metadata = create_test_metadata(
            execution_id=self.execution_id,
            activity_index_map={"script-node": 0},
            pending_activity_updates={
                10: {
                    "activity_id": "script-node",
                    "activity_name": "script-node",
                    "status": ActivityStatus.COMPLETED,
                    "started_at": datetime.now(UTC),
                    "completed_at": datetime.now(UTC),
                    "error_details": None,
                    "retry_count": 0,
                },
            },
        )

        await self.service._sync_activities_to_db(metadata, handle)

        # Should be cleared from pending (terminal + has output)
        assert 10 not in metadata.pending_activity_updates

    @pytest.mark.asyncio
    async def test_non_completed_activity_stays_in_pending(self) -> None:
        """Activities in non-terminal states (RUNNING, FAILED) remain in pending_activity_updates."""
        activity = self._create_mock_activity_execution(activity_name="running-node")
        self._mock_session_with_activities([activity])

        handle = self._create_mock_handle(output_data=None)

        metadata = create_test_metadata(
            execution_id=self.execution_id,
            activity_index_map={"running-node": 0},
            pending_activity_updates={
                10: {
                    "activity_id": "running-node",
                    "activity_name": "running-node",
                    "status": ActivityStatus.RUNNING,
                    "started_at": datetime.now(UTC),
                    "completed_at": None,
                    "error_details": None,
                    "retry_count": 0,
                },
            },
        )

        await self.service._sync_activities_to_db(metadata, handle)

        # RUNNING activity should remain in pending (not terminal)
        assert 10 in metadata.pending_activity_updates

    @pytest.mark.asyncio
    async def test_waiting_approval_stays_waiting_when_no_output(self) -> None:
        """WAITING approval activity remains WAITING when output_data is still None."""
        activity = self._create_mock_activity_execution(
            activity_name="approval-node",
            status=ActivityStatus.WAITING,
        )
        self._mock_session_with_activities([activity])

        handle = self._create_mock_handle(output_data=None)

        metadata = create_test_metadata(
            execution_id=self.execution_id,
            activity_index_map={"approval-node": 0},
            pending_activity_updates={
                10: {
                    "activity_id": "approval-node",
                    "activity_name": "approval-node",
                    "status": ActivityStatus.WAITING,
                    "started_at": datetime.now(UTC),
                    "completed_at": None,
                    "error_details": None,
                    "retry_count": 0,
                },
            },
        )

        await self.service._sync_activities_to_db(metadata, handle)

        assert activity.status == ActivityStatus.WAITING
        assert activity.completed_at is None

    @pytest.mark.asyncio
    async def test_running_agentic_stays_running_when_no_output(self) -> None:
        """RUNNING agentic activity remains RUNNING when output_data is still None."""
        activity = self._create_mock_activity_execution(
            activity_name="agent-node",
            status=ActivityStatus.RUNNING,
        )
        self._mock_session_with_activities([activity])

        handle = self._create_mock_handle(output_data=None)

        metadata = create_test_metadata(
            execution_id=self.execution_id,
            activity_index_map={"agent-node": 0},
            activity_definitions_map={
                "agent-node": {"type": "agentic"},
            },
            pending_activity_updates={
                10: {
                    "activity_id": "agent-node",
                    "activity_name": "agent-node",
                    "status": ActivityStatus.RUNNING,
                    "started_at": datetime.now(UTC),
                    "completed_at": None,
                    "error_details": None,
                    "retry_count": 0,
                },
            },
        )

        await self.service._sync_activities_to_db(metadata, handle)

        assert activity.status == ActivityStatus.RUNNING
        assert activity.completed_at is None


class TestLoopIterationSync:
    """Test loop iteration handling in _sync_activities_to_db."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.execution_id = uuid4()
        self.mock_session_factory = Mock()
        self.mock_activity_publisher = AsyncMock()
        self.service = ActivitySyncService(Mock(), self.mock_session_factory, self.mock_activity_publisher)

    def _create_mock_activity_execution(
        self,
        activity_name: str = "loop-node",
        status: ActivityStatus = ActivityStatus.PENDING,
    ) -> Mock:
        """Create a mock ActivityExecution database record."""
        activity = Mock()
        activity.activity_name = activity_name
        activity.status = status
        activity.started_at = None
        activity.completed_at = None
        activity.error_details = None
        activity.retry_count = 0
        activity.input_data = {}
        activity.output_data = None
        activity.updated_at = None
        activity.iteration = None
        activity.node_type = NodeType.SCRIPT
        return activity

    def _mock_session_with_activities(self, activities: list[Mock]) -> Mock:
        """Create a mock session that returns the given activities and a mock execution."""
        mock_activity_result = Mock()
        mock_activity_result.all.return_value = activities

        mock_execution = Mock(spec=Execution)
        mock_execution.id = self.execution_id
        mock_execution.last_processed_event_id = 0
        mock_execution_result = Mock()
        mock_execution_result.one_or_none.return_value = mock_execution

        mock_session = Mock()
        mock_session.exec = AsyncMock(side_effect=[mock_activity_result, mock_execution_result])
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        self.mock_session_factory.return_value = mock_session
        return mock_session

    def _create_mock_handle(
        self,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
    ) -> AsyncMock:
        """Create a mock workflow handle that returns given data for queries."""
        handle = AsyncMock()

        async def mock_query(query_name: str, activity_id: str) -> dict[str, object] | None:
            if query_name == "get_activity_input":
                return input_data or {}
            if query_name == "get_activity_output":
                return output_data
            return None

        handle.query = AsyncMock(side_effect=mock_query)
        return handle

    @pytest.mark.asyncio
    async def test_terminal_status_blocks_non_loop_update(self) -> None:
        """A completed non-loop activity should not be updated by a later event."""
        activity = self._create_mock_activity_execution(activity_name="action-node", status=ActivityStatus.COMPLETED)
        self._mock_session_with_activities([activity])
        handle = self._create_mock_handle(output_data={"result": "done"})

        metadata = create_test_metadata(
            execution_id=self.execution_id,
            activity_index_map={"action-node": 0},
            pending_activity_updates={
                10: {
                    "activity_id": "action-node",
                    "activity_name": "action-node",
                    "status": ActivityStatus.CANCELLED,
                    "started_at": datetime.now(UTC),
                    "completed_at": datetime.now(UTC),
                    "error_details": None,
                    "retry_count": 0,
                },
            },
        )

        await self.service._sync_activities_to_db(metadata, handle)

        assert activity.status == ActivityStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_terminal_body_child_creates_per_iteration_record(self) -> None:
        """A completed body child with _is_loop_iteration creates a new per-iteration record."""
        activity = self._create_mock_activity_execution(activity_name="body-node", status=ActivityStatus.COMPLETED)
        mock_session = self._mock_session_with_activities([activity])
        handle = self._create_mock_handle(output_data={"result": "iteration-2"})

        metadata = create_test_metadata(
            execution_id=self.execution_id,
            activity_index_map={"body-node": 0},
            pending_activity_updates={
                10: {
                    "activity_id": "body-node",
                    "activity_name": "body-node",
                    "_is_loop_iteration": True,
                    "_is_loop_control": False,
                    "status": ActivityStatus.RUNNING,
                    "started_at": datetime.now(UTC),
                    "completed_at": None,
                    "error_details": None,
                    "retry_count": 0,
                },
            },
        )

        await self.service._sync_activities_to_db(metadata, handle)

        # Original record stays COMPLETED and gets iteration=0
        assert activity.status == ActivityStatus.COMPLETED
        assert activity.iteration == 0

        # A new record was added to the session
        mock_session.add.assert_called_once()
        new_record = mock_session.add.call_args[0][0]
        assert new_record.activity_name == "body-node#iter-1"
        assert new_record.iteration == 1

    @pytest.mark.asyncio
    async def test_loop_control_node_stays_running_between_iterations(self) -> None:
        """A loop control node in terminal status stays RUNNING when iteration_results is absent."""
        activity = self._create_mock_activity_execution(activity_name="loop-node", status=ActivityStatus.PENDING)
        self._mock_session_with_activities([activity])
        handle = self._create_mock_handle(output_data={"iteration_count": 1})

        metadata = create_test_metadata(
            execution_id=self.execution_id,
            activity_index_map={"loop-node": 0},
            pending_activity_updates={
                10: {
                    "activity_id": "loop-node",
                    "activity_name": "loop-node",
                    "_is_loop_iteration": True,
                    "_is_loop_control": True,
                    "status": ActivityStatus.COMPLETED,
                    "started_at": datetime.now(UTC),
                    "completed_at": datetime.now(UTC),
                    "error_details": None,
                    "retry_count": 0,
                },
            },
        )

        await self.service._sync_activities_to_db(metadata, handle)

        assert activity.status == ActivityStatus.RUNNING

    @pytest.mark.asyncio
    async def test_loop_control_node_stays_completed_on_final_iteration(self) -> None:
        """A loop control node keeps COMPLETED when iteration_results is present (final iteration)."""
        activity = self._create_mock_activity_execution(activity_name="loop-node", status=ActivityStatus.PENDING)
        self._mock_session_with_activities([activity])
        handle = self._create_mock_handle(
            output_data={"iteration_count": 3, "iteration_results": {"0": {}, "1": {}, "2": {}}}
        )

        metadata = create_test_metadata(
            execution_id=self.execution_id,
            activity_index_map={"loop-node": 0},
            pending_activity_updates={
                10: {
                    "activity_id": "loop-node",
                    "activity_name": "loop-node",
                    "_is_loop_iteration": True,
                    "_is_loop_control": True,
                    "status": ActivityStatus.COMPLETED,
                    "started_at": datetime.now(UTC),
                    "completed_at": datetime.now(UTC),
                    "error_details": None,
                    "retry_count": 0,
                },
            },
        )

        await self.service._sync_activities_to_db(metadata, handle)

        assert activity.status == ActivityStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_failed_loop_control_node_preserves_failed_status(self) -> None:
        """A FAILED loop control node must not be overridden to RUNNING by a subsequent event."""
        activity = self._create_mock_activity_execution(activity_name="loop-node", status=ActivityStatus.FAILED)
        activity.error_details = "connection timeout"
        self._mock_session_with_activities([activity])
        handle = self._create_mock_handle(output_data={"iteration_count": 1})

        metadata = create_test_metadata(
            execution_id=self.execution_id,
            activity_index_map={"loop-node": 0},
            pending_activity_updates={
                10: {
                    "activity_id": "loop-node",
                    "activity_name": "loop-node",
                    "_is_loop_iteration": True,
                    "_is_loop_control": True,
                    "status": ActivityStatus.COMPLETED,
                    "started_at": datetime.now(UTC),
                    "completed_at": datetime.now(UTC),
                    "error_details": None,
                    "retry_count": 0,
                },
            },
        )

        await self.service._sync_activities_to_db(metadata, handle)

        assert activity.status == ActivityStatus.FAILED
        assert activity.error_details == "connection timeout"

    @pytest.mark.asyncio
    async def test_body_node_keeps_real_terminal_status(self) -> None:
        """A loop body node (not control) keeps its real status, not overridden to RUNNING."""
        activity = self._create_mock_activity_execution(activity_name="body-node", status=ActivityStatus.PENDING)
        self._mock_session_with_activities([activity])
        handle = self._create_mock_handle(output_data={"result": "done"})

        metadata = create_test_metadata(
            execution_id=self.execution_id,
            activity_index_map={"body-node": 0},
            pending_activity_updates={
                10: {
                    "activity_id": "body-node",
                    "activity_name": "body-node",
                    "_is_loop_iteration": True,
                    "_is_loop_control": False,
                    "status": ActivityStatus.COMPLETED,
                    "started_at": datetime.now(UTC),
                    "completed_at": datetime.now(UTC),
                    "error_details": None,
                    "retry_count": 0,
                },
            },
        )

        await self.service._sync_activities_to_db(metadata, handle)

        assert activity.status == ActivityStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_commit_failure_restores_all_metadata_fields(self) -> None:
        """All mutable metadata fields must be restored when commit fails."""
        activity = self._create_mock_activity_execution(activity_name="body-node", status=ActivityStatus.COMPLETED)
        mock_session = self._mock_session_with_activities([activity])
        mock_session.commit = AsyncMock(side_effect=RuntimeError("db error"))
        handle = self._create_mock_handle(output_data={"result": "done"})

        metadata = create_test_metadata(
            execution_id=self.execution_id,
            activity_index_map={"body-node": 0},
            iteration_counters={"body-node": 1},
            next_activity_index=1,
            pending_activity_updates={
                10: {
                    "activity_id": "body-node",
                    "activity_name": "body-node",
                    "_is_loop_iteration": True,
                    "_is_loop_control": False,
                    "status": ActivityStatus.RUNNING,
                    "started_at": datetime.now(UTC),
                    "completed_at": None,
                    "error_details": None,
                    "retry_count": 0,
                },
            },
        )
        metadata.terminal_activity_ids.add("previously-done")

        saved_counters = dict(metadata.iteration_counters)
        saved_index = metadata.next_activity_index
        saved_map = dict(metadata.activity_index_map)
        saved_terminal = set(metadata.terminal_activity_ids)

        with pytest.raises(RuntimeError, match="db error"):
            await self.service._sync_activities_to_db(metadata, handle)

        assert metadata.iteration_counters == saved_counters
        assert metadata.next_activity_index == saved_index
        assert metadata.activity_index_map == saved_map
        assert metadata.terminal_activity_ids == saved_terminal


class TestCollectTerminalActivitiesTracking:
    """Test that _collect_terminal_activities populates terminal_activity_ids."""

    def test_terminal_activity_ids_populated(self) -> None:
        """Completed activities should be tracked in terminal_activity_ids."""
        metadata = create_test_metadata(
            pending_activity_updates={
                10: {
                    "activity_id": "node-a",
                    "activity_name": "node-a",
                    "status": ActivityStatus.COMPLETED,
                },
                20: {
                    "activity_id": "node-b",
                    "activity_name": "node-b",
                    "status": ActivityStatus.RUNNING,
                },
            },
        )

        ActivitySyncService._collect_terminal_activities(metadata)

        assert "node-a" in metadata.terminal_activity_ids
        assert "node-b" not in metadata.terminal_activity_ids
        assert 10 not in metadata.pending_activity_updates
        assert 20 in metadata.pending_activity_updates

    def test_terminal_activity_ids_accumulates_across_calls(self) -> None:
        """Multiple calls accumulate IDs rather than replacing them."""
        metadata = create_test_metadata(
            pending_activity_updates={
                10: {
                    "activity_id": "node-a",
                    "activity_name": "node-a",
                    "status": ActivityStatus.COMPLETED,
                },
            },
        )
        metadata.terminal_activity_ids.add("previously-completed")

        ActivitySyncService._collect_terminal_activities(metadata)

        assert "previously-completed" in metadata.terminal_activity_ids
        assert "node-a" in metadata.terminal_activity_ids

    def test_stale_cleanup_removes_overridden_loop_control_entries(self) -> None:
        """Loop control entries with _status_overridden should be cleaned up."""
        metadata = create_test_metadata(
            pending_activity_updates={
                10: {
                    "activity_id": "loop-node",
                    "activity_name": "loop-node",
                    "_is_loop_control": True,
                    "_status_overridden": True,
                    "status": ActivityStatus.RUNNING,
                },
            },
        )

        ActivitySyncService._collect_terminal_activities(metadata)

        assert 10 not in metadata.pending_activity_updates

    def test_stale_cleanup_preserves_naturally_running_loop_control(self) -> None:
        """Loop control entries that are naturally RUNNING (not overridden) must be kept."""
        metadata = create_test_metadata(
            pending_activity_updates={
                10: {
                    "activity_id": "loop-node",
                    "activity_name": "loop-node",
                    "_is_loop_control": True,
                    "status": ActivityStatus.RUNNING,
                },
            },
        )

        ActivitySyncService._collect_terminal_activities(metadata)

        assert 10 in metadata.pending_activity_updates

    def test_removed_entries_returned_for_rollback(self) -> None:
        """removed_entries should contain both terminal and stale loop control entries."""
        metadata = create_test_metadata(
            pending_activity_updates={
                10: {
                    "activity_id": "node-a",
                    "activity_name": "node-a",
                    "status": ActivityStatus.COMPLETED,
                },
                20: {
                    "activity_id": "loop-ctl",
                    "activity_name": "loop-ctl",
                    "_is_loop_control": True,
                    "_status_overridden": True,
                    "status": ActivityStatus.RUNNING,
                },
                30: {
                    "activity_id": "node-b",
                    "activity_name": "node-b",
                    "status": ActivityStatus.RUNNING,
                },
            },
        )

        _terminal_ids, _timed_out, removed_entries = ActivitySyncService._collect_terminal_activities(metadata)

        assert 10 in removed_entries
        assert removed_entries[10]["activity_id"] == "node-a"
        assert 20 in removed_entries
        assert removed_entries[20]["activity_id"] == "loop-ctl"
        assert 30 not in removed_entries
        assert 30 in metadata.pending_activity_updates


class TestGetOrCreateIterationRecord:
    """Test _get_or_create_iteration_record static method."""

    def _create_mock_activity(
        self,
        activity_name: str = "body-node",
        status: ActivityStatus = ActivityStatus.COMPLETED,
        iteration: int | None = None,
    ) -> Mock:
        """Create a mock ActivityExecution for iteration record tests."""
        activity = Mock(spec=ActivityExecution)
        activity.activity_name = activity_name
        activity.status = status
        activity.iteration = iteration
        activity.node_type = NodeType.SCRIPT
        return activity

    def test_returns_none_when_original_not_found(self) -> None:
        """Returns (None, False) when the original activity is not in existing_activities."""
        metadata = create_test_metadata(execution_id=uuid4())
        existing_activities: dict[str, ActivityExecution] = {}
        session = Mock()

        result, is_new = ActivitySyncService._get_or_create_iteration_record(
            "missing-node", existing_activities, metadata, session
        )

        assert result is None
        assert is_new is False
        session.add.assert_not_called()

    def test_creates_new_record_when_no_iterations_exist(self) -> None:
        """Creates a new iteration record when only the original exists."""
        metadata = create_test_metadata(execution_id=uuid4(), activity_index_map={"body-node": 0})
        original = self._create_mock_activity()
        existing_activities: dict[str, ActivityExecution] = {"body-node": original}
        session = Mock()

        result, is_new = ActivitySyncService._get_or_create_iteration_record(
            "body-node", existing_activities, metadata, session
        )

        assert is_new is True
        assert result is not None
        assert result.activity_name == "body-node#iter-1"
        assert result.iteration == 1
        assert original.iteration == 0
        session.add.assert_called_once()

    def test_reuses_non_terminal_iteration_record(self) -> None:
        """Returns existing non-terminal iteration record instead of creating a new one."""
        metadata = create_test_metadata(
            execution_id=uuid4(),
            activity_index_map={"body-node": 0, "body-node#iter-1": 1},
            iteration_counters={"body-node": 1},
        )
        original = self._create_mock_activity(iteration=0)
        running_iter = self._create_mock_activity(
            activity_name="body-node#iter-1", status=ActivityStatus.RUNNING, iteration=1
        )
        existing_activities: dict[str, ActivityExecution] = {
            "body-node": original,
            "body-node#iter-1": running_iter,
        }
        session = Mock()

        result, is_new = ActivitySyncService._get_or_create_iteration_record(
            "body-node", existing_activities, metadata, session
        )

        assert is_new is False
        assert result is running_iter
        session.add.assert_not_called()

    def test_creates_new_record_when_latest_iteration_is_terminal(self) -> None:
        """Creates a new record when the latest iteration has reached terminal status."""
        metadata = create_test_metadata(
            execution_id=uuid4(),
            activity_index_map={"body-node": 0, "body-node#iter-1": 1},
            iteration_counters={"body-node": 1},
        )
        original = self._create_mock_activity(iteration=0)
        completed_iter = self._create_mock_activity(
            activity_name="body-node#iter-1", status=ActivityStatus.COMPLETED, iteration=1
        )
        existing_activities: dict[str, ActivityExecution] = {
            "body-node": original,
            "body-node#iter-1": completed_iter,
        }
        session = Mock()

        result, is_new = ActivitySyncService._get_or_create_iteration_record(
            "body-node", existing_activities, metadata, session
        )

        assert is_new is True
        assert result is not None
        assert result.activity_name == "body-node#iter-2"
        assert result.iteration == 2
        session.add.assert_called_once()


class TestExtractFailedActivityErrors:
    """Test _extract_failed_activity_errors static method."""

    def test_with_failed_activities(self) -> None:
        """Test extraction from failed_activities dict."""
        result_data = {"failed_activities": {"node-1": "error A", "node-2": "error B"}}
        result = ActivitySyncService._extract_failed_activity_errors(result_data)
        assert "node-1: error A" in result
        assert "node-2: error B" in result

    def test_empty_failed_activities(self) -> None:
        """Test fallback when failed_activities is empty."""
        result_data: dict[str, object] = {"failed_activities": {}}
        result = ActivitySyncService._extract_failed_activity_errors(result_data)
        assert result == "One or more workflow activities failed"

    def test_no_failed_activities_key(self) -> None:
        """Test fallback when no failed_activities key."""
        result = ActivitySyncService._extract_failed_activity_errors({})
        assert result == "One or more workflow activities failed"


class TestExtractFailedActivitiesFromEvent:
    """Test _extract_failed_activities_from_event static method."""

    def setup_method(self) -> None:
        self.service = ActivitySyncService(
            temporal_client=AsyncMock(),
            session_factory=AsyncMock(),
        )

    def _make_completed_event(self, result_data: dict[str, object]) -> Mock:
        import json

        event = Mock()
        event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
        payload = Mock()
        payload.data = json.dumps(result_data).encode()
        event.workflow_execution_completed_event_attributes.result.payloads = [payload]
        return event

    def test_extracts_failed_activities(self) -> None:
        event = self._make_completed_event(
            {
                "status": "failed",
                "failed_activities": {"loop-1": "exceeded max_iterations", "loop-2": "exceeded max_iterations"},
            }
        )
        result = self.service._extract_failed_activities_from_event(event)
        assert result == {"loop-1": "exceeded max_iterations", "loop-2": "exceeded max_iterations"}

    def test_returns_empty_for_non_completed_event(self) -> None:
        event = Mock()
        event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED
        result = self.service._extract_failed_activities_from_event(event)
        assert result == {}

    def test_returns_empty_when_no_failed_activities(self) -> None:
        event = self._make_completed_event({"status": "completed", "failed_activities": {}})
        result = self.service._extract_failed_activities_from_event(event)
        assert result == {}

    def test_returns_empty_when_no_payloads(self) -> None:
        event = Mock()
        event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
        event.workflow_execution_completed_event_attributes.result.payloads = []
        result = self.service._extract_failed_activities_from_event(event)
        assert result == {}

    def test_returns_empty_on_malformed_payload(self) -> None:
        event = Mock()
        event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
        payload = Mock()
        payload.data = b"not valid json"
        event.workflow_execution_completed_event_attributes.result.payloads = [payload]
        result = self.service._extract_failed_activities_from_event(event)
        assert result == {}


class TestSyncNodesToTerminalStatus:
    """Test _sync_nodes_to_terminal_status shared method and its callers.

    Both _sync_skipped_nodes and _sync_failed_nodes delegate to a shared
    method that handles DB updates and WebSocket patch publishing.
    """

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.execution_id = uuid4()
        self.mock_session_factory = Mock()
        self.mock_activity_publisher = AsyncMock()
        self.service = ActivitySyncService(Mock(), self.mock_session_factory, self.mock_activity_publisher)

    def _create_metadata(
        self,
        activity_index_map: dict[str, int] | None = None,
    ) -> ExecutionMonitorMetadata:
        return create_test_metadata(
            execution_id=self.execution_id,
            activity_index_map=activity_index_map or {},
        )

    def _create_mock_activity_execution(
        self,
        activity_name: str,
        status: ActivityStatus = ActivityStatus.PENDING,
    ) -> Mock:
        """Create a mock ActivityExecution database record."""
        activity = Mock()
        activity.activity_name = activity_name
        activity.status = status
        activity.started_at = None
        activity.completed_at = None
        activity.error_details = None
        activity.updated_at = None
        return activity

    def _mock_session(
        self,
        activities: list[Mock],
        actually_updated_names: set[str] | None = None,
    ) -> Mock:
        """Create a mock session returning given activities.

        activities: PENDING activities returned by the SELECT (Phase 1).
        actually_updated_names: names returned by the RETURNING clause of the atomic
            UPDATE (Phase 2). Defaults to all activity names, simulating every
            activity being updated successfully.
        """
        mock_result = Mock()
        mock_result.all.return_value = activities
        mock_session = Mock()
        mock_session.exec = AsyncMock(return_value=mock_result)

        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        self.mock_session_factory.return_value = mock_session
        return mock_session

    # -- _sync_failed_nodes tests --

    @pytest.mark.asyncio
    async def test_failed_node_marked_as_failed_in_database(self) -> None:
        """Node that failed during expression resolution should be marked FAILED."""
        activity = self._create_mock_activity_execution("node-A")
        self._mock_session([activity])
        metadata = self._create_metadata(activity_index_map={"node-A": 0})

        handle = AsyncMock()
        handle.query = AsyncMock(return_value={"node-A": "Key 'output' not found in namespace path"})

        result = await self.service._sync_failed_nodes(metadata, handle)

        handle.query.assert_awaited_once_with("get_failed_nodes")
        assert activity.status == ActivityStatus.FAILED
        assert activity.completed_at is not None
        assert activity.error_details == "Key 'output' not found in namespace path"
        assert result == {"node-A": "Key 'output' not found in namespace path"}

    @pytest.mark.asyncio
    async def test_multiple_failed_nodes_all_marked(self) -> None:
        """Multiple failed nodes should each get the correct error message."""
        activity_a = self._create_mock_activity_execution("node-A")
        activity_b = self._create_mock_activity_execution("node-B")
        self._mock_session([activity_a, activity_b])
        metadata = self._create_metadata(activity_index_map={"node-A": 0, "node-B": 1})

        handle = AsyncMock()
        handle.query = AsyncMock(
            return_value={
                "node-A": "Key 'output' not found",
                "node-B": "Namespace 'missing' not found",
            }
        )

        await self.service._sync_failed_nodes(metadata, handle)

        assert activity_a.status == ActivityStatus.FAILED
        assert activity_a.error_details == "Key 'output' not found"
        assert activity_b.status == ActivityStatus.FAILED
        assert activity_b.error_details == "Namespace 'missing' not found"

    @pytest.mark.asyncio
    async def test_no_failed_nodes_is_noop(self) -> None:
        """When no nodes failed, no database operations should occur."""
        metadata = self._create_metadata()
        handle = AsyncMock()
        handle.query = AsyncMock(return_value={})

        await self.service._sync_failed_nodes(metadata, handle)

        self.mock_session_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_sync_skips_already_failed_node(self) -> None:
        """Node already in FAILED status is filtered out by the PENDING WHERE clause.

        The SELECT in Phase 1 filters to status=PENDING, so Temporal-synced FAILED
        activities are never loaded and the atomic UPDATE never runs.
        """
        mock_session = self._mock_session([])  # FAILED activity excluded by WHERE status=PENDING
        metadata = self._create_metadata()

        handle = AsyncMock()
        handle.query = AsyncMock(return_value={"node-A": "some error"})

        await self.service._sync_failed_nodes(metadata, handle)

        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_sync_preserves_temporal_error_details(self) -> None:
        """Temporal-synced FAILED activities must not be overwritten by query-based sync.

        In production the SELECT WHERE status=PENDING excludes already-FAILED records.
        This test verifies that when no PENDING activities are found (because Temporal
        already synced them), no UPDATE is executed and no patches are published —
        preserving the rich Temporal error details.
        """
        mock_session = self._mock_session([])  # Temporal-synced FAILED not in PENDING results
        metadata = self._create_metadata()

        handle = AsyncMock()
        handle.query = AsyncMock(return_value={"node-A": "Key 'output' not found in namespace path"})

        with patch.object(self.service, "_publish_activity_patches", new_callable=AsyncMock) as mock_publish:
            await self.service._sync_failed_nodes(metadata, handle)

        mock_session.commit.assert_not_awaited()
        mock_publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_sync_publishes_websocket_patches(self) -> None:
        """Status changes should be published to WebSocket via activity patches."""
        activity = self._create_mock_activity_execution("node-A")
        self._mock_session([activity])
        metadata = self._create_metadata(activity_index_map={"node-A": 0})

        handle = AsyncMock()
        handle.query = AsyncMock(return_value={"node-A": "expression error"})

        with patch.object(self.service, "_publish_activity_patches", new_callable=AsyncMock) as mock_publish:
            await self.service._sync_failed_nodes(metadata, handle)

            mock_publish.assert_awaited_once()
            call_args = mock_publish.call_args
            assert call_args[0][0] is metadata
            updated = call_args[0][1]
            assert len(updated) == 1
            assert updated[0][0] is activity
            assert updated[0][1]["status"] == ActivityStatus.PENDING

    @pytest.mark.asyncio
    async def test_failed_sync_query_error_does_not_propagate(self) -> None:
        """Errors during failed node sync should be logged, not raised, and return None."""
        metadata = self._create_metadata()
        handle = AsyncMock()
        handle.query = AsyncMock(side_effect=RuntimeError("workflow not reachable"))

        result = await self.service._sync_failed_nodes(metadata, handle)

        assert result is None

    # -- _sync_skipped_nodes tests --

    @pytest.mark.asyncio
    async def test_skipped_node_marked_as_skipped_in_database(self) -> None:
        """Node on non-taken condition branch should be marked SKIPPED."""
        activity = self._create_mock_activity_execution("node-B")
        self._mock_session([activity])
        metadata = self._create_metadata(activity_index_map={"node-B": 1})

        handle = AsyncMock()
        skipped_return = ["node-B"]
        pre_resolved_return: list[str] = []
        handle.query = AsyncMock(side_effect=[skipped_return, pre_resolved_return])

        await self.service._sync_skipped_nodes(metadata, handle)

        assert handle.query.await_count == 2
        handle.query.assert_any_await("get_skipped_nodes")
        handle.query.assert_any_await("get_pre_resolved_nodes")
        assert activity.status == ActivityStatus.SKIPPED
        assert activity.completed_at is not None
        assert activity.error_details is None

    @pytest.mark.asyncio
    async def test_skipped_sync_publishes_websocket_patches(self) -> None:
        """Skipped nodes should trigger WebSocket activity patches after DB commit."""
        activity = self._create_mock_activity_execution("node-B")
        self._mock_session([activity])
        metadata = self._create_metadata(activity_index_map={"node-B": 1})

        handle = AsyncMock()
        handle.query = AsyncMock(side_effect=[["node-B"], []])

        with patch.object(self.service, "_publish_activity_patches", new_callable=AsyncMock) as mock_publish:
            await self.service._sync_skipped_nodes(metadata, handle)

            mock_publish.assert_awaited_once()
            call_args = mock_publish.call_args
            assert call_args[0][0] is metadata
            updated = call_args[0][1]
            assert len(updated) == 1
            assert updated[0][0] is activity
            assert updated[0][1]["status"] == ActivityStatus.PENDING

    @pytest.mark.asyncio
    async def test_no_skipped_nodes_is_noop(self) -> None:
        """When no nodes skipped, no database operations should occur."""
        metadata = self._create_metadata()
        handle = AsyncMock()
        handle.query = AsyncMock(side_effect=[[], []])

        await self.service._sync_skipped_nodes(metadata, handle)

        self.mock_session_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_skipped_sync_query_error_does_not_propagate(self) -> None:
        """Errors during skipped node sync should be logged, not raised."""
        metadata = self._create_metadata()
        handle = AsyncMock()
        handle.query = AsyncMock(side_effect=RuntimeError("workflow not reachable"))

        await self.service._sync_skipped_nodes(metadata, handle)

    # -- _ensure_activity_records_exist tests --

    @pytest.mark.asyncio
    async def test_ensure_activity_records_creates_missing_records(self) -> None:
        """Pre-resolved nodes without existing records get SKIPPED ActivityExecution rows."""
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session = Mock()
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        self.mock_session_factory.return_value = mock_session

        node_def = {"id": "node-A", "type": "script"}
        metadata = self._create_metadata()
        metadata.activity_definitions_map = {"node-A": node_def}

        await self.service._ensure_activity_records_exist(metadata, ["node-A"], ActivityStatus.SKIPPED)

        mock_session.add.assert_called_once()
        record = mock_session.add.call_args[0][0]
        assert record.activity_name == "node-A"
        assert record.status == ActivityStatus.SKIPPED
        assert record.node_type == node_def.get("type", "script")
        assert record.temporal_activity_id.startswith("pre-resolved-")
        assert record.started_at is not None
        assert record.completed_at is not None
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ensure_activity_records_handles_invalid_node_type(self) -> None:
        """Invalid node types fall back to INTERNAL_ACTIVITY instead of crashing."""
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session = Mock()
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        self.mock_session_factory.return_value = mock_session

        # Provide an invalid node type that will trigger ValueError
        node_def = {"id": "node-invalid", "type": "not_a_valid_node_type"}
        metadata = self._create_metadata()
        metadata.activity_definitions_map = {"node-invalid": node_def}

        # Should not raise ValueError - should fall back to INTERNAL_ACTIVITY
        await self.service._ensure_activity_records_exist(metadata, ["node-invalid"], ActivityStatus.SKIPPED)

        mock_session.add.assert_called_once()
        record = mock_session.add.call_args[0][0]
        assert record.activity_name == "node-invalid"
        assert record.status == ActivityStatus.SKIPPED
        # Should have fallen back to INTERNAL_ACTIVITY
        assert record.node_type == NodeType.INTERNAL_ACTIVITY
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ensure_activity_records_skips_existing(self) -> None:
        """Nodes that already have records are not duplicated."""
        mock_result = Mock()
        mock_result.all.return_value = ["node-A"]
        mock_session = Mock()
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        self.mock_session_factory.return_value = mock_session

        metadata = self._create_metadata()

        await self.service._ensure_activity_records_exist(metadata, ["node-A"], ActivityStatus.SKIPPED)

        mock_session.add.assert_not_called()
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ensure_activity_records_mixed_existing_and_missing(self) -> None:
        """Only missing nodes get new records when some already exist."""
        mock_result = Mock()
        mock_result.all.return_value = ["node-A"]
        mock_session = Mock()
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        self.mock_session_factory.return_value = mock_session

        metadata = self._create_metadata()

        await self.service._ensure_activity_records_exist(metadata, ["node-A", "node-B"], ActivityStatus.SKIPPED)

        mock_session.add.assert_called_once()
        record = mock_session.add.call_args[0][0]
        assert record.activity_name == "node-B"
        mock_session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: input_data credential scrubbing before DB persistence (AAP-74431)
# ---------------------------------------------------------------------------


class TestInputDataCredentialScrubbing(TestActivitySyncTerminalCleanup):
    """Verify input_data is scrubbed before writing to ActivityExecution (AAP-74431)."""

    @pytest.mark.asyncio
    async def test_credential_fields_scrubbed_before_persistence(self) -> None:
        """Input data containing credential fields should be redacted before DB write."""
        from syntara.workflows.workflow_engine.utils.credential_scrubber import REDACTED

        activity = self._create_mock_activity_execution(activity_name="approval-node")
        self._mock_session_with_activities([activity])

        handle = self._create_mock_handle(
            input_data={"url": "http://example.com", "bearer_token": "sk-secret-123"},
            output_data={"status": "ok"},
        )

        metadata = create_test_metadata(
            execution_id=self.execution_id,
            activity_index_map={"approval-node": 0},
            pending_activity_updates={
                10: {
                    "activity_id": "approval-node",
                    "activity_name": "approval-node",
                    "status": ActivityStatus.COMPLETED,
                    "started_at": datetime.now(UTC),
                    "completed_at": datetime.now(UTC),
                    "error_details": None,
                    "retry_count": 0,
                },
            },
        )

        await self.service._sync_activities_to_db(metadata, handle)

        assert activity.input_data["bearer_token"] == REDACTED
        assert activity.input_data["url"] == "http://example.com"

    @pytest.mark.asyncio
    async def test_clean_input_data_preserved(self) -> None:
        """Input data without credential fields should pass through unchanged."""
        activity = self._create_mock_activity_execution(activity_name="approval-node")
        self._mock_session_with_activities([activity])

        handle = self._create_mock_handle(
            input_data={"url": "http://example.com", "method": "GET"},
            output_data={"status": "ok"},
        )

        metadata = create_test_metadata(
            execution_id=self.execution_id,
            activity_index_map={"approval-node": 0},
            pending_activity_updates={
                10: {
                    "activity_id": "approval-node",
                    "activity_name": "approval-node",
                    "status": ActivityStatus.COMPLETED,
                    "started_at": datetime.now(UTC),
                    "completed_at": datetime.now(UTC),
                    "error_details": None,
                    "retry_count": 0,
                },
            },
        )

        await self.service._sync_activities_to_db(metadata, handle)

        assert activity.input_data == {"url": "http://example.com", "method": "GET"}


class TestSyntheticActivityStarted:
    """Test synthetic STARTED event processing from describe() probing."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = ActivitySyncService(Mock(), Mock())
        self.execution_id = uuid4()

    @pytest.mark.asyncio
    async def test_updates_pending_activity_to_running(self) -> None:
        """Test that a synthetic STARTED event transitions PENDING to RUNNING."""
        metadata = create_test_metadata(
            execution_id=self.execution_id,
            activity_definitions_map={"my-activity": {"type": "script"}},
            pending_activity_updates={
                5: {
                    "activity_id": "my-activity",
                    "activity_name": "my-activity",
                    "status": ActivityStatus.PENDING,
                    "started_at": None,
                    "completed_at": None,
                    "error_details": None,
                    "retry_count": 0,
                },
            },
        )

        event = SyntheticActivityStarted(activity_id="my-activity", scheduled_event_id=5)

        with patch.object(self.service, "_sync_activities_to_db", new_callable=AsyncMock):
            await self.service._process_synthetic_activity_started(event, metadata, Mock())

        assert metadata.pending_activity_updates[5]["status"] == ActivityStatus.RUNNING
        assert metadata.pending_activity_updates[5]["started_at"] is not None

    @pytest.mark.asyncio
    async def test_updates_approval_activity_to_waiting(self) -> None:
        """Test that a synthetic STARTED event transitions approval nodes to WAITING."""
        metadata = create_test_metadata(
            execution_id=self.execution_id,
            activity_definitions_map={"approval-node": {"type": "approval"}},
            pending_activity_updates={
                5: {
                    "activity_id": "approval-node",
                    "activity_name": "approval-node",
                    "status": ActivityStatus.PENDING,
                    "started_at": None,
                    "completed_at": None,
                    "error_details": None,
                    "retry_count": 0,
                },
            },
        )

        event = SyntheticActivityStarted(activity_id="approval-node", scheduled_event_id=5)

        with patch.object(self.service, "_sync_activities_to_db", new_callable=AsyncMock):
            await self.service._process_synthetic_activity_started(event, metadata, Mock())

        assert metadata.pending_activity_updates[5]["status"] == ActivityStatus.WAITING
        assert metadata.pending_activity_updates[5]["started_at"] is not None

    @pytest.mark.asyncio
    async def test_skips_if_already_running(self) -> None:
        """Test that synthetic STARTED is a no-op if activity is already RUNNING."""
        metadata = create_test_metadata(
            execution_id=self.execution_id,
            pending_activity_updates={
                5: {
                    "activity_id": "my-activity",
                    "status": ActivityStatus.RUNNING,
                    "started_at": datetime.now(UTC),
                },
            },
        )

        event = SyntheticActivityStarted(activity_id="my-activity", scheduled_event_id=5)

        with patch.object(self.service, "_sync_activities_to_db", new_callable=AsyncMock) as mock_sync:
            await self.service._process_synthetic_activity_started(event, metadata, Mock())
            mock_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_if_already_completed(self) -> None:
        """Test that synthetic STARTED is a no-op if activity is already COMPLETED."""
        metadata = create_test_metadata(
            execution_id=self.execution_id,
            pending_activity_updates={
                5: {
                    "activity_id": "my-activity",
                    "status": ActivityStatus.COMPLETED,
                },
            },
        )

        event = SyntheticActivityStarted(activity_id="my-activity", scheduled_event_id=5)

        with patch.object(self.service, "_sync_activities_to_db", new_callable=AsyncMock) as mock_sync:
            await self.service._process_synthetic_activity_started(event, metadata, Mock())
            mock_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_if_not_in_pending_updates(self) -> None:
        """Test that synthetic STARTED is a no-op if activity not found in pending updates."""
        metadata = create_test_metadata(execution_id=self.execution_id)
        event = SyntheticActivityStarted(activity_id="unknown", scheduled_event_id=99)

        with patch.object(self.service, "_sync_activities_to_db", new_callable=AsyncMock) as mock_sync:
            await self.service._process_synthetic_activity_started(event, metadata, Mock())
            mock_sync.assert_not_called()


class TestScheduleDescribeProbe:
    """Test _schedule_describe_probe describe() polling logic."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = ActivitySyncService(Mock(), Mock())

    @staticmethod
    def _make_started_pa_with_heartbeat(
        activity_id: str = "my-activity",
        partial_output: dict[str, Any] | None = None,
    ) -> Mock:
        """Create a STARTED pending activity mock with STOP_MONITOR heartbeat."""
        pa = Mock()
        pa.activity_id = activity_id
        pa.state = STARTED_STATE
        payload = Mock()
        payload.data = json.dumps({"stop_monitor": True, "partial_output": partial_output})
        pa.heartbeat_details.payloads = [payload]
        return pa

    @pytest.mark.asyncio
    async def test_pushes_started_then_partial_output(self) -> None:
        """Test that probe pushes SyntheticActivityStarted then SyntheticPartialOutput as separate events."""
        pa = self._make_started_pa_with_heartbeat(partial_output={"job_id": 42})
        mock_desc = Mock()
        mock_desc.raw_description.pending_activities = [pa]
        mock_handle = AsyncMock()
        mock_handle.describe.return_value = mock_desc

        queue: asyncio.Queue[Any] = asyncio.Queue()

        with patch(
            "syntara.workflows.workflow_engine.services.activity_sync_service.asyncio.sleep", new_callable=AsyncMock
        ):
            await self.service._schedule_describe_probe(
                handle=mock_handle,
                queue=queue,
                activity_id="my-activity",
                scheduled_event_id=5,
            )

        # First event: status → RUNNING
        item1 = await queue.get()
        assert isinstance(item1, SyntheticActivityStarted)
        assert item1.activity_id == "my-activity"
        assert item1.scheduled_event_id == 5

        # Second event: partial output
        item2 = await queue.get()
        assert isinstance(item2, SyntheticPartialOutput)
        assert item2.partial_output == {"job_id": 42}

    @pytest.mark.asyncio
    async def test_stops_when_activity_no_longer_pending(self) -> None:
        """Test that probe pushes event and stops when activity disappears before STARTED."""
        mock_handle = AsyncMock()
        mock_desc = Mock()
        mock_desc.raw_description.pending_activities = []
        mock_handle.describe.return_value = mock_desc

        queue: asyncio.Queue[Any] = asyncio.Queue()

        with patch(
            "syntara.workflows.workflow_engine.services.activity_sync_service.asyncio.sleep", new_callable=AsyncMock
        ):
            await self.service._schedule_describe_probe(
                handle=mock_handle,
                queue=queue,
                activity_id="my-activity",
                scheduled_event_id=5,
            )

        # Activity disappeared before STARTED — probe pushes a synthetic event
        # so the DB still gets the status transition.
        assert not queue.empty()
        item = await queue.get()
        assert isinstance(item, SyntheticActivityStarted)
        mock_handle.describe.assert_called_once()

    @pytest.mark.asyncio
    async def test_retries_with_backoff_when_still_scheduled(self) -> None:
        """Test that probe retries with backoff when activity is still SCHEDULED."""
        pa_scheduled = Mock()
        pa_scheduled.activity_id = "my-activity"
        pa_scheduled.state = 1  # SCHEDULED

        pa_started = self._make_started_pa_with_heartbeat(partial_output={"job_id": 99})

        desc_scheduled = Mock()
        desc_scheduled.raw_description.pending_activities = [pa_scheduled]

        desc_started = Mock()
        desc_started.raw_description.pending_activities = [pa_started]

        mock_handle = AsyncMock()
        mock_handle.describe.side_effect = [desc_scheduled, desc_scheduled, desc_started]

        queue: asyncio.Queue[Any] = asyncio.Queue()

        with patch(
            "syntara.workflows.workflow_engine.services.activity_sync_service.asyncio.sleep", new_callable=AsyncMock
        ):
            await self.service._schedule_describe_probe(
                handle=mock_handle,
                queue=queue,
                activity_id="my-activity",
                scheduled_event_id=5,
            )

        assert mock_handle.describe.call_count == 3
        item1 = await queue.get()
        assert isinstance(item1, SyntheticActivityStarted)
        item2 = await queue.get()
        assert isinstance(item2, SyntheticPartialOutput)

    @pytest.mark.asyncio
    async def test_retries_on_exception(self) -> None:
        """Test that probe retries when describe() raises an exception."""
        pa_started = self._make_started_pa_with_heartbeat(partial_output={"job_id": 77})
        desc_started = Mock()
        desc_started.raw_description.pending_activities = [pa_started]

        mock_handle = AsyncMock()
        mock_handle.describe.side_effect = [RuntimeError("connection failed"), desc_started]

        queue: asyncio.Queue[Any] = asyncio.Queue()

        with patch(
            "syntara.workflows.workflow_engine.services.activity_sync_service.asyncio.sleep", new_callable=AsyncMock
        ):
            await self.service._schedule_describe_probe(
                handle=mock_handle,
                queue=queue,
                activity_id="my-activity",
                scheduled_event_id=5,
            )

        assert mock_handle.describe.call_count == 2
        item1 = await queue.get()
        assert isinstance(item1, SyntheticActivityStarted)
        item2 = await queue.get()
        assert isinstance(item2, SyntheticPartialOutput)

    @pytest.mark.asyncio
    async def test_stops_on_shutdown(self) -> None:
        """Test that probe stops when service is shutting down."""
        self.service._shutdown = True

        mock_handle = AsyncMock()
        queue: asyncio.Queue[Any] = asyncio.Queue()

        await self.service._schedule_describe_probe(
            handle=mock_handle,
            queue=queue,
            activity_id="my-activity",
            scheduled_event_id=5,
        )

        assert queue.empty()
        mock_handle.describe.assert_not_called()


class TestExtractHeartbeatData:
    """Test _extract_heartbeat_data static method."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = ActivitySyncService(Mock(), Mock())

    def test_returns_decoded_dict_from_valid_payload(self) -> None:
        """Test decoding a valid JSON heartbeat payload."""
        import json

        pa = Mock()
        payload = Mock()
        payload.data = json.dumps({"stop_monitor": True, "partial_output": {"job_id": 42}}).encode()
        pa.heartbeat_details = Mock()
        pa.heartbeat_details.payloads = [payload]

        result = ActivitySyncService._extract_heartbeat_data(pa)

        assert result is not None
        assert result["stop_monitor"] is True
        assert result["partial_output"]["job_id"] == 42

    def test_returns_none_when_no_heartbeat_details(self) -> None:
        """Test returns None when heartbeat_details is None."""
        pa = Mock()
        pa.heartbeat_details = None

        result = ActivitySyncService._extract_heartbeat_data(pa)

        assert result is None

    def test_returns_none_when_no_payloads(self) -> None:
        """Test returns None when heartbeat_details has empty payloads."""
        pa = Mock()
        pa.heartbeat_details = Mock()
        pa.heartbeat_details.payloads = []

        result = ActivitySyncService._extract_heartbeat_data(pa)

        assert result is None

    def test_returns_none_on_malformed_json(self) -> None:
        """Test returns None when payload contains invalid JSON."""
        pa = Mock()
        payload = Mock()
        payload.data = b"not valid json"
        pa.heartbeat_details = Mock()
        pa.heartbeat_details.payloads = [payload]

        result = ActivitySyncService._extract_heartbeat_data(pa)

        assert result is None

    def test_returns_none_when_heartbeat_details_falsy(self) -> None:
        """Test returns None when heartbeat_details is falsy (empty object)."""
        pa = Mock()
        pa.heartbeat_details = Mock()
        pa.heartbeat_details.__bool__ = Mock(return_value=False)
        pa.heartbeat_details.payloads = []

        result = ActivitySyncService._extract_heartbeat_data(pa)

        assert result is None

    def test_returns_none_on_attribute_error(self) -> None:
        """Test returns None when payload data attribute raises AttributeError."""
        pa = Mock()
        payload = Mock()
        payload.data = None  # json.loads(None) will raise TypeError, but we mock it
        pa.heartbeat_details = Mock()
        pa.heartbeat_details.payloads = [payload]

        # When data is None, json.loads will raise TypeError which is not caught,
        # but AttributeError on accessing .data is caught
        pa2 = Mock()
        pa2.heartbeat_details = Mock()
        pa2.heartbeat_details.payloads = [Mock(spec=[])]  # spec=[] means no 'data' attribute

        result = ActivitySyncService._extract_heartbeat_data(pa2)

        assert result is None


class TestHistoryEventProducer:
    """Test _history_event_producer streaming into queue."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = ActivitySyncService(Mock(), Mock())

    @pytest.mark.asyncio
    async def test_uses_page_size_100(self) -> None:
        """fetch_history_events must be called with page_size=100 to cap per-request memory."""
        mock_handle = AsyncMock()
        captured: list[dict[str, int]] = []

        async def mock_fetch(**kwargs: int) -> AsyncIterator[None]:
            captured.append(dict(kwargs))
            return
            yield  # type: ignore[unreachable]

        mock_handle.fetch_history_events = mock_fetch

        queue: asyncio.Queue[Any] = asyncio.Queue()
        await self.service._history_event_producer(mock_handle, queue, uuid4())

        assert captured == [{"page_size": 100, "wait_new_event": True}]

    @pytest.mark.asyncio
    async def test_streams_events_into_queue(self) -> None:
        """Test that history events are pushed into the queue."""
        event1 = Mock()
        event2 = Mock()

        mock_handle = AsyncMock()

        async def mock_fetch(**kwargs: int) -> AsyncIterator[Mock]:
            yield event1
            yield event2

        mock_handle.fetch_history_events = mock_fetch

        queue: asyncio.Queue[Any] = asyncio.Queue()
        await self.service._history_event_producer(mock_handle, queue, uuid4())

        items = []
        while not queue.empty():
            items.append(await queue.get())

        assert items == [event1, event2, None]

    @pytest.mark.asyncio
    async def test_pushes_none_sentinel_on_completion(self) -> None:
        """Test that None sentinel is pushed when history stream ends."""
        mock_handle = AsyncMock()

        async def mock_fetch(**kwargs: int) -> AsyncIterator[Mock]:
            return
            yield

        mock_handle.fetch_history_events = mock_fetch

        queue: asyncio.Queue[Any] = asyncio.Queue()
        await self.service._history_event_producer(mock_handle, queue, uuid4())

        item = await queue.get()
        assert item is None

    @pytest.mark.asyncio
    async def test_pushes_none_sentinel_on_error(self) -> None:
        """Test that None sentinel is pushed even when producer encounters an error."""
        mock_handle = AsyncMock()

        async def mock_fetch(**kwargs: int) -> AsyncIterator[Mock]:
            yield Mock()
            msg = "connection lost"
            raise RuntimeError(msg)

        mock_handle.fetch_history_events = mock_fetch

        queue: asyncio.Queue[Any] = asyncio.Queue()
        await self.service._history_event_producer(mock_handle, queue, uuid4())

        items = []
        while not queue.empty():
            items.append(await queue.get())

        assert len(items) == 2
        assert items[-1] is None

    @pytest.mark.asyncio
    async def test_stops_on_shutdown(self) -> None:
        """Test that producer stops streaming when shutdown is requested."""
        self.service._shutdown = True

        event1 = Mock()
        mock_handle = AsyncMock()

        async def mock_fetch(**kwargs: int) -> AsyncIterator[Mock]:
            yield event1

        mock_handle.fetch_history_events = mock_fetch

        queue: asyncio.Queue[Any] = asyncio.Queue()
        await self.service._history_event_producer(mock_handle, queue, uuid4())

        items = []
        while not queue.empty():
            items.append(await queue.get())

        assert items == [None]


class TestProcessHistoryEvent:
    """Test _process_history_event dispatching logic."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = ActivitySyncService(Mock(), Mock())
        self.execution_id = uuid4()
        self.metadata = create_test_metadata(
            execution_id=self.execution_id,
            last_processed_event_id=0,
        )
        self.mock_handle = AsyncMock()
        self.queue: asyncio.Queue[Any] = asyncio.Queue()
        self.probe_tasks: list[asyncio.Task[None]] = []

    def _create_event(self, event_type: int, event_id: int, activity_id: str = "test-activity") -> Mock:
        """Create a mock Temporal history event."""
        event = Mock()
        event.event_type = event_type
        event.event_id = event_id
        event.event_time = datetime.now(UTC)

        attrs = Mock()
        if event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
            attrs.activity_id = activity_id
            attrs.start_to_close_timeout = None
            event.activity_task_scheduled_event_attributes = attrs
        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED:
            attrs.scheduled_event_id = 1
            attrs.attempt = 1
            attrs.last_failure = None
            event.activity_task_started_event_attributes = attrs
        elif event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED:
            attrs.scheduled_event_id = 1
            attrs.result = None
            event.activity_task_completed_event_attributes = attrs

        return event

    @pytest.mark.asyncio
    async def test_skips_already_processed_events(self) -> None:
        """Test that events with IDs <= last_processed are skipped."""
        self.metadata.last_processed_event_id = 10
        event = self._create_event(EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED, event_id=5)

        with patch.object(self.service, "_process_activity_event") as mock_process:
            result = await self.service._process_history_event(
                event,
                self.metadata,
                self.mock_handle,
                self.queue,
                self.probe_tasks,
            )

        assert result is True
        mock_process.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_workflow_started_event(self) -> None:
        """Test that WORKFLOW_EXECUTION_STARTED updates execution to RUNNING."""
        event = self._create_event(EventType.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED, event_id=1)

        with patch.object(self.service, "_update_execution_to_running", new_callable=AsyncMock) as mock_update:
            result = await self.service._process_history_event(
                event,
                self.metadata,
                self.mock_handle,
                self.queue,
                self.probe_tasks,
            )

        assert result is True
        mock_update.assert_called_once_with(self.metadata, event)
        assert self.metadata.last_processed_event_id == 1

    @pytest.mark.asyncio
    async def test_handles_workflow_completion_event(self) -> None:
        """Test that workflow completion events trigger final sync.

        Order matters: _sync_failed_nodes and _sync_skipped_nodes must run
        BEFORE _update_execution_status_from_event so that
        _finalize_non_terminal_activities (called inside the latter) does not
        overwrite already-synced terminal statuses (e.g. a converge node that
        is FAILED in the workflow but still PENDING in the DB).
        """
        event = self._create_event(EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED, event_id=20)

        call_order: list[str] = []

        async def track_failed(*_args: object, **_kwargs: object) -> dict[str, str]:
            call_order.append("failed")
            return {}

        async def track_skipped(*_args: object, **_kwargs: object) -> None:
            call_order.append("skipped")

        async def track_status(*_args: object, **_kwargs: object) -> None:
            call_order.append("status")

        with (
            patch.object(self.service, "_update_execution_status_from_event", side_effect=track_status) as mock_status,
            patch.object(self.service, "_sync_skipped_nodes", side_effect=track_skipped) as mock_skipped,
            patch.object(self.service, "_sync_failed_nodes", side_effect=track_failed) as mock_failed,
        ):
            result = await self.service._process_history_event(
                event,
                self.metadata,
                self.mock_handle,
                self.queue,
                self.probe_tasks,
            )

        assert result is True
        mock_status.assert_called_once()
        mock_skipped.assert_called_once()
        mock_failed.assert_called_once()
        assert call_order == ["failed", "skipped", "status"]
        assert self.metadata.last_processed_event_id == 20

    @pytest.mark.asyncio
    async def test_sync_failed_nodes_none_falls_back_to_event_extraction(self) -> None:
        """When _sync_failed_nodes returns None, _extract_failed_activities_from_event is used."""
        event = self._create_event(EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED, event_id=20)
        fallback_map = {"node-X": "expression error"}

        with (
            patch.object(self.service, "_sync_failed_nodes", new_callable=AsyncMock, return_value=None),
            patch.object(
                self.service, "_extract_failed_activities_from_event", return_value=fallback_map
            ) as mock_extract,
            patch.object(self.service, "_sync_skipped_nodes", new_callable=AsyncMock),
            patch.object(self.service, "_update_execution_status_from_event", new_callable=AsyncMock) as mock_update,
        ):
            result = await self.service._process_history_event(
                event,
                self.metadata,
                self.mock_handle,
                self.queue,
                self.probe_tasks,
            )

        assert result is True
        mock_extract.assert_called_once_with(event)
        mock_update.assert_called_once()
        passed_failed_map = mock_update.call_args[0][2]
        assert passed_failed_map == fallback_map

    @pytest.mark.asyncio
    async def test_processes_activity_events(self) -> None:
        """Test that activity events are processed and post-processed."""
        event = self._create_event(EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED, event_id=5)

        with (
            patch.object(self.service, "_process_activity_event") as mock_process,
            patch.object(
                self.service, "_handle_event_post_processing", new_callable=AsyncMock, return_value=5
            ) as mock_post,
        ):
            result = await self.service._process_history_event(
                event,
                self.metadata,
                self.mock_handle,
                self.queue,
                self.probe_tasks,
            )

        assert result is True
        mock_process.assert_called_once_with(event, self.metadata)
        mock_post.assert_called_once()
        assert self.metadata.last_processed_event_id == 5

    @pytest.mark.asyncio
    async def test_launches_probe_on_scheduled_event(self) -> None:
        """Test that SCHEDULED events launch a describe probe task."""
        event = self._create_event(
            EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED,
            event_id=10,
            activity_id="my-activity",
        )

        with (
            patch.object(self.service, "_process_activity_event"),
            patch.object(self.service, "_handle_event_post_processing", new_callable=AsyncMock, return_value=10),
            patch.object(self.service, "_schedule_describe_probe", new_callable=AsyncMock) as mock_probe,
        ):
            await self.service._process_history_event(
                event,
                self.metadata,
                self.mock_handle,
                self.queue,
                self.probe_tasks,
            )

        assert len(self.probe_tasks) == 1
        # Wait for the task and verify it called the probe
        await self.probe_tasks[0]
        mock_probe.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_probe_for_internal_activities(self) -> None:
        """Test that __internal__ activities do not launch probes."""
        event = self._create_event(
            EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED,
            event_id=10,
            activity_id="__internal__monitoring",
        )

        with (
            patch.object(self.service, "_process_activity_event"),
            patch.object(self.service, "_handle_event_post_processing", new_callable=AsyncMock, return_value=10),
        ):
            await self.service._process_history_event(
                event,
                self.metadata,
                self.mock_handle,
                self.queue,
                self.probe_tasks,
            )

        assert len(self.probe_tasks) == 0

    @pytest.mark.asyncio
    async def test_caps_probe_tasks(self) -> None:
        """Test that probe tasks are capped at _DESCRIBE_PROBE_MAX_TASKS."""
        from syntara.workflows.workflow_engine.services.activity_sync_service import _DESCRIBE_PROBE_MAX_TASKS

        # Fill probe_tasks with non-done tasks to hit the cap
        for _ in range(_DESCRIBE_PROBE_MAX_TASKS):
            self.probe_tasks.append(asyncio.create_task(asyncio.sleep(100)))

        event = self._create_event(
            EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED,
            event_id=10,
            activity_id="my-activity",
        )

        with (
            patch.object(self.service, "_process_activity_event"),
            patch.object(self.service, "_handle_event_post_processing", new_callable=AsyncMock, return_value=10),
        ):
            await self.service._process_history_event(
                event,
                self.metadata,
                self.mock_handle,
                self.queue,
                self.probe_tasks,
            )

        # No new task should have been added
        assert len(self.probe_tasks) == _DESCRIBE_PROBE_MAX_TASKS

        # Cleanup
        for t in self.probe_tasks:
            t.cancel()
        await asyncio.gather(*self.probe_tasks, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_prunes_done_tasks_before_cap_check(self) -> None:
        """Test that completed probe tasks are pruned before checking the cap."""
        from syntara.workflows.workflow_engine.services.activity_sync_service import _DESCRIBE_PROBE_MAX_TASKS

        # Fill with done tasks
        for _ in range(_DESCRIBE_PROBE_MAX_TASKS):
            task = asyncio.create_task(asyncio.sleep(0))
            await task
            self.probe_tasks.append(task)

        event = self._create_event(
            EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED,
            event_id=10,
            activity_id="my-activity",
        )

        with (
            patch.object(self.service, "_process_activity_event"),
            patch.object(self.service, "_handle_event_post_processing", new_callable=AsyncMock, return_value=10),
            patch.object(self.service, "_schedule_describe_probe", new_callable=AsyncMock),
        ):
            await self.service._process_history_event(
                event,
                self.metadata,
                self.mock_handle,
                self.queue,
                self.probe_tasks,
            )

        # Done tasks pruned, new one added
        assert len(self.probe_tasks) == 1


class TestMonitorExecutionIntegration:
    """Integration tests for _monitor_execution queue-based consumer."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = ActivitySyncService(Mock(), Mock())
        self.execution_id = uuid4()

    @pytest.mark.asyncio
    async def test_processes_synthetic_started_events(self) -> None:
        """Test that SyntheticActivityStarted events are processed by the consumer."""
        metadata = create_test_metadata(
            execution_id=self.execution_id,
            activity_definitions_map={"my-activity": {"type": "script"}},
            pending_activity_updates={
                5: {
                    "activity_id": "my-activity",
                    "activity_name": "my-activity",
                    "status": ActivityStatus.PENDING,
                    "started_at": None,
                    "completed_at": None,
                    "error_details": None,
                    "retry_count": 0,
                },
            },
        )

        with (
            patch.object(self.service, "_initialize_monitoring", new_callable=AsyncMock, return_value=metadata),
            patch.object(self.service, "_sync_activities_to_db", new_callable=AsyncMock) as mock_sync,
        ):

            async def mock_producer(handle: Mock, queue: asyncio.Queue[Any], exec_id: UUID) -> None:
                await queue.put(SyntheticActivityStarted(activity_id="my-activity", scheduled_event_id=5))
                await queue.put(None)

            with patch.object(self.service, "_history_event_producer", side_effect=mock_producer):
                await self.service._monitor_execution(
                    self.execution_id,
                    "temporal-wf-id",
                )

            assert metadata.pending_activity_updates[5]["status"] == ActivityStatus.RUNNING
            assert metadata.pending_activity_updates[5]["started_at"] is not None
            mock_sync.assert_called()

    @pytest.mark.asyncio
    async def test_stops_on_shutdown(self) -> None:
        """Test that the consumer stops when shutdown is requested."""
        metadata = create_test_metadata(execution_id=self.execution_id)
        self.service._shutdown = True

        event = Mock()
        event.event_type = EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
        event.event_id = 5

        with patch.object(self.service, "_initialize_monitoring", new_callable=AsyncMock, return_value=metadata):

            async def mock_producer(handle: Mock, queue: asyncio.Queue[Any], exec_id: UUID) -> None:
                await queue.put(event)
                await queue.put(None)

            with (
                patch.object(self.service, "_history_event_producer", side_effect=mock_producer),
                patch.object(self.service, "_process_history_event", new_callable=AsyncMock) as mock_process,
            ):
                await self.service._monitor_execution(
                    self.execution_id,
                    "temporal-wf-id",
                )

            mock_process.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleans_up_tasks_on_completion(self) -> None:
        """Test that producer and probe tasks are cancelled on normal completion."""
        metadata = create_test_metadata(execution_id=self.execution_id)

        with patch.object(self.service, "_initialize_monitoring", new_callable=AsyncMock, return_value=metadata):

            async def mock_producer(handle: Mock, queue: asyncio.Queue[Any], exec_id: UUID) -> None:
                await queue.put(None)

            with patch.object(self.service, "_history_event_producer", side_effect=mock_producer):
                await self.service._monitor_execution(
                    self.execution_id,
                    "temporal-wf-id",
                )


class TestPendingSyncEventIds:
    """Test pending_sync_event_ids mechanism."""

    def test_scheduled_event_adds_to_pending_sync(self) -> None:
        """Test that SCHEDULED events add to pending_sync_event_ids."""
        mock_client = Mock()
        mock_session_factory = Mock()
        service = ActivitySyncService(mock_client, mock_session_factory)

        metadata = create_test_metadata()
        event = Mock()
        event.event_id = 10
        event.event_type = None
        event.event_time = Mock()
        event.activity_task_scheduled_event_attributes = Mock()
        event.activity_task_scheduled_event_attributes.activity_id = "test_activity"
        event.activity_task_scheduled_event_attributes.start_to_close_timeout = None

        service._process_activity_scheduled(event, metadata)

        assert 10 in metadata.pending_sync_event_ids
        assert metadata.pending_activity_updates[10]["activity_id"] == "test_activity"

    def test_started_event_adds_to_pending_sync(self) -> None:
        """Test that STARTED events add to pending_sync_event_ids."""
        mock_client = Mock()
        mock_session_factory = Mock()
        service = ActivitySyncService(mock_client, mock_session_factory)

        metadata = create_test_metadata(
            pending_activity_updates={
                5: {
                    "activity_id": "test_activity",
                    "activity_name": "test_activity",
                    "status": ActivityStatus.PENDING,
                    "started_at": None,
                    "completed_at": None,
                    "error_details": None,
                    "retry_count": 0,
                }
            }
        )

        event = Mock()
        event.event_id = 11
        event.event_time = Mock()
        event.event_time.ToDatetime = Mock(return_value=datetime.now(UTC))
        event.activity_task_started_event_attributes = Mock()
        event.activity_task_started_event_attributes.scheduled_event_id = 5
        event.activity_task_started_event_attributes.attempt = 1

        service._process_activity_started(event, metadata)

        assert 5 in metadata.pending_sync_event_ids
        assert metadata.pending_activity_updates[5]["status"] == ActivityStatus.RUNNING


class TestUpdateNonTerminalActivitiesOnCancel:
    """Test _update_non_terminal_activities_on_cancel method."""

    def test_in_flight_cancelled_pending_skipped(self) -> None:
        """In-flight activities (RUNNING, WAITING) are CANCELLED; PENDING is SKIPPED."""
        mock_client = Mock()
        mock_session_factory = Mock()
        service = ActivitySyncService(mock_client, mock_session_factory)

        execution_id = uuid4()
        cancelled_at = datetime.now(UTC)

        execution = Execution(
            id=execution_id,
            workflow_id=uuid4(),
            workflow_version_id=uuid4(),
            temporal_workflow_id=f"workflow-{execution_id}",
            status=ExecutionStatus.CANCELLED,
            created_by=uuid4(),
            input_data={},
            labels={},
            project_id=uuid4(),
        )

        pending_activity = ActivityExecution(
            id=uuid4(),
            execution_id=execution_id,
            activity_name="pending_activity",
            node_type="script",
            temporal_activity_id="temporal-pending",
            status=ActivityStatus.PENDING,
        )

        running_activity = ActivityExecution(
            id=uuid4(),
            execution_id=execution_id,
            activity_name="running_activity",
            node_type="script",
            temporal_activity_id="temporal-running",
            status=ActivityStatus.RUNNING,
            started_at=datetime.now(UTC),
        )

        waiting_activity = ActivityExecution(
            id=uuid4(),
            execution_id=execution_id,
            activity_name="waiting_activity",
            node_type="approval",
            temporal_activity_id="temporal-waiting",
            status=ActivityStatus.WAITING,
            started_at=datetime.now(UTC),
        )

        completed_activity = ActivityExecution(
            id=uuid4(),
            execution_id=execution_id,
            activity_name="completed_activity",
            node_type="script",
            temporal_activity_id="temporal-completed",
            status=ActivityStatus.COMPLETED,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )

        execution.activities = [pending_activity, running_activity, waiting_activity, completed_activity]

        updated_activities = service._update_non_terminal_activities_on_cancel(execution, cancelled_at)

        assert len(updated_activities) == 3

        assert running_activity.status == ActivityStatus.CANCELLED
        assert running_activity.completed_at == cancelled_at
        assert running_activity.error_details == "Workflow was cancelled"

        assert pending_activity.status == ActivityStatus.SKIPPED
        assert pending_activity.completed_at == cancelled_at
        assert pending_activity.error_details is None

        assert waiting_activity.status == ActivityStatus.CANCELLED
        assert waiting_activity.completed_at == cancelled_at
        assert waiting_activity.error_details == "Workflow was cancelled"

        assert completed_activity.status == ActivityStatus.COMPLETED

    def test_retrying_activity_is_cancelled(self) -> None:
        """A retrying activity is actively in-flight — it should be CANCELLED."""
        mock_client = Mock()
        mock_session_factory = Mock()
        service = ActivitySyncService(mock_client, mock_session_factory)

        execution_id = uuid4()
        cancelled_at = datetime.now(UTC)

        execution = Execution(
            id=execution_id,
            workflow_id=uuid4(),
            workflow_version_id=uuid4(),
            temporal_workflow_id=f"workflow-{execution_id}",
            status=ExecutionStatus.CANCELLED,
            created_by=uuid4(),
            input_data={},
            labels={},
            project_id=uuid4(),
        )

        retrying_activity = ActivityExecution(
            id=uuid4(),
            execution_id=execution_id,
            activity_name="retrying_activity",
            node_type="script",
            temporal_activity_id="temporal-retrying",
            status=ActivityStatus.RETRYING,
            started_at=datetime.now(UTC),
        )

        execution.activities = [retrying_activity]

        updated = service._update_non_terminal_activities_on_cancel(execution, cancelled_at)

        assert len(updated) == 1
        assert retrying_activity.status == ActivityStatus.CANCELLED
        assert retrying_activity.completed_at == cancelled_at
        assert retrying_activity.error_details == "Workflow was cancelled"

    def test_noop_when_all_terminal(self) -> None:
        """Activities already in terminal states are not modified."""
        mock_client = Mock()
        mock_session_factory = Mock()
        service = ActivitySyncService(mock_client, mock_session_factory)

        execution_id = uuid4()
        cancelled_at = datetime.now(UTC)

        execution = Execution(
            id=execution_id,
            workflow_id=uuid4(),
            workflow_version_id=uuid4(),
            temporal_workflow_id=f"workflow-{execution_id}",
            status=ExecutionStatus.CANCELLED,
            created_by=uuid4(),
            input_data={},
            labels={},
            project_id=uuid4(),
        )

        completed_activity = ActivityExecution(
            id=uuid4(),
            execution_id=execution_id,
            activity_name="completed_activity",
            node_type="script",
            temporal_activity_id="temporal-completed",
            status=ActivityStatus.COMPLETED,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )

        failed_activity = ActivityExecution(
            id=uuid4(),
            execution_id=execution_id,
            activity_name="failed_activity",
            node_type="script",
            temporal_activity_id="temporal-failed",
            status=ActivityStatus.FAILED,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )

        execution.activities = [completed_activity, failed_activity]

        updated = service._update_non_terminal_activities_on_cancel(execution, cancelled_at)

        assert len(updated) == 0
        assert completed_activity.status == ActivityStatus.COMPLETED
        assert failed_activity.status == ActivityStatus.FAILED

    def test_only_pending_activities_all_skipped(self) -> None:
        """When all non-terminal activities are PENDING, all are SKIPPED."""
        mock_client = Mock()
        mock_session_factory = Mock()
        service = ActivitySyncService(mock_client, mock_session_factory)

        execution_id = uuid4()
        cancelled_at = datetime.now(UTC)

        execution = Execution(
            id=execution_id,
            workflow_id=uuid4(),
            workflow_version_id=uuid4(),
            temporal_workflow_id=f"workflow-{execution_id}",
            status=ExecutionStatus.CANCELLED,
            created_by=uuid4(),
            input_data={},
            labels={},
            project_id=uuid4(),
        )

        pending_1 = ActivityExecution(
            id=uuid4(),
            execution_id=execution_id,
            activity_name="pending_1",
            node_type="script",
            temporal_activity_id="temporal-pending-1",
            status=ActivityStatus.PENDING,
        )

        pending_2 = ActivityExecution(
            id=uuid4(),
            execution_id=execution_id,
            activity_name="pending_2",
            node_type="script",
            temporal_activity_id="temporal-pending-2",
            status=ActivityStatus.PENDING,
        )

        execution.activities = [pending_1, pending_2]

        updated = service._update_non_terminal_activities_on_cancel(execution, cancelled_at)

        assert len(updated) == 2
        assert all(a.status == ActivityStatus.SKIPPED for a, _ in updated)


class TestFinalizeNonTerminalActivities:
    """Tests for _finalize_non_terminal_activities."""

    def test_marks_pending_activities_as_skipped(self) -> None:
        execution = Mock(spec=Execution)
        pending_activity = Mock()
        pending_activity.status = ActivityStatus.PENDING
        pending_activity.activity_name = "task-1"
        completed_activity = Mock()
        completed_activity.status = ActivityStatus.COMPLETED
        execution.activities = [pending_activity, completed_activity]

        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4())

        assert pending_activity.status == ActivityStatus.SKIPPED
        assert pending_activity.completed_at is not None
        assert completed_activity.status == ActivityStatus.COMPLETED

    def test_marks_running_activities_as_skipped(self) -> None:
        execution = Mock(spec=Execution)
        running_activity = Mock()
        running_activity.status = ActivityStatus.RUNNING
        running_activity.activity_name = "task-1"
        execution.activities = [running_activity]

        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4())

        assert running_activity.status == ActivityStatus.SKIPPED

    def test_noop_when_all_terminal(self) -> None:
        execution = Mock(spec=Execution)
        done = Mock()
        done.status = ActivityStatus.COMPLETED
        skipped = Mock()
        skipped.status = ActivityStatus.SKIPPED
        execution.activities = [done, skipped]

        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4())

        assert done.status == ActivityStatus.COMPLETED
        assert skipped.status == ActivityStatus.SKIPPED

    def test_noop_when_no_activities(self) -> None:
        execution = Mock(spec=Execution)
        execution.activities = None
        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4())

    def test_marks_failed_nodes_as_failed_not_skipped(self) -> None:
        """Running activities whose node is in failed_node_map should be FAILED."""
        execution = Mock(spec=Execution)
        loop_activity = Mock()
        loop_activity.status = ActivityStatus.RUNNING
        loop_activity.activity_name = "loop-1"
        pending_activity = Mock()
        pending_activity.status = ActivityStatus.PENDING
        pending_activity.activity_name = "task-2"
        execution.activities = [loop_activity, pending_activity]

        failed_node_map = {"loop-1": "Loop loop-1 exceeded max_iterations (3)"}
        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4(), failed_node_map)

        assert loop_activity.status == ActivityStatus.FAILED
        assert loop_activity.error_details == "Loop loop-1 exceeded max_iterations (3)"
        assert loop_activity.completed_at is not None
        assert pending_activity.status == ActivityStatus.SKIPPED

    def test_failed_node_map_matches_iteration_records(self) -> None:
        """Iteration records whose base ID is in failed_node_map should be FAILED."""
        execution = Mock(spec=Execution)
        iter_activity = Mock()
        iter_activity.status = ActivityStatus.RUNNING
        iter_activity.activity_name = "loop-1#iter-2"
        execution.activities = [iter_activity]

        failed_node_map = {"loop-1": "Loop loop-1 exceeded max_iterations (3)"}
        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4(), failed_node_map)

        assert iter_activity.status == ActivityStatus.FAILED
        assert iter_activity.error_details == "Loop loop-1 exceeded max_iterations (3)"


class TestInitializeMonitoringWorkflowLookup:
    """Test _initialize_monitoring workflow name loading logic."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.mock_temporal_client = AsyncMock()
        self.mock_session_factory = Mock()
        self.service = ActivitySyncService(self.mock_temporal_client, self.mock_session_factory)
        self.execution_id = uuid4()
        self.workflow_id = uuid4()
        self.workflow_version_id = uuid4()

    def _create_mock_execution(self) -> Execution:
        """Create a mock Execution object."""
        return Execution(
            id=self.execution_id,
            workflow_id=self.workflow_id,
            workflow_version_id=self.workflow_version_id,
            status=ExecutionStatus.PENDING,
            last_processed_event_id=0,
            project_id=uuid4(),
        )

    def _create_mock_workflow(self, name: str = "test-workflow") -> Mock:
        """Create a mock Workflow object."""
        workflow = Mock()
        workflow.id = self.workflow_id
        workflow.name = name
        return workflow

    def _create_mock_session(
        self,
        execution: Execution | None,
        workflow: Mock | None,
        activity_defs: list[dict[str, str]] | None = None,
    ) -> Mock:
        """Create a mock session that returns execution and workflow from queries."""
        # Mock execution query result
        exec_result = Mock()
        exec_result.one_or_none.return_value = execution

        # Mock workflow query result
        workflow_result = Mock()
        workflow_result.one_or_none.return_value = workflow

        # Mock workflow version query result (for activity definitions)
        wf_version_result = Mock()
        wf_version_result.one_or_none.return_value = Mock(workflow_definition={"nodes": activity_defs or []})

        # Mock activity query result (for building activity index map - empty list)
        activity_result = Mock()
        activity_result.all.return_value = []

        # Mock terminal activity IDs query result (for _load_terminal_activity_ids)
        terminal_result = Mock()
        terminal_result.all.return_value = []

        mock_session = AsyncMock()
        # Order: execution query, workflow query, workflow_version query,
        # activity creation check query, activity index map query,
        # terminal activity IDs query
        mock_session.exec = AsyncMock(
            side_effect=[
                exec_result,
                workflow_result,
                wf_version_result,
                Mock(one_or_none=Mock(return_value=None)),
                activity_result,
                terminal_result,
            ]
        )
        mock_session.commit = AsyncMock()
        mock_session.add = Mock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        self.mock_session_factory.return_value = mock_session
        return mock_session

    @pytest.mark.asyncio
    async def test_workflow_found_uses_workflow_name(self) -> None:
        """When workflow exists, metadata should include workflow.name."""
        execution = self._create_mock_execution()
        workflow = self._create_mock_workflow(name="my-workflow")
        self._create_mock_session(execution, workflow)

        metadata = await self.service._initialize_monitoring(self.execution_id)

        assert metadata.execution_id == self.execution_id
        assert metadata.workflow_id == self.workflow_id
        assert metadata.workflow_name == "my-workflow"

    @pytest.mark.asyncio
    async def test_workflow_not_found_raises_error(self) -> None:
        """When workflow does not exist, should raise RuntimeError."""
        execution = self._create_mock_execution()
        self._create_mock_session(execution, workflow=None)

        with pytest.raises(RuntimeError, match=f"Workflow {self.workflow_id} not found in database"):
            await self.service._initialize_monitoring(self.execution_id)

    @pytest.mark.asyncio
    async def test_execution_not_found_raises_error(self) -> None:
        """When execution does not exist, should raise RuntimeError."""
        self._create_mock_session(execution=None, workflow=None)

        with pytest.raises(RuntimeError, match=f"Execution {self.execution_id} not found in database"):
            await self.service._initialize_monitoring(self.execution_id)

    @pytest.mark.asyncio
    async def test_request_id_threaded_to_metadata(self) -> None:
        """Request ID should be passed through to metadata."""
        request_id = uuid4()
        execution = self._create_mock_execution()
        workflow = self._create_mock_workflow()
        self._create_mock_session(execution, workflow)

        metadata = await self.service._initialize_monitoring(self.execution_id, request_id=request_id)

        assert metadata.request_id == request_id

    @pytest.mark.asyncio
    async def test_iteration_counters_rebuilt_from_composite_keys(self) -> None:
        """When activity_index_map contains #iter-N keys, iteration_counters should be rebuilt."""
        execution = self._create_mock_execution()
        workflow = self._create_mock_workflow()
        self._create_mock_session(execution, workflow)

        index_map = {
            "script-1": 0,
            "script-1#iter-1": 1,
            "script-1#iter-2": 2,
            "script-2": 3,
            "script-2#iter-1": 4,
        }
        terminal_ids = {"script-1", "script-2"}

        with (
            patch.object(self.service, "_build_activity_index_map", new_callable=AsyncMock, return_value=index_map),
            patch.object(
                self.service, "_load_terminal_activity_ids", new_callable=AsyncMock, return_value=terminal_ids
            ),
        ):
            metadata = await self.service._initialize_monitoring(self.execution_id)

        assert metadata.iteration_counters == {"script-1": 2, "script-2": 1}
        assert metadata.terminal_activity_ids == terminal_ids
        assert metadata.next_activity_index == len(index_map)

    @pytest.mark.asyncio
    async def test_iteration_counters_empty_when_no_composite_keys(self) -> None:
        """When no #iter-N keys exist, iteration_counters should be empty."""
        execution = self._create_mock_execution()
        workflow = self._create_mock_workflow()
        self._create_mock_session(execution, workflow)

        index_map = {"script-1": 0, "script-2": 1, "condition-1": 2}

        with patch.object(self.service, "_build_activity_index_map", new_callable=AsyncMock, return_value=index_map):
            metadata = await self.service._initialize_monitoring(self.execution_id)

        assert metadata.iteration_counters == {}

    @pytest.mark.asyncio
    async def test_non_contiguous_iteration_counter_uses_max(self) -> None:
        """When only #iter-3 exists (gaps), the counter should be set to 3."""
        execution = self._create_mock_execution()
        workflow = self._create_mock_workflow()
        self._create_mock_session(execution, workflow)

        index_map = {
            "script-1": 0,
            "script-1#iter-3": 1,
        }
        terminal_ids = {"script-1"}

        with (
            patch.object(self.service, "_build_activity_index_map", new_callable=AsyncMock, return_value=index_map),
            patch.object(
                self.service, "_load_terminal_activity_ids", new_callable=AsyncMock, return_value=terminal_ids
            ),
        ):
            metadata = await self.service._initialize_monitoring(self.execution_id)

        assert metadata.iteration_counters == {"script-1": 3}


class TestUpdateApprovalPendingFlag:
    """Tests for _update_approval_pending_flag method."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = ActivitySyncService(
            temporal_client=Mock(),
            session_factory=Mock(),
        )

    def _make_execution(self, *, approval_pending: bool = False) -> Mock:
        execution = Mock(spec=Execution)
        execution.approval_pending = approval_pending
        execution.id = uuid4()
        return execution

    def _make_activity(self, node_type: str, status: ActivityStatus) -> Mock:
        activity = Mock(spec=ActivityExecution)
        activity.node_type = node_type
        activity.status = status
        return activity

    def test_sets_true_when_approval_waiting(self) -> None:
        """Flag should become True when an approval activity is WAITING."""
        execution = self._make_execution(approval_pending=False)
        activities = [
            self._make_activity(NodeType.APPROVAL, ActivityStatus.WAITING),
        ]

        result = self.service._update_approval_pending_flag(execution, activities)

        assert result is True
        assert execution.approval_pending is True

    def test_sets_false_when_approval_completed(self) -> None:
        """Flag should become False when approval activity is completed."""
        execution = self._make_execution(approval_pending=True)
        activities = [
            self._make_activity(NodeType.APPROVAL, ActivityStatus.COMPLETED),
        ]

        result = self.service._update_approval_pending_flag(execution, activities)

        assert result is False
        assert execution.approval_pending is False

    def test_no_change_returns_none(self) -> None:
        """Should return None when flag hasn't changed."""
        execution = self._make_execution(approval_pending=False)
        activities = [
            self._make_activity(NodeType.APPROVAL, ActivityStatus.COMPLETED),
        ]

        result = self.service._update_approval_pending_flag(execution, activities)

        assert result is None

    def test_wait_node_does_not_trigger_flag(self) -> None:
        """Wait nodes in WAITING status should NOT set approval_pending."""
        execution = self._make_execution(approval_pending=False)
        activities = [
            self._make_activity(NodeType.WAIT, ActivityStatus.WAITING),
        ]

        result = self.service._update_approval_pending_flag(execution, activities)

        assert result is None
        assert execution.approval_pending is False

    def test_multiple_activities_one_approval_waiting(self) -> None:
        """Flag should be True if any approval is WAITING among multiple activities."""
        execution = self._make_execution(approval_pending=False)
        activities = [
            self._make_activity(NodeType.SCRIPT, ActivityStatus.COMPLETED),
            self._make_activity(NodeType.APPROVAL, ActivityStatus.WAITING),
            self._make_activity(NodeType.WAIT, ActivityStatus.WAITING),
        ]

        result = self.service._update_approval_pending_flag(execution, activities)

        assert result is True
        assert execution.approval_pending is True

    def test_all_approvals_completed_clears_flag(self) -> None:
        """Flag should clear when all approval activities complete."""
        execution = self._make_execution(approval_pending=True)
        activities = [
            self._make_activity(NodeType.APPROVAL, ActivityStatus.COMPLETED),
            self._make_activity(NodeType.APPROVAL, ActivityStatus.COMPLETED),
        ]

        result = self.service._update_approval_pending_flag(execution, activities)

        assert result is False
        assert execution.approval_pending is False

    def test_non_approval_node_type_does_not_trigger(self) -> None:
        """Non-approval node types in WAITING status should not set flag."""
        execution = self._make_execution(approval_pending=False)
        activity = Mock(spec=ActivityExecution)
        activity.node_type = "script"
        activity.status = ActivityStatus.WAITING

        result = self.service._update_approval_pending_flag(execution, [activity])

        assert result is None
        assert execution.approval_pending is False


class TestReconcileStaleExecutions:
    """Tests for reconcile_stale_executions startup recovery."""

    def _make_service(self) -> tuple[ActivitySyncService, AsyncMock, AsyncMock]:
        """Create a service with mocked temporal client and session factory."""
        mock_client = AsyncMock()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_factory = Mock(return_value=mock_session)

        service = ActivitySyncService(
            temporal_client=mock_client,
            session_factory=mock_factory,
        )
        return service, mock_session, mock_client

    def _make_stale_execution(self, *, execution_id: UUID | None = None) -> Mock:
        """Create a mock execution in RUNNING state."""
        execution = Mock(spec=Execution)
        execution.id = execution_id or uuid4()
        execution.temporal_workflow_id = f"workflow-{execution.id}"
        execution.status = ExecutionStatus.RUNNING
        execution.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        execution.activities = []
        return execution

    @pytest.mark.asyncio
    async def test_no_stale_executions(self) -> None:
        """No-op when no RUNNING executions exist."""
        service, mock_session, _mock_client = self._make_service()
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_result)

        await service.reconcile_stale_executions()

    def _make_temporal_handle(
        self,
        status_name: str,
        *,
        events: list[Mock] | None = None,
    ) -> AsyncMock:
        """Create a mock Temporal workflow handle with describe() and fetch_history()."""
        mock_handle = AsyncMock()
        mock_description = Mock()
        mock_description.status = Mock()
        mock_description.status.name = status_name
        mock_handle.describe = AsyncMock(return_value=mock_description)
        if events is not None:
            mock_history = Mock()
            mock_history.events = events
            mock_handle.fetch_history = AsyncMock(return_value=mock_history)
        return mock_handle

    @pytest.mark.asyncio
    async def test_completed_workflow_updates_db(self) -> None:
        """Execution is updated to terminal status when Temporal workflow is done."""
        service, mock_session, mock_client = self._make_service()
        execution = self._make_stale_execution()

        mock_result_list = Mock()
        mock_result_list.all.return_value = [execution]
        mock_result_single = Mock()
        mock_result_single.one_or_none.return_value = execution
        mock_session.exec = AsyncMock(side_effect=[mock_result_list, mock_result_single])

        mock_event = Mock()
        mock_event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
        mock_event.event_time = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
        mock_event.workflow_execution_completed_event_attributes = None
        mock_client.get_workflow_handle = Mock(
            return_value=self._make_temporal_handle("COMPLETED", events=[mock_event]),
        )

        with patch.object(service, "_publish_snapshot", new_callable=AsyncMock) as mock_snapshot:
            await service.reconcile_stale_executions()
            mock_snapshot.assert_awaited_once()

        assert execution.status == ExecutionStatus.COMPLETED
        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_completed_at_before_created_at_is_adjusted(self) -> None:
        """When event_time <= created_at, completed_at is bumped to created_at + 1 microsecond."""
        from datetime import timedelta

        service, mock_session, mock_client = self._make_service()
        execution = self._make_stale_execution()
        created_at = execution.created_at

        mock_result_list = Mock()
        mock_result_list.all.return_value = [execution]
        mock_result_single = Mock()
        mock_result_single.one_or_none.return_value = execution
        mock_session.exec = AsyncMock(side_effect=[mock_result_list, mock_result_single])

        mock_event = Mock()
        mock_event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
        mock_event.event_time = datetime(2025, 12, 31, tzinfo=UTC)
        mock_event.workflow_execution_completed_event_attributes = None
        mock_client.get_workflow_handle = Mock(
            return_value=self._make_temporal_handle("COMPLETED", events=[mock_event]),
        )

        with patch.object(service, "_publish_snapshot", new_callable=AsyncMock):
            await service.reconcile_stale_executions()

        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.completed_at == created_at + timedelta(microseconds=1)

    @pytest.mark.asyncio
    async def test_failed_workflow_updates_db(self) -> None:
        """Execution is updated to FAILED when Temporal workflow failed."""
        service, mock_session, mock_client = self._make_service()
        execution = self._make_stale_execution()

        mock_result_list = Mock()
        mock_result_list.all.return_value = [execution]
        mock_result_single = Mock()
        mock_result_single.one_or_none.return_value = execution
        mock_session.exec = AsyncMock(side_effect=[mock_result_list, mock_result_single])

        mock_event = Mock()
        mock_event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED
        mock_event.event_time = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
        mock_event.workflow_execution_failed_event_attributes = Mock()
        mock_event.workflow_execution_failed_event_attributes.failure = Mock()
        mock_event.workflow_execution_failed_event_attributes.failure.message = "activity timed out"
        mock_client.get_workflow_handle = Mock(
            return_value=self._make_temporal_handle("FAILED", events=[mock_event]),
        )

        with patch.object(service, "_publish_snapshot", new_callable=AsyncMock):
            await service.reconcile_stale_executions()

        assert execution.status == ExecutionStatus.FAILED
        assert execution.error_details == "activity timed out"

    @pytest.mark.asyncio
    async def test_still_running_in_temporal_is_skipped(self) -> None:
        """Executions still running in Temporal are skipped to avoid duplicate monitoring."""
        service, mock_session, mock_client = self._make_service()
        execution = self._make_stale_execution()

        mock_result = Mock()
        mock_result.all.return_value = [execution]
        mock_session.exec = AsyncMock(return_value=mock_result)

        mock_client.get_workflow_handle = Mock(return_value=self._make_temporal_handle("RUNNING"))

        await service.reconcile_stale_executions()

        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_temporal_error_continues_to_next(self) -> None:
        """A Temporal error on one execution doesn't block reconciling others."""
        from temporalio.exceptions import TemporalError

        service, mock_session, mock_client = self._make_service()
        exec_bad = self._make_stale_execution()
        exec_good = self._make_stale_execution()

        mock_result_list = Mock()
        mock_result_list.all.return_value = [exec_bad, exec_good]
        mock_result_single = Mock()
        mock_result_single.one_or_none.return_value = exec_good
        mock_session.exec = AsyncMock(side_effect=[mock_result_list, mock_result_single])

        mock_handle_bad = AsyncMock()
        mock_handle_bad.describe = AsyncMock(side_effect=TemporalError("connection lost"))

        mock_event = Mock()
        mock_event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
        mock_event.event_time = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
        mock_event.workflow_execution_completed_event_attributes = None

        mock_client.get_workflow_handle = Mock(
            side_effect=lambda wf_id: (
                mock_handle_bad
                if wf_id == exec_bad.temporal_workflow_id
                else self._make_temporal_handle("COMPLETED", events=[mock_event])
            ),
        )

        with patch.object(service, "_publish_snapshot", new_callable=AsyncMock):
            await service.reconcile_stale_executions()

        assert exec_good.status == ExecutionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_missing_close_event_forces_failed(self) -> None:
        """Execution is forced to FAILED when Temporal says done but has no close event."""
        service, mock_session, mock_client = self._make_service()
        execution = self._make_stale_execution()

        mock_result_list = Mock()
        mock_result_list.all.return_value = [execution]
        mock_result_single = Mock()
        mock_result_single.one_or_none.return_value = execution
        mock_session.exec = AsyncMock(side_effect=[mock_result_list, mock_result_single])

        mock_client.get_workflow_handle = Mock(
            return_value=self._make_temporal_handle("COMPLETED", events=[]),
        )

        with patch.object(service, "_publish_snapshot", new_callable=AsyncMock):
            await service.reconcile_stale_executions()

        assert execution.status == ExecutionStatus.FAILED
        assert "close event could not be retrieved" in execution.error_details
        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_generic_exception_continues_to_next(self) -> None:
        """A non-Temporal exception on one execution doesn't block others."""
        service, mock_session, mock_client = self._make_service()
        exec_bad = self._make_stale_execution()
        exec_good = self._make_stale_execution()

        mock_result_list = Mock()
        mock_result_list.all.return_value = [exec_bad, exec_good]
        mock_result_single = Mock()
        mock_result_single.one_or_none.return_value = exec_good
        mock_session.exec = AsyncMock(side_effect=[mock_result_list, mock_result_single])

        mock_handle_bad = AsyncMock()
        mock_handle_bad.describe = AsyncMock(side_effect=RuntimeError("unexpected"))

        mock_event = Mock()
        mock_event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
        mock_event.event_time = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
        mock_event.workflow_execution_completed_event_attributes = None

        mock_client.get_workflow_handle = Mock(
            side_effect=lambda wf_id: (
                mock_handle_bad
                if wf_id == exec_bad.temporal_workflow_id
                else self._make_temporal_handle("COMPLETED", events=[mock_event])
            ),
        )

        with patch.object(service, "_publish_snapshot", new_callable=AsyncMock):
            await service.reconcile_stale_executions()

        assert exec_good.status == ExecutionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_db_query_failure_is_caught(self) -> None:
        """Exception during initial DB query is caught and logged."""
        service, mock_session, _mock_client = self._make_service()
        mock_session.exec = AsyncMock(side_effect=RuntimeError("db connection lost"))

        await service.reconcile_stale_executions()

    @pytest.mark.asyncio
    async def test_already_reconciled_execution_skipped(self) -> None:
        """Execution that was already updated by another worker is skipped."""
        service, mock_session, mock_client = self._make_service()
        execution = self._make_stale_execution()

        mock_result_list = Mock()
        mock_result_list.all.return_value = [execution]

        fresh_execution = self._make_stale_execution(execution_id=execution.id)
        fresh_execution.status = ExecutionStatus.FAILED
        mock_result_single = Mock()
        mock_result_single.one_or_none.return_value = fresh_execution
        mock_session.exec = AsyncMock(side_effect=[mock_result_list, mock_result_single])

        mock_event = Mock()
        mock_event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
        mock_event.event_time = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
        mock_event.workflow_execution_completed_event_attributes = None
        mock_client.get_workflow_handle = Mock(
            return_value=self._make_temporal_handle("COMPLETED", events=[mock_event]),
        )

        with patch.object(service, "_publish_snapshot", new_callable=AsyncMock) as mock_snapshot:
            await service.reconcile_stale_executions()
            mock_snapshot.assert_not_awaited()

        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deleted_execution_during_reconcile_skipped(self) -> None:
        """Execution deleted between initial query and re-fetch is skipped."""
        service, mock_session, mock_client = self._make_service()
        execution = self._make_stale_execution()

        mock_result_list = Mock()
        mock_result_list.all.return_value = [execution]
        mock_result_single = Mock()
        mock_result_single.one_or_none.return_value = None
        mock_session.exec = AsyncMock(side_effect=[mock_result_list, mock_result_single])

        mock_event = Mock()
        mock_event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
        mock_event.event_time = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
        mock_event.workflow_execution_completed_event_attributes = None
        mock_client.get_workflow_handle = Mock(
            return_value=self._make_temporal_handle("COMPLETED", events=[mock_event]),
        )

        with patch.object(service, "_publish_snapshot", new_callable=AsyncMock) as mock_snapshot:
            await service.reconcile_stale_executions()
            mock_snapshot.assert_not_awaited()

        mock_session.commit.assert_not_awaited()
