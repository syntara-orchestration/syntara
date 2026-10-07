"""Unit tests for NodeStalledEvent audit handler."""

from datetime import UTC, datetime
from uuid import uuid4

from syntara.audit.handler import AuditEventHandler
from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.audit.models.structured_data import AuditContextData
from syntara.workflows.audit.node_stalled import NodeStalledEvent, NodeStalledHandler
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType

ACTIVITY_EXECUTION_ID = uuid4()
EXECUTION_ID = uuid4()
STARTED_AT = datetime(2026, 10, 2, 10, 0, 0, tzinfo=UTC)
STALL_ALERT_AT = datetime(2026, 10, 2, 10, 5, 0, tzinfo=UTC)


class TestNodeStalledHandler:
    """Tests for NodeStalledHandler."""

    def test_is_audit_event_handler_subclass(self) -> None:
        assert issubclass(NodeStalledHandler, AuditEventHandler)

    def test_produces_audit_event_with_resource_fields(self) -> None:
        event = NodeStalledEvent(
            activity_execution_id=ACTIVITY_EXECUTION_ID,
            execution_id=EXECUTION_ID,
            activity_name="api_call",
            node_type=NodeType.HTTP_REQUEST,
            expected_duration=60,
            started_at=STARTED_AT,
            stall_alert_at=STALL_ALERT_AT,
        )
        result = NodeStalledHandler().handle(event)

        assert result.event_category == EventCategory.WORKFLOW_EVENT
        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "activity_stalled"
        assert result.event_message == "Activity 'api_call' stalled (exceeded expected duration of 60s)"
        assert result.source_component == "syntara.workflows.workers.stall_detection"
        assert result.execution_id == EXECUTION_ID
        assert result.resource_urn == f"urn:syntara:activity:{ACTIVITY_EXECUTION_ID}"
        assert result.resource_name == "api_call"

    def test_structured_data_contains_expected_fields(self) -> None:
        event = NodeStalledEvent(
            activity_execution_id=ACTIVITY_EXECUTION_ID,
            execution_id=EXECUTION_ID,
            activity_name="api_call",
            node_type=NodeType.HTTP_REQUEST,
            expected_duration=120,
            started_at=STARTED_AT,
            stall_alert_at=STALL_ALERT_AT,
        )
        result = NodeStalledHandler().handle(event)

        assert isinstance(result.structured_data, AuditContextData)
        data = result.structured_data.model_dump()
        assert data["data_type"] == "activity-stalled"
        assert data["activity_name"] == "api_call"
        assert data["node_type"] == NodeType.HTTP_REQUEST.value
        assert data["expected_duration"] == 120
        assert data["started_at"] == STARTED_AT.isoformat()
        assert data["stall_alert_at"] == STALL_ALERT_AT.isoformat()

    def test_different_node_types(self) -> None:
        """Handler should work with any NodeType."""
        for node_type in [NodeType.APPROVAL, NodeType.AGENTIC, NodeType.CONDITION, NodeType.LOOP]:
            event = NodeStalledEvent(
                activity_execution_id=ACTIVITY_EXECUTION_ID,
                execution_id=EXECUTION_ID,
                activity_name=f"test_{node_type.value}",
                node_type=node_type,
                expected_duration=30,
                started_at=STARTED_AT,
                stall_alert_at=STALL_ALERT_AT,
            )
            result = NodeStalledHandler().handle(event)

            data = result.structured_data.model_dump()
            assert data["node_type"] == node_type.value
            assert result.resource_name == f"test_{node_type.value}"

    def test_expected_duration_in_message(self) -> None:
        """Event message should include the expected duration."""
        event = NodeStalledEvent(
            activity_execution_id=ACTIVITY_EXECUTION_ID,
            execution_id=EXECUTION_ID,
            activity_name="slow_task",
            node_type=NodeType.WEBHOOK_TRIGGER,
            expected_duration=300,
            started_at=STARTED_AT,
            stall_alert_at=STALL_ALERT_AT,
        )
        result = NodeStalledHandler().handle(event)

        assert "300s" in result.event_message
        assert "slow_task" in result.event_message
