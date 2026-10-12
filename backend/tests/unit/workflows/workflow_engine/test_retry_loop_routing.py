"""Routing a loop that is being replayed.

The replay asks a factual question — did the next iteration happen — rather than
re-deriving the loop's decision. That is what makes it correct under
``continue_on_failure``, where a failed body node does not mean the loop exited.
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from syntara.workflows.utils.namespace_resolver import NamespaceResolver
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.models.workflow_definition import ForEachLoopState, LoopType


def _wf(*, retry_points: list[str], bodies: dict[str, set[str]]) -> OrchestratorWorkflow:
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
    wf._active_loop_iteration = {}
    wf._retry_replay_candidates = set()
    wf._restored_node_timestamps = {}
    wf._restored_node_statuses = {}
    wf._restored_node_outputs = {}
    wf._retry_source_statuses = {}
    wf._retry_restorable_cache = None
    wf._runtime_settings = {}
    return wf


@pytest.fixture
def patched_workflow():
    """The loop control calls the module-level workflow API, so patch that."""
    with patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as patched:
        patched.execute_activity = AsyncMock()
        yield patched


async def _probe(wf: OrchestratorWorkflow, patched, *, reached: bool) -> dict[str, Any] | None:
    patched.execute_activity.return_value = reached
    state = ForEachLoopState(type=LoopType.FOR_EACH, items=[1, 2, 3], current_index=1)
    return await wf._replayed_loop_control("loop_1", state)


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
    assert wf._replay_source_name("body_a") == "body_a#iter-1"


@pytest.mark.asyncio
async def test_replaying_stops_when_the_loop_reaches_the_retry_point(patched_workflow) -> None:
    """Once the loop holds the node this retry resumes from, it runs for real.

    That node has to execute — it is the failure being retried — and the loop
    around it has to behave normally again, so the replay hands control back.
    """
    wf = _wf(retry_points=["body_a"], bodies={"loop_1": {"body_a"}})
    result = await _probe(wf, patched_workflow, reached=True)

    assert result is None
    patched_workflow.execute_activity.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_loop_outside_the_retry_is_executed_normally(patched_workflow) -> None:
    """A loop this retry never reaches runs as it always would.

    Only loops whose bodies were recorded during the source run have a replay at
    all; anything else has nothing to ask about, so the real loop activity runs.
    """
    wf = _wf(retry_points=["step_2"], bodies={"loop_1": {"body_a"}})

    result = await wf._replayed_loop_control(
        "other_loop", ForEachLoopState(type=LoopType.FOR_EACH, items=[1], current_index=0)
    )

    assert result is None
    patched_workflow.execute_activity.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_ordinary_run_never_replays_a_loop(patched_workflow) -> None:
    """With no retry context there is nothing to replay, so the loop just runs."""
    wf = _wf(retry_points=[], bodies={"loop_1": {"body_a"}})
    result = await _probe(wf, patched_workflow, reached=True)

    assert result is None
    patched_workflow.execute_activity.assert_not_awaited()
