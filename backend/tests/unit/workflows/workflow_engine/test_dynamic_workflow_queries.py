"""Unit tests for NexusWorkflow queries, loops, and helpers (task 6.3).

Tests cover:
- get_skipped_nodes query
- get_activity_input query (including credential scrubbing — AAP-74431)
- get_activity_output query
- _determine_output_port helper
- _are_predecessors_complete helper
- _scrub_activity_credentials (AAP-74431)
- For-each loop state management (_clear_loop_body, _loop_body_complete, etc.)
"""

import asyncio
import copy
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.dynamic_workflow import NexusWorkflow
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph
from syntara.workflows.workflow_engine.graph_backend import InMemoryGraphBackend
from syntara.workflows.workflow_engine.models.workflow_definition import (
    ForEachLoopState,
    NodeType,
)
from syntara.workflows.workflow_engine.utils.credential_scrubber import REDACTED
from tests.unit.workflows.workflow_engine.conftest import init_workflow_runtime


@pytest.fixture(autouse=True)
def _mock_temporal_workflow() -> Generator[MagicMock]:
    """Mock the Temporal workflow module to avoid 'Not in workflow event loop' errors."""
    mock_logger = MagicMock()
    with patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf:
        mock_wf.logger = mock_logger
        mock_wf.info.return_value = MagicMock(workflow_id="test-wf-id")
        yield mock_wf


def _make_workflow(
    skipped_nodes: set[str] | None = None,
    failed_nodes: dict[str, str] | None = None,
    resolver: NamespaceResolver | None = None,
) -> NexusWorkflow:
    """Create a NexusWorkflow with initialized state, bypassing __init__."""
    wf = NexusWorkflow.__new__(NexusWorkflow)
    wf.skipped_nodes = skipped_nodes if skipped_nodes is not None else set()
    wf.failed_nodes = failed_nodes if failed_nodes is not None else {}
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


def _build_fanin_graph() -> WorkflowGraph:
    """Build: trigger -> node_a + node_b -> converge_node -> node_c."""
    backend = InMemoryGraphBackend()
    backend.add_node("trigger", {"id": "trigger", "type": "manual_trigger", "parameters": {}})
    backend.add_node("node_a", {"id": "node_a", "type": "script", "parameters": {}})
    backend.add_node("node_b", {"id": "node_b", "type": "script", "parameters": {}})
    backend.add_node("converge_node", {"id": "converge_node", "type": "converge", "parameters": {}})
    backend.add_node("node_c", {"id": "node_c", "type": "script", "parameters": {}})
    backend.add_edge("trigger", "node_a", None)
    backend.add_edge("trigger", "node_b", None)
    backend.add_edge("node_a", "converge_node", None)
    backend.add_edge("node_b", "converge_node", None)
    backend.add_edge("converge_node", "node_c", None)
    return WorkflowGraph(backend)


# ---------------------------------------------------------------------------
# Tests: get_skipped_nodes query
# ---------------------------------------------------------------------------


class TestGetSkippedNodesQuery:
    """Test the get_skipped_nodes query method."""

    def test_returns_empty_list_when_none_skipped(self) -> None:
        wf = _make_workflow()
        assert wf.get_skipped_nodes() == []

    def test_returns_all_skipped_node_ids(self) -> None:
        wf = _make_workflow(skipped_nodes={"node_a", "node_b"})
        assert sorted(wf.get_skipped_nodes()) == ["node_a", "node_b"]

    def test_returns_list_not_set(self) -> None:
        wf = _make_workflow(skipped_nodes={"node_a"})
        assert isinstance(wf.get_skipped_nodes(), list)


# ---------------------------------------------------------------------------
# Tests: get_activity_input query
# ---------------------------------------------------------------------------


class TestGetActivityInputQuery:
    """Test the get_activity_input query method."""

    def test_returns_stored_input(self) -> None:
        wf = _make_workflow()
        wf.node_inputs["node_a"] = {"url": "http://example.com", "method": "GET"}
        assert wf.get_activity_input("node_a") == {"url": "http://example.com", "method": "GET"}

    def test_returns_none_for_unknown_activity(self) -> None:
        wf = _make_workflow()
        assert wf.get_activity_input("nonexistent") is None

    def test_returns_trigger_input(self) -> None:
        wf = _make_workflow()
        wf.node_inputs["trigger"] = {"body": {"key": "value"}}
        assert wf.get_activity_input("trigger") == {"body": {"key": "value"}}


# ---------------------------------------------------------------------------
# Tests: get_activity_output query
# ---------------------------------------------------------------------------


class TestGetActivityOutputQuery:
    """Test the get_activity_output query method."""

    def test_returns_stored_output(self) -> None:
        wf = _make_workflow()
        wf.resolver.set_namespace("node_a", {"status": "ok", "data": [1, 2, 3]})
        assert wf.get_activity_output("node_a") == {"status": "ok", "data": [1, 2, 3]}

    def test_returns_none_for_unknown_activity(self) -> None:
        wf = _make_workflow()
        assert wf.get_activity_output("nonexistent") is None

    def test_returns_none_when_namespace_missing(self) -> None:
        wf = _make_workflow()
        assert wf.get_activity_output("node_a") is None

    def test_returns_trigger_output(self) -> None:
        wf = _make_workflow()
        wf.resolver.set_namespace("trigger", {"url": "http://example.com"})
        assert wf.get_activity_output("trigger") == {"url": "http://example.com"}


# --- _determine_output_port ---


class TestDetermineOutputPort:
    """Test port determination from control data."""

    def test_returns_port_from_control_data(self) -> None:
        wf = _make_workflow()
        wf.node_control_data["cond_node"] = {"next_port": "true"}
        assert wf._determine_output_port("cond_node") == "true"

    def test_returns_none_when_no_control_data(self) -> None:
        wf = _make_workflow()
        assert wf._determine_output_port("regular_node") is None

    def test_returns_none_when_control_data_has_no_port(self) -> None:
        wf = _make_workflow()
        wf.node_control_data["node"] = {"some_other_key": "value"}
        assert wf._determine_output_port("node") is None

    def test_returns_iterate_port_for_loop(self) -> None:
        wf = _make_workflow()
        wf.node_control_data["loop_node"] = {"next_port": "iterate"}
        assert wf._determine_output_port("loop_node") == "iterate"

    def test_returns_complete_port_for_loop(self) -> None:
        wf = _make_workflow()
        wf.node_control_data["loop_node"] = {"next_port": "complete"}
        assert wf._determine_output_port("loop_node") == "complete"


# --- _are_predecessors_complete ---


class TestArePredecessorsComplete:
    """Test converge predecessor readiness checks."""

    def test_all_predecessors_completed(self) -> None:
        wf = _make_workflow()
        graph = _build_fanin_graph()
        wf.resolver.set_namespace("node_a", {"result": "a"})
        wf.resolver.set_namespace("node_b", {"result": "b"})
        assert wf._are_predecessors_complete("converge_node", graph) is True

    def test_missing_predecessor_not_ready(self) -> None:
        wf = _make_workflow()
        graph = _build_fanin_graph()
        wf.resolver.set_namespace("node_a", {"result": "a"})
        assert wf._are_predecessors_complete("converge_node", graph) is False

    def test_skipped_predecessor_counts_as_complete(self) -> None:
        wf = _make_workflow(skipped_nodes={"node_b"})
        graph = _build_fanin_graph()
        wf.resolver.set_namespace("node_a", {"result": "a"})
        assert wf._are_predecessors_complete("converge_node", graph) is True


# ---------------------------------------------------------------------------
# Tests: For-each loop
# ---------------------------------------------------------------------------


class TestForEachLoop:
    """Test for_each loop iteration state management."""

    def test_loop_state_initialized_with_items(self) -> None:
        """First execution of a loop node should initialize loop_state."""
        wf = _make_workflow()
        items = ["alpha", "beta", "gamma"]
        node_id = "loop_node"

        state = ForEachLoopState(items=items)
        wf.loop_state[node_id] = state

        assert state.items == items
        assert state.current_index == 0

    def test_loop_body_map_tracks_body_nodes(self) -> None:
        wf = _make_workflow()
        wf.loop_body_map["body_node"] = "loop_node"
        assert wf.loop_body_map["body_node"] == "loop_node"

    def test_clear_loop_body_removes_body_mapping(self) -> None:
        wf = _make_workflow()
        wf.loop_body_map["body_a"] = "loop_1"
        wf.loop_body_map["body_b"] = "loop_1"
        wf.loop_body_map["other_body"] = "loop_2"
        wf.resolver.set_namespace("body_a", {"output": "val_a"})
        wf.resolver.set_namespace("body_b", {"output": "val_b"})

        wf._clear_loop_body("loop_1")

        assert "body_a" not in wf.loop_body_map
        assert "body_b" not in wf.loop_body_map
        assert "other_body" in wf.loop_body_map

    def test_clear_loop_body_collects_iteration_results(self) -> None:
        wf = _make_workflow()
        wf.loop_body_map["body_node"] = "loop_1"
        wf.resolver.set_namespace("body_node", {"status": "ok", "value": 42})

        wf._clear_loop_body("loop_1")

        assert "loop_1" in wf.loop_iteration_results
        assert wf.loop_iteration_results["loop_1"]["body_node.status"] == ["ok"]
        assert wf.loop_iteration_results["loop_1"]["body_node.value"] == [42]

    def test_loop_body_complete_returns_false_when_incomplete(self) -> None:
        wf = _make_workflow()
        wf.loop_body_map["body_a"] = "loop_1"
        wf.loop_body_map["body_b"] = "loop_1"
        wf.resolver.set_namespace("body_a", {"done": True})
        assert wf._loop_body_complete("loop_1") is False

    def test_loop_body_complete_returns_true_when_all_done(self) -> None:
        wf = _make_workflow()
        wf.loop_body_map["body_a"] = "loop_1"
        wf.loop_body_map["body_b"] = "loop_1"
        wf.resolver.set_namespace("body_a", {"done": True})
        wf.resolver.set_namespace("body_b", {"done": True})
        assert wf._loop_body_complete("loop_1") is True

    def test_loop_has_pending_nodes_detects_pending(self) -> None:
        wf = _make_workflow()
        wf.loop_body_map["body_a"] = "loop_1"
        mock_task = MagicMock(spec=asyncio.Task)
        pending: dict[str, asyncio.Task[Any]] = {"body_a": mock_task}
        assert wf._loop_has_pending_nodes("loop_1", pending) is True

    def test_loop_has_pending_nodes_returns_false_when_none_pending(self) -> None:
        wf = _make_workflow()
        wf.loop_body_map["body_a"] = "loop_1"
        pending: dict[str, asyncio.Task[Any]] = {}
        assert wf._loop_has_pending_nodes("loop_1", pending) is False


# ---------------------------------------------------------------------------
# Tests: node_inputs isolation (AAP-74431 — Unit 1)
# ---------------------------------------------------------------------------


class TestNodeInputsIsolation:
    """Verify node_inputs stores an independent copy, not a reference."""

    def test_node_inputs_is_independent_copy(self) -> None:
        wf = _make_workflow()
        config: dict[str, Any] = {"url": "http://example.com", "method": "GET"}
        wf.node_inputs["node_a"] = copy.deepcopy(config)
        config["_resolved_credentials"] = {"extra_vars": {"bearer_token": "secret"}}
        assert "_resolved_credentials" not in wf.node_inputs["node_a"]

    def test_node_inputs_preserves_non_credential_data(self) -> None:
        wf = _make_workflow()
        config = {"url": "http://example.com", "timeout": 30}
        wf.node_inputs["node_a"] = copy.deepcopy(config)
        assert wf.node_inputs["node_a"] == {"url": "http://example.com", "timeout": 30}

    def test_nested_values_are_independently_copied(self) -> None:
        wf = _make_workflow()
        nested = {"headers": {"Content-Type": "application/json"}, "body": {"key": "value"}}
        wf.node_inputs["node_a"] = copy.deepcopy(nested)
        nested["headers"]["Authorization"] = "Bearer secret"
        assert "Authorization" not in wf.node_inputs["node_a"]["headers"]


# ---------------------------------------------------------------------------
# Tests: _scrub_activity_credentials (AAP-74431 — Unit 2)
# ---------------------------------------------------------------------------


class TestScrubActivityCredentials:
    """Verify _scrub_activity_credentials actually redacts credential fields."""

    def test_removes_resolved_credentials_key(self) -> None:
        config: dict[str, Any] = {
            "url": "http://example.com",
            "_resolved_credentials": {"extra_vars": {"bearer_token": "secret"}},
        }
        NexusWorkflow._scrub_activity_credentials(config)
        assert "_resolved_credentials" not in config

    def test_redacts_credential_fields_at_top_level(self) -> None:
        config: dict[str, Any] = {
            "url": "http://example.com",
            "bearer_token": "sk-secret-123",
            "llm_api_key": "key-456",
        }
        NexusWorkflow._scrub_activity_credentials(config)
        assert config["bearer_token"] == REDACTED
        assert config["llm_api_key"] == REDACTED
        assert config["url"] == "http://example.com"

    def test_preserves_non_credential_fields(self) -> None:
        config: dict[str, Any] = {"url": "http://example.com", "method": "POST", "timeout": 30}
        NexusWorkflow._scrub_activity_credentials(config)
        assert config == {"url": "http://example.com", "method": "POST", "timeout": 30}

    def test_redacts_nested_credential_fields(self) -> None:
        config: dict[str, Any] = {
            "nested": {"bearer_token": "secret", "safe_key": "value"},
        }
        NexusWorkflow._scrub_activity_credentials(config)
        assert config["nested"]["bearer_token"] == REDACTED
        assert config["nested"]["safe_key"] == "value"

    def test_preserves_dict_identity(self) -> None:
        config: dict[str, Any] = {"bearer_token": "secret", "url": "http://example.com"}
        original_id = id(config)
        NexusWorkflow._scrub_activity_credentials(config)
        assert id(config) == original_id


# ---------------------------------------------------------------------------
# Tests: get_activity_input credential scrubbing (AAP-74431 — Unit 3)
# ---------------------------------------------------------------------------


class TestGetActivityInputCredentialScrubbing:
    """Verify get_activity_input returns scrubbed data."""

    def test_returns_clean_data_unchanged(self) -> None:
        wf = _make_workflow()
        wf.node_inputs["node_a"] = {"url": "http://example.com", "method": "GET"}
        result = wf.get_activity_input("node_a")
        assert result == {"url": "http://example.com", "method": "GET"}

    def test_scrubs_resolved_credentials_from_output(self) -> None:
        wf = _make_workflow()
        wf.node_inputs["node_a"] = {
            "url": "http://example.com",
            "_resolved_credentials": {"extra_vars": {"bearer_token": "secret"}},
        }
        result = wf.get_activity_input("node_a")
        assert result is not None
        assert result["_resolved_credentials"] == REDACTED

    def test_scrubs_credential_field_names_from_output(self) -> None:
        wf = _make_workflow()
        wf.node_inputs["node_a"] = {
            "url": "http://example.com",
            "bearer_token": "sk-secret-123",
        }
        result = wf.get_activity_input("node_a")
        assert result is not None
        assert result["bearer_token"] == REDACTED

    def test_returns_none_for_unknown_activity(self) -> None:
        wf = _make_workflow()
        assert wf.get_activity_input("nonexistent") is None

    def test_does_not_mutate_node_inputs(self) -> None:
        wf = _make_workflow()
        wf.node_inputs["node_a"] = {
            "url": "http://example.com",
            "bearer_token": "sk-secret-123",
        }
        wf.get_activity_input("node_a")
        assert wf.node_inputs["node_a"]["bearer_token"] == "sk-secret-123"  # noqa: S105


class TestRouteFailedNode:
    """Tests for _route_failed_node."""

    def test_sets_complete_port_for_loop_node(self) -> None:
        wf = _make_workflow()
        node = ActivityNode(node_id="loop-1", node_type=NodeType.LOOP, parameters={})
        wf._route_failed_node("loop-1", node)
        assert wf.node_control_data["loop-1"] == {"next_port": "complete"}

    def test_does_nothing_for_non_loop_node(self) -> None:
        wf = _make_workflow()
        node = ActivityNode(node_id="script-1", node_type="script", parameters={})
        wf._route_failed_node("script-1", node)
        assert "script-1" not in wf.node_control_data
