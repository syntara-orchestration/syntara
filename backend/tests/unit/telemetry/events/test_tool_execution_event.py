"""Unit tests for ToolExecutionEvent model."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from syntara.telemetry.events.tool_execution import ToolExecutionEvent
from syntara.tool_manager.models.tool_execution import ToolExecutionStatus

VALID_WORKFLOW_EXECUTION_ID = UUID("550e8400-e29b-41d4-a716-446655440000")


class TestToolExecutionEvent:
    """Tests for ToolExecutionEvent model."""

    def test_event_construction(self):
        event = ToolExecutionEvent(
            namespaced_name="mcp::get_greeting",
            status=ToolExecutionStatus.SUCCESS,
            duration_ms=142,
            entitlement_id="ent-123",
        )
        assert event.namespaced_name == "mcp::get_greeting"
        assert event.status == ToolExecutionStatus.SUCCESS
        assert event.duration_ms == 142
        assert event.workflow_execution_id is None

    def test_event_with_workflow_execution_id(self):
        event = ToolExecutionEvent(
            namespaced_name="mcp::get_greeting",
            status=ToolExecutionStatus.SUCCESS,
            duration_ms=100,
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            entitlement_id="ent-123",
        )
        assert event.workflow_execution_id == VALID_WORKFLOW_EXECUTION_ID

    def test_to_segment_event_name(self):
        event = ToolExecutionEvent(
            namespaced_name="mcp::get_greeting",
            status=ToolExecutionStatus.SUCCESS,
            duration_ms=100,
            entitlement_id="ent-123",
        )
        segment = event.to_segment_event()
        assert segment["event"] == "tool_execution"

    def test_to_segment_event_properties(self):
        event = ToolExecutionEvent(
            namespaced_name="mcp::get_greeting",
            status=ToolExecutionStatus.SUCCESS,
            duration_ms=142,
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            entitlement_id="ent-123",
        )
        props = event.to_segment_event()["properties"]
        assert props["namespaced_name"] == "mcp::get_greeting"
        assert props["status"] == "success"
        assert props["duration_ms"] == 142
        assert props["workflow_execution_id"] == VALID_WORKFLOW_EXECUTION_ID
        assert props["entitlement_id"] == "ent-123"

    def test_workflow_execution_id_null_when_none(self):
        event = ToolExecutionEvent(
            namespaced_name="mcp::tool",
            status=ToolExecutionStatus.ERROR,
            duration_ms=50,
            entitlement_id="ent-123",
        )
        props = event.to_segment_event()["properties"]
        assert props["workflow_execution_id"] is None

    def test_duration_ms_validation_rejects_negative(self):
        with pytest.raises(ValidationError):
            ToolExecutionEvent(
                namespaced_name="mcp::tool",
                status=ToolExecutionStatus.SUCCESS,
                duration_ms=-1,
                entitlement_id="ent-123",
            )

    def test_frozen_immutability(self):
        event = ToolExecutionEvent(
            namespaced_name="mcp::tool",
            status=ToolExecutionStatus.SUCCESS,
            duration_ms=100,
            entitlement_id="ent-123",
        )
        with pytest.raises(ValidationError):
            event.namespaced_name = "changed"
