"""Replay compatibility for the loop-wait completion command change."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from temporalio import activity, workflow
from temporalio.worker import Replayer, Worker

from syntara.workflows.workflow_engine.constants import DEFAULT_ACTIVITY_TIMEOUT_SECONDS
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

if TYPE_CHECKING:
    from temporalio.testing import WorkflowEnvironment

_WAIT_COMPLETIONS: list[asyncio.Queue[str] | None] = [None]


@activity.defn(name=ActivityName.WAIT)
async def _pending_wait(_input_config: dict[str, Any], _output_config: dict[str, str] | None) -> dict[str, Any]:
    """Keep the wait activity pending so the history remains open for replay."""
    await asyncio.Event().wait()
    return {"output": {"status": "completed"}}


@activity.defn(name="complete_wait")
async def _record_wait_completion(_workflow_id: str, _run_id: str, activity_id: str) -> None:
    """Record which wait ID the legacy local activity tried to complete."""
    queue = _WAIT_COMPLETIONS[0]
    if queue is None:
        msg = "Wait completion queue is not initialized"
        raise RuntimeError(msg)
    await queue.put(activity_id)


@workflow.defn(name="loop_wait_history_compatibility")
class _LegacyLoopWaitWorkflow:
    """Generate history with the pre-fix local activity command."""

    def __init__(self) -> None:
        self._legacy_completion_recorded = False

    @workflow.run
    async def run(self) -> None:
        wait_handle = workflow.start_activity(
            ActivityName.WAIT,
            args=[{"duration": 1}, None],
            activity_id="wait_node_iter_0",
            start_to_close_timeout=timedelta(seconds=1 + OrchestratorWorkflow._TEMPORAL_MARGIN),
        )
        await workflow.sleep(timedelta(seconds=1))
        await workflow.execute_local_activity(
            _record_wait_completion,
            args=[workflow.info().workflow_id, workflow.info().run_id, "wait_node"],
            start_to_close_timeout=timedelta(seconds=DEFAULT_ACTIVITY_TIMEOUT_SECONDS),
            activity_id="__internal__complete_wait_wait_node",
        )
        self._legacy_completion_recorded = True
        await wait_handle

    @workflow.query
    def legacy_completion_recorded(self) -> bool:
        return self._legacy_completion_recorded


@workflow.defn(name="loop_wait_history_compatibility")
class _CurrentLoopWaitWorkflow:
    """Replay legacy history through the production wait-node implementation."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        orchestrator = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
        orchestrator.loop_body_map = {"wait_node": "loop_node"}
        orchestrator.node_control_data = {"loop_node": {"current_index": 0}}
        return await orchestrator._execute_wait_node("wait_node", {"duration": 1}, None)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_legacy_loop_wait_history_replays_with_recovery(
    temporal_env: WorkflowEnvironment,
) -> None:
    """Old completion commands replay, then the new recovery command is accepted."""
    completion_calls = asyncio.Queue[str]()
    _WAIT_COMPLETIONS[0] = completion_calls
    test_id = uuid4().hex
    task_queue = f"loop-wait-history-{test_id}"
    workflow_id = f"loop-wait-history-{test_id}"

    try:
        async with Worker(
            temporal_env.client,
            task_queue=task_queue,
            workflows=[_LegacyLoopWaitWorkflow],
            activities=[_pending_wait, _record_wait_completion],
        ):
            handle = await temporal_env.client.start_workflow(
                _LegacyLoopWaitWorkflow.run,
                id=workflow_id,
                task_queue=task_queue,
            )
            try:
                assert await asyncio.wait_for(completion_calls.get(), timeout=15) == "wait_node"

                for _ in range(50):
                    if await handle.query(_LegacyLoopWaitWorkflow.legacy_completion_recorded):
                        break
                    await asyncio.sleep(0.1)
                else:
                    pytest.fail("Legacy workflow did not reach its pending wait")

                history = await handle.fetch_history()
                await Replayer(workflows=[_CurrentLoopWaitWorkflow]).replay_workflow(history)
            finally:
                await handle.terminate("End replay compatibility test")
    finally:
        _WAIT_COMPLETIONS[0] = None
