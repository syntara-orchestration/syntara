"""Tests for the sub-workflow invocation Segment event model."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from syntara.telemetry.events.sub_workflow_invocation import (
    SubWorkflowInvocationEvent,
    SubWorkflowInvocationMode,
)
from syntara.workflows.workflow_engine.models.workflow_definition import WorkflowTerminalStatus


def _event(mode: SubWorkflowInvocationMode) -> SubWorkflowInvocationEvent:
    """Create a valid event for the requested future-compatible mode."""
    return SubWorkflowInvocationEvent(
        parent_execution_id=uuid4(),
        parent_workflow_id=uuid4(),
        parent_workflow_name="Parent workflow",
        parent_node_id="run_child",
        child_execution_id=uuid4(),
        child_workflow_id=uuid4(),
        child_workflow_name="Child workflow",
        invocation_mode=mode,
        status=WorkflowTerminalStatus.COMPLETED,
        invocation_duration_ms=1500,
        child_execution_duration_ms=1200,
        installation_anon_id="anonymous-installation-id",
        occurred_at=datetime(2026, 11, 24, 10, 0, tzinfo=UTC),
        entitlement_id="entitlement-id",
    )


def test_event_serializes_as_segment_event_with_reference_mode() -> None:
    event = _event(SubWorkflowInvocationMode.REFERENCE)

    assert event.to_segment_event()["event"] == "sub_workflow_invocation"
    serialized = json.dumps(event.to_segment_event())
    assert '"invocation_mode": "reference"' in serialized
    assert '"installation_anon_id": "anonymous-installation-id"' in serialized
    assert '"parent_execution_id"' in serialized
    assert '"child_workflow_id"' in serialized


def test_event_schema_accepts_future_embed_mode() -> None:
    event = _event(SubWorkflowInvocationMode.EMBED)

    assert event.invocation_mode == SubWorkflowInvocationMode.EMBED
    schema = SubWorkflowInvocationEvent.model_json_schema()
    assert "embed" in schema["$defs"]["SubWorkflowInvocationMode"]["enum"]
    assert {
        "parent_execution_id",
        "parent_workflow_id",
        "child_execution_id",
        "child_workflow_id",
        "invocation_mode",
        "status",
        "installation_anon_id",
        "occurred_at",
    } <= set(schema["required"])
