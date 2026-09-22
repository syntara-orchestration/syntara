"""Unit tests for denied-node handling in OrchestratorWorkflow (ANSTRAT-1750, slice 4).

Covers:
- a denied node reaching terminal DENIED without executing anything;
- parallel siblings and other branches continuing;
- final status COMPLETED vs COMPLETED_WITH_ERRORS (F-23/AD-22);
- ``permission_check`` routing on the allowed/denied ports;
- the kill-switch check at activity start (AD-19);
- the denied-set re-check when a suspended run resumes (AD-12).

Follows the harness used by the other dynamic-workflow unit tests: Temporal's
``workflow`` module is mocked so the engine's own logic can be driven directly.
"""

import asyncio
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.graph import WorkflowGraph
from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend
from tests.unit.workflows.workflow_engine.conftest import init_workflow_runtime

DENIED_BY = "no-scripts"


@pytest.fixture(autouse=True)
def mock_workflow() -> Generator[MagicMock]:
    """Mock the Temporal workflow module used by the engine and its mixins."""
    mock_logger = MagicMock()
    with (
        patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf,
        patch("syntara.workflows.workflow_engine.converge_mixin.workflow", mock_wf),
    ):
        mock_wf.logger = mock_logger
        mock_wf.info.return_value = MagicMock(workflow_id="test-wf-id", run_id="test-run-id")
        mock_wf.patched.return_value = True
        mock_wf.execute_activity = AsyncMock(return_value={})
        mock_wf.execute_local_activity = AsyncMock(return_value=None)
        yield mock_wf


def _make_workflow(denied: dict[str, dict[str, Any]] | None = None) -> OrchestratorWorkflow:
    """Create an OrchestratorWorkflow with initialized state, bypassing __init__."""
    wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
    wf.execution_id = "exec-1"
    wf.request_id = None
    wf.skipped_nodes = set()
    wf.failed_nodes = {}
    wf.resolver = NamespaceResolver()
    wf.node_inputs = {}
    wf.node_control_data = {}
    wf.loop_state = {}
    wf.loop_body_map = {}
    wf.loop_iteration_results = {}
    wf._timeout_tasks = {}
    wf._timed_out_converge_nodes = set()
    wf._permission_check_results = {}
    wf._detached_nodes = set()
    wf._cof_failed_nodes = set()
    wf._converge_branch_nodes = {}
    wf._cancelled_node = None
    wf._secret_values = set()
    init_workflow_runtime(wf)
    wf.pre_resolved_outputs = {}
    wf.stop_after_nodes = set()
    wf._denied_node_kinds = dict(denied or {})
    wf._trigger_node_id = "trigger"
    wf._run_principal_id = "11111111-1111-4111-8111-111111111111"
    return wf


def _fanout_graph() -> WorkflowGraph:
    """Build: trigger -> (denied_node, sibling); denied_node -> downstream."""
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node("denied_node", {"id": "denied_node", "type": "script", "parameters": {}})
    backend.add_node("sibling", {"id": "sibling", "type": "script", "parameters": {}})
    backend.add_node("downstream", {"id": "downstream", "type": "script", "parameters": {}})
    backend.add_edge("trigger", "denied_node", None)
    backend.add_edge("trigger", "sibling", None)
    backend.add_edge("denied_node", "downstream", None)
    return WorkflowGraph(backend)


def _sole_path_graph() -> WorkflowGraph:
    """Build: trigger -> denied_node -> downstream (no other branch)."""
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node("denied_node", {"id": "denied_node", "type": "script", "parameters": {}})
    backend.add_node("downstream", {"id": "downstream", "type": "script", "parameters": {}})
    backend.add_edge("trigger", "denied_node", None)
    backend.add_edge("denied_node", "downstream", None)
    return WorkflowGraph(backend)


def _permission_check_graph() -> WorkflowGraph:
    """Build: trigger -> step -> check -> (allowed: ok, denied: fallback)."""
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node("step", {"id": "step", "type": "script", "parameters": {}})
    backend.add_node("check", {"id": "check", "type": "permission_check", "parameters": {}})
    backend.add_node("ok", {"id": "ok", "type": "script", "parameters": {}})
    backend.add_node("fallback", {"id": "fallback", "type": "script", "parameters": {}})
    backend.add_edge("trigger", "step", None)
    backend.add_edge("step", "check", None)
    backend.add_edge("check", "ok", {"from_port": "allowed"})
    backend.add_edge("check", "fallback", {"from_port": "denied"})
    return WorkflowGraph(backend)


def _run(coro: Any) -> Any:  # noqa: ANN401
    """Drive a coroutine to completion in a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _schedule(wf: OrchestratorWorkflow, node_id: str, graph: WorkflowGraph) -> dict[str, asyncio.Task[Any]]:
    """Run _schedule_successors for *node_id*, cancelling any tasks it created."""
    pending: dict[str, asyncio.Task[Any]] = {}
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(wf._schedule_successors(node_id, graph, pending))
    finally:
        for task in pending.values():
            task.cancel()
        loop.close()
    return pending


class TestDeniedNodeHandling:
    """A denied node is terminal, runs nothing, and only blocks its own branch."""

    def test_denied_node_is_terminal_and_never_scheduled(self) -> None:
        wf = _make_workflow({"denied_node": {"kind": "script", "denied_by": DENIED_BY}})
        graph = _fanout_graph()

        pending = _schedule(wf, "trigger", graph)

        assert "denied_node" in wf._denied_nodes
        assert "denied_node" not in pending
        namespace = wf.resolver.get_namespace("denied_node")
        assert namespace["status"] == "denied"
        assert namespace["error"] == {
            "code": "node_execute_denied",
            "kind": "script",
            "denied_by": DENIED_BY,
        }

    def test_parallel_sibling_still_runs(self) -> None:
        wf = _make_workflow({"denied_node": {"kind": "script", "denied_by": DENIED_BY}})
        graph = _fanout_graph()

        pending = _schedule(wf, "trigger", graph)

        assert "sibling" in pending
        assert "sibling" not in wf.skipped_nodes

    def test_downstream_on_the_denied_branch_is_skipped(self) -> None:
        wf = _make_workflow({"denied_node": {"kind": "script", "denied_by": DENIED_BY}})
        graph = _fanout_graph()

        _schedule(wf, "trigger", graph)

        assert "downstream" in wf.skipped_nodes

    def test_one_audit_event_per_denied_node(self, mock_workflow: MagicMock) -> None:
        wf = _make_workflow({"denied_node": {"kind": "script", "denied_by": DENIED_BY}})
        graph = _fanout_graph()

        _schedule(wf, "trigger", graph)

        audit_calls = [
            call
            for call in mock_workflow.execute_activity.await_args_list
            if str(call.kwargs.get("activity_id", "")).startswith("__internal__node_denied_")
        ]
        assert len(audit_calls) == 1
        assert audit_calls[0].kwargs["args"][:4] == ["exec-1", "denied_node", "script", DENIED_BY]

    def test_query_exposes_reached_denied_nodes_only(self) -> None:
        wf = _make_workflow(
            {
                "denied_node": {"kind": "script", "denied_by": DENIED_BY},
                "never_reached": {"kind": "script", "denied_by": DENIED_BY},
            }
        )
        _schedule(wf, "trigger", _fanout_graph())

        assert wf.get_denied_nodes() == {"denied_node": {"kind": "script", "denied_by": DENIED_BY}}

    def test_no_denials_leaves_scheduling_untouched(self) -> None:
        wf = _make_workflow()
        pending = _schedule(wf, "trigger", _fanout_graph())

        assert set(pending) == {"denied_node", "sibling"}
        assert wf.get_denied_nodes() == {}


class TestFinalStatus:
    """Denial alone never fails a run (F-23/AD-22)."""

    def test_completed_when_another_branch_finished(self) -> None:
        wf = _make_workflow({"denied_node": {"kind": "script", "denied_by": DENIED_BY}})
        _schedule(wf, "trigger", _fanout_graph())
        wf.resolver.set_namespace("sibling", {"status": "completed"})

        result = wf._build_result("exec-1", include_node_results=False)

        assert result["status"] == "completed"
        assert result["failed_activities"] == {}
        assert "denied_node" in result["denied_activities"]
        assert "node_execute_denied" in result["denied_activities"]["denied_node"]

    def test_completed_with_errors_when_denial_was_the_only_path(self) -> None:
        wf = _make_workflow({"denied_node": {"kind": "script", "denied_by": DENIED_BY}})
        _schedule(wf, "trigger", _sole_path_graph())

        result = wf._build_result("exec-1", include_node_results=False)

        assert result["status"] == "completed_with_errors"
        assert result["failed_activities"] == {}
        assert list(result["denied_activities"]) == ["denied_node"]

    def test_trigger_output_alone_does_not_count_as_another_branch(self) -> None:
        wf = _make_workflow({"denied_node": {"kind": "script", "denied_by": DENIED_BY}})
        _schedule(wf, "trigger", _sole_path_graph())
        wf.resolver.set_namespace("trigger", {"status": "completed"})

        assert wf._build_result("exec-1", include_node_results=False)["status"] == "completed_with_errors"

    def test_clean_run_is_completed(self) -> None:
        wf = _make_workflow()
        wf.resolver.set_namespace("sibling", {"status": "completed"})

        assert wf._build_result("exec-1", include_node_results=False)["status"] == "completed"


class TestPermissionCheckNode:
    """permission_check evaluates the node feeding its single incoming edge."""

    def test_routes_denied_when_upstream_was_denied(self) -> None:
        wf = _make_workflow({"step": {"kind": "script", "denied_by": DENIED_BY}})
        graph = _permission_check_graph()

        _schedule(wf, "trigger", graph)
        result = wf._execute_permission_check_node(graph.get_node("check"), graph)
        assert wf.get_permission_check_results() == {"check": result["output"]}

        assert result["control"] == {"next_port": "denied"}
        assert result["output"]["allowed"] is False
        assert result["output"]["checked_node_id"] == "step"
        assert result["output"]["denied_by"] == DENIED_BY

    def test_routes_allowed_when_upstream_ran(self) -> None:
        wf = _make_workflow()
        graph = _permission_check_graph()
        wf.resolver.set_namespace("step", {"status": "completed"})

        result = wf._execute_permission_check_node(graph.get_node("check"), graph)

        assert result["control"] == {"next_port": "allowed"}
        assert result["output"]["allowed"] is True
        assert "denied_by" not in result["output"]

    def test_still_scheduled_downstream_of_a_denied_node(self) -> None:
        wf = _make_workflow({"step": {"kind": "script", "denied_by": DENIED_BY}})
        graph = _permission_check_graph()

        pending = _schedule(wf, "trigger", graph)

        assert "check" in pending
        assert "check" not in wf.skipped_nodes

    def test_denied_port_skips_the_allowed_branch(self) -> None:
        wf = _make_workflow({"step": {"kind": "script", "denied_by": DENIED_BY}})
        graph = _permission_check_graph()
        wf.resolver.set_namespace("check", {"status": "completed"})
        wf.node_control_data["check"] = {"next_port": "denied"}

        pending = _schedule(wf, "check", graph)

        assert "fallback" in pending
        assert "ok" in wf.skipped_nodes

    def test_dispatch_routes_permission_check_without_an_activity(self, mock_workflow: MagicMock) -> None:
        wf = _make_workflow({"step": {"kind": "script", "denied_by": DENIED_BY}})
        graph = _permission_check_graph()
        wf._denied_nodes["step"] = {"kind": "script", "denied_by": DENIED_BY}

        result = _run(wf._dispatch_node_to_executor(graph.get_node("check"), {}, graph, 60))

        assert result["control"] == {"next_port": "denied"}
        mock_workflow.execute_activity.assert_not_awaited()


class TestKillSwitchAtActivityStart:
    """Every executor node re-reads the kill switch before its activity runs (AD-19)."""

    def test_checks_the_kind_before_dispatching_an_action_node(self, mock_workflow: MagicMock) -> None:
        wf = _make_workflow()
        node = _fanout_graph().get_node("sibling")

        _run(wf._execute_executor_node(node, "script", {}, None, 60))

        mock_workflow.execute_local_activity.assert_awaited_once()
        call = mock_workflow.execute_local_activity.await_args
        assert call.kwargs["activity_id"] == "__internal__node_kind_enabled_sibling"
        assert call.kwargs["args"] == ["script"]
        # The executor activity still runs, and only once.
        mock_workflow.execute_activity.assert_awaited_once()

    def test_skips_the_check_for_flow_control_kinds(self, mock_workflow: MagicMock) -> None:
        wf = _make_workflow()
        backend = InMemoryGraphBackend()
        backend.add_node("cond", {"id": "cond", "type": "condition", "parameters": {}})
        node = WorkflowGraph(backend).get_node("cond")

        _run(wf._execute_executor_node(node, "condition", {}, None, 60))

        mock_workflow.execute_local_activity.assert_not_awaited()

    def test_disabled_kind_prevents_the_executor_activity(self, mock_workflow: MagicMock) -> None:
        from temporalio.exceptions import ApplicationError

        wf = _make_workflow()
        node = _fanout_graph().get_node("sibling")
        failure = ApplicationError(
            "Node kind 'script' is disabled (node_kind_disabled)",
            type="NodeKindDisabledError",
            non_retryable=True,
        )
        mock_workflow.execute_local_activity = AsyncMock(side_effect=failure)

        with pytest.raises(ApplicationError, match="node_kind_disabled"):
            _run(wf._execute_executor_node(node, "script", {}, None, 60))

        mock_workflow.execute_activity.assert_not_awaited()


class TestResumeRecheck:
    """A suspension re-evaluates the denied set before the run continues (AD-12)."""

    def test_recheck_replaces_the_denied_set(self, mock_workflow: MagicMock) -> None:
        wf = _make_workflow({"old_node": {"kind": "script", "denied_by": "stale"}})
        mock_workflow.execute_activity = AsyncMock(
            return_value=[{"node_id": "new_node", "kind": "http_request", "denied_by": "fresh"}]
        )

        _run(wf._recheck_denied_nodes("approval_node"))

        assert wf._denied_node_kinds == {"new_node": {"kind": "http_request", "denied_by": "fresh"}}

    def test_recheck_clears_the_set_when_the_policy_was_removed(self, mock_workflow: MagicMock) -> None:
        wf = _make_workflow({"old_node": {"kind": "script", "denied_by": "stale"}})
        mock_workflow.execute_activity = AsyncMock(return_value=[])

        _run(wf._recheck_denied_nodes("approval_node"))

        assert wf._denied_node_kinds == {}

    def test_recheck_keeps_the_launch_time_set_when_the_activity_fails(self, mock_workflow: MagicMock) -> None:
        launch_set = {"old_node": {"kind": "script", "denied_by": "stale"}}
        wf = _make_workflow(launch_set)
        mock_workflow.execute_activity = AsyncMock(side_effect=RuntimeError("temporal down"))

        _run(wf._recheck_denied_nodes("approval_node"))

        assert wf._denied_node_kinds == launch_set

    def test_recheck_is_a_no_op_without_a_run_principal(self, mock_workflow: MagicMock) -> None:
        wf = _make_workflow()
        wf._run_principal_id = ""

        _run(wf._recheck_denied_nodes("approval_node"))

        mock_workflow.execute_activity.assert_not_awaited()


class TestStateInitialisation:
    """The launch-time list is indexed by node ID and tolerates junk."""

    def test_indexes_entries_and_drops_malformed_ones(self) -> None:
        indexed = OrchestratorWorkflow._index_denied_nodes(
            [
                {"node_id": "a", "kind": "script", "denied_by": "p"},
                {"kind": "script", "denied_by": "p"},
                {"node_id": "", "kind": "script"},
            ]
        )
        assert indexed == {"a": {"kind": "script", "denied_by": "p"}}

    def test_none_yields_an_empty_index(self) -> None:
        assert OrchestratorWorkflow._index_denied_nodes(None) == {}
