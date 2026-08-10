"""Unit tests for loop state initialization helpers.

Tests cover:
- _create_loop_state_for_type: creates ForEachLoopState or DoWhileLoopState
- Pre-resolved loop node initialization in _execute_node
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.dynamic_workflow import NexusWorkflow
from syntara.workflows.workflow_engine.graph import ActivityNode
from syntara.workflows.workflow_engine.models.workflow_definition import (
    DoWhileLoopState,
    ForEachLoopState,
    LoopType,
)


@pytest.fixture(autouse=True)
def mock_temporal_workflow() -> Generator[MagicMock]:
    """Mock the Temporal workflow module to avoid 'Not in workflow event loop' errors."""
    mock_logger = MagicMock()
    with patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock_wf:
        mock_wf.logger = mock_logger
        mock_wf.info.return_value = MagicMock(workflow_id="test-wf-id")
        yield mock_wf


def _make_workflow(
    pre_resolved_outputs: dict[str, dict[str, Any]] | None = None,
) -> NexusWorkflow:
    """Create a NexusWorkflow with initialized state, bypassing __init__."""
    wf = NexusWorkflow.__new__(NexusWorkflow)
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
    wf._converge_branch_nodes = {}
    wf.pre_resolved_outputs = pre_resolved_outputs or {}
    wf.stop_after_nodes = set()
    wf.execution_id = "test-exec-id"
    wf.request_id = None
    return wf


def _make_loop_node(
    node_id: str = "loop_1",
    loop_type: str = LoopType.FOR_EACH,
    extra_config: dict[str, Any] | None = None,
) -> ActivityNode:
    """Create a loop ActivityNode with the given config."""
    config: dict[str, Any] = {"type": loop_type}
    if extra_config:
        config.update(extra_config)
    return ActivityNode(node_id=node_id, node_type="loop", parameters=config)


class TestCreateLoopStateForType:
    """Tests for _create_loop_state_for_type factory."""

    def test_for_each_creates_state_with_items(self) -> None:
        wf = _make_workflow()
        node = _make_loop_node(extra_config={"items": ["a", "b"]})
        state = wf._create_loop_state_for_type(LoopType.FOR_EACH, node, {"items": ["a", "b"]})
        assert isinstance(state, ForEachLoopState)
        assert state.items == ["a", "b"]
        assert state.current_index == 0

    def test_do_while_creates_state_with_condition(self) -> None:
        wf = _make_workflow()
        node = _make_loop_node(
            loop_type=LoopType.DO_WHILE,
            extra_config={"condition": "${done}"},
        )
        config: dict[str, Any] = {"condition": "${done}", "max_iterations": 5}
        state = wf._create_loop_state_for_type(LoopType.DO_WHILE, node, config)
        assert isinstance(state, DoWhileLoopState)
        assert state.condition == "${done}"
        assert state.max_iterations == 5
        assert state.current_index == 0

    def test_do_while_without_max_iterations(self) -> None:
        wf = _make_workflow()
        node = _make_loop_node(
            loop_type=LoopType.DO_WHILE,
            extra_config={"condition": "${done}"},
        )
        config: dict[str, Any] = {"condition": "${done}"}
        state = wf._create_loop_state_for_type(LoopType.DO_WHILE, node, config)
        assert isinstance(state, DoWhileLoopState)
        assert state.max_iterations is None

    def test_uses_node_config_when_loop_config_is_none(self) -> None:
        wf = _make_workflow()
        node = _make_loop_node(extra_config={"items": ["x", "y"]})
        state = wf._create_loop_state_for_type(LoopType.FOR_EACH, node)
        assert isinstance(state, ForEachLoopState)
        assert state.items == ["x", "y"]

    def test_condition_read_from_loop_config(self) -> None:
        """Condition must come from loop_config, not node.parameters, for consistency."""
        wf = _make_workflow()
        node = _make_loop_node(
            loop_type=LoopType.DO_WHILE,
            extra_config={"condition": "${raw_template}"},
        )
        config: dict[str, Any] = {"condition": "${overridden_template}", "max_iterations": 10}
        state = wf._create_loop_state_for_type(LoopType.DO_WHILE, node, config)
        assert isinstance(state, DoWhileLoopState)
        assert state.condition == "${overridden_template}"


class TestPreResolvedLoopStateInit:
    """Tests for pre-resolved loop state initialization in _execute_node."""

    @pytest.mark.asyncio
    async def test_for_each_pre_resolved_initializes_state(self) -> None:
        """Pre-resolved for_each loop node gets loop state from node.parameters."""
        node = _make_loop_node(extra_config={"items": ["a", "b", "c"]})
        wf = _make_workflow(pre_resolved_outputs={"loop_1": {"output": {"status": "completed"}}})
        await wf._execute_node(node, MagicMock())
        assert "loop_1" in wf.loop_state
        assert isinstance(wf.loop_state["loop_1"], ForEachLoopState)
        assert wf.loop_state["loop_1"].items == ["a", "b", "c"]
        assert "loop_1" in wf.loop_iteration_results

    @pytest.mark.asyncio
    async def test_do_while_pre_resolved_initializes_state(self) -> None:
        """Pre-resolved do_while loop node gets loop state from node.parameters."""
        node = _make_loop_node(
            loop_type=LoopType.DO_WHILE,
            extra_config={"condition": "${x}", "max_iterations": 10},
        )
        wf = _make_workflow(pre_resolved_outputs={"loop_1": {"output": {"status": "completed"}}})
        await wf._execute_node(node, MagicMock())
        state = wf.loop_state["loop_1"]
        assert isinstance(state, DoWhileLoopState)
        assert state.condition == "${x}"
        assert state.max_iterations == 10

    @pytest.mark.asyncio
    async def test_skips_if_state_already_exists(self) -> None:
        """Pre-resolved path does not overwrite existing loop state."""
        existing_state = ForEachLoopState(items=["existing"])
        node = _make_loop_node(extra_config={"items": ["new"]})
        wf = _make_workflow(pre_resolved_outputs={"loop_1": {"output": {}}})
        wf.loop_state["loop_1"] = existing_state
        await wf._execute_node(node, MagicMock())
        assert wf.loop_state["loop_1"] is existing_state

    @pytest.mark.asyncio
    async def test_non_loop_pre_resolved_does_not_init_loop_state(self) -> None:
        """Pre-resolved non-loop nodes should not touch loop state."""
        node = ActivityNode(node_id="script_1", node_type="script", parameters={})
        wf = _make_workflow(pre_resolved_outputs={"script_1": {"output": {"result": "ok"}}})
        await wf._execute_node(node, MagicMock())
        assert "script_1" not in wf.loop_state
