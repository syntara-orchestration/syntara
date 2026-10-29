"""Unit tests for completed-node precedence in _finalize_non_terminal_activities.

Precedence on completion for non-terminal activity rows:
    FAILED  (base node in failed_node_map)
    > COMPLETED  (base node in completed_node_ids)
    > SKIPPED  (default)

Sub-workflow nodes never emit an ACTIVITY_TASK_COMPLETED event, so their row
stays PENDING until finalization; completed_node_ids lets it be marked COMPLETED.
"""

import json
from unittest.mock import Mock
from uuid import uuid4

from temporalio.api.enums.v1 import EventType

from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.models.execution import Execution
from syntara.workflows.workflow_engine.services.activity_sync_service import ActivitySyncService


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
