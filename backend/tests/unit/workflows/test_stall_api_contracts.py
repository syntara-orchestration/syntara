"""Unit tests for AAP-92826 stall detection API contract fields.

Validates that stall_alert_at and first_stall_detected_at are correctly
propagated through ActivityData, ExecutionRead, the activity update publisher,
and the execution service conversion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from syntara.workflows.models.execution import ActivityData, ExecutionInclude, ExecutionRead, ExecutionStatus

FIXED_STALL_TS = datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC)
FIXED_FIRST_STALL_TS = datetime(2026, 10, 7, 11, 55, 0, tzinfo=UTC)
FIXED_STARTED_AT = datetime(2026, 10, 7, 11, 0, 0, tzinfo=UTC)


class TestActivityDataStallField:
    """ActivityData includes nullable stall_alert_at."""

    def test_stall_alert_at_defaults_to_none(self) -> None:
        data = ActivityData(activity_id="step-1", status="running")
        assert data.stall_alert_at is None

    def test_stall_alert_at_set(self) -> None:
        data = ActivityData(
            activity_id="step-1",
            status="running",
            stall_alert_at=FIXED_STALL_TS,
        )
        assert data.stall_alert_at == FIXED_STALL_TS

    def test_stall_alert_at_serialized_in_json(self) -> None:
        data = ActivityData(
            activity_id="step-1",
            status="running",
            stall_alert_at=FIXED_STALL_TS,
        )
        dumped = data.model_dump(mode="json")
        assert "stall_alert_at" in dumped
        assert dumped["stall_alert_at"] == "2026-10-07T12:00:00Z"

    def test_stall_alert_at_null_serialized(self) -> None:
        data = ActivityData(activity_id="step-1", status="completed")
        dumped = data.model_dump(mode="json")
        assert dumped["stall_alert_at"] is None


class TestExecutionReadStallFields:
    """ExecutionRead includes first_stall_detected_at."""

    def _minimal_execution_read(self, **overrides: object) -> ExecutionRead:
        defaults: dict[str, object] = {
            "id": uuid4(),
            "workflow_id": uuid4(),
            "workflow_version_id": uuid4(),
            "project_id": uuid4(),
            "temporal_workflow_id": "temporal-123",
            "status": ExecutionStatus.RUNNING,
            "created_at": FIXED_STARTED_AT,
            "updated_at": FIXED_STARTED_AT,
            "completed_at": None,
            "error_details": None,
            "input_data": {},
        }
        defaults.update(overrides)
        return ExecutionRead(**defaults)

    def test_first_stall_detected_at_defaults_to_none(self) -> None:
        result = self._minimal_execution_read()
        assert result.first_stall_detected_at is None

    def test_first_stall_detected_at_set(self) -> None:
        result = self._minimal_execution_read(first_stall_detected_at=FIXED_FIRST_STALL_TS)
        assert result.first_stall_detected_at == FIXED_FIRST_STALL_TS

    def test_first_stall_detected_at_serialized(self) -> None:
        result = self._minimal_execution_read(first_stall_detected_at=FIXED_FIRST_STALL_TS)
        dumped = result.model_dump(mode="json")
        assert dumped["first_stall_detected_at"] == "2026-10-07T11:55:00Z"


class TestActivityUpdatePublisherStallField:
    """_convert_activity_to_data includes stall_alert_at from ActivityExecution."""

    def test_stall_alert_at_propagated(self) -> None:
        from syntara.workflows.services.activity_update_publisher import ActivityUpdatePublisher

        publisher = ActivityUpdatePublisher.__new__(ActivityUpdatePublisher)

        activity = MagicMock()
        activity.activity_name = "step-1"
        activity.status = "running"
        activity.started_at = FIXED_STARTED_AT
        activity.completed_at = None
        activity.error_details = None
        activity.output_data = None
        activity.iteration = None
        activity.stall_alert_at = FIXED_STALL_TS

        result = publisher._convert_activity_to_data(activity)

        assert result["stall_alert_at"] == "2026-10-07T12:00:00Z"

    def test_stall_alert_at_null_when_not_stalled(self) -> None:
        from syntara.workflows.services.activity_update_publisher import ActivityUpdatePublisher

        publisher = ActivityUpdatePublisher.__new__(ActivityUpdatePublisher)

        activity = MagicMock()
        activity.activity_name = "step-1"
        activity.status = "running"
        activity.started_at = FIXED_STARTED_AT
        activity.completed_at = None
        activity.error_details = None
        activity.output_data = None
        activity.iteration = None
        activity.stall_alert_at = None

        result = publisher._convert_activity_to_data(activity)

        assert result["stall_alert_at"] is None


class TestExecutionServiceStallFields:
    """convert_resource propagates first_stall_detected_at and activity stall_alert_at."""

    def _make_resource(self, *, first_stall_detected_at: datetime | None = None) -> MagicMock:
        resource = MagicMock()
        resource.id = uuid4()
        resource.workflow_id = uuid4()
        resource.workflow_version_id = uuid4()
        resource.project_id = uuid4()
        resource.temporal_workflow_id = "temporal-456"
        resource.status = ExecutionStatus.RUNNING
        resource.created_by = uuid4()
        resource.created_at = FIXED_STARTED_AT
        resource.completed_at = None
        resource.updated_at = FIXED_STARTED_AT
        resource.updated_by = None
        resource.input_data = {}
        resource.trigger_node_id = None
        resource.error_details = None
        resource.labels = {}
        resource.approval_pending = False
        resource.first_stall_detected_at = first_stall_detected_at
        resource.mode = "standard"
        resource.execution_metadata = None
        resource.retried_from_execution_id = None
        resource.trigger_type = None
        resource.interface = None

        wv = MagicMock()
        wv.version = 1
        wv.name = None
        wv.created_at = FIXED_STARTED_AT
        resource.workflow_version = wv

        wf = MagicMock()
        wf.name = "Test Workflow"
        resource.workflow = wf

        resource.activities = []

        return resource

    def test_first_stall_detected_at_propagated(self) -> None:
        from syntara.workflows.services.execution_service import ExecutionsConvertResourceMixin

        converter = ExecutionsConvertResourceMixin()
        resource = self._make_resource(first_stall_detected_at=FIXED_FIRST_STALL_TS)

        result = converter.convert_resource(resource)

        assert result.first_stall_detected_at == FIXED_FIRST_STALL_TS

    def test_activities_include_stall_alert_at(self) -> None:
        """When include=activities, stall_alert_at is propagated."""
        from syntara.workflows.services.execution_service import ExecutionsConvertResourceMixin

        converter = ExecutionsConvertResourceMixin(include={ExecutionInclude.ACTIVITIES})
        resource = self._make_resource()

        activity = MagicMock()
        activity.activity_name = "step-1"
        activity.status = MagicMock()
        activity.status.value = "running"
        activity.error_details = None
        activity.output_data = None
        activity.started_at = FIXED_STARTED_AT
        activity.completed_at = None
        activity.iteration = None
        activity.stall_alert_at = FIXED_STALL_TS
        resource.activities = [activity]

        result = converter.convert_resource(resource)

        assert result.activities is not None
        assert len(result.activities) == 1
        assert result.activities[0].stall_alert_at == FIXED_STALL_TS


class TestStallAlertAtIncrementalPatches:
    """WebSocket incremental patches include stall_alert_at when it changes."""

    def test_build_field_patch_ops_includes_stall_alert_at_change(self) -> None:
        """stall_alert_at changes generate a replace patch operation."""
        from syntara.workflows.models.activity_execution import ActivityStatus
        from syntara.workflows.workflow_engine.services.activity_sync_publisher import ActivitySyncPublisherMixin

        activity = MagicMock()
        activity.activity_name = "step-1"
        activity.status = ActivityStatus.RUNNING
        activity.started_at = FIXED_STARTED_AT
        activity.completed_at = None
        activity.error_details = None
        activity.output_data = None
        activity.iteration = None
        activity.stall_alert_at = FIXED_STALL_TS

        # Old values: stall_alert_at was None
        old_values = {
            "status": ActivityStatus.RUNNING,
            "started_at": FIXED_STARTED_AT,
            "completed_at": None,
            "error_details": None,
            "output_data": None,
            "iteration": None,
            "stall_alert_at": None,
        }

        ops = ActivitySyncPublisherMixin._build_field_patch_ops(activity, old_values, activity_idx=0)

        # Should generate a patch for stall_alert_at change
        assert any(op["path"] == "/activities/0/stall_alert_at" for op in ops)
        stall_patch = next(op for op in ops if op["path"] == "/activities/0/stall_alert_at")
        assert stall_patch["op"] == "replace"
        assert stall_patch["value"] == "2026-10-07T12:00:00+00:00"

    def test_build_field_patch_ops_no_change_when_stall_alert_at_unchanged(self) -> None:
        """No patch generated when stall_alert_at hasn't changed."""
        from syntara.workflows.models.activity_execution import ActivityStatus
        from syntara.workflows.workflow_engine.services.activity_sync_publisher import ActivitySyncPublisherMixin

        activity = MagicMock()
        activity.activity_name = "step-1"
        activity.status = ActivityStatus.RUNNING
        activity.started_at = FIXED_STARTED_AT
        activity.completed_at = None
        activity.error_details = None
        activity.output_data = None
        activity.iteration = None
        activity.stall_alert_at = FIXED_STALL_TS

        # Old values: stall_alert_at was already set to the same value
        old_values = {
            "status": ActivityStatus.RUNNING,
            "started_at": FIXED_STARTED_AT,
            "completed_at": None,
            "error_details": None,
            "output_data": None,
            "iteration": None,
            "stall_alert_at": FIXED_STALL_TS,
        }

        ops = ActivitySyncPublisherMixin._build_field_patch_ops(activity, old_values, activity_idx=0)

        # Should not generate a patch for stall_alert_at (no change)
        assert not any(op["path"] == "/activities/0/stall_alert_at" for op in ops)

    def test_build_iteration_patch_ops_includes_stall_alert_at(self) -> None:
        """New iteration activity records include stall_alert_at in add operations."""
        from syntara.workflows.models.activity_execution import ActivityStatus
        from syntara.workflows.workflow_engine.services.activity_sync_publisher import ActivitySyncPublisherMixin

        activity = MagicMock()
        activity.activity_name = "step-1#iter-2"
        activity.status = ActivityStatus.RUNNING
        activity.started_at = FIXED_STARTED_AT
        activity.completed_at = None
        activity.error_details = None
        activity.output_data = None
        activity.iteration = 2
        activity.stall_alert_at = FIXED_STALL_TS

        activity_index_map = {"step-1": 0}

        ops = ActivitySyncPublisherMixin._build_iteration_patch_ops([activity], activity_index_map)

        # Should generate an "add" op with stall_alert_at included
        add_ops = [op for op in ops if op["op"] == "add"]
        assert len(add_ops) == 1
        # ActivityData uses model_dump(mode="json") which produces 'Z' suffix
        assert add_ops[0]["value"]["stall_alert_at"] == "2026-10-07T12:00:00Z"
