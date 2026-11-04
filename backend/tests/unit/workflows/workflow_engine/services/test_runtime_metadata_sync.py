"""C1: runtime_metadata persistence (writer) + websocket field-diff (publisher).

Covers the preserve-on-omit / explicit-null semantics of the sync writer and
that a websocket patch is emitted only when runtime_metadata changes. No
populator sets runtime_metadata yet (C1 is additive plumbing).
"""

from uuid import uuid4

from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.workflow_engine.services.activity_execution_sync import ActivityExecutionSyncMixin
from syntara.workflows.workflow_engine.services.activity_sync_publisher import ActivitySyncPublisherMixin


def _activity(runtime_metadata: dict | None = None) -> ActivityExecution:
    return ActivityExecution(
        id=uuid4(),
        execution_id=uuid4(),
        activity_name="node-1",
        node_type="script",
        temporal_activity_id="temporal-node-1",
        status=ActivityStatus.RUNNING,
        runtime_metadata=runtime_metadata,
    )


def _update(**over: object) -> dict:
    data = {
        "status": ActivityStatus.COMPLETED,
        "started_at": None,
        "completed_at": None,
        "error_details": None,
        "retry_count": 0,
    }
    data.update(over)
    return data


class TestRuntimeMetadataWriter:
    """runtime_metadata preserve-on-omit / explicit-null semantics in the sync writer."""

    def test_partial_update_preserves_existing_runtime_metadata(self) -> None:
        existing = _activity(runtime_metadata={"child_execution_id": "c-1"})
        # activity_data omits "runtime_metadata" entirely → value is preserved.
        ActivityExecutionSyncMixin._update_activity_record(existing, _update(), None, None)
        assert existing.runtime_metadata == {"child_execution_id": "c-1"}

    def test_explicit_null_clears_runtime_metadata(self) -> None:
        existing = _activity(runtime_metadata={"child_execution_id": "c-1"})
        ActivityExecutionSyncMixin._update_activity_record(existing, _update(runtime_metadata=None), None, None)
        assert existing.runtime_metadata is None

    def test_explicit_value_sets_runtime_metadata(self) -> None:
        existing = _activity(runtime_metadata=None)
        rm = {"child_execution_id": "c-2", "child_workflow_version": 3}
        ActivityExecutionSyncMixin._update_activity_record(existing, _update(runtime_metadata=rm), None, None)
        assert existing.runtime_metadata == rm

    def test_old_values_capture_prior_runtime_metadata(self) -> None:
        existing = _activity(runtime_metadata={"a": 1})
        old = ActivityExecutionSyncMixin._update_activity_record(
            existing, _update(runtime_metadata={"b": 2}), None, None
        )
        assert old["runtime_metadata"] == {"a": 1}


class TestRuntimeMetadataPatch:
    """runtime_metadata websocket field-diff: patch only on change."""

    @staticmethod
    def _old(runtime_metadata: dict | None) -> dict:
        return {
            "status": ActivityStatus.RUNNING,
            "started_at": None,
            "completed_at": None,
            "error_details": None,
            "output_data": None,
            "runtime_metadata": runtime_metadata,
            "iteration": None,
        }

    def test_patch_emitted_on_runtime_metadata_change(self) -> None:
        activity = _activity(runtime_metadata={"b": 2})
        ops = ActivitySyncPublisherMixin._build_field_patch_ops(activity, self._old({"a": 1}), 3)
        assert {"op": "replace", "path": "/activities/3/runtime_metadata", "value": {"b": 2}} in ops

    def test_patch_emitted_when_runtime_metadata_cleared(self) -> None:
        activity = _activity(runtime_metadata=None)
        ops = ActivitySyncPublisherMixin._build_field_patch_ops(activity, self._old({"a": 1}), 0)
        assert {"op": "replace", "path": "/activities/0/runtime_metadata", "value": None} in ops

    def test_no_patch_when_runtime_metadata_unchanged(self) -> None:
        activity = _activity(runtime_metadata={"a": 1})
        ops = ActivitySyncPublisherMixin._build_field_patch_ops(activity, self._old({"a": 1}), 3)
        assert all("/runtime_metadata" not in op["path"] for op in ops)
