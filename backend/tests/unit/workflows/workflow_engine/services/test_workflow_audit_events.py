"""Unit tests for workflow audit event emission in ActivitySyncService.

Tests verify that WorkflowCompletedEvent and WorkflowExecutionErrorEvent are emitted
with correct resource_urn and resource_name fields populated from workflow_name,
and that trigger_type and interface fields are correctly forwarded.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from temporalio.api.enums.v1 import EventType

from syntara.workflows.audit.execution_completed import WorkflowCompletedEvent
from syntara.workflows.audit.execution_error import WorkflowExecutionErrorEvent
from syntara.workflows.audit.execution_started import WorkflowStartEvent
from syntara.workflows.models import Execution
from syntara.workflows.models.execution import ExecutionStatus
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName, WorkflowTerminalStatus
from syntara.workflows.workflow_engine.services.activity_sync_service import (
    ActivitySyncService,
    ExecutionMonitorMetadata,
)


@pytest.fixture
def mock_session_factory_for_execution() -> Callable[[Execution], Mock]:
    """Create a mock session factory that returns the given execution from queries."""

    def _create_mock_session_factory(execution: Execution) -> Mock:
        """Create a mock session factory for the given execution."""
        mock_result = Mock()
        mock_result.one_or_none.return_value = execution
        mock_session = AsyncMock()

        async def mock_exec_result(*_args: object, **_kwargs: object) -> Mock:
            return mock_result

        mock_session.exec = mock_exec_result
        mock_session.commit = AsyncMock()
        mock_session.add = Mock()  # For adding updated execution
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        return Mock(return_value=mock_session)

    return _create_mock_session_factory


class TestWorkflowStartEventEmission:
    """Test WorkflowStartEvent emission with trigger_type and interface fields."""

    @pytest.fixture
    def mock_start_event(self) -> AsyncMock:
        """Create a mock Temporal workflow started event."""
        event = AsyncMock()
        event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED
        event.event_id = 1
        attrs = AsyncMock()
        attrs.workflow_run_timeout = None
        event.workflow_execution_started_event_attributes = attrs
        return event

    @pytest.mark.asyncio
    async def test_start_event_forwards_interface_from_execution(
        self,
        mock_session_factory_for_execution: Callable[[Execution], Mock],
        mock_start_event: AsyncMock,
    ) -> None:
        """WorkflowStartEvent should include execution.interface when dispatched."""
        workflow_id = uuid4()
        execution_id = uuid4()
        execution = Execution(
            id=execution_id,
            workflow_id=workflow_id,
            status=ExecutionStatus.PENDING,
            created_at=datetime(2025, 1, 20, 10, 0, 0, tzinfo=UTC),
            project_id=uuid4(),
            interface="api",
        )

        metadata = ExecutionMonitorMetadata(
            execution_id=execution_id,
            last_processed_event_id=0,
            activity_definitions_map={"trigger_1": {"type": "manual_trigger"}},
            activity_index_map={},
            pending_activity_updates={},
            workflow_id=workflow_id,
            workflow_name="test-workflow",
        )

        mock_session_factory = mock_session_factory_for_execution(execution)
        service = ActivitySyncService(AsyncMock(), mock_session_factory)

        with patch(
            "syntara.workflows.workflow_engine.services.activity_sync_service.AuditEventDispatcher"
        ) as mock_dispatcher:
            await service._update_execution_to_running(metadata, mock_start_event)

            assert mock_dispatcher.dispatch.call_count == 1
            emitted_event: WorkflowStartEvent = mock_dispatcher.dispatch.call_args[0][0]
            assert isinstance(emitted_event, WorkflowStartEvent)
            assert emitted_event.interface == "api"
            assert emitted_event.trigger_type == ActivityName.MANUAL_TRIGGER

    @pytest.mark.asyncio
    async def test_start_event_interface_none_when_not_set(
        self,
        mock_session_factory_for_execution: Callable[[Execution], Mock],
        mock_start_event: AsyncMock,
    ) -> None:
        """WorkflowStartEvent should have interface=None when execution has no interface."""
        workflow_id = uuid4()
        execution_id = uuid4()
        execution = Execution(
            id=execution_id,
            workflow_id=workflow_id,
            status=ExecutionStatus.PENDING,
            created_at=datetime(2025, 1, 20, 10, 0, 0, tzinfo=UTC),
            project_id=uuid4(),
            interface=None,
        )

        metadata = ExecutionMonitorMetadata(
            execution_id=execution_id,
            last_processed_event_id=0,
            activity_definitions_map={},
            activity_index_map={},
            pending_activity_updates={},
            workflow_id=workflow_id,
            workflow_name="test-workflow",
        )

        mock_session_factory = mock_session_factory_for_execution(execution)
        service = ActivitySyncService(AsyncMock(), mock_session_factory)

        with patch(
            "syntara.workflows.workflow_engine.services.activity_sync_service.AuditEventDispatcher"
        ) as mock_dispatcher:
            await service._update_execution_to_running(metadata, mock_start_event)

            emitted_event: WorkflowStartEvent = mock_dispatcher.dispatch.call_args[0][0]
            assert isinstance(emitted_event, WorkflowStartEvent)
            assert emitted_event.interface is None
            assert emitted_event.trigger_type is None


class TestWorkflowCompletedEventEmission:
    """Test WorkflowCompletedEvent emission with resource fields."""

    @pytest.mark.asyncio
    async def test_workflow_completed_event_emitted_with_workflow_name(
        self,
        mock_session_factory_for_execution: Callable[[Execution], Mock],
    ) -> None:
        """WorkflowCompletedEvent should be emitted with workflow_name from metadata."""
        workflow_id = uuid4()
        workflow_name = "test-workflow-name"
        execution_id = uuid4()
        execution = Execution(
            id=execution_id,
            workflow_id=workflow_id,
            status=ExecutionStatus.RUNNING,
            created_at=datetime(2025, 1, 20, 10, 0, 0, tzinfo=UTC),
            project_id=uuid4(),
        )

        # Create metadata with workflow_name
        metadata = ExecutionMonitorMetadata(
            execution_id=execution_id,
            last_processed_event_id=0,
            activity_definitions_map={},
            activity_index_map={},
            pending_activity_updates={},
            workflow_id=workflow_id,
            workflow_name=workflow_name,
        )

        # Create WORKFLOW_EXECUTION_COMPLETED event
        event = AsyncMock()
        event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
        event.event_id = 100
        event.event_time = datetime(2025, 1, 20, 12, 30, 0, tzinfo=UTC)
        attrs = AsyncMock()
        attrs.result = AsyncMock(payloads=[])
        event.workflow_execution_completed_event_attributes = attrs

        # Create session factory that returns the execution
        mock_session_factory = mock_session_factory_for_execution(execution)
        service = ActivitySyncService(AsyncMock(), mock_session_factory)

        with patch(
            "syntara.workflows.workflow_engine.services.activity_sync_service.AuditEventDispatcher"
        ) as mock_dispatcher:
            await service._update_execution_status_from_event(metadata, event)

            # Verify WorkflowCompletedEvent was dispatched
            assert mock_dispatcher.dispatch.call_count == 1
            emitted_event: WorkflowCompletedEvent = mock_dispatcher.dispatch.call_args[0][0]

            # Verify it's the correct event type
            assert isinstance(emitted_event, WorkflowCompletedEvent)

            # Verify resource fields
            assert emitted_event.execution_id == execution_id
            assert emitted_event.workflow_id == workflow_id
            assert emitted_event.workflow_name == workflow_name
            assert emitted_event.status == WorkflowTerminalStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_workflow_completed_event_without_workflow_name(
        self,
        mock_session_factory_for_execution: Callable[[Execution], Mock],
    ) -> None:
        """WorkflowCompletedEvent should handle None workflow_name when workflow was deleted."""
        workflow_id = uuid4()
        execution_id = uuid4()
        execution = Execution(
            id=execution_id,
            workflow_id=workflow_id,
            status=ExecutionStatus.RUNNING,
            created_at=datetime(2025, 1, 20, 10, 0, 0, tzinfo=UTC),
            project_id=uuid4(),
        )

        # Create metadata with None workflow_name (workflow was deleted)
        metadata = ExecutionMonitorMetadata(
            execution_id=execution_id,
            last_processed_event_id=0,
            activity_definitions_map={},
            activity_index_map={},
            pending_activity_updates={},
            workflow_id=workflow_id,
            workflow_name=None,
        )

        event = AsyncMock()
        event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
        event.event_id = 100
        event.event_time = datetime(2025, 1, 20, 12, 30, 0, tzinfo=UTC)
        attrs = AsyncMock()
        attrs.result = AsyncMock(payloads=[])
        event.workflow_execution_completed_event_attributes = attrs

        mock_session_factory = mock_session_factory_for_execution(execution)
        service = ActivitySyncService(AsyncMock(), mock_session_factory)

        with patch(
            "syntara.workflows.workflow_engine.services.activity_sync_service.AuditEventDispatcher"
        ) as mock_dispatcher:
            await service._update_execution_status_from_event(metadata, event)

            emitted_event: WorkflowCompletedEvent = mock_dispatcher.dispatch.call_args[0][0]
            assert isinstance(emitted_event, WorkflowCompletedEvent)
            assert emitted_event.workflow_name is None

    @pytest.mark.asyncio
    async def test_workflow_completed_event_with_fallback_name(
        self,
        mock_session_factory_for_execution: Callable[[Execution], Mock],
    ) -> None:
        """WorkflowCompletedEvent should include fallback workflow_name pattern for deleted workflows."""
        workflow_id = uuid4()
        execution_id = uuid4()
        execution = Execution(
            id=execution_id,
            workflow_id=workflow_id,
            status=ExecutionStatus.RUNNING,
            created_at=datetime(2025, 1, 20, 10, 0, 0, tzinfo=UTC),
            project_id=uuid4(),
        )

        fallback_name = f"<workflow-{workflow_id}>"
        metadata = ExecutionMonitorMetadata(
            execution_id=execution_id,
            last_processed_event_id=0,
            activity_definitions_map={},
            activity_index_map={},
            pending_activity_updates={},
            workflow_id=workflow_id,
            workflow_name=fallback_name,
        )

        event = AsyncMock()
        event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
        event.event_id = 100
        event.event_time = datetime(2025, 1, 20, 12, 30, 0, tzinfo=UTC)
        attrs = AsyncMock()
        attrs.result = AsyncMock(payloads=[])
        event.workflow_execution_completed_event_attributes = attrs

        mock_session_factory = mock_session_factory_for_execution(execution)
        service = ActivitySyncService(AsyncMock(), mock_session_factory)

        with patch(
            "syntara.workflows.workflow_engine.services.activity_sync_service.AuditEventDispatcher"
        ) as mock_dispatcher:
            await service._update_execution_status_from_event(metadata, event)

            emitted_event: WorkflowCompletedEvent = mock_dispatcher.dispatch.call_args[0][0]
            assert isinstance(emitted_event, WorkflowCompletedEvent)
            assert emitted_event.workflow_name == fallback_name

    @pytest.mark.asyncio
    async def test_completed_event_converts_trigger_type_string_to_enum(
        self,
        mock_session_factory_for_execution: Callable[[Execution], Mock],
    ) -> None:
        """WorkflowCompletedEvent should convert execution.trigger_type string to ActivityName enum."""
        workflow_id = uuid4()
        execution_id = uuid4()
        execution = Execution(
            id=execution_id,
            workflow_id=workflow_id,
            status=ExecutionStatus.RUNNING,
            created_at=datetime(2025, 1, 20, 10, 0, 0, tzinfo=UTC),
            project_id=uuid4(),
            trigger_type="manual_trigger",
            interface="ui",
        )

        metadata = ExecutionMonitorMetadata(
            execution_id=execution_id,
            last_processed_event_id=0,
            activity_definitions_map={},
            activity_index_map={},
            pending_activity_updates={},
            workflow_id=workflow_id,
            workflow_name="test-workflow",
        )

        event = AsyncMock()
        event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
        event.event_id = 100
        event.event_time = datetime(2025, 1, 20, 12, 30, 0, tzinfo=UTC)
        attrs = AsyncMock()
        attrs.result = AsyncMock(payloads=[])
        event.workflow_execution_completed_event_attributes = attrs

        mock_session_factory = mock_session_factory_for_execution(execution)
        service = ActivitySyncService(AsyncMock(), mock_session_factory)

        with patch(
            "syntara.workflows.workflow_engine.services.activity_sync_service.AuditEventDispatcher"
        ) as mock_dispatcher:
            await service._update_execution_status_from_event(metadata, event)

            emitted_event: WorkflowCompletedEvent = mock_dispatcher.dispatch.call_args[0][0]
            assert isinstance(emitted_event, WorkflowCompletedEvent)
            assert emitted_event.trigger_type == ActivityName.MANUAL_TRIGGER
            assert emitted_event.interface == "ui"

    @pytest.mark.asyncio
    async def test_completed_event_unrecognized_trigger_type_yields_none(
        self,
        mock_session_factory_for_execution: Callable[[Execution], Mock],
    ) -> None:
        """Unrecognized trigger_type string should yield trigger_type=None in the completed event."""
        workflow_id = uuid4()
        execution_id = uuid4()
        execution = Execution(
            id=execution_id,
            workflow_id=workflow_id,
            status=ExecutionStatus.RUNNING,
            created_at=datetime(2025, 1, 20, 10, 0, 0, tzinfo=UTC),
            project_id=uuid4(),
            trigger_type="nonexistent_trigger",
            interface="api",
        )

        metadata = ExecutionMonitorMetadata(
            execution_id=execution_id,
            last_processed_event_id=0,
            activity_definitions_map={},
            activity_index_map={},
            pending_activity_updates={},
            workflow_id=workflow_id,
            workflow_name="test-workflow",
        )

        event = AsyncMock()
        event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
        event.event_id = 100
        event.event_time = datetime(2025, 1, 20, 12, 30, 0, tzinfo=UTC)
        attrs = AsyncMock()
        attrs.result = AsyncMock(payloads=[])
        event.workflow_execution_completed_event_attributes = attrs

        mock_session_factory = mock_session_factory_for_execution(execution)
        service = ActivitySyncService(AsyncMock(), mock_session_factory)

        with patch(
            "syntara.workflows.workflow_engine.services.activity_sync_service.AuditEventDispatcher"
        ) as mock_dispatcher:
            await service._update_execution_status_from_event(metadata, event)

            emitted_event: WorkflowCompletedEvent = mock_dispatcher.dispatch.call_args[0][0]
            assert isinstance(emitted_event, WorkflowCompletedEvent)
            assert emitted_event.trigger_type is None
            # interface should still be forwarded even with unrecognized trigger_type
            assert emitted_event.interface == "api"

    @pytest.mark.asyncio
    async def test_completed_event_forwards_interface_from_execution(
        self,
        mock_session_factory_for_execution: Callable[[Execution], Mock],
    ) -> None:
        """WorkflowCompletedEvent should forward execution.interface."""
        workflow_id = uuid4()
        execution_id = uuid4()
        execution = Execution(
            id=execution_id,
            workflow_id=workflow_id,
            status=ExecutionStatus.RUNNING,
            created_at=datetime(2025, 1, 20, 10, 0, 0, tzinfo=UTC),
            project_id=uuid4(),
            trigger_type=None,
            interface="api",
        )

        metadata = ExecutionMonitorMetadata(
            execution_id=execution_id,
            last_processed_event_id=0,
            activity_definitions_map={},
            activity_index_map={},
            pending_activity_updates={},
            workflow_id=workflow_id,
            workflow_name="test-workflow",
        )

        event = AsyncMock()
        event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
        event.event_id = 100
        event.event_time = datetime(2025, 1, 20, 12, 30, 0, tzinfo=UTC)
        attrs = AsyncMock()
        attrs.result = AsyncMock(payloads=[])
        event.workflow_execution_completed_event_attributes = attrs

        mock_session_factory = mock_session_factory_for_execution(execution)
        service = ActivitySyncService(AsyncMock(), mock_session_factory)

        with patch(
            "syntara.workflows.workflow_engine.services.activity_sync_service.AuditEventDispatcher"
        ) as mock_dispatcher:
            await service._update_execution_status_from_event(metadata, event)

            emitted_event: WorkflowCompletedEvent = mock_dispatcher.dispatch.call_args[0][0]
            assert isinstance(emitted_event, WorkflowCompletedEvent)
            assert emitted_event.interface == "api"
            assert emitted_event.trigger_type is None


class TestWorkflowExecutionErrorEventEmission:
    """Test WorkflowExecutionErrorEvent emission with resource fields."""

    @pytest.mark.asyncio
    async def test_workflow_timeout_error_event_with_workflow_name(
        self,
        mock_session_factory_for_execution: Callable[[Execution], Mock],
    ) -> None:
        """WorkflowExecutionErrorEvent should be emitted for workflow timeout with workflow_name."""
        workflow_id = uuid4()
        workflow_name = "test-workflow-name"
        execution_id = uuid4()
        execution = Execution(
            id=execution_id,
            workflow_id=workflow_id,
            status=ExecutionStatus.RUNNING,
            created_at=datetime(2025, 1, 20, 10, 0, 0, tzinfo=UTC),
            project_id=uuid4(),
        )

        metadata = ExecutionMonitorMetadata(
            execution_id=execution_id,
            last_processed_event_id=0,
            activity_definitions_map={},
            activity_index_map={},
            pending_activity_updates={},
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            workflow_run_timeout_seconds=3600.0,
        )

        # Create WORKFLOW_EXECUTION_TIMED_OUT event
        event = AsyncMock()
        event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_TIMED_OUT
        event.event_id = 100
        event.event_time = datetime(2025, 1, 20, 11, 0, 0, tzinfo=UTC)
        attrs = AsyncMock()
        attrs.failure = AsyncMock(message="Workflow timeout")
        event.workflow_execution_timed_out_event_attributes = attrs

        mock_session_factory = mock_session_factory_for_execution(execution)
        service = ActivitySyncService(AsyncMock(), mock_session_factory)

        with patch(
            "syntara.workflows.workflow_engine.services.activity_sync_service.AuditEventDispatcher"
        ) as mock_dispatcher:
            await service._update_execution_status_from_event(metadata, event)

            # Should emit 2 events: WorkflowCompletedEvent + WorkflowExecutionErrorEvent
            assert mock_dispatcher.dispatch.call_count == 2

            # Find the WorkflowExecutionErrorEvent (second call)
            error_event: WorkflowExecutionErrorEvent = mock_dispatcher.dispatch.call_args_list[1][0][0]
            assert isinstance(error_event, WorkflowExecutionErrorEvent)

            # Verify resource fields
            assert error_event.execution_id == execution_id
            assert error_event.workflow_id == workflow_id
            assert error_event.workflow_name == workflow_name
            assert error_event.timed_out_component.value == "workflow"
            assert error_event.configured_timeout_seconds == 3600.0
            assert error_event.error_type == "WorkflowTimedOut"

    @pytest.mark.asyncio
    async def test_workflow_timeout_error_event_without_workflow_name(
        self,
        mock_session_factory_for_execution: Callable[[Execution], Mock],
    ) -> None:
        """WorkflowExecutionErrorEvent should handle None workflow_name."""
        workflow_id = uuid4()
        execution_id = uuid4()
        execution = Execution(
            id=execution_id,
            workflow_id=workflow_id,
            status=ExecutionStatus.RUNNING,
            created_at=datetime(2025, 1, 20, 10, 0, 0, tzinfo=UTC),
            project_id=uuid4(),
        )

        metadata = ExecutionMonitorMetadata(
            execution_id=execution_id,
            last_processed_event_id=0,
            activity_definitions_map={},
            activity_index_map={},
            pending_activity_updates={},
            workflow_id=workflow_id,
            workflow_name=None,  # Workflow was deleted
            workflow_run_timeout_seconds=1800.0,
        )

        event = AsyncMock()
        event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_TIMED_OUT
        event.event_id = 100
        event.event_time = datetime(2025, 1, 20, 10, 30, 0, tzinfo=UTC)
        attrs = AsyncMock()
        attrs.failure = AsyncMock(message="Workflow timeout")
        event.workflow_execution_timed_out_event_attributes = attrs

        mock_session_factory = mock_session_factory_for_execution(execution)
        service = ActivitySyncService(AsyncMock(), mock_session_factory)

        with patch(
            "syntara.workflows.workflow_engine.services.activity_sync_service.AuditEventDispatcher"
        ) as mock_dispatcher:
            await service._update_execution_status_from_event(metadata, event)

            error_event: WorkflowExecutionErrorEvent = mock_dispatcher.dispatch.call_args_list[1][0][0]
            assert isinstance(error_event, WorkflowExecutionErrorEvent)
            assert error_event.workflow_name is None
