"""Integration tests for V2 workflow execution patterns through real Temporal.

Verifies that V2 workflow execution patterns (condition routing, loops, switch,
converge strategies, expression resolution, continue-on-failure) work correctly
when dispatched through a real Temporal test server.

These complement the 210+ unit tests (which mock Temporal) and the E2E tests
(which require the full API stack). This tier uses WorkflowEnvironment with
time-skipping for fast, deterministic, infrastructure-free testing.

Story: AAP-74236 — E2E Testing for V2 Schema
"""

import asyncio
from collections.abc import Callable, Sequence
from typing import Any

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from syntara.workflows.workflow_engine.activities.condition import condition
from syntara.workflows.workflow_engine.activities.converge import converge
from syntara.workflows.workflow_engine.activities.loop import loop
from syntara.workflows.workflow_engine.activities.manual_trigger import manual_trigger
from syntara.workflows.workflow_engine.activities.runtime_settings_activity import fetch_workflow_runtime_settings
from syntara.workflows.workflow_engine.activities.script_activity import execute_script_activity
from syntara.workflows.workflow_engine.activities.switch import switch
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService

_V2_ACTIVITIES: Sequence[Callable[..., Any]] = [
    execute_script_activity,
    manual_trigger,
    condition,
    converge,
    loop,
    switch,
    fetch_workflow_runtime_settings,
]


def _manual_trigger() -> dict[str, Any]:
    return {"id": "trigger", "type": "manual_trigger", "parameters": {}}


_WORKFLOW_RESULT_TIMEOUT = 30


async def _run_workflow(
    temporal_env: WorkflowEnvironment,
    task_queue: str,
    workflow_def: dict[str, Any],
) -> dict[str, Any]:
    """Start a workflow, wait for completion, and return the raw Temporal result.

    Bypasses the Pydantic WorkflowResultResponse (which drops extra fields)
    and returns the raw dict from Temporal so tests can inspect all fields
    including ``failed_activities``.
    """
    async with Worker(
        temporal_env.client,
        task_queue=task_queue,
        workflows=[OrchestratorWorkflow],
        activities=_V2_ACTIVITIES,
    ):
        svc = TemporalExecutionService(
            temporal_client=temporal_env.client,
            task_queue=task_queue,
        )
        start = await svc.start_workflow(
            workflow_def=workflow_def,
            workflow_name="v2-pattern-test",
            trigger_node_id="trigger",
            include_node_results=True,
        )
        handle = temporal_env.client.get_workflow_handle(start.temporal_workflow_id)
        raw: dict[str, Any] = await asyncio.wait_for(handle.result(), timeout=_WORKFLOW_RESULT_TIMEOUT)
        return raw


@pytest.mark.integration
@pytest.mark.asyncio
class TestConditionRouting:
    """Verify condition node evaluates expressions and routes to the correct branch."""

    async def test_condition_true_branch(self, temporal_env: WorkflowEnvironment) -> None:
        """When condition evaluates to true, the true-branch script runs and the false-branch is skipped."""
        result = await _run_workflow(
            temporal_env,
            "v2-cond-true",
            {
                "schema_version": "2.0.0",
                "triggers": [_manual_trigger()],
                "nodes": [
                    {
                        "id": "cond",
                        "type": "condition",
                        "parameters": {"condition": "1 == 1"},
                    },
                    {
                        "id": "on_true",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo true_path"},
                    },
                    {
                        "id": "on_false",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo false_path"},
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "cond"},
                    {"from": "cond", "to": "on_true", "from_port": "true"},
                    {"from": "cond", "to": "on_false", "from_port": "false"},
                ],
            },
        )

        assert result["status"] == "completed"
        assert "on_true" in result["completed_activities"]
        assert "on_false" not in result["completed_activities"]

    async def test_condition_false_branch(self, temporal_env: WorkflowEnvironment) -> None:
        """When condition evaluates to false, the false-branch script runs."""
        result = await _run_workflow(
            temporal_env,
            "v2-cond-false",
            {
                "schema_version": "2.0.0",
                "triggers": [_manual_trigger()],
                "nodes": [
                    {
                        "id": "cond",
                        "type": "condition",
                        "parameters": {"condition": "1 == 2"},
                    },
                    {
                        "id": "on_true",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo true_path"},
                    },
                    {
                        "id": "on_false",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo false_path"},
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "cond"},
                    {"from": "cond", "to": "on_true", "from_port": "true"},
                    {"from": "cond", "to": "on_false", "from_port": "false"},
                ],
            },
        )

        assert result["status"] == "completed"
        assert "on_false" in result["completed_activities"]
        assert "on_true" not in result["completed_activities"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestLoopExecution:
    """Verify loop nodes iterate correctly through Temporal."""

    async def test_for_each_loop(self, temporal_env: WorkflowEnvironment) -> None:
        """for_each loop iterates over items list and executes body for each item."""
        result = await _run_workflow(
            temporal_env,
            "v2-foreach",
            {
                "schema_version": "2.0.0",
                "triggers": [_manual_trigger()],
                "nodes": [
                    {
                        "id": "loop_node",
                        "type": "loop",
                        "parameters": {"type": "for_each", "items": ["a", "b", "c"]},
                    },
                    {
                        "id": "body",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo iteration"},
                    },
                    {
                        "id": "after_loop",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo done"},
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "loop_node"},
                    {"from": "loop_node", "to": "body", "from_port": "iterate"},
                    {"from": "loop_node", "to": "after_loop", "from_port": "complete"},
                ],
            },
        )

        assert result["status"] == "completed"
        assert "after_loop" in result["completed_activities"]
        assert "body" in result["completed_activities"]

        loop_output = result["activity_outputs"].get("loop_node", {})
        assert loop_output.get("iteration_count") == 3

    async def test_do_while_loop(self, temporal_env: WorkflowEnvironment) -> None:
        """do_while loop executes body at least once, then checks condition."""
        result = await _run_workflow(
            temporal_env,
            "v2-dowhile",
            {
                "schema_version": "2.0.0",
                "triggers": [_manual_trigger()],
                "nodes": [
                    {
                        "id": "loop_node",
                        "type": "loop",
                        "parameters": {
                            "type": "do_while",
                            "condition": "False",
                            "max_iterations": 10,
                        },
                    },
                    {
                        "id": "body",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo iteration"},
                    },
                    {
                        "id": "after_loop",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo done"},
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "loop_node"},
                    {"from": "loop_node", "to": "body", "from_port": "iterate"},
                    {"from": "loop_node", "to": "after_loop", "from_port": "complete"},
                ],
            },
        )

        assert result["status"] == "completed"
        assert "body" in result["completed_activities"]
        assert "after_loop" in result["completed_activities"]

        loop_output = result["activity_outputs"].get("loop_node", {})
        assert loop_output.get("iteration_count") == 1


@pytest.mark.integration
@pytest.mark.asyncio
class TestSwitchRouting:
    """Verify switch node evaluates cases and routes to the matching port."""

    async def test_switch_routes_to_matching_case(self, temporal_env: WorkflowEnvironment) -> None:
        """Switch evaluates cases in order and routes to the first match."""
        result = await _run_workflow(
            temporal_env,
            "v2-switch",
            {
                "schema_version": "2.0.0",
                "triggers": [_manual_trigger()],
                "nodes": [
                    {
                        "id": "sw",
                        "type": "switch",
                        "parameters": {
                            "cases": [
                                {"port": "case_a", "label": "A", "condition": "1 == 2"},
                                {"port": "case_b", "label": "B", "condition": "1 == 1"},
                            ],
                            "default_port": "fallback",
                        },
                    },
                    {
                        "id": "branch_a",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo A"},
                    },
                    {
                        "id": "branch_b",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo B"},
                    },
                    {
                        "id": "branch_default",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo default"},
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "sw"},
                    {"from": "sw", "to": "branch_a", "from_port": "case_a"},
                    {"from": "sw", "to": "branch_b", "from_port": "case_b"},
                    {"from": "sw", "to": "branch_default", "from_port": "fallback"},
                ],
            },
        )

        assert result["status"] == "completed"
        assert "branch_b" in result["completed_activities"]
        assert "branch_a" not in result["completed_activities"]
        assert "branch_default" not in result["completed_activities"]

    async def test_switch_routes_to_default(self, temporal_env: WorkflowEnvironment) -> None:
        """Switch falls through to default port when no case matches."""
        result = await _run_workflow(
            temporal_env,
            "v2-switch-default",
            {
                "schema_version": "2.0.0",
                "triggers": [_manual_trigger()],
                "nodes": [
                    {
                        "id": "sw",
                        "type": "switch",
                        "parameters": {
                            "cases": [
                                {"port": "case_a", "label": "A", "condition": "1 == 2"},
                            ],
                            "default_port": "fallback",
                        },
                    },
                    {
                        "id": "branch_a",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo A"},
                    },
                    {
                        "id": "branch_default",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo default"},
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "sw"},
                    {"from": "sw", "to": "branch_a", "from_port": "case_a"},
                    {"from": "sw", "to": "branch_default", "from_port": "fallback"},
                ],
            },
        )

        assert result["status"] == "completed"
        assert "branch_default" in result["completed_activities"]
        assert "branch_a" not in result["completed_activities"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestConvergeStrategies:
    """Verify converge node strategies work through real Temporal execution."""

    async def test_converge_all_waits_for_both_branches(self, temporal_env: WorkflowEnvironment) -> None:
        """Converge with default 'all' strategy waits for every branch to complete."""
        result = await _run_workflow(
            temporal_env,
            "v2-converge-all",
            {
                "schema_version": "2.0.0",
                "triggers": [_manual_trigger()],
                "nodes": [
                    {
                        "id": "branch_a",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo A"},
                    },
                    {
                        "id": "branch_b",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo B"},
                    },
                    {
                        "id": "join",
                        "type": "converge",
                        "parameters": {},
                    },
                    {
                        "id": "final",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo done"},
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "branch_a"},
                    {"from": "trigger", "to": "branch_b"},
                    {"from": "branch_a", "to": "join"},
                    {"from": "branch_b", "to": "join"},
                    {"from": "join", "to": "final"},
                ],
            },
        )

        assert result["status"] == "completed"
        completed = result["completed_activities"]
        assert "branch_a" in completed
        assert "branch_b" in completed
        assert "join" in completed
        assert "final" in completed

    async def test_converge_any_fires_after_n_required(self, temporal_env: WorkflowEnvironment) -> None:
        """Converge with 'any' strategy and n_required=1 fires after the first branch completes."""
        result = await _run_workflow(
            temporal_env,
            "v2-converge-any",
            {
                "schema_version": "2.0.0",
                "triggers": [_manual_trigger()],
                "nodes": [
                    {
                        "id": "branch_a",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo A"},
                    },
                    {
                        "id": "branch_b",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo B"},
                    },
                    {
                        "id": "join",
                        "type": "converge",
                        "parameters": {"strategy": "any", "n_required": 1},
                    },
                    {
                        "id": "final",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo done"},
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "branch_a"},
                    {"from": "trigger", "to": "branch_b"},
                    {"from": "branch_a", "to": "join"},
                    {"from": "branch_b", "to": "join"},
                    {"from": "join", "to": "final"},
                ],
            },
        )

        assert result["status"] == "completed"
        assert "join" in result["completed_activities"]
        assert "final" in result["completed_activities"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestExpressionResolution:
    """Verify template expressions resolve upstream node outputs at runtime."""

    async def test_downstream_node_receives_upstream_output(self, temporal_env: WorkflowEnvironment) -> None:
        """Script B references ${script_a.stdout} and receives the resolved value."""
        result = await _run_workflow(
            temporal_env,
            "v2-expr-resolve",
            {
                "schema_version": "2.0.0",
                "triggers": [_manual_trigger()],
                "nodes": [
                    {
                        "id": "script_a",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo hello_from_a"},
                    },
                    {
                        "id": "script_b",
                        "type": "script",
                        "parameters": {
                            "language": "bash",
                            "code": "echo received: ${script_a.stdout}",
                        },
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "script_a"},
                    {"from": "script_a", "to": "script_b"},
                ],
            },
        )

        assert result["status"] == "completed"
        assert "script_a" in result["completed_activities"]
        assert "script_b" in result["completed_activities"]

        script_b_output = result["activity_outputs"].get("script_b", {})
        assert "hello_from_a" in script_b_output.get("stdout", "")


@pytest.mark.integration
@pytest.mark.asyncio
class TestContinueOnFailure:
    """Verify continue_on_failure allows downstream execution after a node failure."""

    async def test_continue_on_failure_executes_next_node(self, temporal_env: WorkflowEnvironment) -> None:
        """When continue_on_failure is true, a failing node does not block downstream."""
        result = await _run_workflow(
            temporal_env,
            "v2-cof",
            {
                "schema_version": "2.0.0",
                "triggers": [_manual_trigger()],
                "nodes": [
                    {
                        "id": "failing_node",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "exit 1"},
                        "settings": {"continue_on_failure": True},
                    },
                    {
                        "id": "next_node",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo survived"},
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "failing_node"},
                    {"from": "failing_node", "to": "next_node"},
                ],
            },
        )

        assert result["status"] == "completed_with_errors"
        assert "failing_node" in result["failed_activities"]
        assert "next_node" in result["completed_activities"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestMixedPatterns:
    """Verify combined execution patterns work together through Temporal."""

    async def test_condition_then_parallel_converge(self, temporal_env: WorkflowEnvironment) -> None:
        """Condition routes to true branch which fans out to parallel nodes, then converges."""
        result = await _run_workflow(
            temporal_env,
            "v2-mixed",
            {
                "schema_version": "2.0.0",
                "triggers": [_manual_trigger()],
                "nodes": [
                    {
                        "id": "cond",
                        "type": "condition",
                        "parameters": {"condition": "1 == 1"},
                    },
                    {
                        "id": "para_a",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo A"},
                    },
                    {
                        "id": "para_b",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo B"},
                    },
                    {
                        "id": "join",
                        "type": "converge",
                        "parameters": {},
                    },
                    {
                        "id": "final",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo done"},
                    },
                    {
                        "id": "skipped_branch",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo never"},
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "cond"},
                    {"from": "cond", "to": "para_a", "from_port": "true"},
                    {"from": "cond", "to": "para_b", "from_port": "true"},
                    {"from": "cond", "to": "skipped_branch", "from_port": "false"},
                    {"from": "para_a", "to": "join"},
                    {"from": "para_b", "to": "join"},
                    {"from": "join", "to": "final"},
                ],
            },
        )

        assert result["status"] == "completed"
        completed = result["completed_activities"]
        assert "cond" in completed
        assert "para_a" in completed
        assert "para_b" in completed
        assert "join" in completed
        assert "final" in completed
        assert "skipped_branch" not in completed
