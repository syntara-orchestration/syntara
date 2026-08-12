"""Tests for WorkflowGraph and ActivityNode (task 6.1).

Tests cover:
- ActivityNode.from_dict / to_dict round-trip and edge cases
- WorkflowGraph.from_dict with valid workflow definitions
- get_trigger_nodes, get_node, get_next_activities, get_next_activities_by_port
- has_successors, get_predecessors, get_all_nodes
- Loop edge stripping (edges with to_port="iterate" are excluded)
"""

from typing import Any

import pytest
from pydantic import ValidationError

from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph, _parse_node_settings
from syntara.workflows.workflow_engine.models.workflow_definition import (
    NodeSettingsBase,
    NodeSettingsCof,
    NodeSettingsCofDisabled,
    NodeSettingsFull,
    NodeSettingsNoRetry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_workflow() -> dict[str, Any]:
    """Trigger -> script -> condition -> (true: action_a, false: action_b)."""
    return {
        "schema_version": "2.0.0",
        "name": "simple",
        "description": "test",
        "triggers": [{"id": "trigger1", "type": "manual_trigger", "parameters": {"method": "POST"}}],
        "nodes": [
            {"id": "script1", "type": "script", "parameters": {"lang": "python"}, "outputs": {"result": "out"}},
            {"id": "cond1", "type": "condition", "parameters": {"expr": "true"}},
            {"id": "action_a", "type": "script", "parameters": {}},
            {"id": "action_b", "type": "script", "parameters": {}},
        ],
        "edges": [
            {"from": "trigger1", "to": "script1"},
            {"from": "script1", "to": "cond1"},
            {"from": "cond1", "to": "action_a", "from_port": "true"},
            {"from": "cond1", "to": "action_b", "from_port": "false"},
        ],
    }


def _loop_workflow() -> dict[str, Any]:
    """Trigger -> loop -> body, with iterate feedback edge."""
    return {
        "schema_version": "2.0.0",
        "name": "loop-wf",
        "description": "test loop",
        "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {"id": "loop1", "type": "loop", "parameters": {}},
            {"id": "body1", "type": "script", "parameters": {}},
        ],
        "edges": [
            {"from": "t1", "to": "loop1"},
            {"from": "loop1", "to": "body1", "from_port": "iterate"},
            {"from": "body1", "to": "loop1", "to_port": "iterate"},  # feedback edge — should be stripped
            {"from": "loop1", "to": "body1"},  # non-loop edge kept for connectivity
        ],
    }


# ---------------------------------------------------------------------------
# ActivityNode tests
# ---------------------------------------------------------------------------


class TestActivityNodeFromDict:
    """Tests for ActivityNode.from_dict."""

    def test_minimal_dict(self) -> None:
        node = ActivityNode.from_dict({"id": "n1", "type": "script"})
        assert node.id == "n1"
        assert node.type == "script"
        assert node.name is None
        assert node.parameters == {}
        assert node.outputs is None

    def test_full_dict(self) -> None:
        node = ActivityNode.from_dict(
            {
                "id": "n2",
                "type": "http_request",
                "name": "Fetch Data",
                "parameters": {"url": "https://example.com"},
                "outputs": {"body": "response.body"},
            }
        )
        assert node.id == "n2"
        assert node.name == "Fetch Data"
        assert node.type == "http_request"
        assert node.parameters == {"url": "https://example.com"}
        assert node.outputs == {"body": "response.body"}

    def test_name_preserved_from_dict(self) -> None:
        node = ActivityNode.from_dict({"id": "step1", "type": "approval", "name": "Review Deployment"})
        assert node.name == "Review Deployment"

    def test_name_defaults_to_none(self) -> None:
        node = ActivityNode.from_dict({"id": "step1", "type": "script"})
        assert node.name is None

    def test_config_defaults_to_empty_dict(self) -> None:
        node = ActivityNode.from_dict({"id": "x", "type": "t"})
        assert node.parameters == {}

    def test_extra_keys_ignored(self) -> None:
        node = ActivityNode.from_dict({"id": "x", "type": "t", "unknown_field": 42})
        assert node.id == "x"

    def test_missing_id_raises(self) -> None:
        with pytest.raises(KeyError):
            ActivityNode.from_dict({"type": "script"})

    def test_missing_type_raises(self) -> None:
        with pytest.raises(KeyError):
            ActivityNode.from_dict({"id": "n1"})


class TestParseNodeSettings:
    """Tests for _parse_node_settings per-node-type dispatch."""

    def test_http_request_gets_full(self) -> None:
        settings = _parse_node_settings("http_request", {"timeout": 30, "retry_policy": {"max_retries": 5}})
        assert isinstance(settings, NodeSettingsFull)
        assert settings.timeout == 30
        assert settings.retry_policy is not None
        assert settings.retry_policy.max_retries == 5

    def test_script_gets_no_retry(self) -> None:
        settings = _parse_node_settings("script", {"timeout": 60})
        assert isinstance(settings, NodeSettingsNoRetry)
        assert settings.timeout == 60

    def test_script_rejects_retry_policy(self) -> None:
        with pytest.raises(ValidationError):
            _parse_node_settings("script", {"retry_policy": {"max_retries": 3}})

    def test_converge_gets_cof(self) -> None:
        settings = _parse_node_settings("converge", {"continue_on_failure": True})
        assert isinstance(settings, NodeSettingsCof)
        assert settings.continue_on_failure is True

    def test_converge_rejects_timeout(self) -> None:
        with pytest.raises(ValidationError):
            _parse_node_settings("converge", {"timeout": 30})

    def test_condition_gets_base(self) -> None:
        settings = _parse_node_settings("condition", None)
        assert isinstance(settings, NodeSettingsBase)

    def test_unknown_type_gets_base(self) -> None:
        settings = _parse_node_settings("unknown_future_type", None)
        assert isinstance(settings, NodeSettingsBase)

    def test_none_raw_returns_default(self) -> None:
        settings = _parse_node_settings("http_request", None)
        assert isinstance(settings, NodeSettingsFull)
        assert settings.retry_policy is None

    def test_converge_rejects_disabled(self) -> None:
        with pytest.raises(ValidationError):
            _parse_node_settings("converge", {"disabled": True})

    def test_wait_gets_cof_disabled(self) -> None:
        settings = _parse_node_settings("wait", {"disabled": True, "continue_on_failure": True})
        assert isinstance(settings, NodeSettingsCofDisabled)
        assert settings.disabled is True
        assert settings.continue_on_failure is True

    def test_wait_rejects_timeout(self) -> None:
        with pytest.raises(ValidationError):
            _parse_node_settings("wait", {"timeout": 300})

    def test_script_accepts_disabled(self) -> None:
        settings = _parse_node_settings("script", {"disabled": True})
        assert isinstance(settings, NodeSettingsNoRetry)
        assert settings.disabled is True


class TestActivityNodeToDict:
    """Tests for ActivityNode.to_dict."""

    def test_round_trip_without_outputs(self) -> None:
        original = {"id": "n1", "type": "script", "parameters": {"lang": "bash"}}
        node = ActivityNode.from_dict(original)
        assert node.to_dict() == original

    def test_round_trip_with_name(self) -> None:
        original = {"id": "n1", "type": "approval", "name": "Review", "parameters": {}}
        node = ActivityNode.from_dict(original)
        result = node.to_dict()
        assert result["name"] == "Review"

    def test_round_trip_with_outputs(self) -> None:
        original = {
            "id": "n1",
            "type": "script",
            "parameters": {},
            "outputs": {"result": "out"},
        }
        node = ActivityNode.from_dict(original)
        result = node.to_dict()
        assert result["outputs"] == {"result": "out"}

    def test_none_name_omitted(self) -> None:
        node = ActivityNode(node_id="n1", node_type="t", parameters={})
        assert "name" not in node.to_dict()

    def test_none_outputs_omitted(self) -> None:
        node = ActivityNode(node_id="n1", node_type="t", parameters={}, outputs=None)
        assert "outputs" not in node.to_dict()

    def test_empty_dict_outputs_included(self) -> None:
        """Empty dict outputs ({}) are falsy — verify behavior."""
        node = ActivityNode(node_id="n1", node_type="t", parameters={}, outputs={})
        # Empty dict is falsy so outputs is excluded
        assert "outputs" not in node.to_dict()


# ---------------------------------------------------------------------------
# WorkflowGraph.from_dict tests
# ---------------------------------------------------------------------------


class TestWorkflowGraphFromDict:
    """Tests for WorkflowGraph.from_dict with valid workflow definitions."""

    def test_creates_graph_with_correct_node_count(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        assert len(graph.get_all_nodes()) == 5  # trigger + 4 nodes

    def test_stores_metadata(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        assert graph.metadata["schema_version"] == "2.0.0"
        assert graph.metadata["name"] == "simple"

    def test_unknown_backend_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown backend"):
            WorkflowGraph.from_dict(_simple_workflow(), backend_type="nope")


# ---------------------------------------------------------------------------
# get_trigger_nodes
# ---------------------------------------------------------------------------


class TestGetTriggerNodes:
    """Tests for get_trigger_nodes."""

    def test_returns_trigger_nodes(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        triggers = graph.get_trigger_nodes()
        assert len(triggers) == 1
        assert triggers[0].id == "trigger1"
        assert triggers[0].type == "manual_trigger"

    def test_multiple_triggers(self) -> None:
        data = _simple_workflow()
        data["triggers"].append({"id": "trigger2", "type": "schedule_trigger", "parameters": {}})
        data["edges"].append({"from": "trigger2", "to": "script1"})
        graph = WorkflowGraph.from_dict(data)
        triggers = graph.get_trigger_nodes()
        assert len(triggers) == 2
        trigger_ids = {t.id for t in triggers}
        assert trigger_ids == {"trigger1", "trigger2"}


# ---------------------------------------------------------------------------
# get_node
# ---------------------------------------------------------------------------


class TestGetNode:
    """Tests for get_node."""

    def test_returns_correct_node(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        node = graph.get_node("script1")
        assert node.id == "script1"
        assert node.type == "script"
        assert node.parameters == {"lang": "python"}
        assert node.outputs == {"result": "out"}

    def test_nonexistent_node_raises(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        with pytest.raises(KeyError):
            graph.get_node("does_not_exist")


# ---------------------------------------------------------------------------
# get_next_activities
# ---------------------------------------------------------------------------


class TestGetNextActivities:
    """Tests for get_next_activities."""

    def test_single_successor(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        nexts = graph.get_next_activities("trigger1")
        assert len(nexts) == 1
        assert nexts[0].id == "script1"

    def test_multiple_successors(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        nexts = graph.get_next_activities("cond1")
        successor_ids = {n.id for n in nexts}
        assert successor_ids == {"action_a", "action_b"}

    def test_leaf_node_has_no_successors(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        nexts = graph.get_next_activities("action_a")
        assert nexts == []


# ---------------------------------------------------------------------------
# get_next_activities_by_port
# ---------------------------------------------------------------------------


class TestGetNextActivitiesByPort:
    """Tests for get_next_activities_by_port."""

    def test_filter_by_true_port(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        nexts = graph.get_next_activities_by_port("cond1", from_port="true")
        assert len(nexts) == 1
        assert nexts[0].id == "action_a"

    def test_filter_by_false_port(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        nexts = graph.get_next_activities_by_port("cond1", from_port="false")
        assert len(nexts) == 1
        assert nexts[0].id == "action_b"

    def test_none_port_returns_all_successors(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        nexts = graph.get_next_activities_by_port("cond1", from_port=None)
        assert len(nexts) == 2

    def test_nonexistent_port_returns_empty(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        nexts = graph.get_next_activities_by_port("cond1", from_port="nonexistent")
        assert nexts == []


# ---------------------------------------------------------------------------
# has_successors
# ---------------------------------------------------------------------------


class TestHasSuccessors:
    """Tests for has_successors."""

    def test_node_with_successors(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        assert graph.has_successors("trigger1") is True

    def test_leaf_node(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        assert graph.has_successors("action_a") is False


# ---------------------------------------------------------------------------
# get_predecessors
# ---------------------------------------------------------------------------


class TestGetPredecessors:
    """Tests for get_predecessors."""

    def test_node_with_single_predecessor(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        preds = graph.get_predecessors("script1")
        assert preds == ["trigger1"]

    def test_node_with_single_predecessor_from_condition(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        preds = graph.get_predecessors("action_a")
        assert preds == ["cond1"]

    def test_trigger_has_no_predecessors(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        preds = graph.get_predecessors("trigger1")
        assert preds == []


# ---------------------------------------------------------------------------
# get_all_nodes
# ---------------------------------------------------------------------------


class TestGetAllNodes:
    """Tests for get_all_nodes."""

    def test_returns_all_nodes(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        all_nodes = graph.get_all_nodes()
        node_ids = {n.id for n in all_nodes}
        assert node_ids == {"trigger1", "script1", "cond1", "action_a", "action_b"}

    def test_returns_activity_node_instances(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        all_nodes = graph.get_all_nodes()
        assert all(isinstance(n, ActivityNode) for n in all_nodes)


# ---------------------------------------------------------------------------
# Loop edge stripping
# ---------------------------------------------------------------------------


class TestLoopEdgeStripping:
    """Edges with to_port='iterate' are excluded during graph build."""

    def test_iterate_feedback_edge_stripped(self) -> None:
        graph = WorkflowGraph.from_dict(_loop_workflow())
        # body1 should NOT have loop1 as a successor via the feedback edge
        outgoing = graph.get_outgoing_edges("body1")
        iterate_edges = [e for e in outgoing if e.get("to_port") == "iterate"]
        assert iterate_edges == []

    def test_non_iterate_edges_preserved(self) -> None:
        graph = WorkflowGraph.from_dict(_loop_workflow())
        # loop1 should still have body1 as successor via non-iterate edges
        nexts = graph.get_next_activities("loop1")
        next_ids = {n.id for n in nexts}
        assert "body1" in next_ids

    def test_all_nodes_present_after_stripping(self) -> None:
        graph = WorkflowGraph.from_dict(_loop_workflow())
        node_ids = {n.id for n in graph.get_all_nodes()}
        assert node_ids == {"t1", "loop1", "body1"}

    def test_iterate_from_port_edge_preserved(self) -> None:
        """Edges with from_port='iterate' (not to_port) should be kept."""
        graph = WorkflowGraph.from_dict(_loop_workflow())
        outgoing = graph.get_outgoing_edges("loop1")
        iterate_edges = [e for e in outgoing if e.get("from_port") == "iterate"]
        assert len(iterate_edges) == 1
        assert iterate_edges[0]["to"] == "body1"


# ---------------------------------------------------------------------------
# WorkflowGraph.from_dict — validation failures
# ---------------------------------------------------------------------------


class TestWorkflowGraphValidation:
    """Tests for validate_structure triggered by from_dict."""

    def test_no_trigger_raises(self) -> None:
        """Graph with no trigger nodes fails validation."""
        data: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "bad",
            "description": "no trigger",
            "triggers": [],
            "nodes": [
                {"id": "n1", "type": "script", "parameters": {}},
                {"id": "n2", "type": "script", "parameters": {}},
            ],
            "edges": [{"from": "n1", "to": "n2"}],
        }
        with pytest.raises(ValueError, match="trigger"):
            WorkflowGraph.from_dict(data)

    def test_orphan_node_raises(self) -> None:
        """Node with no edges (non-trigger) fails validation."""
        data: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "bad",
            "description": "orphan",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {"id": "n1", "type": "script", "parameters": {}},
                {"id": "orphan", "type": "script", "parameters": {}},
            ],
            "edges": [{"from": "t1", "to": "n1"}],
        }
        with pytest.raises(ValueError, match="Orphan"):
            WorkflowGraph.from_dict(data)

    def test_trigger_only_graph_valid(self) -> None:
        """A graph with only a trigger (no other nodes) is valid."""
        data: dict[str, Any] = {
            "schema_version": "2.0.0",
            "name": "minimal",
            "description": "trigger only",
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [],
            "edges": [],
        }
        graph = WorkflowGraph.from_dict(data)
        assert len(graph.get_all_nodes()) == 1


# ---------------------------------------------------------------------------
# get_successors / get_outgoing_edges (WorkflowGraph wrappers)
# ---------------------------------------------------------------------------


class TestWorkflowGraphEdgeWrappers:
    """Tests for get_successors and get_outgoing_edges on WorkflowGraph."""

    def test_get_successors_returns_ids(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        succ = graph.get_successors("trigger1")
        assert succ == ["script1"]

    def test_get_outgoing_edges_includes_port_data(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        edges = graph.get_outgoing_edges("cond1")
        ports = {e.get("from_port") for e in edges}
        assert ports == {"true", "false"}

    def test_get_outgoing_edges_empty_for_leaf(self) -> None:
        graph = WorkflowGraph.from_dict(_simple_workflow())
        assert graph.get_outgoing_edges("action_a") == []
