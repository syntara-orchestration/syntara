"""Unit tests for the replayed flag plumbing (AAP-92821, PR 1)."""

from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import ExecutionInclude, ExecutionMode, ExecutionStatus
from syntara.workflows.services.activity_update_publisher import ActivityUpdatePublisher
from syntara.workflows.services.execution_service import ExecutionsConvertResourceMixin
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType


def _make_activity(*, replayed: bool | None) -> ActivityExecution:
    return ActivityExecution(
        execution_id=uuid4(),
        activity_name="step_1",
        node_type=NodeType.SCRIPT,
        temporal_activity_id="temporal-1",
        status=ActivityStatus.COMPLETED,
        output_data={"result": "ok"},
        replayed=replayed,
    )


def _make_execution(*, replayed: bool | None) -> Mock:
    execution = Mock()
    execution.id = uuid4()
    execution.workflow_id = uuid4()
    execution.workflow_version_id = uuid4()
    execution.workflow_version = None
    execution.workflow = None
    execution.project_id = uuid4()
    execution.temporal_workflow_id = "temporal-x"
    execution.status = ExecutionStatus.COMPLETED
    execution.created_by = uuid4()
    execution.created_at = datetime.now(UTC)
    execution.completed_at = None
    execution.updated_at = datetime.now(UTC)
    execution.updated_by = None
    execution.input_data = {}
    execution.trigger_node_id = "trigger_1"
    execution.error_details = None
    execution.labels = {}
    execution.approval_pending = False
    execution.mode = ExecutionMode.STANDARD
    execution.execution_metadata = None
    execution.retried_from_execution_id = None
    execution.source_execution_id = None
    execution.failed_node_ids = []
    execution.triggered_by = None
    execution.restart_count = 0
    execution.trigger_type = None
    execution.interface = None
    execution.activities = [_make_activity(replayed=replayed)]
    return execution


def test_convert_resource_maps_replayed() -> None:
    """convert_resource passes replayed through for True, False, and None."""
    for value in (True, False, None):
        read = ExecutionsConvertResourceMixin(include={ExecutionInclude.ACTIVITIES}).convert_resource(
            _make_execution(replayed=value)
        )
        assert read.activities is not None
        assert read.activities[0].replayed is value


def test_publisher_maps_replayed() -> None:
    """Streaming snapshots carry replayed."""
    publisher = ActivityUpdatePublisher()
    for value in (True, False, None):
        data = publisher._convert_activity_to_data(_make_activity(replayed=value))
        assert data["replayed"] is value
