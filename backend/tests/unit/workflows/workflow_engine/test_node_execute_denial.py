"""A node execute denial stops that branch without stopping other branches."""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syntara.workflows.models.activity_execution import TERMINAL_ACTIVITY_STATUSES, ActivityStatus
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from tests.unit.workflows.workflow_engine.conftest import make_workflow_runtime_settings


@pytest.fixture
def temporal_workflow() -> Generator[MagicMock]:
    with patch("syntara.workflows.workflow_engine.dynamic_workflow.workflow") as mock:
        mock.logger = MagicMock()
        mock.info.return_value = MagicMock(workflow_id="test-workflow")
        mock.execute_local_activity = AsyncMock(return_value=make_workflow_runtime_settings())
        mock.execute_activity = AsyncMock(return_value={"output": {"value": "ok"}})
        yield mock


def _definition(*, parallel_branch: bool) -> dict[str, Any]:
    nodes = [
        {"id": "blocked", "type": "script", "parameters": {"language": "python"}},
        {"id": "descendant", "type": "script", "parameters": {}},
    ]
    edges = [{"from": "start", "to": "blocked"}, {"from": "blocked", "to": "descendant"}]
    if parallel_branch:
        nodes.append({"id": "safe", "type": "script", "parameters": {"language": "bash"}})
        edges.append({"from": "start", "to": "safe"})
    return {
        "schema_version": "2.0.0",
        "triggers": [{"id": "start", "type": "manual_trigger", "parameters": {}}],
        "nodes": nodes,
        "edges": edges,
    }


class TestDeniedNodeStatus:
    """Denied is a terminal activity state distinct from failure and skip."""

    def test_denied_is_a_distinct_terminal_activity_status(self) -> None:
        assert ActivityStatus("denied") in TERMINAL_ACTIVITY_STATUSES


class TestAllowedNodes:
    """The same graph runs normally when no node is denied."""

    async def test_both_branches_and_descendant_run_without_a_deny(self, temporal_workflow: MagicMock) -> None:
        workflow = OrchestratorWorkflow()

        result = await workflow.run(
            _definition(parallel_branch=True),
            "execution-1",
            "start",
            {},
            include_node_results=True,
        )

        executed_ids = {call.kwargs["activity_id"] for call in temporal_workflow.execute_activity.await_args_list}
        assert {"start", "blocked", "descendant", "safe"} == executed_ids
        assert result["status"] == "completed"


class TestDeniedBranch:
    """A denial stops only its branch and reports the denying policy."""

    @pytest.mark.parametrize(
        ("parallel_branch", "expected_status"),
        [(True, "completed"), (False, "completed_with_errors")],
        ids=["parallel-branch-completes", "sole-path-denied"],
    )
    async def test_denial_stops_its_branch_and_reports_the_policy(
        self,
        temporal_workflow: MagicMock,
        parallel_branch: bool,  # noqa: FBT001
        expected_status: str,
    ) -> None:
        workflow = OrchestratorWorkflow()
        denied = [
            {"node_id": "blocked", "labels": {"kind": "script", "language": "python"}, "denied_by": "deny-python"}
        ]

        result = await workflow.run(
            _definition(parallel_branch=parallel_branch),
            "execution-1",
            "start",
            {},
            include_node_results=True,
            denied_nodes=denied,
            run_principal_id="user-1",
        )

        executed_ids = {call.kwargs["activity_id"] for call in temporal_workflow.execute_activity.await_args_list}
        assert "blocked" not in executed_ids
        assert "descendant" not in executed_ids
        assert ("safe" in executed_ids) is parallel_branch
        assert result["activity_outputs"]["blocked"]["status"] == "denied"
        assert "descendant" in workflow.skipped_nodes
        assert result["status"] == expected_status
        assert "blocked" in str(result["denied_nodes"])
        assert "deny-python" in str(result["denied_nodes"])
