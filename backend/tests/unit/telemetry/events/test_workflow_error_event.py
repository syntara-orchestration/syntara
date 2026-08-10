"""Unit tests for WorkflowErrorEvent model."""

import pytest
from pydantic import ValidationError

from syntara.telemetry.events.workflow_error import WorkflowErrorEvent
from tests.unit.telemetry.conftest import VALID_WORKFLOW_EXECUTION_ID


class TestWorkflowErrorEvent:
    """Tests for WorkflowErrorEvent model."""

    def test_activity_timeout_event(self):
        event = WorkflowErrorEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            timed_out_component="activity",
            configured_timeout_seconds=30.0,
            elapsed_time_ms=30500,
            activity_id="script-1",
            entitlement_id="ent-123",
        )
        assert event.timed_out_component == "activity"
        assert event.configured_timeout_seconds == 30.0
        assert event.elapsed_time_ms == 30500
        assert event.activity_id == "script-1"
        assert event.retry_count == 0

    def test_workflow_timeout_event(self):
        event = WorkflowErrorEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            timed_out_component="workflow",
            configured_timeout_seconds=3600.0,
            elapsed_time_ms=3600000,
            entitlement_id="ent-123",
        )
        assert event.timed_out_component == "workflow"
        assert event.activity_id is None

    def test_to_segment_event_name(self):
        event = WorkflowErrorEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            timed_out_component="activity",
            configured_timeout_seconds=30.0,
            elapsed_time_ms=30500,
            entitlement_id="ent-123",
        )
        segment = event.to_segment_event()
        assert segment["event"] == "workflow_error"

    def test_to_segment_event_properties(self):
        event = WorkflowErrorEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            timed_out_component="activity",
            configured_timeout_seconds=30.0,
            elapsed_time_ms=30500,
            activity_id="http-request-1",
            entitlement_id="ent-456",
        )
        props = event.to_segment_event()["properties"]
        assert props["workflow_execution_id"] == VALID_WORKFLOW_EXECUTION_ID
        assert props["timed_out_component"] == "activity"
        assert props["configured_timeout_seconds"] == 30.0
        assert props["elapsed_time_ms"] == 30500
        assert props["activity_id"] == "http-request-1"
        assert props["entitlement_id"] == "ent-456"

    def test_activity_id_null_for_workflow_timeout(self):
        event = WorkflowErrorEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            timed_out_component="workflow",
            configured_timeout_seconds=3600.0,
            elapsed_time_ms=3600000,
            entitlement_id="ent-123",
        )
        props = event.to_segment_event()["properties"]
        assert props["activity_id"] is None

    def test_invalid_timed_out_component(self):
        with pytest.raises(ValidationError):
            WorkflowErrorEvent(
                workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
                timed_out_component="invalid",
                configured_timeout_seconds=30.0,
                elapsed_time_ms=30000,
                entitlement_id="ent-123",
            )

    def test_negative_elapsed_time_rejected(self):
        with pytest.raises(ValidationError):
            WorkflowErrorEvent(
                workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
                timed_out_component="activity",
                configured_timeout_seconds=30.0,
                elapsed_time_ms=-1,
                entitlement_id="ent-123",
            )

    def test_activity_timeout_with_retries(self):
        event = WorkflowErrorEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            timed_out_component="activity",
            configured_timeout_seconds=30.0,
            elapsed_time_ms=90500,
            activity_id="http-request-1",
            retry_count=2,
            entitlement_id="ent-123",
        )
        assert event.retry_count == 2
        props = event.to_segment_event()["properties"]
        assert props["retry_count"] == 2

    def test_negative_retry_count_rejected(self):
        with pytest.raises(ValidationError):
            WorkflowErrorEvent(
                workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
                timed_out_component="activity",
                configured_timeout_seconds=30.0,
                elapsed_time_ms=30000,
                retry_count=-1,
                entitlement_id="ent-123",
            )

    def test_negative_configured_timeout_rejected(self):
        with pytest.raises(ValidationError):
            WorkflowErrorEvent(
                workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
                timed_out_component="activity",
                configured_timeout_seconds=-1.0,
                elapsed_time_ms=30000,
                entitlement_id="ent-123",
            )

    def test_frozen_immutability(self):
        event = WorkflowErrorEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            timed_out_component="activity",
            configured_timeout_seconds=30.0,
            elapsed_time_ms=30000,
            entitlement_id="ent-123",
        )
        with pytest.raises(ValidationError):
            event.timed_out_component = "workflow"

    def test_error_type_defaults_to_none(self):
        event = WorkflowErrorEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            timed_out_component="activity",
            configured_timeout_seconds=30.0,
            elapsed_time_ms=30000,
            entitlement_id="ent-123",
        )
        assert event.error_type is None
        assert event.retry_reason is None

    def test_error_type_accepts_exception_name(self):
        event = WorkflowErrorEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            timed_out_component="activity",
            configured_timeout_seconds=30.0,
            elapsed_time_ms=0,
            activity_id="http-request-1",
            retry_count=1,
            error_type="ConnectionError",
            retry_reason="Connection refused",
            entitlement_id="ent-123",
        )
        assert event.error_type == "ConnectionError"
        assert event.retry_reason == "Connection refused"
        assert event.retry_count == 1
        props = event.to_segment_event()["properties"]
        assert props["error_type"] == "ConnectionError"
        assert props["retry_reason"] == "Connection refused"

    def test_entitlement_id_in_segment_properties(self):
        event = WorkflowErrorEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            timed_out_component="workflow",
            configured_timeout_seconds=60.0,
            elapsed_time_ms=60000,
            entitlement_id="ent-test-789",
        )
        props = event.to_segment_event()["properties"]
        assert props["entitlement_id"] == "ent-test-789"
