"""Contract tests for telemetry event schemas.

Validates that Pydantic models produce valid events and consistent JSON schemas.
"""

import json

import jsonschema

from syntara.telemetry.events.node_execution import NodeExecutionEvent
from syntara.telemetry.events.workflow_execution import (
    WorkflowExecutionCompletedEvent,
    WorkflowExecutionStartEvent,
)
from syntara.telemetry.events.workflow_version import WorkflowVersionCreatedEvent
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

# Import shared test data from unit telemetry conftest
from tests.unit.telemetry.conftest import (
    VALID_NODE_HASH,
    VALID_WORKFLOW_EXECUTION_ID,
)


class TestWorkflowExecutionStartEventSchema:
    """Contract tests for WorkflowExecutionStartEvent JSON schema."""

    def test_model_generates_valid_json_schema(self):
        schema = WorkflowExecutionStartEvent.model_json_schema()
        assert schema["type"] == "object"
        assert "workflow_execution_id" in schema["properties"]
        assert "trigger_type" in schema["properties"]

    def test_valid_event_conforms_to_schema(self):
        schema = WorkflowExecutionStartEvent.model_json_schema()
        event = WorkflowExecutionStartEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            entitlement_id="",
            trigger_type=ActivityName.MANUAL_TRIGGER,
        )
        event_dict = event.model_dump()
        jsonschema.validate(instance=event_dict, schema=schema)
        # Segment event must be JSON-serializable
        assert json.dumps(event.to_segment_event())


class TestWorkflowExecutionCompletedEventSchema:
    """Contract tests for WorkflowExecutionCompletedEvent JSON schema."""

    def test_model_generates_valid_json_schema(self):
        schema = WorkflowExecutionCompletedEvent.model_json_schema()
        assert schema["type"] == "object"
        assert "status" in schema["properties"]
        assert "duration_ms" in schema["properties"]
        assert "node_count" in schema["properties"]
        assert "error_count" in schema["properties"]

    def test_valid_event_conforms_to_schema(self):
        schema = WorkflowExecutionCompletedEvent.model_json_schema()
        event = WorkflowExecutionCompletedEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            status="completed",
            duration_ms=12500,
            node_count=8,
            error_count=0,
            error_type=None,
            entitlement_id="",
        )
        event_dict = event.model_dump()
        jsonschema.validate(instance=event_dict, schema=schema)
        # Segment event must be JSON-serializable
        assert json.dumps(event.to_segment_event())


class TestNodeExecutionEventSchema:
    """Contract tests for NodeExecutionEvent JSON schema."""

    def test_model_generates_valid_json_schema(self):
        schema = NodeExecutionEvent.model_json_schema()
        assert schema["type"] == "object"
        assert "node_type" in schema["properties"]
        assert "node_hash" in schema["properties"]
        assert "status" in schema["properties"]

    def test_valid_event_conforms_to_schema(self):
        schema = NodeExecutionEvent.model_json_schema()
        event = NodeExecutionEvent(
            workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
            node_type="script",
            node_hash=VALID_NODE_HASH,
            status="completed",
            error_type=None,
            entitlement_id="",
        )
        event_dict = event.model_dump()
        jsonschema.validate(instance=event_dict, schema=schema)
        # Segment event must be JSON-serializable
        assert json.dumps(event.to_segment_event())

    def test_all_node_types_valid_against_schema(self):
        schema = NodeExecutionEvent.model_json_schema()
        for node_type in [
            "manual_trigger",
            "condition",
            "converge",
            "loop",
            "aap_job_template",
            "agentic",
            "approval",
            "http_request",
            "script",
        ]:
            event = NodeExecutionEvent(
                workflow_execution_id=VALID_WORKFLOW_EXECUTION_ID,
                node_type=node_type,
                node_hash=VALID_NODE_HASH,
                status="completed",
                entitlement_id="",
            )
            event_dict = event.model_dump()
            jsonschema.validate(instance=event_dict, schema=schema)


class TestWorkflowVersionCreatedEventSchema:
    """Contract tests for WorkflowVersionCreatedEvent JSON schema."""

    def test_model_generates_valid_json_schema(self):
        schema = WorkflowVersionCreatedEvent.model_json_schema()
        assert schema["type"] == "object"
        assert "workflow_id" in schema["properties"]
        assert "version" in schema["properties"]

    def test_valid_event_conforms_to_schema(self):
        schema = WorkflowVersionCreatedEvent.model_json_schema()
        event = WorkflowVersionCreatedEvent(
            workflow_id="550e8400-e29b-41d4-a716-446655440000",
            version=3,
            entitlement_id="",
        )
        event_dict = event.model_dump()
        jsonschema.validate(instance=event_dict, schema=schema)
        assert json.dumps(event.to_segment_event())
