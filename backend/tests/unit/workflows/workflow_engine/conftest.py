"""Shared test helpers for workflow engine unit tests."""

from typing import Any

from syntara.settings.catalog import SETTINGS_CATALOG
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.graph import ActivityNode, WorkflowGraph


def make_workflow_runtime_settings() -> dict[str, object]:
    """Return a runtime_settings dict seeded with all workflow_engine.* catalog defaults."""
    return {e.key: e.default_value for e in SETTINGS_CATALOG if e.key.startswith("workflow_engine.")}


def init_workflow_runtime(wf: OrchestratorWorkflow) -> None:
    """Initialise the runtime-fetched fields on an OrchestratorWorkflow test instance.

    Call this inside every _make_workflow helper after the other state fields
    are set. Keeps the 4-line block from being copy-pasted across all 8 test files.
    """
    wf._runtime_settings = make_workflow_runtime_settings()
    wf._has_unhandled_failure = False
    # Retry-from-failure state. Set in __init__ for a real run; defaulted here so
    # a workflow built for a non-retry test behaves as one.
    wf.retry_context = {}
    wf._retry_restorable_cache = None
    wf._restored_nodes = set()
    # Set in __init__ for a real run. Guarded because some tests build the workflow
    # by hand, and a converge reads it to tell whether a loop predecessor is still
    # iterating, so it must exist even on a workflow with nothing to do with retries.
    if not hasattr(wf, "node_control_data"):
        wf.node_control_data = {}
    if not hasattr(wf, "_cof_failed_nodes"):
        wf._cof_failed_nodes = set()
    wf._retry_replay_candidates = set()
    wf._restored_node_timestamps = {}
    wf._restored_node_statuses = {}
    wf._restored_node_outputs = {}
    wf._retry_source_statuses = {}


async def complete_supplied_node(
    wf: OrchestratorWorkflow, node: ActivityNode, result: dict[str, Any], graph: WorkflowGraph
) -> None:
    """Drive supplied output through the same completion boundary as a live task."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    async def supplied() -> dict[str, Any]:
        return wf._process_supplied_result(node, result)

    task = asyncio.create_task(supplied())
    with (
        patch.object(wf, "_schedule_successors", new_callable=AsyncMock),
        patch.object(wf, "_cancel_skipped_pending_tasks"),
    ):
        await wf._process_completed_task(task, {node.id: task}, graph)
