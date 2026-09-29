"""Recorded routes preserve replay, activity limits and the disabled fallback."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.graph import ActivityNode


@pytest.mark.parametrize(
    "node_type", ["http_request", "agentic", "script", "aap_job_template", "aap_workflow_job_template"]
)
@pytest.mark.parametrize("enabled", [True, False])
async def test_recorded_container_routing(node_type, enabled):
    workflow = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
    route = {"integration_id": "cluster", "image": "node:test", "startup_seconds": 120, "grace_seconds": 30}
    workflow._runtime_settings = {"_container_routes": {node_type: route} if enabled else {}}
    node = ActivityNode(node_id="test-node", node_type=node_type, parameters={})
    inputs = {"_engine_timeout_seconds": 300, "_container_route": {"image": "untrusted:user-selected"}}
    with patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as temporal:
        temporal.patched.return_value = True
        temporal.execute_activity = AsyncMock(return_value={"output": {"ok": True}})
        result = await workflow._execute_executor_node(node, node_type, inputs, None, 300)
    assert result == {"output": {"ok": True}}
    arguments = temporal.execute_activity.call_args.kwargs
    assert arguments["start_to_close_timeout"] == timedelta(seconds=450 if enabled else 300)
    assert arguments["heartbeat_timeout"] == (timedelta(seconds=30) if enabled and node_type != "agentic" else None)
    assert inputs["_engine_timeout_seconds"] == 300
    assert inputs.get("_container_route") == (route if enabled else None)


async def test_history_without_patch_keeps_legacy_activity_schedule():
    workflow = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
    workflow._runtime_settings = {"_container_routes": {"script": {"image": "node:test"}}}
    node = ActivityNode(node_id="script", node_type="script", parameters={})
    inputs = {}
    with patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as temporal:
        temporal.patched.return_value = False
        temporal.execute_activity = AsyncMock(return_value={"output": {}})
        await workflow._execute_executor_node(node, "script", inputs, None, 300)
    assert "_container_route" not in inputs
    assert temporal.execute_activity.call_args.kwargs["start_to_close_timeout"] == timedelta(seconds=300)
