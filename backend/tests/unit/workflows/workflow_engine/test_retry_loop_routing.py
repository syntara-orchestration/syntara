"""Routing a loop that is being replayed.

The replay asks a factual question — did the next iteration happen — rather than
re-deriving the loop's decision. That is what makes it correct under
``continue_on_failure``, where a failed body node does not mean the loop exited.
"""

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph
from syntara.workflows.workflow_engine.models.workflow_definition import (
    DoWhileLoopState,
    ForEachLoopState,
    LoopType,
    NodeSettingsNoRetry,
)
from syntara.workflows.workflow_engine.utils.loop_iteration_ids import retry_loop_record_activity_id

_TEST_GRAPHS: dict[int, MagicMock] = {}


def _wf(
    *,
    retry_points: list[str],
    bodies: dict[str, set[str]],
    iterate_successors: dict[str, list[ActivityNode]] | None = None,
    downstream_successors: dict[str, list[ActivityNode]] | None = None,
) -> OrchestratorWorkflow:
    wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
    wf.retry_context = {"retry_from_execution_id": "src-1", "eligible_point_ids": retry_points} if retry_points else {}
    wf.resolver = NamespaceResolver()
    wf.skipped_nodes = set()
    wf.failed_nodes = {}
    wf.node_inputs = {}
    wf.node_control_data = {}
    wf.loop_state = {}
    wf.loop_body_map = {}
    wf.loop_iteration_results = {}
    wf._loop_bodies = bodies
    graph = MagicMock()
    successors = iterate_successors
    if successors is None:
        successors = {
            loop_id: [ActivityNode(node_id=sorted(body)[0], node_type="script", parameters={})]
            for loop_id, body in bodies.items()
            if body
        }
    next_nodes = downstream_successors or {}
    graph.get_next_activities_by_port.side_effect = lambda node_id, port: (
        successors.get(node_id, []) if port == "iterate" else []
    )
    graph.get_next_activities.side_effect = lambda node_id: next_nodes.get(node_id, [])
    _TEST_GRAPHS[id(wf)] = graph
    wf._active_loop_iteration = {}
    wf._retry_replay_candidates = set(bodies)
    wf._retry_loop_record_states = {}
    wf._retry_live_loop_ids = set()
    wf._restored_node_timestamps = {}
    wf._restored_node_statuses = {}
    wf._restored_node_outputs = {}
    wf._retry_source_statuses = {}
    wf._retry_source_temporal_statuses = {}
    wf._retry_selected_failure_paths = {}
    wf._retry_restorable_cache = None
    wf._runtime_settings = {}
    return wf


def _graph(wf: OrchestratorWorkflow) -> WorkflowGraph:
    return cast("WorkflowGraph", _TEST_GRAPHS[id(wf)])


def _graph_mock(wf: OrchestratorWorkflow) -> MagicMock:
    return _TEST_GRAPHS[id(wf)]


async def _replay_loop(
    wf: OrchestratorWorkflow,
    node_id: str,
    state: ForEachLoopState | DoWhileLoopState,
) -> dict[str, Any] | None:
    return await wf._replayed_loop_control(node_id, state, _graph(wf))


@pytest.fixture
def patched_workflow():
    """The loop control calls the module-level workflow API, so patch that."""
    with (
        patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as patched,
        patch("syntara.workflows.workflow_engine.retry_mixin.workflow", patched),
    ):
        patched.execute_activity = AsyncMock()
        yield patched


async def _probe(wf: OrchestratorWorkflow, patched, *, reached: bool) -> dict[str, Any] | None:
    patched.execute_activity.return_value = reached
    state = ForEachLoopState(type=LoopType.FOR_EACH, items=[1, 2, 3], current_index=1)
    return await _replay_loop(wf, "loop_1", state)


@pytest.mark.asyncio
async def test_a_reached_iteration_routes_to_iterate(patched_workflow) -> None:
    """The source run got there, so the loop goes there too."""
    wf = _wf(retry_points=["step_2"], bodies={"loop_1": {"body_a"}})

    result = await _probe(wf, patched_workflow, reached=True)

    assert result is not None
    assert result["control"]["next_port"] == "iterate"
    assert result["control"]["next_index"] == 2


@pytest.mark.asyncio
async def test_an_unreached_iteration_exits_the_loop(patched_workflow) -> None:
    """No row for that iteration means the source run never got there."""
    wf = _wf(retry_points=["step_2"], bodies={"loop_1": {"body_a"}})

    result = await _probe(wf, patched_workflow, reached=False)

    assert result is not None
    assert result["control"]["next_port"] == "complete"
    assert result["control"]["next_index"] == 1


@pytest.mark.asyncio
async def test_the_iteration_being_replayed_is_recorded_for_its_body(patched_workflow) -> None:
    """A body replays the row for the iteration the loop is on, not the first."""
    wf = _wf(retry_points=["step_2"], bodies={"loop_1": {"body_a"}})

    await _probe(wf, patched_workflow, reached=True)

    assert wf._active_loop_iteration["loop_1"] == 1
    from syntara.workflows.workflow_engine.graph import ActivityNode

    wf.loop_body_map = {"body_a": "loop_1"}
    wf.node_control_data = {"loop_1": {"current_index": 1}}
    body = ActivityNode(node_id="body_a", node_type="script", parameters={})
    assert wf._source_temporal_activity_id(body) == "body_a_iter_1"


@pytest.mark.asyncio
async def test_loop_probes_the_iteration_that_contains_the_retry_point(patched_workflow) -> None:
    """The loop must route into the target iteration before the body hands off."""
    wf = _wf(retry_points=["body_a"], bodies={"loop_1": {"body_a"}})
    wf._retry_selected_failure_paths = {"body_a": [[1]]}
    state = ForEachLoopState(type=LoopType.FOR_EACH, items=[1, 2, 3], current_index=1)
    patched_workflow.execute_activity.return_value = True

    result = await _replay_loop(wf, "loop_1", state)

    assert result is not None
    assert result["control"]["next_port"] == "iterate"
    patched_workflow.execute_activity.assert_awaited_once()


@pytest.mark.asyncio
async def test_body_occurrence_switches_enclosing_loop_to_live_mode(patched_workflow) -> None:
    wf = _wf(retry_points=["body_a"], bodies={"loop_1": {"body_a"}})
    wf._retry_selected_failure_paths = {"body_a": [[2]]}
    wf.loop_body_map = {"body_a": "loop_1"}
    patched_workflow.execute_activity.return_value = True
    state = ForEachLoopState(type=LoopType.FOR_EACH, items=[1, 2, 3], current_index=1)

    result = await _replay_loop(wf, "loop_1", state)

    assert result is not None
    assert result["control"]["next_port"] == "iterate"
    patched_workflow.execute_activity.assert_awaited_once()

    patched_workflow.execute_activity.reset_mock()
    state.current_index = 2
    result = await _replay_loop(wf, "loop_1", state)

    assert result is not None
    patched_workflow.execute_activity.assert_awaited_once()

    from syntara.workflows.workflow_engine.graph import ActivityNode

    wf.node_control_data["loop_1"] = {"current_index": 2}
    wf._enter_live_retry_mode_at_selected_node(ActivityNode(node_id="body_a", node_type="script", parameters={}))
    assert wf._retry_live_loop_ids == {"loop_1"}
    assert "loop_1" not in wf._retry_replay_candidates


@pytest.mark.asyncio
async def test_continue_on_failure_restarts_at_lowest_failed_iteration(patched_workflow) -> None:
    """Multiple failures of one selected node resume from the earliest occurrence."""
    wf = _wf(retry_points=["body_a"], bodies={"loop_1": {"body_a"}})
    wf.loop_body_map = {"body_a": "loop_1"}
    wf._retry_source_temporal_statuses = {
        "body_a_iter_5": "failed",
        "body_a_iter_3": "completed",
        "body_a_iter_2": "failed",
    }
    wf._retry_selected_failure_paths = wf._selected_failure_iteration_paths()

    assert wf._retry_selected_failure_paths == {"body_a": [[2], [5]]}

    # Passing the earliest failed iteration would mean we selected the later one.
    state = ForEachLoopState(type=LoopType.FOR_EACH, items=list(range(6)), current_index=3)
    with pytest.raises(ApplicationError, match=r"after selected failure path \[2\]"):
        await _replay_loop(wf, "loop_1", state)
    patched_workflow.execute_activity.assert_not_awaited()

    # Replay reaches iteration 2, then hands the selected body node and its loop
    # back to normal execution. Later iterations (including the second failure)
    # are handled by that live pass.
    state.current_index = 2
    wf.node_control_data["loop_1"] = {"current_index": 2}
    patched_workflow.execute_activity.return_value = True
    result = await _replay_loop(wf, "loop_1", state)

    assert result is not None
    assert result["control"]["next_port"] == "iterate"
    assert wf._active_loop_iteration["loop_1"] == 2

    from syntara.workflows.workflow_engine.graph import ActivityNode

    selected_node = ActivityNode(node_id="body_a", node_type="script", parameters={})
    assert wf._enter_live_retry_mode_at_selected_node(selected_node)
    assert wf._retry_live_loop_ids == {"loop_1"}
    assert "loop_1" not in wf._retry_replay_candidates

    state.current_index = 3
    assert await _replay_loop(wf, "loop_1", state) is None
    patched_workflow.execute_activity.assert_awaited_once()


@pytest.mark.asyncio
async def test_nested_loop_replays_before_inner_failed_iteration(patched_workflow) -> None:
    wf = _wf(retry_points=["body_a"], bodies={"outer": {"inner", "body_a"}, "inner": {"body_a"}})
    wf.loop_body_map = {"inner": "outer", "body_a": "inner"}
    wf.node_control_data = {"outer": {"current_index": 2}}
    wf._retry_selected_failure_paths = {"body_a": [[2, 1]]}
    patched_workflow.execute_activity.return_value = True
    state = ForEachLoopState(type=LoopType.FOR_EACH, items=[1, 2], current_index=0)

    result = await _replay_loop(wf, "inner", state)

    assert result is not None
    assert result["control"]["next_port"] == "iterate"
    assert patched_workflow.execute_activity.await_args.kwargs["args"][-1] == [2, 0]

    patched_workflow.execute_activity.reset_mock()
    state.current_index = 1
    result = await _replay_loop(wf, "inner", state)

    assert result is not None
    assert result["control"]["next_port"] == "iterate"
    patched_workflow.execute_activity.assert_awaited_once()


@pytest.mark.asyncio
async def test_loop_probe_uses_iterate_successors_not_recursive_loop_membership(patched_workflow) -> None:
    wf = _wf(
        retry_points=["step_after_loops"],
        bodies={"outer": {"outer_step", "inner", "inner_step"}},
        iterate_successors={
            "outer": [
                ActivityNode(node_id="outer_step", node_type="script", parameters={}),
                ActivityNode(node_id="inner", node_type="loop", parameters={}),
            ]
        },
    )
    patched_workflow.execute_activity.return_value = True
    state = ForEachLoopState(type=LoopType.FOR_EACH, items=[1, 2], current_index=1)

    await _replay_loop(wf, "outer", state)

    args = patched_workflow.execute_activity.await_args.kwargs["args"]
    assert args == ["src-1", ["outer_step"], ["inner"], [1]]
    _graph_mock(wf).get_next_activities_by_port.assert_called_once_with("outer", "iterate")


@pytest.mark.asyncio
async def test_loop_probe_never_falls_back_to_recursive_body_membership(patched_workflow) -> None:
    wf = _wf(
        retry_points=["step_after_loops"],
        bodies={"outer": {"outer_step", "inner_step"}},
        iterate_successors={"outer": [ActivityNode(node_id="outer_step", node_type="script", parameters={})]},
    )
    patched_workflow.execute_activity.return_value = False
    state = ForEachLoopState(type=LoopType.FOR_EACH, items=[1], current_index=0)

    await _replay_loop(wf, "outer", state)

    assert patched_workflow.execute_activity.await_args.kwargs["args"] == ["src-1", ["outer_step"], [], [0]]


@pytest.mark.asyncio
async def test_loop_probe_walks_through_disabled_iterate_entries(patched_workflow) -> None:
    disabled_entry = ActivityNode(
        node_id="disabled_entry",
        node_type="script",
        parameters={},
        settings=NodeSettingsNoRetry(disabled=True),
    )
    executable_entry = ActivityNode(node_id="body_a", node_type="script", parameters={})
    wf = _wf(
        retry_points=["after"],
        bodies={"loop_1": {"disabled_entry", "body_a"}},
        iterate_successors={"loop_1": [disabled_entry]},
        downstream_successors={"disabled_entry": [executable_entry]},
    )
    patched_workflow.execute_activity.return_value = True
    state = ForEachLoopState(type=LoopType.FOR_EACH, items=[1, 2], current_index=1)

    await _replay_loop(wf, "loop_1", state)

    assert patched_workflow.execute_activity.await_args.kwargs["args"] == ["src-1", ["body_a"], [], [1]]
    _graph_mock(wf).get_next_activities.assert_called_once_with("disabled_entry")


@pytest.mark.asyncio
async def test_loop_without_executable_entry_uses_synced_iteration_count(patched_workflow) -> None:
    disabled_entry = ActivityNode(
        node_id="disabled_entry",
        node_type="script",
        parameters={},
        settings=NodeSettingsNoRetry(disabled=True),
    )
    wf = _wf(
        retry_points=["after"],
        bodies={"loop_1": {"disabled_entry"}},
        iterate_successors={"loop_1": [disabled_entry]},
    )
    wf._retry_loop_record_states = {"loop_1": {"output_data": {"iteration_count": 2}}}
    state = ForEachLoopState(type=LoopType.FOR_EACH, items=[1, 2], current_index=1)

    result = await _replay_loop(wf, "loop_1", state)

    assert result is not None
    assert result["control"]["next_port"] == "iterate"
    patched_workflow.execute_activity.assert_not_awaited()

    state.current_index = 2
    result = await _replay_loop(wf, "loop_1", state)

    assert result is not None
    assert result["control"]["next_port"] == "complete"
    patched_workflow.execute_activity.assert_not_awaited()


@pytest.mark.asyncio
async def test_loop_without_entry_or_synced_count_fails_closed(patched_workflow) -> None:
    disabled_entry = ActivityNode(
        node_id="disabled_entry",
        node_type="script",
        parameters={},
        settings=NodeSettingsNoRetry(disabled=True),
    )
    wf = _wf(
        retry_points=["after"],
        bodies={"loop_1": {"disabled_entry"}},
        iterate_successors={"loop_1": [disabled_entry]},
    )
    state = ForEachLoopState(type=LoopType.FOR_EACH, items=[1], current_index=0)

    with pytest.raises(ApplicationError, match="no iteration entry or source iteration count"):
        await _replay_loop(wf, "loop_1", state)

    patched_workflow.execute_activity.assert_not_awaited()


@pytest.mark.asyncio
async def test_nested_loop_probe_passes_outer_then_inner_index(patched_workflow) -> None:
    wf = _wf(
        retry_points=["step_after_loops"],
        bodies={"inner": {"inner_step"}},
        iterate_successors={"inner": [ActivityNode(node_id="inner_step", node_type="script", parameters={})]},
    )
    wf.loop_body_map = {"inner": "outer"}
    wf.node_control_data = {"outer": {"current_index": 2}}
    patched_workflow.execute_activity.return_value = True
    state = ForEachLoopState(type=LoopType.FOR_EACH, items=[1, 2], current_index=1)

    await _replay_loop(wf, "inner", state)

    args = patched_workflow.execute_activity.await_args.kwargs["args"]
    assert args == ["src-1", ["inner_step"], [], [2, 1]]
    assert patched_workflow.execute_activity.await_args.kwargs["activity_id"] == (
        "__internal__probe_retry_loop_inner_iter_2_iter_1"
    )


@pytest.mark.asyncio
async def test_a_loop_outside_the_retry_is_executed_normally(patched_workflow) -> None:
    """A loop this retry never reaches runs as it always would.

    Only loops whose bodies were recorded during the source run have a replay at
    all; anything else has nothing to ask about, so the real loop activity runs.
    """
    wf = _wf(retry_points=["step_2"], bodies={"loop_1": {"body_a"}})

    result = await _replay_loop(wf, "other_loop", ForEachLoopState(type=LoopType.FOR_EACH, items=[1], current_index=0))

    assert result is None
    patched_workflow.execute_activity.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_ordinary_run_never_replays_a_loop(patched_workflow) -> None:
    """With no retry context there is nothing to replay, so the loop just runs."""
    wf = _wf(retry_points=[], bodies={"loop_1": {"body_a"}})
    result = await _probe(wf, patched_workflow, reached=True)

    assert result is None
    patched_workflow.execute_activity.assert_not_awaited()


@pytest.mark.asyncio
async def test_nested_loop_with_ambiguous_legacy_failure_path_fails_closed(patched_workflow) -> None:
    wf = _wf(retry_points=["body_a"], bodies={"inner": {"body_a"}})
    wf.loop_body_map = {"inner": "outer", "body_a": "inner"}
    state = ForEachLoopState(type=LoopType.FOR_EACH, items=[1], current_index=0)

    with pytest.raises(ApplicationError, match="does not record a complete iteration path"):
        await _replay_loop(wf, "inner", state)

    patched_workflow.execute_activity.assert_not_awaited()


@pytest.mark.asyncio
async def test_restore_loop_record_caches_resolved_inputs_and_source_times(patched_workflow) -> None:
    wf = _wf(retry_points=["body_a"], bodies={"loop_1": {"body_a"}})
    wf._retry_selected_failure_paths = {"body_a": [[1]]}
    source_state = {
        "status": "skipped",
        "input_data": {"type": "for_each", "items": ["one", "two"]},
        "output_data": {"iteration_count": 1, "iteration_results": None},
        "control_data": {"next_port": "iterate", "current_index": 1},
        "started_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T00:01:00+00:00",
        "error_details": "unfinished loop finalized",
    }

    async def return_source_then_assert_staged_state(*_args: object, **kwargs: object) -> dict[str, Any] | None:
        activity_id = cast("str", kwargs["activity_id"])
        if activity_id.startswith("__internal__"):
            return source_state
        assert wf.node_inputs["loop_1"] == source_state["input_data"]
        assert wf.resolver.get_namespace("loop_1") == source_state["output_data"]
        assert retry_loop_record_activity_id("loop_1") in wf._restored_node_timestamps
        return None

    patched_workflow.execute_activity.side_effect = return_source_then_assert_staged_state

    state = await wf._restore_retry_loop_record("loop_1")

    assert state["status"] == "running"
    assert state["completed_at"] is None
    assert state["error_details"] is None
    assert wf.node_inputs["loop_1"] == {"type": "for_each", "items": ["one", "two"]}
    assert wf.resolver.get_namespace("loop_1") == {"iteration_count": 1, "iteration_results": None}
    assert wf._restored_node_timestamps[retry_loop_record_activity_id("loop_1")] == {
        "started_at": "2026-01-01T00:00:00+00:00",
        "completed_at": None,
        "status": "running",
        "error_details": None,
    }
    assert len(patched_workflow.execute_activity.await_args_list) == 2
    assert [call.kwargs["activity_id"] for call in patched_workflow.execute_activity.await_args_list] == [
        "__internal__fetch_retry_loop_record_loop_1",
        retry_loop_record_activity_id("loop_1"),
    ]


@pytest.mark.asyncio
async def test_retry_loop_uses_stored_resolved_inputs_without_resolving_expression(patched_workflow) -> None:
    from unittest.mock import MagicMock

    from syntara.workflows.workflow_engine.graph import ActivityNode

    wf = _wf(retry_points=["after"], bodies={"loop_1": {"body_a"}})
    wf.pre_resolved_outputs = {}
    wf.stop_after_nodes = set()
    wf._secret_values = set()
    stored_inputs = {"type": "for_each", "items": ["source-value"]}
    node = ActivityNode(
        node_id="loop_1",
        node_type="loop",
        parameters={"type": "for_each", "items": "${trigger.items}"},
    )
    dispatch = AsyncMock(return_value={"output": {"iteration_count": 0}})

    with (
        patch.object(
            wf, "_restore_retry_loop_record", new_callable=AsyncMock, return_value={"input_data": stored_inputs}
        ),
        patch.object(wf, "_resolve_node_parameters") as resolve_parameters,
        patch.object(wf, "_dispatch_node", dispatch),
        patch.object(wf, "_process_node_result", return_value={"output": {"iteration_count": 0}}),
        patch("syntara.workflows.workflow_engine.dynamic_workflow.resolve_timeout", return_value=30),
        patch.object(wf, "_apply_input_overrides"),
    ):
        await wf._execute_node(node, MagicMock())

    resolve_parameters.assert_not_called()
    dispatch.assert_awaited_once()
    dispatch_call = dispatch.await_args
    assert dispatch_call is not None
    assert dispatch_call.args[1] == stored_inputs


@pytest.mark.asyncio
async def test_replayed_loop_does_not_evaluate_do_while_condition(patched_workflow) -> None:
    from syntara.workflows.workflow_engine.graph import ActivityNode

    wf = _wf(retry_points=["after"], bodies={"loop_1": {"body_a"}})
    wf.loop_state["loop_1"] = DoWhileLoopState(condition="${body_a.done}", max_iterations=5, current_index=2)
    wf.loop_iteration_results["loop_1"] = {}
    replayed_result = {"output": {"iteration_count": 2}, "control": {"next_index": 3, "current_index": 2}}

    with (
        patch.object(wf, "_replayed_loop_control", new_callable=AsyncMock, return_value=replayed_result),
        patch("syntara.workflows.workflow_engine.dynamic_workflow.safe_eval_with_namespace") as evaluate,
        patch(
            "syntara.workflows.workflow_engine.dynamic_workflow.workflow.execute_activity", new_callable=AsyncMock
        ) as execute,
    ):
        result = await wf._execute_loop_node(
            "loop_1",
            ActivityNode(
                node_id="loop_1",
                node_type="loop",
                parameters={"type": "do_while", "condition": "${body_a.done}"},
            ),
            {"type": "do_while", "condition": "${body_a.done}", "max_iterations": 5},
            graph=_graph(wf),
        )

    assert result == replayed_result
    evaluate.assert_not_called()
    execute.assert_not_awaited()


def test_selected_failure_path_uses_the_full_temporal_id_not_the_display_counter() -> None:
    wf = _wf(retry_points=["body_a"], bodies={"outer": {"inner", "body_a"}, "inner": {"body_a"}})
    wf._retry_source_temporal_statuses = {"body_a_iter_2_iter_1": "failed"}

    assert wf._selected_failure_iteration_paths() == {"body_a": [[2, 1]]}


def test_display_name_cannot_supply_a_missing_failure_iteration_path() -> None:
    wf = _wf(retry_points=["body_a"], bodies={"loop_1": {"body_a"}})
    wf._retry_source_statuses = {"body_a": "failed"}

    assert wf._selected_failure_iteration_paths() == {}


def test_selected_nested_failure_refreshes_inner_items_from_the_target_outer_item(patched_workflow) -> None:
    from unittest.mock import MagicMock

    from syntara.workflows.workflow_engine.graph import ActivityNode

    wf = _wf(retry_points=["body_a"], bodies={"outer": {"inner", "body_a"}, "inner": {"body_a"}})
    wf.loop_body_map = {"inner": "outer", "body_a": "inner"}
    wf.node_control_data = {"outer": {"current_index": 0}, "inner": {"current_index": 1}}
    wf._retry_selected_failure_paths = {"body_a": [[0, 1]]}
    wf.loop_state = {
        "outer": ForEachLoopState(items=[{"children": ["target-0", "target-1"]}], current_index=1),
        # The one visible inner-loop row contains inputs from a later outer pass.
        "inner": ForEachLoopState(items=["stale-0", "stale-1", "stale-2"], current_index=2),
    }
    wf.resolver.set_namespace("loop", {})
    selected_node = ActivityNode(node_id="body_a", node_type="script", parameters={})
    inner_loop = ActivityNode(
        node_id="inner",
        node_type="loop",
        parameters={"type": "for_each", "items": "${loop.item.children}"},
    )
    graph = MagicMock()
    graph.get_node.return_value = inner_loop

    assert wf._enter_live_retry_mode_at_selected_node(selected_node)
    wf._refresh_nested_loop_inputs_at_retry(selected_node, graph)

    inner_state = wf.loop_state["inner"]
    assert isinstance(inner_state, ForEachLoopState)
    assert inner_state.items == ["target-0", "target-1"]
    assert inner_state.current_index == 2
    assert wf.resolver.get_namespace("loop")["outer"]["item"] == {"children": ["target-0", "target-1"]}
    assert wf.resolver.get_namespace("loop")["inner"]["item"] == "target-1"
