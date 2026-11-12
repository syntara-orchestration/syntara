"""C2: sub-workflow lifecycle sync through ActivitySyncService.

Covers the event-processor path that makes a Sub-workflow node RUNNING on its
setup activity's start and populates ``runtime_metadata`` on the setup
activity's completion (non-iterated nodes only), without ever terminalizing the
node (terminal status stays owned by the finalizer), plus the sync-writer path
that keys the aggregate row and preserves the I/O owned by
``_persist_parent_node_io``.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any, ClassVar
from unittest.mock import Mock
from uuid import uuid4

from temporalio.api.enums.v1 import EventType
from temporalio.converter import DataConverter

from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution
from syntara.workflows.workflow_engine.codecs.credential_codec import CredentialPayloadCodec
from syntara.workflows.workflow_engine.services.activity_execution_sync import ActivityExecutionSyncMixin
from syntara.workflows.workflow_engine.services.activity_sync_publisher import ActivitySyncPublisherMixin
from syntara.workflows.workflow_engine.services.activity_sync_service import ActivitySyncService

from .test_activity_sync_service import create_test_metadata

_PREFIX = "__internal__setup_sub_workflow_"


def _setup_result(**over: object) -> dict[str, object]:
    data: dict[str, object] = {
        "execution_id": "child-exec-1",
        "child_workflow_id": "wf-123",
        "child_workflow_name": "demo-child",
        "child_workflow_version": 2,
        "trigger_node_id": "child_trigger",
        "input_data": {"greeting": "hi"},
        # Fields the setup activity also returns but must NOT be surfaced in runtime_metadata:
        "workflow_definition": {"nodes": ["lots", "of", "stuff"]},
        "task_queue": "tq",
    }
    data.update(over)
    return data


def _scheduled(event_id: int, activity_id: str) -> Mock:
    event = Mock()
    event.event_type = EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
    event.event_id = event_id
    event.event_time = datetime.now(UTC)
    attrs = Mock()
    attrs.activity_id = activity_id
    attrs.start_to_close_timeout = None
    event.activity_task_scheduled_event_attributes = attrs
    return event


def _started(event_id: int, scheduled_event_id: int, attempt: int = 1) -> Mock:
    event = Mock()
    event.event_type = EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED
    event.event_id = event_id
    event.event_time = datetime.now(UTC)
    attrs = Mock()
    attrs.scheduled_event_id = scheduled_event_id
    attrs.attempt = attempt
    attrs.last_failure = None
    event.activity_task_started_event_attributes = attrs
    return event


def _completed(event_id: int, scheduled_event_id: int, result: dict[str, object] | None = None) -> Mock:
    event = Mock()
    event.event_type = EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED
    event.event_id = event_id
    event.event_time = datetime.now(UTC)
    attrs = Mock()
    attrs.scheduled_event_id = scheduled_event_id
    if result is None:
        attrs.result = None
    else:
        payload = Mock()
        payload.data = json.dumps(result).encode()
        attrs.result = Mock(payloads=[payload])
    event.activity_task_completed_event_attributes = attrs
    return event


def _row(node_id: str, **over: object) -> ActivityExecution:
    kwargs: dict[str, object] = {
        "id": uuid4(),
        "execution_id": uuid4(),
        "activity_name": node_id,
        "node_type": "sub_workflow",
        "temporal_activity_id": node_id,
        "status": ActivityStatus.PENDING,
    }
    kwargs.update(over)
    return ActivityExecution(**kwargs)


def _nn(d: dict[str, Any] | None) -> dict[str, Any]:
    """Narrow an optional dict so it can be indexed in assertions (mypy --strict)."""
    assert d is not None
    return d


class TestSetupScheduled:
    """SCHEDULED → canvas-keyed pending entry marked as a sub-workflow setup."""

    def setup_method(self) -> None:
        self.service = ActivitySyncService(Mock(), Mock())
        self.metadata = create_test_metadata()
        self.session = Mock()

    def test_single_node_scheduled_keys_canvas_node(self) -> None:
        self.service._process_activity_scheduled(_scheduled(10, f"{_PREFIX}node-A"), self.metadata)
        update = self.metadata.pending_activity_updates[10]
        assert update["activity_id"] == "node-A"
        assert update["activity_name"] == "node-A"
        assert update["_subworkflow_setup"] is True
        assert update["_subworkflow_iteration"] is None
        assert update["status"] == ActivityStatus.PENDING
        assert update["iteration"] is None
        assert 10 in self.metadata.pending_sync_event_ids

    def test_for_each_iterations_map_to_same_canvas_node(self) -> None:
        self.service._process_activity_scheduled(_scheduled(11, f"{_PREFIX}node-B_iter_0"), self.metadata)
        self.service._process_activity_scheduled(_scheduled(12, f"{_PREFIX}node-B_iter_1"), self.metadata)
        u0 = self.metadata.pending_activity_updates[11]
        u1 = self.metadata.pending_activity_updates[12]
        assert u0["activity_id"] == "node-B"
        assert u1["activity_id"] == "node-B"
        assert u0["_subworkflow_iteration"] == 0
        assert u1["_subworkflow_iteration"] == 1

    def test_nested_for_each_strips_to_canvas_node(self) -> None:
        self.service._process_activity_scheduled(_scheduled(13, f"{_PREFIX}node-C_iter_1_iter_0"), self.metadata)
        update = self.metadata.pending_activity_updates[13]
        assert update["activity_id"] == "node-C"
        assert update["_subworkflow_iteration"] == 0

    def test_other_internal_activities_still_skipped(self) -> None:
        self.service._process_activity_scheduled(_scheduled(14, "__internal__register_monitoring"), self.metadata)
        assert 14 not in self.metadata.pending_activity_updates


class TestSetupStartedRunning:
    """STARTED → RUNNING via the existing started handler (DECISION 1 trigger)."""

    def setup_method(self) -> None:
        self.service = ActivitySyncService(Mock(), Mock())
        self.metadata = create_test_metadata()
        self.session = Mock()

    def test_started_sets_running(self) -> None:
        self.service._process_activity_scheduled(_scheduled(10, f"{_PREFIX}node-A"), self.metadata)
        self.service._process_activity_started(_started(11, scheduled_event_id=10), self.metadata)
        update = self.metadata.pending_activity_updates[10]
        assert update["status"] == ActivityStatus.RUNNING
        assert update["started_at"] is not None


class TestSetupCompleted:
    """COMPLETED → runtime_metadata (single only), never terminal."""

    def setup_method(self) -> None:
        self.service = ActivitySyncService(Mock(), Mock())
        self.metadata = create_test_metadata()
        self.session = Mock()

    def _run(self, activity_id: str, result: dict[str, object] | None, sched_id: int = 10) -> dict[str, Any]:
        self.service._process_activity_scheduled(_scheduled(sched_id, activity_id), self.metadata)
        self.service._process_activity_started(_started(sched_id + 1, sched_id), self.metadata)
        self.service._process_activity_completed(_completed(sched_id + 2, sched_id, result), self.metadata)
        return self.metadata.pending_activity_updates[sched_id]

    def test_single_node_populates_runtime_metadata_and_stays_running(self) -> None:
        update = self._run(f"{_PREFIX}node-A", _setup_result())
        assert update["status"] == ActivityStatus.RUNNING
        assert update["completed_at"] is None
        assert update["runtime_metadata"] == {
            "child_execution_id": "child-exec-1",
            "child_workflow_id": "wf-123",
            "child_workflow_name": "demo-child",
            "child_workflow_version": 2,
        }
        # Terminal status is NOT taken over by setup completion.
        assert "node-A" not in self.metadata.terminal_activity_ids

    def test_runtime_metadata_excludes_workflow_definition(self) -> None:
        update = self._run(f"{_PREFIX}node-A", _setup_result())
        assert "workflow_definition" not in update["runtime_metadata"]
        assert "task_queue" not in update["runtime_metadata"]

    def test_for_each_completion_populates_runtime_metadata_per_iteration(self) -> None:
        # AAP-101640: each for_each iteration's setup result carries its own child
        # link, so runtime_metadata is now populated for every iteration (not only
        # non-looped nodes). Terminal status still stays owned by the finalizer.
        update = self._run(f"{_PREFIX}node-B_iter_0", _setup_result(), sched_id=20)
        assert update["status"] == ActivityStatus.RUNNING
        assert update["runtime_metadata"] == {
            "child_execution_id": "child-exec-1",
            "child_workflow_id": "wf-123",
            "child_workflow_name": "demo-child",
            "child_workflow_version": 2,
        }
        assert "node-B" not in self.metadata.terminal_activity_ids

    def test_missing_payload_leaves_runtime_metadata_unset(self) -> None:
        update = self._run(f"{_PREFIX}node-A", None)
        assert update["status"] == ActivityStatus.RUNNING
        assert "runtime_metadata" not in update


class TestSetupTerminalEventsDoNotTerminalize:
    """FAILED / TIMED_OUT / CANCELED on the setup activity are inert in C2."""

    def setup_method(self) -> None:
        self.service = ActivitySyncService(Mock(), Mock())
        self.metadata = create_test_metadata()
        self.session = Mock()
        self.service._process_activity_scheduled(_scheduled(10, f"{_PREFIX}node-A"), self.metadata)
        self.service._process_activity_started(_started(11, 10), self.metadata)

    def _failed(self, sched_id: int) -> Mock:
        event = Mock()
        event.event_type = EventType.EVENT_TYPE_ACTIVITY_TASK_FAILED
        event.event_id = 12
        event.event_time = datetime.now(UTC)
        attrs = Mock()
        attrs.scheduled_event_id = sched_id
        attrs.failure = Mock(message="boom", application_failure_info=None)
        event.activity_task_failed_event_attributes = attrs
        return event

    def _timed_out(self, sched_id: int) -> Mock:
        event = Mock()
        event.event_type = EventType.EVENT_TYPE_ACTIVITY_TASK_TIMED_OUT
        event.event_id = 12
        event.event_time = datetime.now(UTC)
        attrs = Mock()
        attrs.scheduled_event_id = sched_id
        event.activity_task_timed_out_event_attributes = attrs
        return event

    def _canceled(self, sched_id: int) -> Mock:
        event = Mock()
        event.event_type = EventType.EVENT_TYPE_ACTIVITY_TASK_CANCELED
        event.event_id = 12
        event.event_time = datetime.now(UTC)
        attrs = Mock()
        attrs.scheduled_event_id = sched_id
        event.activity_task_canceled_event_attributes = attrs
        return event

    def test_failed_is_inert(self) -> None:
        self.service._process_activity_failed(self._failed(10), self.metadata)
        update = self.metadata.pending_activity_updates[10]
        assert update["status"] == ActivityStatus.RUNNING
        assert update["completed_at"] is None
        assert "node-A" not in self.metadata.terminal_activity_ids

    def test_timed_out_is_inert(self) -> None:
        self.service._process_activity_timed_out(self._timed_out(10), self.metadata)
        update = self.metadata.pending_activity_updates[10]
        assert update["status"] == ActivityStatus.RUNNING
        assert "node-A" not in self.metadata.terminal_activity_ids

    def test_canceled_is_inert(self) -> None:
        self.service._process_activity_canceled(self._canceled(10), self.metadata)
        update = self.metadata.pending_activity_updates[10]
        assert update["status"] == ActivityStatus.RUNNING
        assert "node-A" not in self.metadata.terminal_activity_ids


class TestExtractChildRuntimeMetadata:
    """_decode_setup_result / _child_runtime_metadata parsing and guards."""

    def _attrs(self, result: object | None, *, raw: bytes | None = None) -> Mock:
        attrs = Mock()
        if raw is not None:
            payload = Mock()
            payload.data = raw
            attrs.result = Mock(payloads=[payload])
        elif result is None:
            attrs.result = None
        else:
            payload = Mock()
            payload.data = json.dumps(result).encode()
            attrs.result = Mock(payloads=[payload])
        return attrs

    def test_extracts_four_identifiers(self) -> None:
        out = ActivitySyncService._child_runtime_metadata(_setup_result())
        assert out == {
            "child_execution_id": "child-exec-1",
            "child_workflow_id": "wf-123",
            "child_workflow_name": "demo-child",
            "child_workflow_version": 2,
        }

    def test_decode_returns_dict(self) -> None:
        assert ActivitySyncService._decode_setup_result(self._attrs(_setup_result())) == _setup_result()

    def test_none_when_no_result(self) -> None:
        assert ActivitySyncService._decode_setup_result(self._attrs(None)) is None

    def test_none_when_unparseable(self) -> None:
        assert ActivitySyncService._decode_setup_result(self._attrs(None, raw=b"not-json")) is None

    def test_none_when_no_expected_keys(self) -> None:
        assert ActivitySyncService._child_runtime_metadata({"unrelated": 1}) is None


class TestWriterPreserveIo:
    """preserve_io keeps input/output untouched while applying status/runtime_metadata."""

    def _row_with_io(self) -> ActivityExecution:
        return _row(
            "node-A",
            status=ActivityStatus.PENDING,
            input_data={"execution_mode": "reference"},
            output_data={"child_execution_id": "child-exec-1"},
        )

    def _update(self, **over: object) -> dict[str, object]:
        data: dict[str, object] = {
            "status": ActivityStatus.RUNNING,
            "started_at": datetime.now(UTC),
            "completed_at": None,
            "error_details": None,
            "retry_count": 0,
        }
        data.update(over)
        return data

    def test_preserve_io_leaves_input_output(self) -> None:
        row = self._row_with_io()
        ActivityExecutionSyncMixin._update_activity_record(row, self._update(), None, None, preserve_io=True)
        assert row.status == ActivityStatus.RUNNING
        assert row.input_data == {"execution_mode": "reference"}
        assert row.output_data == {"child_execution_id": "child-exec-1"}

    def test_preserve_io_applies_runtime_metadata(self) -> None:
        row = self._row_with_io()
        rm = {"child_execution_id": "child-exec-1"}
        ActivityExecutionSyncMixin._update_activity_record(
            row, self._update(runtime_metadata=rm), None, None, preserve_io=True
        )
        assert row.runtime_metadata == rm
        assert row.output_data == {"child_execution_id": "child-exec-1"}

    def test_without_preserve_io_output_is_overwritten(self) -> None:
        row = self._row_with_io()
        ActivityExecutionSyncMixin._update_activity_record(row, self._update(), None, None)
        assert row.output_data is None


class TestSyncSubworkflowSetup:
    """_sync_subworkflow_setup: reuse writer, preserve I/O, no terminal regression."""

    def setup_method(self) -> None:
        self.service = ActivitySyncService(Mock(), Mock())
        self.metadata = create_test_metadata()
        self.session = Mock()

    def _activity_data(self, **over: object) -> dict[str, object]:
        data: dict[str, object] = {
            "activity_id": "node-A",
            "activity_name": "node-A",
            "_subworkflow_setup": True,
            "_subworkflow_iteration": None,
            "status": ActivityStatus.RUNNING,
            "started_at": datetime.now(UTC),
            "completed_at": None,
            "error_details": None,
            "retry_count": 0,
            "iteration": None,
        }
        data.update(over)
        return data

    def test_updates_existing_row_and_preserves_io(self) -> None:
        row = _row(
            "node-A",
            input_data={"execution_mode": "reference"},
            output_data={"child_execution_id": "child-exec-1"},
        )
        result = self.service._sync_subworkflow_setup(
            self._activity_data(runtime_metadata={"child_execution_id": "child-exec-1"}),
            {"node-A": row},
            self.metadata,
            self.session,
        )
        assert result is not None
        activity, old_values, is_new = result
        assert is_new is False
        assert activity.status == ActivityStatus.RUNNING
        assert activity.runtime_metadata == {"child_execution_id": "child-exec-1"}
        # I/O owned by _persist_parent_node_io untouched.
        assert activity.input_data == {"execution_mode": "reference"}
        assert activity.output_data == {"child_execution_id": "child-exec-1"}
        assert old_values["status"] == ActivityStatus.PENDING

    def test_missing_row_returns_none(self) -> None:
        assert self.service._sync_subworkflow_setup(self._activity_data(), {}, self.metadata, self.session) is None

    def test_terminal_row_is_not_regressed(self) -> None:
        row = _row("node-A", status=ActivityStatus.COMPLETED)
        result = self.service._sync_subworkflow_setup(
            self._activity_data(), {"node-A": row}, self.metadata, self.session
        )
        assert result is None
        assert row.status == ActivityStatus.COMPLETED


class TestWebsocketDelta:
    """Publisher emits status + runtime_metadata deltas for the setup sync."""

    def test_status_and_runtime_metadata_deltas(self) -> None:
        row = _row(
            "node-A",
            status=ActivityStatus.RUNNING,
            runtime_metadata={"child_execution_id": "child-exec-1"},
        )
        old_values = {
            "status": ActivityStatus.PENDING,
            "started_at": None,
            "completed_at": None,
            "error_details": None,
            "output_data": None,
            "runtime_metadata": None,
            "iteration": None,
        }
        ops = ActivitySyncPublisherMixin._build_field_patch_ops(row, old_values, 2)
        assert {"op": "replace", "path": "/activities/2/status", "value": "running"} in ops
        assert {
            "op": "replace",
            "path": "/activities/2/runtime_metadata",
            "value": {"child_execution_id": "child-exec-1"},
        } in ops

    def test_idempotent_replay_emits_no_delta(self) -> None:
        row = _row(
            "node-A",
            status=ActivityStatus.RUNNING,
            runtime_metadata={"child_execution_id": "child-exec-1"},
        )
        # Old values already equal to current (re-read of history) → no ops.
        old_values = {
            "status": ActivityStatus.RUNNING,
            "started_at": None,
            "completed_at": None,
            "error_details": None,
            "output_data": None,
            "runtime_metadata": {"child_execution_id": "child-exec-1"},
            "iteration": None,
        }
        ops = ActivitySyncPublisherMixin._build_field_patch_ops(row, old_values, 2)
        assert ops == []


class TestNormalActivityUnaffected:
    """Normal (non-sub-workflow) activity handling is unchanged."""

    def setup_method(self) -> None:
        self.service = ActivitySyncService(Mock(), Mock())
        self.metadata = create_test_metadata()
        self.session = Mock()

    def test_normal_completed_terminalizes(self) -> None:
        self.service._process_activity_scheduled(_scheduled(10, "plain-node"), self.metadata)
        self.service._process_activity_started(_started(11, 10), self.metadata)
        self.service._process_activity_completed(_completed(12, 10, None), self.metadata)
        update = self.metadata.pending_activity_updates[10]
        assert update["status"] == ActivityStatus.COMPLETED
        assert update["completed_at"] is not None
        assert "plain-node" in self.metadata.terminal_activity_ids


class TestSetupSyncNoOutputDelta:
    """Regression: the setup sync must not touch output_data or emit its delta.

    output_data is owned by _persist_parent_node_io. The setup path uses
    preserve_io=True, so a RUNNING transition on a row that already carries
    output_data must leave that column byte-for-byte and emit no
    /output_data websocket op (only /status, and /runtime_metadata when set).
    """

    def setup_method(self) -> None:
        self.service = ActivitySyncService(Mock(), Mock())
        self.metadata = create_test_metadata()
        self.session = Mock()

    def _activity_data(self, **over: object) -> dict[str, object]:
        data: dict[str, object] = {
            "activity_id": "node-A",
            "activity_name": "node-A",
            "_subworkflow_setup": True,
            "_subworkflow_iteration": None,
            "status": ActivityStatus.RUNNING,
            "started_at": datetime.now(UTC),
            "completed_at": None,
            "error_details": None,
            "retry_count": 0,
            "iteration": None,
        }
        data.update(over)
        return data

    def test_output_data_unchanged_and_no_delta(self) -> None:
        existing_output = {"child_execution_id": "child-exec-1", "workflow_name": "demo-child"}
        row = _row("node-A", status=ActivityStatus.PENDING, output_data=dict(existing_output))

        result = self.service._sync_subworkflow_setup(
            self._activity_data(runtime_metadata={"child_execution_id": "child-exec-1"}),
            {"node-A": row},
            self.metadata,
            self.session,
        )
        assert result is not None
        activity, old_values, _ = result

        # output_data must be exactly what _persist_parent_node_io left there.
        assert activity.output_data == existing_output

        ops = ActivitySyncPublisherMixin._build_field_patch_ops(activity, old_values, 4)
        # No output_data op at all; status + runtime_metadata ops are expected.
        assert all("/output_data" not in op["path"] for op in ops)
        assert {"op": "replace", "path": "/activities/4/status", "value": "running"} in ops
        assert {
            "op": "replace",
            "path": "/activities/4/runtime_metadata",
            "value": {"child_execution_id": "child-exec-1"},
        } in ops


def _finalizer_activity(
    name: str,
    *,
    status: ActivityStatus,
    runtime_metadata: dict[str, Any] | None,
) -> Mock:
    a = Mock()
    a.status = status
    a.activity_name = name
    a.started_at = None
    a.error_details = None
    a.runtime_metadata = runtime_metadata
    return a


class TestFinalizerPreservesRuntimeMetadata:
    """Regression: finalizing a RUNNING sub-workflow node keeps runtime_metadata.

    C2 is the first populator of runtime_metadata, and the finalizer owns the
    RUNNING -> terminal transition. Across all three terminal resolutions
    (COMPLETED / SKIPPED / FAILED) the finalizer must change status (and
    completed_at) only, never clobber the child metadata written on setup.
    """

    _RM: ClassVar[dict[str, object]] = {
        "child_execution_id": "child-exec-1",
        "child_workflow_id": "wf-123",
        "child_workflow_name": "demo-child",
        "child_workflow_version": 2,
    }

    def test_running_to_completed_preserves_runtime_metadata(self) -> None:
        act = _finalizer_activity("sub_wf_node", status=ActivityStatus.RUNNING, runtime_metadata=dict(self._RM))
        execution = Mock(spec=Execution)
        execution.activities = [act]

        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4(), None, {"sub_wf_node"})

        assert act.status == ActivityStatus.COMPLETED
        assert act.completed_at is not None
        assert act.runtime_metadata == self._RM

    def test_running_to_skipped_preserves_runtime_metadata(self) -> None:
        act = _finalizer_activity("sub_wf_node", status=ActivityStatus.RUNNING, runtime_metadata=dict(self._RM))
        execution = Mock(spec=Execution)
        execution.activities = [act]

        # No completed_node_ids / failed_node_map → default SKIPPED.
        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4(), None, None)

        assert act.status == ActivityStatus.SKIPPED
        assert act.runtime_metadata == self._RM

    def test_running_to_failed_preserves_runtime_metadata(self) -> None:
        act = _finalizer_activity("sub_wf_node", status=ActivityStatus.RUNNING, runtime_metadata=dict(self._RM))
        execution = Mock(spec=Execution)
        execution.activities = [act]

        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4(), {"sub_wf_node": "child failed"}, None)

        assert act.status == ActivityStatus.FAILED
        assert act.error_details == "child failed"
        assert act.runtime_metadata == self._RM


# ---------------------------------------------------------------------------
# C3 · B1 — ActivitySyncService owns input_data/output_data (from the setup
# result payload), same shapes _persist_parent_node_io wrote; terminal backfill.
# ---------------------------------------------------------------------------

from syntara.workflows.workflow_engine.services.activity_sync_event_processor import (  # noqa: E402
    ActivitySyncEventProcessorMixin,
)

_EP = ActivitySyncEventProcessorMixin


class TestSetupIoReconstruction:
    """_build_subworkflow_io / _decode_setup_result / _child_runtime_metadata."""

    def test_build_io_exact_shapes(self) -> None:
        io = _EP._build_subworkflow_io(_setup_result())
        assert io["input"] == {
            "execution_mode": "reference",
            "workflow_id": "wf-123",
            "workflow_name": "demo-child",
            "trigger_node_id": "child_trigger",
            "input_parameters": {"greeting": "hi"},
        }
        assert io["output"] == {
            "workflow_id": "wf-123",
            "workflow_name": "demo-child",
            "child_workflow_version": 2,
            "child_execution_id": "child-exec-1",
        }

    def test_build_io_input_parameters_defaults_to_empty_dict(self) -> None:
        io = _EP._build_subworkflow_io(_setup_result(input_data=None))
        assert io["input"]["input_parameters"] == {}

    def test_build_io_missing_keys_become_none(self) -> None:
        io = _EP._build_subworkflow_io({})
        assert io["input"]["workflow_id"] is None
        assert io["output"]["child_execution_id"] is None
        assert io["input"]["input_parameters"] == {}

    def test_build_io_excludes_workflow_definition(self) -> None:
        io = _EP._build_subworkflow_io(_setup_result())
        assert "workflow_definition" not in io["input"]
        assert "workflow_definition" not in io["output"]

    def test_run_link_fields_present(self) -> None:
        # extractSubWorkflowChild reads output_data.child_execution_id + .workflow_name
        out = _EP._build_subworkflow_io(_setup_result())["output"]
        assert out["child_execution_id"] == "child-exec-1"
        assert out["workflow_name"] == "demo-child"

    def test_decode_none_when_no_payload(self) -> None:
        attrs = Mock()
        attrs.result = None
        assert _EP._decode_setup_result(attrs) is None

    def test_child_runtime_metadata_none_when_empty(self) -> None:
        assert _EP._child_runtime_metadata({"unrelated": 1}) is None


class TestSetupCompletedBuildsIo:
    """The completed handler stashes _subworkflow_io for all nodes; metadata single-only."""

    def setup_method(self) -> None:
        self.service = ActivitySyncService(Mock(), Mock())
        self.metadata = create_test_metadata()
        self.session = Mock()

    def _run(self, activity_id: str, sched: int) -> dict[str, Any]:
        self.service._process_activity_scheduled(_scheduled(sched, activity_id), self.metadata)
        self.service._process_activity_started(_started(sched + 1, sched), self.metadata)
        self.service._process_activity_completed(_completed(sched + 2, sched, _setup_result()), self.metadata)
        return self.metadata.pending_activity_updates[sched]

    def test_single_node_has_io_and_metadata(self) -> None:
        update = self._run(f"{_PREFIX}node-A", 10)
        assert update["_subworkflow_io"]["output"]["child_execution_id"] == "child-exec-1"
        assert update["_subworkflow_io"]["input"]["execution_mode"] == "reference"
        assert update["runtime_metadata"]["child_execution_id"] == "child-exec-1"
        assert update["status"] == ActivityStatus.RUNNING

    def test_for_each_has_io_and_metadata(self) -> None:
        # AAP-101640: a for_each iteration now carries both the I/O summary and its
        # own per-iteration child link.
        update = self._run(f"{_PREFIX}node-B_iter_0", 20)
        assert "_subworkflow_io" in update
        assert update["runtime_metadata"]["child_execution_id"] == "child-exec-1"


class TestSyncWritesIo:
    """_sync_subworkflow_setup persists the reconstructed I/O on a non-terminal row."""

    def setup_method(self) -> None:
        self.service = ActivitySyncService(Mock(), Mock())
        self.metadata = create_test_metadata()
        self.session = Mock()

    def _data(self, *, io: bool, iteration: object = None, **over: object) -> dict[str, object]:
        data: dict[str, object] = {
            "activity_id": "node-A",
            "activity_name": "node-A",
            "_subworkflow_setup": True,
            "_subworkflow_iteration": iteration,
            "status": ActivityStatus.RUNNING,
            "started_at": datetime.now(UTC),
            "completed_at": None,
            "error_details": None,
            "retry_count": 0,
            "iteration": None,
        }
        if io:
            data["_subworkflow_io"] = _EP._build_subworkflow_io(_setup_result())
        data.update(over)
        return data

    def test_completed_writes_exact_io_shapes(self) -> None:
        row = _row("node-A", status=ActivityStatus.PENDING, input_data={}, output_data=None)
        self.service._sync_subworkflow_setup(
            self._data(io=True, runtime_metadata={"child_execution_id": "child-exec-1"}),
            {"node-A": row},
            self.metadata,
            self.session,
        )
        assert row.input_data == {
            "execution_mode": "reference",
            "workflow_id": "wf-123",
            "workflow_name": "demo-child",
            "trigger_node_id": "child_trigger",
            "input_parameters": {"greeting": "hi"},
        }
        assert row.output_data == {
            "workflow_id": "wf-123",
            "workflow_name": "demo-child",
            "child_workflow_version": 2,
            "child_execution_id": "child-exec-1",
        }
        assert row.status == ActivityStatus.RUNNING
        assert row.runtime_metadata == {"child_execution_id": "child-exec-1"}

    def test_started_only_preserves_io(self) -> None:
        row = _row("node-A", status=ActivityStatus.PENDING, input_data={"keep": 1}, output_data={"keep": 2})
        self.service._sync_subworkflow_setup(self._data(io=False), {"node-A": row}, self.metadata, self.session)
        assert row.input_data == {"keep": 1}
        assert row.output_data == {"keep": 2}
        assert row.status == ActivityStatus.RUNNING

    def test_for_each_iterations_create_distinct_rows(self) -> None:
        # AAP-101640: iteration 0 reuses the aggregate row; iteration 1 gets its own
        # #iter-1 row. Each keeps its own child execution id (no last-wins overwrite).
        row = _row("node-A", status=ActivityStatus.RUNNING, input_data={}, output_data=None)
        existing = {"node-A": row}
        io0 = _EP._build_subworkflow_io(_setup_result(execution_id="child-0"))
        io1 = _EP._build_subworkflow_io(_setup_result(execution_id="child-1"))
        d0 = self._data(io=False, iteration=0, _subworkflow_io=io0, runtime_metadata={"child_execution_id": "child-0"})
        d1 = self._data(io=False, iteration=1, _subworkflow_io=io1, runtime_metadata={"child_execution_id": "child-1"})
        r0 = self.service._sync_subworkflow_setup(d0, existing, self.metadata, self.session)
        r1 = self.service._sync_subworkflow_setup(d1, existing, self.metadata, self.session)
        assert r0 is not None
        assert r1 is not None
        assert r0[2] is False  # aggregate row reused for iteration 0
        assert r1[2] is True  # new per-iteration row for iteration 1
        assert set(existing) == {"node-A", "node-A#iter-1"}
        assert _nn(existing["node-A"].output_data)["child_execution_id"] == "child-0"
        assert existing["node-A"].iteration == 0
        assert _nn(existing["node-A#iter-1"].output_data)["child_execution_id"] == "child-1"
        assert existing["node-A#iter-1"].iteration == 1
        assert existing["node-A"].runtime_metadata == {"child_execution_id": "child-0"}
        assert existing["node-A#iter-1"].runtime_metadata == {"child_execution_id": "child-1"}


class TestTerminalBackfill:
    """Terminal-row I/O-only, set-if-empty backfill."""

    def _io(self) -> dict[str, Any]:
        return _EP._build_subworkflow_io(_setup_result())

    def test_backfills_empty_io_without_touching_status(self) -> None:
        row = _row(
            "node-A", status=ActivityStatus.CANCELLED, input_data={}, output_data=None, runtime_metadata={"keep": 1}
        )
        result = ActivityExecutionSyncMixin._backfill_terminal_subworkflow_io(row, self._io())
        assert result is not None
        activity, old_values, is_new = result
        assert is_new is False
        assert activity.status == ActivityStatus.CANCELLED  # untouched
        assert activity.runtime_metadata == {"keep": 1}  # untouched
        assert activity.input_data is not None
        assert activity.input_data["execution_mode"] == "reference"
        assert activity.output_data is not None
        assert activity.output_data["child_execution_id"] == "child-exec-1"
        # old_values carries current status/runtime_metadata so no spurious delta
        assert old_values["status"] == ActivityStatus.CANCELLED

    def test_does_not_overwrite_nonempty_io(self) -> None:
        row = _row("node-A", status=ActivityStatus.FAILED, input_data={"existing": 1}, output_data={"existing": 2})
        assert ActivityExecutionSyncMixin._backfill_terminal_subworkflow_io(row, self._io()) is None
        assert row.input_data == {"existing": 1}
        assert row.output_data == {"existing": 2}

    def test_idempotent_second_backfill_is_noop(self) -> None:
        row = _row("node-A", status=ActivityStatus.CANCELLED, input_data={}, output_data=None)
        assert ActivityExecutionSyncMixin._backfill_terminal_subworkflow_io(row, self._io()) is not None
        assert ActivityExecutionSyncMixin._backfill_terminal_subworkflow_io(row, self._io()) is None

    def test_no_summary_returns_none(self) -> None:
        row = _row("node-A", status=ActivityStatus.CANCELLED, input_data={}, output_data=None)
        assert ActivityExecutionSyncMixin._backfill_terminal_subworkflow_io(row, None) is None


class TestSyncRoutesTerminalToBackfill:
    """_sync_subworkflow_setup dispatches terminal rows to the backfill carve-out."""

    def setup_method(self) -> None:
        self.service = ActivitySyncService(Mock(), Mock())
        self.metadata = create_test_metadata()
        self.session = Mock()

    def test_terminal_row_backfilled_not_regressed(self) -> None:
        row = _row("node-A", status=ActivityStatus.CANCELLED, input_data={}, output_data=None)
        data = {
            "activity_id": "node-A",
            "_subworkflow_setup": True,
            "_subworkflow_iteration": None,
            "status": ActivityStatus.RUNNING,
            "started_at": datetime.now(UTC),
            "completed_at": None,
            "error_details": None,
            "retry_count": 0,
            "iteration": None,
            "_subworkflow_io": _EP._build_subworkflow_io(_setup_result()),
        }
        result = self.service._sync_subworkflow_setup(data, {"node-A": row}, self.metadata, self.session)
        assert result is not None
        assert row.status == ActivityStatus.CANCELLED
        assert row.output_data is not None
        assert row.output_data["child_execution_id"] == "child-exec-1"


class TestIoWebsocketDelta:
    """Writing I/O emits an output_data patch and no spurious deltas."""

    def test_output_data_patch_emitted(self) -> None:
        row = _row("node-A", status=ActivityStatus.RUNNING, output_data={"child_execution_id": "child-exec-1"})
        old = {
            "status": ActivityStatus.RUNNING,
            "started_at": None,
            "completed_at": None,
            "error_details": None,
            "output_data": None,
            "runtime_metadata": None,
            "iteration": None,
        }
        ops = ActivitySyncPublisherMixin._build_field_patch_ops(row, old, 1)
        assert any(op["path"] == "/activities/1/output_data" for op in ops)
        assert all(op["path"] != "/activities/1/status" for op in ops)  # unchanged


_CODEC_KEY = bytes(range(32))  # synthetic AES-256-GCM key for tests only


def _encrypted_attrs(result: dict[str, object]) -> tuple[Mock, CredentialPayloadCodec]:
    """Encode a setup result the way the worker stores it (codec may encrypt)."""
    codec = CredentialPayloadCodec(_CODEC_KEY)
    stored = asyncio.run(DataConverter(payload_codec=codec).encode([result]))[0]
    attrs = Mock()
    attrs.result = Mock(payloads=[stored])
    return attrs, codec


class TestDecodeSetupResultViaCodec:
    """P1-2: credential-bearing setup results are stored encrypted in history."""

    def test_encrypted_setup_result_lost_without_codec(self) -> None:
        # Characterizes the bug: a raw parse (no codec) drops the child link.
        attrs, _ = _encrypted_attrs(_setup_result(input_data={"greeting": "hi", "aap_password": "SYN-x"}))
        assert ActivitySyncService._decode_setup_result(attrs) is None

    def test_encrypted_setup_result_decoded_with_codec(self) -> None:
        # The fix: decoding through the codec recovers the dict + child link.
        res = _setup_result(input_data={"greeting": "hi", "aap_password": "SYN-x"})
        attrs, codec = _encrypted_attrs(res)
        decoded = ActivitySyncService._decode_setup_result(attrs, codec)
        assert decoded is not None
        assert decoded["child_workflow_id"] == "wf-123"

    def test_generic_auth_type_key_also_encrypts_and_decodes(self) -> None:
        res = _setup_result(input_data={"greeting": "hi", "auth_type": "bearer"})
        attrs, codec = _encrypted_attrs(res)
        assert ActivitySyncService._decode_setup_result(attrs) is None  # raw parse loses it
        assert ActivitySyncService._decode_setup_result(attrs, codec) is not None  # codec recovers it

    def test_plain_setup_result_passes_through_codec_unchanged(self) -> None:
        # Safety/idempotency: a non-encrypted payload decodes unchanged.
        res = _setup_result()
        attrs, codec = _encrypted_attrs(res)
        assert ActivitySyncService._decode_setup_result(attrs, codec) == res

    def test_non_codec_object_falls_back_to_raw_parse(self) -> None:
        # A Mock is not a CredentialPayloadCodec -> raw parse (today's behaviour).
        plain = _completed(2, 1, _setup_result()).activity_task_completed_event_attributes
        assert ActivitySyncService._decode_setup_result(plain, Mock()) == _setup_result()


class TestBuildIoScrubsCredentials:
    """P1-2: recognized credential keys are redacted in the persisted input summary."""

    def test_recognized_credential_key_redacted_in_input_parameters(self) -> None:
        res = _setup_result(input_data={"greeting": "hi", "aap_password": "SYN-x"})
        io = ActivitySyncService._build_subworkflow_io(res)
        assert io["input"]["input_parameters"]["aap_password"] == "[REDACTED]"  # noqa: S105
        assert io["input"]["input_parameters"]["greeting"] == "hi"

    def test_no_credential_keys_leaves_input_parameters_unchanged(self) -> None:
        res = _setup_result(input_data={"greeting": "hi"})
        io = ActivitySyncService._build_subworkflow_io(res)
        assert io["input"]["input_parameters"] == {"greeting": "hi"}


# ===========================================================================
# AAP-101640 — Sub-workflow nodes in a loop render one run-details row per
# iteration, each linking to that iteration's distinct child execution.
# ===========================================================================


class TestSubworkflowIterationRecordResolution:
    """Deterministic per-iteration row resolution (``_get_or_create_subworkflow_iteration_record``)."""

    def setup_method(self) -> None:
        self.metadata = create_test_metadata()
        self.session = Mock()

    def _agg(self) -> dict[str, ActivityExecution]:
        return {"node-A": _row("node-A", status=ActivityStatus.PENDING)}

    def _get(self, existing: dict[str, ActivityExecution], n: int | None) -> tuple[Any, bool]:
        return ActivityExecutionSyncMixin._get_or_create_subworkflow_iteration_record(
            "node-A", n, existing, self.metadata, self.session
        )

    def test_non_looped_uses_aggregate_row(self) -> None:
        existing = self._agg()
        row, is_new = self._get(existing, None)
        assert is_new is False
        assert row is existing["node-A"]
        assert set(existing) == {"node-A"}

    def test_iteration_zero_uses_aggregate_row_and_sets_index(self) -> None:
        existing = self._agg()
        row, is_new = self._get(existing, 0)
        assert is_new is False
        assert row is existing["node-A"]
        assert existing["node-A"].iteration == 0
        assert set(existing) == {"node-A"}

    def test_one_iteration_single_row(self) -> None:
        # A for_each that runs once still emits _iter_0 -> aggregate row, no composite.
        existing = self._agg()
        _row_obj, is_new = self._get(existing, 0)
        assert set(existing) == {"node-A"}
        assert is_new is False

    def test_three_iterations_create_three_rows(self) -> None:
        existing = self._agg()
        flags = [self._get(existing, n)[1] for n in (0, 1, 2)]
        assert flags == [False, True, True]
        assert set(existing) == {"node-A", "node-A#iter-1", "node-A#iter-2"}
        assert existing["node-A"].iteration == 0
        assert existing["node-A#iter-1"].iteration == 1
        assert existing["node-A#iter-2"].iteration == 2

    def test_five_iterations_create_five_rows(self) -> None:
        existing = self._agg()
        for n in range(5):
            self._get(existing, n)
        assert set(existing) == {
            "node-A",
            "node-A#iter-1",
            "node-A#iter-2",
            "node-A#iter-3",
            "node-A#iter-4",
        }

    def test_idempotent_repeat_same_iteration_no_duplicate(self) -> None:
        existing = self._agg()
        r1 = self._get(existing, 2)
        r2 = self._get(existing, 2)
        r3 = self._get(existing, 2)
        assert (r1[1], r2[1], r3[1]) == (True, False, False)
        assert r1[0] is r2[0] is r3[0]
        assert set(existing) == {"node-A", "node-A#iter-2"}

    def test_out_of_order_iterations_resolve_deterministically(self) -> None:
        existing = self._agg()
        self._get(existing, 2)
        self._get(existing, 0)
        self._get(existing, 1)
        self._get(existing, 2)  # late duplicate event
        assert set(existing) == {"node-A", "node-A#iter-1", "node-A#iter-2"}
        assert existing["node-A#iter-1"].iteration == 1
        assert existing["node-A#iter-2"].iteration == 2

    def test_missing_aggregate_row_returns_none(self) -> None:
        row, is_new = self._get({}, 1)
        assert row is None
        assert is_new is False

    def test_new_row_registered_in_index_map(self) -> None:
        existing = self._agg()
        self.metadata.activity_index_map["node-A"] = 0
        self.metadata.next_activity_index = 1
        self._get(existing, 1)
        assert self.metadata.activity_index_map["node-A#iter-1"] == 1
        assert self.metadata.next_activity_index == 2


class TestSubworkflowPerIterationSyncChildLinks:
    """_sync_subworkflow_setup yields one row per iteration, each with its own child link."""

    def setup_method(self) -> None:
        self.service = ActivitySyncService(Mock(), Mock())
        self.metadata = create_test_metadata()
        self.session = Mock()

    def _data(self, n: int, child: str) -> dict[str, Any]:
        return {
            "activity_id": "node-A",
            "activity_name": "node-A",
            "_subworkflow_setup": True,
            "_subworkflow_iteration": n,
            "status": ActivityStatus.RUNNING,
            "started_at": datetime.now(UTC),
            "completed_at": None,
            "error_details": None,
            "retry_count": 0,
            "iteration": None,
            "_subworkflow_io": _EP._build_subworkflow_io(_setup_result(execution_id=child)),
            "runtime_metadata": {"child_execution_id": child, "child_workflow_name": "demo-child"},
        }

    def test_three_iterations_distinct_child_links(self) -> None:
        existing = {"node-A": _row("node-A", status=ActivityStatus.PENDING)}
        flags = []
        for n, child in [(0, "child-0"), (1, "child-1"), (2, "child-2")]:
            res = self.service._sync_subworkflow_setup(self._data(n, child), existing, self.metadata, self.session)
            assert res is not None
            flags.append(res[2])
        assert flags == [False, True, True]
        assert set(existing) == {"node-A", "node-A#iter-1", "node-A#iter-2"}
        links = {k: _nn(v.runtime_metadata)["child_execution_id"] for k, v in existing.items()}
        assert links == {"node-A": "child-0", "node-A#iter-1": "child-1", "node-A#iter-2": "child-2"}
        assert len(set(links.values())) == 3  # distinct child executions
        assert _nn(existing["node-A"].output_data)["child_execution_id"] == "child-0"
        assert _nn(existing["node-A#iter-2"].output_data)["child_execution_id"] == "child-2"

    def test_duplicate_completed_event_keeps_single_row_and_link(self) -> None:
        existing = {"node-A": _row("node-A", status=ActivityStatus.PENDING)}
        self.service._sync_subworkflow_setup(self._data(1, "child-1"), existing, self.metadata, self.session)
        # replay the same iteration's completed event (idempotent)
        self.service._sync_subworkflow_setup(self._data(1, "child-1"), existing, self.metadata, self.session)
        assert set(existing) == {"node-A", "node-A#iter-1"}
        assert _nn(existing["node-A#iter-1"].runtime_metadata)["child_execution_id"] == "child-1"


class TestFinalizerOverPerIterationRows:
    """Finalizer terminalizes each per-iteration row, preserving its child link.

    Per-iteration rows take the node-level terminal status; each row's own child
    link (AAP-101640) is never clobbered by finalization.
    """

    @staticmethod
    def _act(name: str, iteration: int, child: str, status: ActivityStatus = ActivityStatus.RUNNING) -> Mock:
        a = Mock()
        a.status = status
        a.activity_name = name
        a.started_at = None
        a.error_details = None
        a.iteration = iteration
        a.runtime_metadata = {"child_execution_id": child}
        return a

    def test_completed_node_marks_all_iterations_completed_preserving_links(self) -> None:
        acts = [
            self._act("node-A", 0, "child-0"),
            self._act("node-A#iter-1", 1, "child-1"),
            self._act("node-A#iter-2", 2, "child-2"),
        ]
        execution = Mock(spec=Execution)
        execution.activities = acts
        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4(), None, {"node-A"})
        assert [a.status for a in acts] == [ActivityStatus.COMPLETED] * 3
        assert [a.runtime_metadata["child_execution_id"] for a in acts] == ["child-0", "child-1", "child-2"]

    def test_failed_node_marks_all_iterations_failed_preserving_links(self) -> None:
        acts = [self._act("node-A", 0, "child-0"), self._act("node-A#iter-1", 1, "child-1")]
        execution = Mock(spec=Execution)
        execution.activities = acts
        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4(), {"node-A": "boom"}, None)
        assert all(a.status == ActivityStatus.FAILED for a in acts)
        assert all(a.error_details == "boom" for a in acts)
        assert [a.runtime_metadata["child_execution_id"] for a in acts] == ["child-0", "child-1"]

    def test_already_terminal_iteration_row_not_regressed(self) -> None:
        # A per-iteration row synced to a terminal status by its own events is left untouched
        # even when the node-level resolution would say FAILED (mixed outcome across iterations).
        running = self._act("node-A", 0, "child-0")
        done = self._act("node-A#iter-1", 1, "child-1", status=ActivityStatus.COMPLETED)
        execution = Mock(spec=Execution)
        execution.activities = [running, done]
        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4(), {"node-A": "boom"}, None)
        assert running.status == ActivityStatus.FAILED
        assert done.status == ActivityStatus.COMPLETED  # untouched
        assert done.runtime_metadata["child_execution_id"] == "child-1"


class TestIterationAddOpIncludesRuntimeMetadata:
    """A new per-iteration row's add-op carries its child link.

    So the first patch already shows the per-iteration 'View sub-workflow run'
    link (AAP-101640).
    """

    def test_add_op_includes_runtime_metadata_and_resets_original(self) -> None:
        row = _row(
            "node-A#iter-1",
            status=ActivityStatus.RUNNING,
            iteration=1,
            runtime_metadata={"child_execution_id": "child-1", "child_workflow_name": "demo-child"},
        )
        ops = ActivitySyncPublisherMixin._build_iteration_patch_ops([row], {"node-A": 0})
        add_ops = [o for o in ops if o["op"] == "add"]
        assert len(add_ops) == 1
        assert add_ops[0]["value"]["runtime_metadata"] == {
            "child_execution_id": "child-1",
            "child_workflow_name": "demo-child",
        }
        assert add_ops[0]["value"]["iteration"] == 1
        assert {"op": "replace", "path": "/activities/0/iteration", "value": 0} in ops
