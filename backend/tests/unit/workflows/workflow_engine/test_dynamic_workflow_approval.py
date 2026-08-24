"""Unit tests for OrchestratorWorkflow approval context preparation methods.

Tests cover:
- _get_previous_step_context: building previous step context for approval requests
- _prepare_approval_args: assembling the full argument list for create_approval_request_activity
- _execute_approval_node: dispatch routing and error handling for invalid decisions
- _handle_node_failure: handling bare ApplicationError raised from workflow code
"""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph
from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName
from tests.unit.workflows.workflow_engine.conftest import init_workflow_runtime


@pytest.fixture(autouse=True)
def _mock_temporal_workflow() -> Generator[MagicMock]:
    """Mock the Temporal workflow module."""
    mock_logger = MagicMock()
    with (
        patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf,
        patch("syntara.workflows.workflow_engine.approval_mixin.workflow", mock_wf),
    ):
        mock_wf.logger = mock_logger
        mock_wf.info.return_value = MagicMock(workflow_id="test-wf-id")
        mock_wf.now.return_value = datetime(2026, 4, 10, 12, 0, 0, tzinfo=UTC)
        yield mock_wf


def _make_workflow(
    execution_id: str = "exec-123",
    resolver: NamespaceResolver | None = None,
) -> OrchestratorWorkflow:
    """Create an OrchestratorWorkflow with initialized state, bypassing __init__."""
    wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
    wf.execution_id = execution_id
    wf._project_id = "00000000-0000-0000-0000-000000000001"
    wf.skipped_nodes = set()
    wf.failed_nodes = {}
    wf.resolver = resolver if resolver is not None else NamespaceResolver()
    wf.node_inputs = {}
    wf.node_control_data = {}
    wf.loop_state = {}
    wf.loop_body_map = {}
    wf.loop_iteration_results = {}
    wf._timeout_tasks = {}
    wf._timed_out_converge_nodes = set()
    wf._detached_nodes = set()
    wf._converge_branch_nodes = {}
    init_workflow_runtime(wf)
    wf.pre_resolved_outputs = {}
    wf.stop_after_nodes = set()
    return wf


def _build_approval_graph(*, with_predecessor: bool = True, with_successor: bool = True) -> WorkflowGraph:
    """Build a graph with an approval node.

    Structure: trigger -> [scan ->] approval -> [deploy]
    """
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node(
        "approval",
        {
            "id": "approval",
            "type": "approval",
            "name": "Review Deployment",
            "parameters": {},
        },
    )

    if with_predecessor:
        backend.add_node(
            "scan",
            {"id": "scan", "type": "script", "name": "Security Scan", "parameters": {}},
        )
        backend.add_edge("trigger", "scan", None)
        backend.add_edge("scan", "approval", None)
    else:
        backend.add_edge("trigger", "approval", None)

    if with_successor:
        backend.add_node(
            "deploy",
            {"id": "deploy", "type": "script", "name": "Deploy to Prod", "parameters": {}},
        )
        backend.add_edge("approval", "deploy", {"from_port": "approved"})

    graph = WorkflowGraph(backend)
    graph.metadata = {"name": "Production Pipeline"}
    return graph


class TestGetPreviousStepContext:
    """Tests for _get_previous_step_context method."""

    def test_returns_none_when_no_predecessors(self) -> None:
        """Approval node with no predecessors returns None."""
        wf = _make_workflow()

        backend = InMemoryGraphBackend()
        backend.add_node("orphan", {"id": "orphan", "type": "approval", "parameters": {}})
        isolated_graph = WorkflowGraph(backend)

        result = wf._get_previous_step_context("orphan", isolated_graph)
        assert result is None

    def test_returns_predecessor_context_with_output(self) -> None:
        """Returns predecessor id, name, type, and output."""
        resolver = NamespaceResolver()
        resolver.set_namespace("scan", {"vulnerabilities": 0, "passed": True})
        wf = _make_workflow(resolver=resolver)
        graph = _build_approval_graph()

        result = wf._get_previous_step_context("approval", graph)

        assert result is not None
        assert result["id"] == "scan"
        assert result["name"] == "Security Scan"
        assert result["type"] == "script"
        assert result["output"] == {"vulnerabilities": 0, "passed": True}

    def test_uses_node_id_when_name_missing(self) -> None:
        """Falls back to node ID when config has no name."""
        wf = _make_workflow()
        backend = InMemoryGraphBackend()
        backend.add_node("prev_node", {"id": "prev_node", "type": "task", "parameters": {}})
        backend.add_node("approval", {"id": "approval", "type": "approval", "parameters": {}})
        backend.add_edge("prev_node", "approval", None)
        graph = WorkflowGraph(backend)

        result = wf._get_previous_step_context("approval", graph)

        assert result is not None
        assert result["name"] == "prev_node"

    def test_returns_none_output_when_namespace_missing(self) -> None:
        """Output is None when predecessor hasn't executed yet."""
        wf = _make_workflow()
        graph = _build_approval_graph()

        result = wf._get_previous_step_context("approval", graph)

        assert result is not None
        assert result["id"] == "scan"
        assert result["output"] is None

    def test_returns_failed_status_when_predecessor_failed(self) -> None:
        """Output includes failure info when predecessor failed (via resolver)."""
        resolver = NamespaceResolver()
        resolver.set_namespace("scan", {"status": "failed", "error": "Script exited with code 1"})
        wf = _make_workflow(resolver=resolver)
        graph = _build_approval_graph()

        result = wf._get_previous_step_context("approval", graph)

        assert result is not None
        assert result["id"] == "scan"
        assert result["output"] == {"status": "failed", "error": "Script exited with code 1"}

    def test_returns_skipped_status_when_predecessor_skipped(self) -> None:
        """Output includes skipped status when predecessor was skipped."""
        wf = _make_workflow()
        wf.skipped_nodes.add("scan")
        graph = _build_approval_graph()

        result = wf._get_previous_step_context("approval", graph)

        assert result is not None
        assert result["id"] == "scan"
        assert result["output"] == {"status": "skipped"}


class TestPrepareApprovalArgs:
    """Tests for _prepare_approval_args method."""

    @pytest.mark.asyncio
    async def test_basic_approval_args(self) -> None:
        """Returns 9-element arg list with correct structure (added approver_user_ids and approver_group_ids)."""
        resolver = NamespaceResolver()
        resolver.set_namespace("trigger", {"env": "production"})
        wf = _make_workflow(execution_id="exec-456", resolver=resolver)
        graph = _build_approval_graph()
        node = ActivityNode("approval", "approval", {}, name="Review Deployment")

        # When no approvers configured, the resolution activity is skipped (optimization)
        # and approver IDs are set to None
        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_approval_args(node, graph, node.parameters)

        assert len(args) == 10
        assert args[0] == "exec-456"  # execution_id
        assert args[1] == "approval"  # approval_node_id
        assert args[2] == "Review Deployment"  # name
        assert args[7] is None  # approver_user_ids (None when no approvers configured)
        assert args[8] is None  # approver_group_ids (None when no approvers configured)

    @pytest.mark.asyncio
    async def test_approval_args_with_approver_config(self) -> None:
        """Approver users and groups are correctly resolved to UUIDs."""
        from uuid import uuid4

        wf = _make_workflow()
        graph = _build_approval_graph()
        config = {
            "approver_users": ["alice", "bob"],
            "approver_groups": ["security-team", "admins"],
        }
        node = ActivityNode("approval", "approval", config, name="Security Review")

        alice_id = str(uuid4())
        bob_id = str(uuid4())
        security_team_id = str(uuid4())
        admins_id = str(uuid4())

        mock_execute = AsyncMock(
            return_value={"user_ids": [alice_id, bob_id], "group_ids": [security_team_id, admins_id]}
        )
        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_approval_args(node, graph, config)

        assert len(args) == 10
        assert args[7] == [alice_id, bob_id]  # approver_user_ids
        assert args[8] == [security_team_id, admins_id]  # approver_group_ids

        # Verify the resolution activity was called with the correct arguments
        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args.kwargs
        assert call_kwargs["args"] == [["alice", "bob"], ["security-team", "admins"]]

    @pytest.mark.asyncio
    async def test_next_step_approved_from_successor(self) -> None:
        """next_step_approved built from first graph successor."""
        wf = _make_workflow()
        graph = _build_approval_graph()
        node = ActivityNode("approval", "approval", {}, name="Review")

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_approval_args(node, graph, node.parameters)

        next_step = args[3]
        assert next_step["id"] == "deploy"
        assert next_step["name"] == "Deploy to Prod"
        assert next_step["type"] == "script"

    @pytest.mark.asyncio
    async def test_raises_when_no_approved_successor(self) -> None:
        """Raises SafeValueError when approval node has no approved successor."""
        from syntara.core.exceptions import SafeValueError

        wf = _make_workflow()
        graph = _build_approval_graph(with_successor=False)
        node = ActivityNode("approval", "approval", {}, name="Review")

        with pytest.raises(SafeValueError, match="has no approved successor"):
            await wf._prepare_approval_args(node, graph, node.parameters)

    @pytest.mark.asyncio
    async def test_workflow_context_populated(self) -> None:
        """Workflow context includes name and trigger inputs."""
        resolver = NamespaceResolver()
        resolver.set_namespace("trigger", {"target": "prod", "version": "2.0"})
        wf = _make_workflow(resolver=resolver)
        graph = _build_approval_graph()
        node = ActivityNode("approval", "approval", {}, name="Review")

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_approval_args(node, graph, node.parameters)

        ctx = args[4]
        assert ctx["workflow_name"] == "Production Pipeline"
        assert ctx["inputs"] == {"target": "prod", "version": "2.0"}
        assert ctx["workflow_id"] is not None

    @pytest.mark.asyncio
    async def test_workflow_context_includes_workflow_id_and_version(self) -> None:
        """workflow_id and workflow_version are read from the workflow_context.workflow namespace.

        Regression test for AAP-85146: the approvals UI links to
        /workflow-builder/{workflow_id}, so these fields must be populated
        from the parent workflow.
        """
        from uuid import uuid4

        workflow_id = str(uuid4())
        resolver = NamespaceResolver()
        resolver.set_namespace(
            "workflow_context",
            {
                "workflow": {"id": workflow_id, "version": 5},
                "execution": {"workflow_version_id": "wfv-789"},
            },
        )
        wf = _make_workflow(resolver=resolver)
        graph = _build_approval_graph()
        node = ActivityNode("approval", "approval", {}, name="Review")

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_approval_args(node, graph, node.parameters)

        ctx = args[4]
        assert ctx["workflow_id"] == workflow_id
        assert ctx["workflow_version"] == 5
        assert "workflow_version_id" not in ctx

    @pytest.mark.asyncio
    async def test_workflow_context_falls_back_to_execution_workflow_version_id(self) -> None:
        """workflow_id falls back to execution.workflow_version_id when workflow.id is absent."""
        resolver = NamespaceResolver()
        resolver.set_namespace(
            "workflow_context",
            {
                "execution": {"workflow_version_id": "wfv-fallback"},
            },
        )
        wf = _make_workflow(resolver=resolver)
        graph = _build_approval_graph()
        node = ActivityNode("approval", "approval", {}, name="Review")

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_approval_args(node, graph, node.parameters)

        ctx = args[4]
        assert ctx["workflow_id"] == "wfv-fallback"
        assert ctx["workflow_version"] is None

    @pytest.mark.asyncio
    async def test_workflow_context_empty_inputs_when_trigger_missing(self) -> None:
        """Inputs default to empty dict when trigger namespace is missing."""
        wf = _make_workflow()
        graph = _build_approval_graph()
        node = ActivityNode("approval", "approval", {}, name="Review")

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_approval_args(node, graph, node.parameters)

        ctx = args[4]
        assert ctx["inputs"] == {}

    @pytest.mark.asyncio
    async def test_timeout_at_computed_from_decision_window(self) -> None:
        """timeout_at is ISO string set to now + decision_window when configured."""
        wf = _make_workflow()
        graph = _build_approval_graph()
        node = ActivityNode("approval", "approval", {"decision_window": 3600}, name="Review")

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_approval_args(node, graph, node.parameters)

        timeout_at = args[5]
        assert timeout_at is not None
        parsed = datetime.fromisoformat(timeout_at)
        mock_now = datetime(2026, 4, 10, 12, 0, 0, tzinfo=UTC)
        assert parsed == mock_now + timedelta(seconds=3600)

    @pytest.mark.asyncio
    async def test_timeout_at_defaults_to_catalog_value_when_not_configured(self) -> None:
        """timeout_at falls back to the catalog default (86400s) when approver_timeout is absent."""
        wf = _make_workflow()
        graph = _build_approval_graph()
        node = ActivityNode("approval", "approval", {}, name="Review")

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_approval_args(node, graph, node.parameters)

        timeout_at = args[5]
        assert timeout_at is not None
        parsed = datetime.fromisoformat(timeout_at)
        mock_now = datetime(2026, 4, 10, 12, 0, 0, tzinfo=UTC)
        assert parsed == mock_now + timedelta(seconds=86400)

    @pytest.mark.asyncio
    async def test_next_step_rejected_always_none(self) -> None:
        """next_step_rejected is None (port-based routing not yet implemented)."""
        wf = _make_workflow()
        graph = _build_approval_graph()
        node = ActivityNode("approval", "approval", {}, name="Review")

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_approval_args(node, graph, node.parameters)

        assert args[6] is None

    @pytest.mark.asyncio
    async def test_name_fallback_to_node_id(self) -> None:
        """Name falls back to 'Approval for {id}' when config has no name."""
        wf = _make_workflow()
        backend = InMemoryGraphBackend()
        backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
        backend.add_node("my_approval", {"id": "my_approval", "type": "approval", "parameters": {}})
        backend.add_node("next", {"id": "next", "type": "script", "name": "Next Step", "parameters": {}})
        backend.add_edge("trigger", "my_approval", None)
        backend.add_edge("my_approval", "next", {"from_port": "approved"})
        graph = WorkflowGraph(backend)
        graph.metadata = {"name": "Test"}
        node = ActivityNode("my_approval", "approval", {})

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_approval_args(node, graph, node.parameters)

        assert args[2] == "Approval for my_approval"

    @pytest.mark.asyncio
    async def test_workflow_name_fallback_to_unknown(self) -> None:
        """Workflow name defaults to 'Unknown' when metadata has no name."""
        wf = _make_workflow()
        graph = _build_approval_graph()
        graph.metadata = {}
        node = ActivityNode("approval", "approval", {}, name="Review")

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_approval_args(node, graph, node.parameters)

        ctx = args[4]
        assert ctx["workflow_name"] == "Unknown"

    @pytest.mark.asyncio
    async def test_workflow_name_fallback_when_none(self) -> None:
        """Workflow name defaults to 'Unknown' when metadata name is None."""
        wf = _make_workflow()
        graph = _build_approval_graph()
        graph.metadata = {"name": None}
        node = ActivityNode("approval", "approval", {}, name="Review")

        mock_execute = AsyncMock(return_value={"user_ids": [], "group_ids": []})
        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_execute):
            args = await wf._prepare_approval_args(node, graph, node.parameters)

        ctx = args[4]
        assert ctx["workflow_name"] == "Unknown"


class TestDispatchApprovalNode:
    """Tests for approval node dispatch integration."""

    @pytest.mark.asyncio
    async def test_dispatch_passes_prepared_args_to_activity(self) -> None:
        """Verify _dispatch_node passes _prepare_approval_args to execute_activity."""
        resolver = NamespaceResolver()
        resolver.set_namespace("trigger", {"env": "prod"})
        wf = _make_workflow(execution_id="exec-789", resolver=resolver)
        graph = _build_approval_graph()
        node = graph.get_node("approval")

        # When no approvers configured, only the create approval activity is called
        # (resolution activity is skipped as an optimization)
        mock_activity = AsyncMock(return_value={"output": {"id": "apr-1", "decision": "approved"}})

        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_activity):
            await wf._dispatch_node_to_executor(node, {}, graph, timeout_seconds=300)

        # With no approvers configured, only approval creation is called (resolution is skipped)
        assert mock_activity.call_count == 1

        # Check the approval creation call
        approval_call = mock_activity.call_args_list[0]
        assert approval_call.args[0] == ActivityName.APPROVAL
        activity_args = approval_call.kwargs["args"]
        assert len(activity_args) == 10
        assert activity_args[0] == "exec-789"  # execution_id
        assert activity_args[1] == "approval"  # approval_node_id
        assert activity_args[2] == "Review Deployment"  # name (from node.name)
        assert activity_args[3]["id"] == "deploy"  # next_step_approved
        assert activity_args[4]["workflow_name"] == "Production Pipeline"  # workflow_context

    @pytest.mark.asyncio
    async def test_dispatch_sets_approved_port(self) -> None:
        """Verify approval dispatch sets control.next_port for approved status."""
        wf = _make_workflow()
        graph = _build_approval_graph()
        node = graph.get_node("approval")

        mock_activity = AsyncMock(return_value={"output": {"decision": "approved", "approval_id": "apr-1"}})

        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_activity):
            result = await wf._dispatch_node_to_executor(node, {}, graph, timeout_seconds=300)

        assert result["control"] == {"next_port": "approved"}

    @pytest.mark.asyncio
    async def test_dispatch_sets_rejected_port(self) -> None:
        """Verify approval dispatch sets control.next_port for rejected status."""
        wf = _make_workflow()
        graph = _build_approval_graph()
        node = graph.get_node("approval")

        mock_activity = AsyncMock(return_value={"output": {"decision": "rejected", "approval_id": "apr-1"}})

        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_activity):
            result = await wf._dispatch_node_to_executor(node, {}, graph, timeout_seconds=300)

        assert result["control"] == {"next_port": "rejected"}


class TestExpireRemainingApprovals:
    """Tests for _expire_remaining_approvals (called when a workflow run ends)."""

    @pytest.mark.asyncio
    async def test_expires_all_pending_approvals_for_execution(self) -> None:
        """Calls EXPIRE_APPROVAL with no node_id filter, scoped to the execution."""
        wf = _make_workflow(execution_id="exec-789")
        graph = _build_approval_graph(with_predecessor=False, with_successor=False)
        wf._detached_nodes = {"approval"}
        mock_activity = AsyncMock(return_value={"expired_count": 1})
        mock_local_activity = AsyncMock(return_value=None)

        with (
            patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_activity),
            patch(
                "syntara.workflows.workflow_engine.approval_mixin.workflow.execute_local_activity",
                mock_local_activity,
            ),
        ):
            await wf._expire_remaining_approvals(graph)

        mock_activity.assert_called_once()
        assert mock_activity.call_args.args[0] == ActivityName.EXPIRE_APPROVAL
        assert mock_activity.call_args.kwargs["args"] == ["exec-789", None]

    @pytest.mark.asyncio
    async def test_no_op_when_nothing_detached(self) -> None:
        """No EXPIRE_APPROVAL call at all when no node was detached.

        This is the case for an approval that already resolved via its own
        timeout or a normal decision — it must not trigger a redundant
        execution-wide expire sweep.
        """
        wf = _make_workflow(execution_id="exec-789")
        graph = _build_approval_graph(with_predecessor=False, with_successor=False)
        mock_activity = AsyncMock(return_value={"expired_count": 0})

        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_activity):
            await wf._expire_remaining_approvals(graph)

        mock_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_swallows_activity_failure(self) -> None:
        """Failures are best-effort and must not propagate to the caller."""
        wf = _make_workflow()
        graph = _build_approval_graph(with_predecessor=False, with_successor=False)
        wf._detached_nodes = {"approval"}
        mock_activity = AsyncMock(side_effect=RuntimeError("boom"))
        mock_local_activity = AsyncMock(return_value=None)

        with (
            patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_activity),
            patch(
                "syntara.workflows.workflow_engine.approval_mixin.workflow.execute_local_activity",
                mock_local_activity,
            ),
        ):
            await wf._expire_remaining_approvals(graph)

    @pytest.mark.asyncio
    async def test_fails_temporal_activity_for_detached_approval_node(self) -> None:
        """A detached approval node's Temporal activity is failed via local activity."""
        wf = _make_workflow(execution_id="exec-789")
        graph = _build_approval_graph(with_predecessor=False, with_successor=False)
        wf._detached_nodes = {"approval"}
        mock_execute_activity = AsyncMock(return_value={"expired_count": 1})
        mock_execute_local_activity = AsyncMock(return_value=None)

        with (
            patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_execute_activity),
            patch(
                "syntara.workflows.workflow_engine.approval_mixin.workflow.execute_local_activity",
                mock_execute_local_activity,
            ),
        ):
            await wf._expire_remaining_approvals(graph)

        mock_execute_local_activity.assert_called_once()
        assert mock_execute_local_activity.call_args.kwargs["args"][2] == "approval"

    @pytest.mark.asyncio
    async def test_skips_non_approval_detached_nodes(self) -> None:
        """Detached nodes that aren't approval-type are not passed to the fail-activity call."""
        wf = _make_workflow(execution_id="exec-789")
        graph = _build_approval_graph(with_predecessor=True, with_successor=False)
        wf._detached_nodes = {"scan"}  # a "script" typed node, not an approval
        mock_execute_activity = AsyncMock(return_value={"expired_count": 0})
        mock_execute_local_activity = AsyncMock(return_value=None)

        with (
            patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_execute_activity),
            patch(
                "syntara.workflows.workflow_engine.approval_mixin.workflow.execute_local_activity",
                mock_execute_local_activity,
            ),
        ):
            await wf._expire_remaining_approvals(graph)

        mock_execute_local_activity.assert_not_called()
        mock_execute_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_raises_on_unexpected_decision(self) -> None:
        """Verify unexpected approval decision raises ApplicationError with output in details."""
        wf = _make_workflow()
        graph = _build_approval_graph()
        node = graph.get_node("approval")

        mock_activity = AsyncMock(return_value={"output": {"decision": "cancelled", "decided_by": "admin"}})

        with (
            patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_activity),
            pytest.raises(ApplicationError, match="invalid decision 'cancelled'") as exc_info,
        ):
            await wf._dispatch_node_to_executor(node, {}, graph, timeout_seconds=300)

        err = exc_info.value
        assert err.type == "InvalidApprovalDecisionError"
        assert err.non_retryable
        details = list(err.details)
        assert len(details) == 1
        assert details[0]["output"]["decision"] == "cancelled"
        assert details[0]["output"]["decided_by"] == "admin"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("approval_status", ["approved", "rejected"])
    async def test_dispatch_sets_control_data_from_approval_decision(self, approval_status: str) -> None:
        """Verify _dispatch_node adds control data with next_port from approval decision."""
        wf = _make_workflow()
        graph = _build_approval_graph()
        node = graph.get_node("approval")

        mock_activity = AsyncMock(return_value={"output": {"decision": approval_status, "approval_id": "apr-1"}})

        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_activity):
            result = await wf._dispatch_node_to_executor(node, {}, graph, timeout_seconds=300)

        assert "control" in result
        assert result["control"]["next_port"] == approval_status

    @pytest.mark.asyncio
    async def test_dispatch_raises_on_missing_decision(self) -> None:
        """Verify missing decision field raises ApplicationError with output in details."""
        wf = _make_workflow()
        graph = _build_approval_graph()
        node = graph.get_node("approval")

        mock_activity = AsyncMock(return_value={"output": {"approval_id": "apr-1"}})

        with (
            patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_activity),
            pytest.raises(ApplicationError, match="invalid decision 'None'") as exc_info,
        ):
            await wf._dispatch_node_to_executor(node, {}, graph, timeout_seconds=300)

        err = exc_info.value
        assert err.type == "InvalidApprovalDecisionError"
        assert err.non_retryable
        details = list(err.details)
        assert len(details) == 1
        assert "output" in details[0]

    @pytest.mark.asyncio
    async def test_dispatch_transforms_output_to_match_result_schema(self) -> None:
        """Verify signal payload is fully transformed to match approval resultSchema."""
        wf = _make_workflow()
        graph = _build_approval_graph()
        node = graph.get_node("approval")

        mock_activity = AsyncMock(
            return_value={
                "output": {
                    "decision": "approved",
                    "decided_by": "jsmith",
                    "decided_at": "2026-05-20T10:00:00+00:00",
                    "decision_notes": "LGTM",
                }
            }
        )

        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_activity):
            result = await wf._dispatch_node_to_executor(node, {}, graph, timeout_seconds=300)

        output = result["output"]
        assert output["status"] == "completed"
        assert output["decision"] == "approved"
        assert output["decided_by"] == "jsmith"
        assert output["decided_at"] == "2026-05-20T10:00:00+00:00"
        assert output["decision_notes"] == "LGTM"

    @pytest.mark.asyncio
    async def test_dispatch_transforms_output_without_notes(self) -> None:
        """Verify decision_notes key is absent (not None) when notes not provided."""
        wf = _make_workflow()
        graph = _build_approval_graph()
        node = graph.get_node("approval")

        mock_activity = AsyncMock(
            return_value={
                "output": {
                    "decision": "rejected",
                    "decided_by": "jsmith",
                    "decided_at": "2026-05-20T10:00:00+00:00",
                }
            }
        )

        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_activity):
            result = await wf._dispatch_node_to_executor(node, {}, graph, timeout_seconds=300)

        output = result["output"]
        assert output["status"] == "completed"
        assert output["decision"] == "rejected"
        assert output["decided_by"] == "jsmith"
        assert output["decided_at"] == "2026-05-20T10:00:00+00:00"
        assert "decision_notes" not in output

    @pytest.mark.asyncio
    async def test_dispatch_truncates_oversized_decision_notes(self) -> None:
        """Verify decision_notes longer than 2000 chars are truncated at the boundary."""
        wf = _make_workflow()
        graph = _build_approval_graph()
        node = graph.get_node("approval")

        oversized_notes = "x" * 3000
        mock_activity = AsyncMock(
            return_value={
                "output": {
                    "decision": "approved",
                    "decided_by": "jsmith",
                    "decided_at": "2026-05-20T10:00:00+00:00",
                    "decision_notes": oversized_notes,
                }
            }
        )

        with patch("syntara.workflows.workflow_engine.approval_mixin.workflow.execute_activity", mock_activity):
            result = await wf._dispatch_node_to_executor(node, {}, graph, timeout_seconds=300)

        assert len(result["output"]["decision_notes"]) == 2000

    @pytest.mark.asyncio
    async def test_dispatch_logs_approval_decision(self) -> None:
        """Verify approval decisions are logged for audit trail."""
        wf = _make_workflow()
        graph = _build_approval_graph()
        node = graph.get_node("approval")

        mock_activity = AsyncMock(
            return_value={
                "output": {"decision": "approved", "decided_by": "jsmith", "decided_at": "2026-05-20T10:00:00+00:00"}
            }
        )

        with (
            patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf,
            patch("syntara.workflows.workflow_engine.approval_mixin.workflow", mock_wf),
        ):
            mock_wf.logger = MagicMock()
            mock_wf.execute_activity = mock_activity
            await wf._dispatch_node_to_executor(node, {}, graph, timeout_seconds=300)

        mock_wf.logger.info.assert_called_once_with(
            "Approval node %s decision: %s by %s",
            "approval",
            "approved",
            "jsmith",
        )


class TestHandleNodeFailureBareApplicationError:
    """Tests that _handle_node_failure extracts details from bare ApplicationError.

    When workflow code raises ApplicationError directly (not via an activity),
    the error is not wrapped in ActivityError. _handle_node_failure must still
    extract error type, message, and details.
    """

    def test_bare_application_error_extracts_message(self) -> None:
        """Bare ApplicationError message is used instead of str(error)."""
        wf = _make_workflow()
        graph = _build_approval_graph()

        error = ApplicationError(
            "Approval node 'approval' received invalid decision 'cancelled'",
            type="InvalidApprovalDecisionError",
            non_retryable=True,
        )
        wf._handle_node_failure("approval", error, graph)

        assert "approval" in wf.failed_nodes
        assert "invalid decision 'cancelled'" in wf.failed_nodes["approval"]

    def test_bare_application_error_extracts_output_from_details(self) -> None:
        """Bare ApplicationError with output in details populates namespace."""
        wf = _make_workflow()
        graph = _build_approval_graph()

        output = {"status": "completed", "decision": "cancelled", "decided_by": "admin"}
        error = ApplicationError(
            "invalid decision",
            {"output": output},
            type="InvalidApprovalDecisionError",
            non_retryable=True,
        )
        wf._handle_node_failure("approval", error, graph)

        ns = wf.resolver.get_namespace("approval")
        assert ns["status"] == "failed"
        assert ns["decision"] == "cancelled"
        assert ns["decided_by"] == "admin"

    def test_bare_application_error_without_details_uses_empty_model(self) -> None:
        """Bare ApplicationError without details falls back to empty model output."""
        wf = _make_workflow()
        graph = _build_approval_graph()

        error = ApplicationError(
            "something went wrong",
            type="SomeError",
            non_retryable=True,
        )
        wf._handle_node_failure("approval", error, graph)

        ns = wf.resolver.get_namespace("approval")
        assert ns["status"] == "failed"
        assert ns["error"] == "something went wrong"
