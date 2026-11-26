"""HTTP placement must not change native requests or historical activity arguments."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from syntara.workflow_core.models import NodeType
from syntara.workflow_runtime.engines.temporal.dynamic_workflow import OrchestratorWorkflow


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("opt_in", "patched", "uses_ep"), [(False, True, False), (True, True, True), (True, False, False)]
)
async def test_http_placement_controls_activity_identity_and_cancellation_tracking(
    *, opt_in: bool, patched: bool, uses_ep: bool
) -> None:
    wf = OrchestratorWorkflow.__new__(OrchestratorWorkflow)
    wf.execution_id = str(uuid4())
    wf._active_ep_nodes = set()
    node = cast("Any", SimpleNamespace(id="http", type=NodeType.HTTP_REQUEST, outputs=None))
    parameters: dict[str, Any] = {"method": "GET", "url": "https://example.com"}
    if opt_in:
        parameters["execution_profile"] = {"type": "execution_target", "execution_target_id": str(uuid4())}
    with (
        patch.object(wf, "_execute_executor_node", AsyncMock(return_value={"output": {}})) as execute,
        patch("syntara.workflow_runtime.engines.temporal.dynamic_workflow.workflow.patched", return_value=patched),
    ):
        await wf._dispatch_node_to_executor(node, parameters, cast("Any", None), 30)
    assert execute.await_args is not None
    assert execute.await_args.kwargs["extra_args"] == ([wf.execution_id] if uses_ep else None)
    assert ("http" in wf._active_ep_nodes) is uses_ep
