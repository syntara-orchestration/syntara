"""Unit tests for telemetry event models and builders."""

import pytest
from pydantic import ValidationError

from syntara.telemetry.events.base import BaseTelemetryEvent, _build_context
from syntara.telemetry.events.node_execution import (
    NodeExecutionEvent,
    NodeExecutionEventBuilder,
)
from syntara.telemetry.events.workflow_execution import (
    WorkflowExecutionCompletedEvent,
    WorkflowExecutionStartEvent,
)
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

# Import shared test data from conftest
from tests.unit.telemetry.conftest import (
    VALID_NODE_HASH,
    VALID_WORKFLOW_EXECUTION_ID,
)

# =============================================================================
# BaseTelemetryEvent Tests
# =============================================================================


class TestBaseTelemetryEventName:
    """Tests for BaseTelemetryEvent._get_event_name method."""

    def test_get_event_name_derives_from_class_name(self):
        """Test that event name is derived from class name when _segment_event_name is not set."""

        class MyCustomEvent(BaseTelemetryEvent):
            pass

        assert MyCustomEvent._get_event_name() == "my_custom"

    def test_get_event_name_removes_event_suffix(self):
        """Test that 'Event' suffix is removed from derived name."""

        class SomeActionEvent(BaseTelemetryEvent):
            pass

        assert SomeActionEvent._get_event_name() == "some_action"

    def test_get_event_name_handles_acronyms(self):
        """Test that consecutive uppercase letters (acronyms) are kept together."""

        class APICallEvent(BaseTelemetryEvent):
            pass

        assert APICallEvent._get_event_name() == "api_call"

    def test_get_event_name_handles_acronym_at_end(self):
        """Test acronym at the end of the class name."""

        class CallAPIEvent(BaseTelemetryEvent):
            pass

        assert CallAPIEvent._get_event_name() == "call_api"

    def test_get_event_name_handles_acronym_before_regular_word(self):
        """Test acronym followed by a regular CamelCase word."""

        class HTMLParserEvent(BaseTelemetryEvent):
            pass

        assert HTMLParserEvent._get_event_name() == "html_parser"


class TestBaseTelemetryEventContext:
    """Tests for the context dict attached to all telemetry events."""

    @pytest.fixture(autouse=True)
    def _clear_context_cache(self) -> None:
        """Clear the _build_context lru_cache so each test gets fresh values."""
        _build_context.cache_clear()

    def test_to_segment_event_includes_context(self, override_settings) -> None:
        """to_segment_event() must include a context dict with version info."""

        class StubEvent(BaseTelemetryEvent):
            pass

        with override_settings(container_image_version="v1.2.3-deadbeef"):
            event = StubEvent(entitlement_id="ent-1")
            segment_event = event.to_segment_event()

        ctx = segment_event["context"]
        assert ctx == {
            "container_image_version": "v1.2.3-deadbeef",
        }

    def test_context_not_in_properties(self, override_settings) -> None:
        """Version info must live in context, not in properties."""

        class StubEvent(BaseTelemetryEvent):
            pass

        with override_settings(container_image_version="img-tag"):
            event = StubEvent(entitlement_id="ent-2")
            props = event.to_segment_event()["properties"]

        assert "container_image_version" not in props  # type: ignore[operator]


# =============================================================================
# WorkflowExecutionStartEvent Tests (T019-TEST)
# =============================================================================


class TestWorkflowExecutionStartEvent:
    """Tests for WorkflowExecutionStartEvent Pydantic model."""

    def test_valid_event_creation(self):
        event = WorkflowExecutionStartEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            entitlement_id="",
        )
        assert event.workflow_execution_id == VALID_WORKFLOW_EXECUTION_ID
        assert event.trigger_type is None

    def test_valid_event_creation_with_trigger_type(self):
        event = WorkflowExecutionStartEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            entitlement_id="",
            trigger_type=ActivityName.MANUAL_TRIGGER,
        )
        assert event.workflow_execution_id == VALID_WORKFLOW_EXECUTION_ID
        assert event.trigger_type == ActivityName.MANUAL_TRIGGER

    def test_to_segment_event(self):
        event = WorkflowExecutionStartEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            entitlement_id="",
            trigger_type=ActivityName.MANUAL_TRIGGER,
        )
        segment_event = event.to_segment_event()
        assert segment_event["event"] == "workflow_execution_start"
        assert "properties" in segment_event
        props = segment_event["properties"]
        assert props["workflow_execution_id"] == VALID_WORKFLOW_EXECUTION_ID
        assert props["trigger_type"] == ActivityName.MANUAL_TRIGGER

    def test_entitlement_id_in_segment_properties(self):
        """entitlement_id value must appear in segment event properties."""
        event = WorkflowExecutionStartEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            entitlement_id="ent-start-123",
        )
        props = event.to_segment_event()["properties"]
        assert props["entitlement_id"] == "ent-start-123"


# =============================================================================
# WorkflowExecutionCompletedEvent Tests (T020-TEST)
# =============================================================================


class TestWorkflowExecutionCompletedEvent:
    """Tests for WorkflowExecutionCompletedEvent Pydantic model."""

    @pytest.mark.parametrize(
        ("status", "error_count", "error_type"),
        [
            ("completed", 0, None),
            ("failed", 1, "ActivityExecutionError"),
        ],
    )
    def test_event_creation(self, status, error_count, error_type):
        event = WorkflowExecutionCompletedEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            status=status,
            duration_ms=12500,
            node_count=8,
            error_count=error_count,
            error_type=error_type,
            entitlement_id="",
        )
        assert event.status == status
        assert event.duration_ms == 12500
        assert event.node_count == 8
        assert event.error_count == error_count
        assert event.error_type == error_type

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            WorkflowExecutionCompletedEvent(
                workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
                status="unknown",
                duration_ms=100,
                node_count=1,
                error_count=0,
                entitlement_id="",
            )

    def test_to_segment_event(self):
        event = WorkflowExecutionCompletedEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            status="completed",
            duration_ms=12500,
            node_count=8,
            error_count=0,
            entitlement_id="",
        )
        segment_event = event.to_segment_event()
        assert segment_event["event"] == "workflow_execution_completed"
        props = segment_event["properties"]
        assert props["status"] == "completed"
        assert props["duration_ms"] == 12500
        assert props["node_count"] == 8
        assert props["error_count"] == 0

    def test_entitlement_id_in_segment_properties(self):
        """entitlement_id value must appear in segment event properties."""
        event = WorkflowExecutionCompletedEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            status="completed",
            duration_ms=100,
            node_count=1,
            error_count=0,
            entitlement_id="ent-completed-456",
        )
        props = event.to_segment_event()["properties"]
        assert props["entitlement_id"] == "ent-completed-456"


# =============================================================================
# NodeExecutionEvent Tests (T021-TEST)
# =============================================================================


class TestNodeExecutionEvent:
    """Tests for NodeExecutionEvent Pydantic model."""

    def test_valid_success_event(self):
        event = NodeExecutionEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            node_type="script",
            node_hash=VALID_NODE_HASH,
            status="completed",
            error_type=None,
            entitlement_id="",
        )
        assert event.node_type == "script"
        assert event.status == "completed"
        assert event.error_type is None

    def test_invalid_node_type(self):
        with pytest.raises(ValidationError):
            NodeExecutionEvent(
                workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
                node_type="invalid",
                node_hash=VALID_NODE_HASH,
                status="completed",
                entitlement_id="",
            )

    def test_to_segment_event(self):
        event = NodeExecutionEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            node_type="script",
            node_hash=VALID_NODE_HASH,
            status="completed",
            entitlement_id="",
        )
        segment_event = event.to_segment_event()
        assert segment_event["event"] == "node_execution"
        props = segment_event["properties"]
        assert props["node_type"] == "script"

    def test_entitlement_id_in_segment_properties(self):
        """entitlement_id value must appear in segment event properties."""
        event = NodeExecutionEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            node_type="script",
            node_hash=VALID_NODE_HASH,
            status="completed",
            entitlement_id="ent-activity-789",
        )
        props = event.to_segment_event()["properties"]
        assert props["entitlement_id"] == "ent-activity-789"


# =============================================================================
# NodeExecutionEventBuilder Tests (T023-TEST)
# =============================================================================


class TestNodeExecutionEventBuilder:
    """Tests for NodeExecutionEventBuilder."""

    def test_build_event(self):
        builder = NodeExecutionEventBuilder()

        # Build event and verify basic properties
        event = builder.build_event(
            execution_id=VALID_WORKFLOW_EXECUTION_ID,
            node_type="script",
            node_def={"a": 1, "b": 2},
            status="completed",
            entitlement_id="",
        )
        assert isinstance(event, NodeExecutionEvent)
        assert event.status == "completed"
        assert len(event.node_hash) == 64

        # Verify hash is deterministic and key-order independent
        event_same = builder.build_event(
            execution_id=VALID_WORKFLOW_EXECUTION_ID,
            node_type="script",
            node_def={"b": 2, "a": 1},
            status="completed",
            entitlement_id="",
        )
        assert event.node_hash == event_same.node_hash
