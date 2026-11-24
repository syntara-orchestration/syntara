"""Integration tests for end-to-end workflow telemetry capture.

Validates that the telemetry client registry and handlers
work together to capture and emit workflow and activity telemetry events.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest
from temporalio.api.enums.v1 import EventType
from temporalio.api.history.v1 import HistoryEvent

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.telemetry.client import TelemetryClientRegistry
from syntara.telemetry.events.workflow_execution import (
    WorkflowExecutionCompletedEvent,
    WorkflowExecutionStartEvent,
)
from syntara.telemetry.handlers.node_execution import NodeExecutedTelemetryHandler
from syntara.telemetry.handlers.sub_workflow_invocation import SubWorkflowInvocationTelemetryHandler
from syntara.telemetry.handlers.workflow_completed import WorkflowCompletedTelemetryHandler
from syntara.workflows.audit.execution_completed import WorkflowCompletedEvent
from syntara.workflows.audit.node_execution import NodeExecutedEvent
from syntara.workflows.audit.sub_workflow_invocation import SubWorkflowInvocationCompletedEvent
from syntara.workflows.models.execution import ExecutionMode, ExecutionStatus
from syntara.workflows.workflow_engine.models.workflow_definition import (
    ActivityTerminalStatus,
    NodeType,
    WorkflowTerminalStatus,
)
from syntara.workflows.workflow_engine.services.activity_sync_service import ActivitySyncService
from syntara.workflows.workflow_engine.services.activity_sync_types import ExecutionMonitorMetadata

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from tests.integration.helpers.execution import ExecutionFactory
    from tests.integration.helpers.workflow import WorkflowFactory


class TestEndToEndWorkflowTelemetry:
    """Integration test: full telemetry lifecycle from event capture to Segment send."""

    def test_workflow_start_and_complete_events_sent(self) -> None:
        """Verify that a workflow start and completion event are both sent to Segment."""
        registry = TelemetryClientRegistry()
        mock_client = MagicMock()
        registry._client = mock_client
        registry._entitlement_id = "test-install-001"
        registry._anonymous_id = "anon-test-id"

        execution_id = str(uuid4())

        registry.send_event(
            WorkflowExecutionStartEvent(
                workflow_execution_id=execution_id,
                entitlement_id=registry.entitlement_id,
            )
        )

        registry.send_event(
            WorkflowExecutionCompletedEvent(
                workflow_execution_id=execution_id,
                status=WorkflowTerminalStatus.COMPLETED,
                duration_ms=1500,
                node_count=3,
                error_count=0,
                entitlement_id=registry.entitlement_id,
            )
        )

        # Verify two track calls were made (start + completed)
        assert mock_client.track.call_count == 2

        # Verify start event
        start_call = mock_client.track.call_args_list[0]
        assert start_call.kwargs["event"] == "workflow_execution_start"
        assert "user_id" not in start_call.kwargs
        assert start_call.kwargs["anonymous_id"] == "anon-test-id"
        assert start_call.kwargs["properties"]["workflow_execution_id"] == execution_id
        assert start_call.kwargs["properties"]["entitlement_id"] == "test-install-001"

        # Verify completed event
        complete_call = mock_client.track.call_args_list[1]
        assert complete_call.kwargs["event"] == "workflow_execution_completed"
        assert complete_call.kwargs["properties"]["status"] == "completed"
        assert complete_call.kwargs["properties"]["duration_ms"] == 1500
        assert complete_call.kwargs["properties"]["node_count"] == 3
        assert complete_call.kwargs["properties"]["error_count"] == 0

    def test_workflow_metrics_properties_reach_segment(self) -> None:
        """AAP-92215: workflow_id, mode, workflow_version, used_published, is_retry are emitted."""
        registry = TelemetryClientRegistry()
        mock_client = MagicMock()
        registry._client = mock_client
        registry._entitlement_id = "test-install-001"
        registry._anonymous_id = "anon-test-id"

        execution_id = uuid4()
        workflow_id = uuid4()
        registry.send_event(
            WorkflowExecutionCompletedEvent(
                workflow_execution_id=execution_id,
                workflow_id=workflow_id,
                status=WorkflowTerminalStatus.FAILED,
                duration_ms=200,
                node_count=2,
                error_count=1,
                error_type="WorkflowTimedOut",
                mode=ExecutionMode.STANDARD,
                workflow_version=3,
                used_published=True,
                is_retry=True,
                entitlement_id=registry.entitlement_id,
            )
        )

        props = mock_client.track.call_args.kwargs["properties"]
        assert props["workflow_id"] == str(workflow_id)
        assert props["mode"] == "standard"
        assert props["workflow_version"] == 3
        assert props["used_published"] is True
        assert props["is_retry"] is True
        assert props["error_type"] == "WorkflowTimedOut"

    @patch("syntara.telemetry.handlers.node_execution.get_telemetry_registry")
    def test_node_event_sent_via_audit_handler(self, mock_get_registry: MagicMock) -> None:
        """Verify that NodeExecutedTelemetryHandler emits node_execution to Segment."""
        registry = TelemetryClientRegistry()
        mock_client = MagicMock()
        registry._client = mock_client
        registry._entitlement_id = "test-install-001"
        registry._anonymous_id = "anon-test-id"
        mock_get_registry.return_value = registry

        execution_id = uuid4()
        node_def: dict[str, object] = {"id": "http-1", "type": "http_request"}

        handler = NodeExecutedTelemetryHandler()
        handler.handle(
            NodeExecutedEvent(
                execution_id=execution_id,
                node_type=NodeType.HTTP_REQUEST,
                node_def=node_def,
                status=ActivityTerminalStatus.COMPLETED,
            )
        )

        assert mock_client.track.call_count == 1
        call = mock_client.track.call_args
        assert call.kwargs["event"] == "node_execution"
        assert call.kwargs["properties"]["workflow_execution_id"] == str(execution_id)
        assert call.kwargs["properties"]["node_type"] == "http_request"
        assert call.kwargs["properties"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_child_completion_sync_emits_one_subworkflow_event(
        self,
        test_db_session: AsyncSession,
        mock_session_factory: async_sessionmaker[AsyncSession],
        workflow_factory: WorkflowFactory,
        execution_factory: ExecutionFactory,
    ) -> None:
        """Exercise child completion sync → parent context lookup → Segment."""
        registry = TelemetryClientRegistry()
        mock_client = MagicMock()
        registry._client = mock_client
        registry._entitlement_id = "test-install-001"
        registry._anonymous_id = "anon-installation-id"

        parent_workflow, parent_version = await workflow_factory.create("Parent workflow")
        child_workflow, child_version = await workflow_factory.create("Child workflow")
        parent_execution = await execution_factory.create(
            parent_workflow,
            parent_version,
            status=ExecutionStatus.RUNNING,
        )
        child_execution = await execution_factory.create(
            child_workflow,
            child_version,
            status=ExecutionStatus.RUNNING,
            trigger_type="subworkflow_trigger",
        )
        completed_at = datetime.now(UTC)
        invocation_started_at = completed_at - timedelta(seconds=8)
        workflow_started_at = completed_at - timedelta(seconds=6)
        child_execution.created_at = completed_at - timedelta(seconds=9)
        child_execution.execution_metadata = {
            "parent_execution_id": str(parent_execution.id),
            "parent_node_id": "run_child",
            "workflow_name": child_workflow.name,
            "subworkflow_invocation_started_at": invocation_started_at.isoformat(),
            "workflow_started_at": workflow_started_at.isoformat(),
        }
        await test_db_session.commit()

        history_event = HistoryEvent(
            event_id=300,
            event_type=EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED,
        )
        history_event.event_time.FromDatetime(completed_at)
        metadata = ExecutionMonitorMetadata(
            execution_id=child_execution.id,
            last_processed_event_id=0,
            activity_definitions_map={},
            activity_index_map={},
            pending_activity_updates={},
            workflow_id=child_workflow.id,
            workflow_name=child_workflow.name,
        )
        service = ActivitySyncService(Mock(), mock_session_factory)

        with (
            patch(
                "syntara.workflows.workflow_engine.services.activity_execution_state.get_telemetry_registry",
                return_value=registry,
            ),
            patch("syntara.telemetry.handlers.workflow_completed.get_telemetry_registry", return_value=registry),
            patch("syntara.telemetry.handlers.sub_workflow_invocation.get_telemetry_registry", return_value=registry),
            patch.object(service, "_publish_snapshot", new_callable=AsyncMock),
        ):
            AuditEventDispatcher._reset()
            AuditEventDispatcher.register(
                {
                    WorkflowCompletedEvent: WorkflowCompletedTelemetryHandler(),
                    SubWorkflowInvocationCompletedEvent: SubWorkflowInvocationTelemetryHandler(),
                }
            )
            try:
                await service._update_execution_status_from_event(metadata, history_event)
                # The completion handler is idempotent after the child is terminal.
                await service._update_execution_status_from_event(metadata, history_event)
            finally:
                AuditEventDispatcher._reset()

        invocation_calls = [
            call for call in mock_client.track.call_args_list if call.kwargs["event"] == "sub_workflow_invocation"
        ]
        assert len(invocation_calls) == 1
        invocation_call = invocation_calls[0]
        properties = invocation_call.kwargs["properties"]
        assert invocation_call.kwargs["anonymous_id"] == "anon-installation-id"
        assert properties["installation_anon_id"] == "anon-installation-id"
        assert properties["invocation_mode"] == "reference"
        assert properties["parent_execution_id"] == str(parent_execution.id)
        assert properties["parent_workflow_id"] == str(parent_workflow.id)
        assert properties["parent_workflow_name"] == "Parent workflow"
        assert properties["child_execution_id"] == str(child_execution.id)
        assert properties["child_workflow_id"] == str(child_workflow.id)
        assert properties["child_workflow_name"] == "Child workflow"
        assert properties["invocation_duration_ms"] == 8000
        assert properties["child_execution_duration_ms"] == 6000
        assert "input" not in properties
        assert "outputs" not in properties


class TestEntitlementIdPropagation:
    """Integration test: entitlement_id flows from registry to Segment event properties."""

    def test_entitlement_id_in_event_properties(self) -> None:
        """Verify entitlement_id set on registry is included in event properties."""
        registry = TelemetryClientRegistry()
        mock_client = MagicMock()
        registry._client = mock_client
        registry._entitlement_id = "prod-install-xyz"
        registry._anonymous_id = "anon-test-id"

        assert registry.entitlement_id == "prod-install-xyz"

        registry.send_event(
            WorkflowExecutionStartEvent(
                workflow_execution_id=uuid4(),
                entitlement_id=registry.entitlement_id,
            )
        )

        call = mock_client.track.call_args
        assert "user_id" not in call.kwargs
        assert call.kwargs["anonymous_id"] == "anon-test-id"
        assert call.kwargs["properties"]["entitlement_id"] == "prod-install-xyz"
