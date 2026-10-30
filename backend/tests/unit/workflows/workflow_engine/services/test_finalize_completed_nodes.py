"""Unit tests for completed-node precedence in _finalize_non_terminal_activities.

Precedence on completion for non-terminal activity rows:
    FAILED  (base node in failed_node_map)
    > COMPLETED  (base node in completed_node_ids)
    > SKIPPED  (default)

Sub-workflow nodes never emit an ACTIVITY_TASK_COMPLETED event, so their row
stays PENDING until finalization; completed_node_ids lets it be marked COMPLETED.
"""

import json
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

from temporalio.api.enums.v1 import EventType

from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.models.execution import Execution
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType
from syntara.workflows.workflow_engine.services.activity_execution_state import _resolve_finalized_completed_at
from syntara.workflows.workflow_engine.services.activity_sync_service import ActivitySyncService


def _sub_wf_activity(
    name: str,
    started_at: datetime | None = None,
    status: ActivityStatus = ActivityStatus.PENDING,
) -> Mock:
    a = Mock()
    a.status = status
    a.activity_name = name
    a.started_at = started_at
    a.error_details = None
    a.node_type = NodeType.SUB_WORKFLOW
    return a


def _activity(name: str, status: ActivityStatus = ActivityStatus.PENDING) -> Mock:
    a = Mock()
    a.status = status
    a.activity_name = name
    a.started_at = None
    a.error_details = None
    return a


class TestFinalizeCompletedNodes:
    """Completed-node reconciliation and precedence."""

    def test_pending_sub_workflow_node_marked_completed(self) -> None:
        """A PENDING node in completed_node_ids becomes COMPLETED, not SKIPPED."""
        execution = Mock(spec=Execution)
        act = _activity("sub_wf_node")
        execution.activities = [act]

        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4(), None, {"sub_wf_node"})

        assert act.status == ActivityStatus.COMPLETED
        assert act.completed_at is not None
        assert act.started_at is None  # started_at must not be fabricated

    def test_failed_takes_precedence_over_completed(self) -> None:
        """A node in both failed_node_map and completed_node_ids is FAILED."""
        execution = Mock(spec=Execution)
        act = _activity("sub_wf_node")
        execution.activities = [act]

        ActivitySyncService._finalize_non_terminal_activities(
            execution, uuid4(), {"sub_wf_node": "child failed"}, {"sub_wf_node"}
        )

        assert act.status == ActivityStatus.FAILED
        assert act.error_details == "child failed"

    def test_completed_takes_precedence_over_skipped(self) -> None:
        """Completed node → COMPLETED; node absent from both sets → SKIPPED."""
        execution = Mock(spec=Execution)
        done = _activity("sub_wf_done")
        other = _activity("unrelated")
        execution.activities = [done, other]

        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4(), None, {"sub_wf_done"})

        assert done.status == ActivityStatus.COMPLETED
        assert other.status == ActivityStatus.SKIPPED

    def test_for_each_iteration_rows_all_completed(self) -> None:
        """All per-iteration composite rows for a completed base node → COMPLETED."""
        execution = Mock(spec=Execution)
        i0 = _activity("sub_wf_node#iter-0")
        i1 = _activity("sub_wf_node#iter-1")
        execution.activities = [i0, i1]

        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4(), None, {"sub_wf_node"})

        assert i0.status == ActivityStatus.COMPLETED
        assert i1.status == ActivityStatus.COMPLETED

    def test_for_each_mixed_order_a_failed_then_success(self) -> None:
        """Mixed loop (iter0 fails, iter1 succeeds): failure retained → FAILED aggregate.

        Engine state: base in failed_node_map (failure never cleared) AND in
        completed_node_ids (last iteration's namespace is 'completed').
        """
        execution = Mock(spec=Execution)
        row = _activity("sub_wf_node")
        execution.activities = [row]

        ActivitySyncService._finalize_non_terminal_activities(
            execution, uuid4(), {"sub_wf_node": "iter0 failed"}, {"sub_wf_node"}
        )

        assert row.status == ActivityStatus.FAILED  # must NOT report COMPLETED

    def test_for_each_mixed_order_b_success_then_failed(self) -> None:
        """Mixed loop (iter0 succeeds, iter1 fails): last namespace 'failed'.

        Engine state: base in failed_node_map, NOT in completed_node_ids.
        """
        execution = Mock(spec=Execution)
        row = _activity("sub_wf_node")
        execution.activities = [row]

        ActivitySyncService._finalize_non_terminal_activities(
            execution, uuid4(), {"sub_wf_node": "iter1 failed"}, set()
        )

        assert row.status == ActivityStatus.FAILED

    def test_existing_terminal_rows_untouched(self) -> None:
        """Rows already terminal are never changed (idempotency / no regression)."""
        execution = Mock(spec=Execution)
        already = _activity("sub_wf_node", status=ActivityStatus.COMPLETED)
        failed = _activity("other", status=ActivityStatus.FAILED)
        execution.activities = [already, failed]

        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4(), {"other": "x"}, {"other"})

        assert already.status == ActivityStatus.COMPLETED
        assert failed.status == ActivityStatus.FAILED

    def test_idempotent_second_pass_noop(self) -> None:
        """Running finalize twice does not change terminal rows."""
        execution = Mock(spec=Execution)
        act = _activity("sub_wf_node")
        execution.activities = [act]

        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4(), None, {"sub_wf_node"})
        first = act.status
        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4(), None, {"sub_wf_node"})

        assert first == ActivityStatus.COMPLETED
        assert act.status == ActivityStatus.COMPLETED

    def test_no_completed_set_preserves_legacy_skip(self) -> None:
        """Without completed_node_ids, a PENDING row still becomes SKIPPED (unchanged behavior)."""
        execution = Mock(spec=Execution)
        act = _activity("sub_wf_node")
        execution.activities = [act]

        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4())

        assert act.status == ActivityStatus.SKIPPED


def _completed_event(result_data: dict[str, object]) -> Mock:
    event = Mock()
    event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
    payload = Mock()
    payload.data = json.dumps(result_data).encode()
    event.workflow_execution_completed_event_attributes.result.payloads = [payload]
    return event


class TestExtractCompletedNodesFromEvent:
    """Payload fallback used when the get_completed_nodes query fails."""

    def test_reads_completed_nodes_field(self) -> None:
        """The authoritative completed_nodes field is returned verbatim."""
        event = _completed_event({"completed_nodes": ["sub_wf_node", "other"]})
        assert ActivitySyncService._extract_completed_nodes_from_event(event) == {"sub_wf_node", "other"}

    def test_empty_for_non_completed_event(self) -> None:
        """A non-COMPLETED terminal event carries no result payload fallback."""
        event = Mock()
        event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED
        assert ActivitySyncService._extract_completed_nodes_from_event(event) == set()

    def test_empty_when_no_payloads(self) -> None:
        """Missing result payloads yield an empty set."""
        event = Mock()
        event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
        event.workflow_execution_completed_event_attributes.result.payloads = []
        assert ActivitySyncService._extract_completed_nodes_from_event(event) == set()

    def test_empty_on_malformed_payload(self) -> None:
        """A non-JSON payload is handled gracefully."""
        event = Mock()
        event.event_type = EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
        payload = Mock()
        payload.data = b"not json"
        event.workflow_execution_completed_event_attributes.result.payloads = [payload]
        assert ActivitySyncService._extract_completed_nodes_from_event(event) == set()

    def test_sub_workflow_node_recovered_from_payload(self) -> None:
        """A successful sub-workflow node is recoverable from the payload (no query)."""
        event = _completed_event({"status": "completed", "completed_nodes": ["sub_wf_node"], "failed_activities": {}})
        assert "sub_wf_node" in ActivitySyncService._extract_completed_nodes_from_event(event)

    def test_skipped_node_not_marked_completed(self) -> None:
        """A disabled/skipped node in completed_activities but NOT in completed_nodes is excluded.

        Regression for the payload fallback: because it reads the positive
        completed_nodes marker (not completed_activities, which includes disabled
        nodes' empty namespaces), a genuinely skipped node is never marked
        COMPLETED even on a query-failure fallback.
        """
        event = _completed_event(
            {
                "completed_nodes": ["sub_wf_node"],
                "completed_activities": ["sub_wf_node", "disabled_node"],
                "failed_activities": {},
            }
        )
        result = ActivitySyncService._extract_completed_nodes_from_event(event)
        assert result == {"sub_wf_node"}
        assert "disabled_node" not in result

    def test_missing_completed_nodes_field_yields_empty(self) -> None:
        """A payload without completed_nodes (e.g. pre-upgrade) yields an empty set, never a wrong COMPLETED."""
        event = _completed_event({"completed_activities": ["sub_wf_node", "disabled_node"], "failed_activities": {}})
        assert ActivitySyncService._extract_completed_nodes_from_event(event) == set()


class TestResolveFinalizedCompletedAt:
    """Unit tests for the completed_at chosen when finalizing a sub-workflow node.

    The sub-workflow node's completed_at should be when its CHILD finished, not
    when the parent execution finalized (which also spans downstream parent
    steps). The helper falls back to ``now`` whenever a child time is absent or
    out of range, and never alters non-sub-workflow nodes.
    """

    NOW = datetime(2024, 1, 1, 0, 5, tzinfo=UTC)
    STARTED = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)

    def test_sub_workflow_uses_child_completion(self) -> None:
        """Child completed at 00:02 → node completed_at is 00:02, not finalization 00:05."""
        child_done = datetime(2024, 1, 1, 0, 2, tzinfo=UTC)
        act = _sub_wf_activity("sub_wf_node", started_at=self.STARTED)
        out = _resolve_finalized_completed_at(act, "sub_wf_node", {"sub_wf_node": child_done}, self.NOW)
        assert out == child_done

    def test_falls_back_to_now_without_child_time(self) -> None:
        """No child time (missing key, empty map, or None) → finalization time."""
        act = _sub_wf_activity("sub_wf_node", started_at=self.STARTED)
        assert _resolve_finalized_completed_at(act, "sub_wf_node", {}, self.NOW) == self.NOW
        assert _resolve_finalized_completed_at(act, "sub_wf_node", None, self.NOW) == self.NOW
        assert _resolve_finalized_completed_at(act, "sub_wf_node", {"other": self.STARTED}, self.NOW) == self.NOW

    def test_non_sub_workflow_node_always_uses_now(self) -> None:
        """A non-sub-workflow node ignores the map entirely (unchanged behavior)."""
        a = Mock()
        a.node_type = NodeType.SCRIPT
        a.started_at = None
        child_done = datetime(2024, 1, 1, 0, 2, tzinfo=UTC)
        assert _resolve_finalized_completed_at(a, "script_node", {"script_node": child_done}, self.NOW) == self.NOW

    def test_candidate_before_started_falls_back_to_now(self) -> None:
        """A child time earlier than the node's start (clock skew) is rejected."""
        started = datetime(2024, 1, 1, 0, 3, tzinfo=UTC)
        child_done = datetime(2024, 1, 1, 0, 1, tzinfo=UTC)
        act = _sub_wf_activity("n", started_at=started)
        assert _resolve_finalized_completed_at(act, "n", {"n": child_done}, self.NOW) == self.NOW

    def test_candidate_after_now_falls_back_to_now(self) -> None:
        """A child time later than finalization is clamped back to now (monotonic)."""
        future = datetime(2024, 1, 1, 0, 9, tzinfo=UTC)
        act = _sub_wf_activity("n", started_at=self.STARTED)
        assert _resolve_finalized_completed_at(act, "n", {"n": future}, self.NOW) == self.NOW

    def test_naive_child_time_is_coerced_to_utc_and_used(self) -> None:
        """A naive child datetime is made timezone-aware before comparison/use."""
        child_done_naive = datetime(2024, 1, 1, 0, 2)  # noqa: DTZ001 - deliberately naive
        act = _sub_wf_activity("n", started_at=self.STARTED)
        out = _resolve_finalized_completed_at(act, "n", {"n": child_done_naive}, self.NOW)
        assert out == datetime(2024, 1, 1, 0, 2, tzinfo=UTC)

    def test_started_at_none_still_uses_child_completion(self) -> None:
        """When started_at was not stamped, a valid child time (<= now) is still used."""
        child_done = datetime(2024, 1, 1, 0, 2, tzinfo=UTC)
        act = _sub_wf_activity("n", started_at=None)
        assert _resolve_finalized_completed_at(act, "n", {"n": child_done}, self.NOW) == child_done


class TestFinalizeUsesChildCompletion:
    """The finalizer wires child completion times through to completed_at."""

    def test_completed_sub_workflow_gets_child_completed_at(self) -> None:
        """A finalized-COMPLETED sub-workflow row records the child's completion, not now."""
        execution = Mock(spec=Execution)
        started = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        child_done = datetime(2024, 1, 1, 0, 2, tzinfo=UTC)
        act = _sub_wf_activity("sub_wf_node", started_at=started)
        execution.activities = [act]

        ActivitySyncService._finalize_non_terminal_activities(
            execution, uuid4(), None, {"sub_wf_node"}, {"sub_wf_node": child_done}
        )

        assert act.status == ActivityStatus.COMPLETED
        assert act.completed_at == child_done

    def test_for_each_rows_use_child_completion_by_base_node(self) -> None:
        """Per-iteration composite rows resolve completion via their base node id."""
        execution = Mock(spec=Execution)
        started = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        child_done = datetime(2024, 1, 1, 0, 3, tzinfo=UTC)
        i0 = _sub_wf_activity("sub_wf_node#iter-0", started_at=started)
        i1 = _sub_wf_activity("sub_wf_node#iter-1", started_at=started)
        execution.activities = [i0, i1]

        ActivitySyncService._finalize_non_terminal_activities(
            execution, uuid4(), None, {"sub_wf_node"}, {"sub_wf_node": child_done}
        )

        assert i0.completed_at == child_done
        assert i1.completed_at == child_done

    def test_without_map_completed_at_is_now_not_none(self) -> None:
        """Omitting the child map preserves prior behavior: completed_at is set (to now)."""
        execution = Mock(spec=Execution)
        act = _sub_wf_activity("sub_wf_node", started_at=datetime(2024, 1, 1, 0, 0, tzinfo=UTC))
        execution.activities = [act]

        ActivitySyncService._finalize_non_terminal_activities(execution, uuid4(), None, {"sub_wf_node"})

        assert act.status == ActivityStatus.COMPLETED
        assert act.completed_at is not None
