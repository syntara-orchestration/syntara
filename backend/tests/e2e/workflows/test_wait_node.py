"""End-to-end tests for the wait node.

Tests the wait activity through the full Nexus stack (API, Temporal worker)
using short durations (1-2 seconds) to keep CI runtime practical.

Run with:
    APP_BASE_URL=http://localhost:8000 make test-e2e
"""

from datetime import datetime
from typing import Any

import pytest
from orchestrator_test_sdk.e2e.helpers import create_and_run_workflow
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models.execution_status import ExecutionStatus

WAIT_POLL_TIMEOUT = 30


def _wait_definition(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a workflow definition with the standard trigger wired to the given nodes."""
    return {
        "name": "nodes",
        "schema_version": "2.0.0",
        "triggers": [
            {"id": "trigger", "type": "manual_trigger", "parameters": {}},
        ],
        "nodes": nodes,
        "edges": edges,
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_wait_node_completes_after_duration(syntara_api: SyntaraApiRegistry) -> None:
    """A wait node with a short duration completes successfully."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-wait-basic",
        _wait_definition(
            nodes=[
                {
                    "id": "wait_1s",
                    "name": "Wait 1 Second",
                    "type": "wait",
                    "parameters": {"duration": 1},
                },
            ],
            edges=[{"from": "trigger", "to": "wait_1s"}],
        ),
        timeout=WAIT_POLL_TIMEOUT,
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a.status for a in (result.activities or [])}
    assert activities["trigger"] == "completed"
    assert activities["wait_1s"] == "completed"


@pytest.mark.e2e
def test_wait_node_downstream_executes_after_wait(syntara_api: SyntaraApiRegistry) -> None:
    """Nodes after a wait execute only after the wait completes."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-wait-downstream",
        _wait_definition(
            nodes=[
                {
                    "id": "wait_1s",
                    "name": "Wait 1 Second",
                    "type": "wait",
                    "parameters": {"duration": 1},
                },
                {
                    "id": "after_wait",
                    "name": "After Wait",
                    "type": "script",
                    "parameters": {
                        "language": "bash",
                        "code": 'echo "Executed after wait"',
                    },
                },
            ],
            edges=[
                {"from": "trigger", "to": "wait_1s"},
                {"from": "wait_1s", "to": "after_wait"},
            ],
        ),
        timeout=WAIT_POLL_TIMEOUT,
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a.status for a in (result.activities or [])}
    assert activities["wait_1s"] == "completed"
    assert activities["after_wait"] == "completed"


@pytest.mark.e2e
def test_wait_node_multiple_in_sequence(syntara_api: SyntaraApiRegistry) -> None:
    """Multiple wait nodes in sequence both complete."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-wait-sequence",
        _wait_definition(
            nodes=[
                {
                    "id": "wait_first",
                    "name": "First Wait",
                    "type": "wait",
                    "parameters": {"duration": 1},
                },
                {
                    "id": "wait_second",
                    "name": "Second Wait",
                    "type": "wait",
                    "parameters": {"duration": 1},
                },
            ],
            edges=[
                {"from": "trigger", "to": "wait_first"},
                {"from": "wait_first", "to": "wait_second"},
            ],
        ),
        timeout=WAIT_POLL_TIMEOUT,
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a.status for a in (result.activities or [])}
    assert activities["wait_first"] == "completed"
    assert activities["wait_second"] == "completed"


# ---------------------------------------------------------------------------
# Activity status tracking
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_wait_node_timestamps_correct(syntara_api: SyntaraApiRegistry) -> None:
    """Wait activity has correct started_at and completed_at with expected duration."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-wait-timestamps",
        _wait_definition(
            nodes=[
                {
                    "id": "wait_1s",
                    "name": "Wait 1 Second",
                    "type": "wait",
                    "parameters": {"duration": 1},
                },
            ],
            edges=[{"from": "trigger", "to": "wait_1s"}],
        ),
        timeout=WAIT_POLL_TIMEOUT,
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"

    wait_activity = next((a for a in (result.activities or []) if a.activity_id == "wait_1s"), None)
    assert wait_activity is not None, "wait_1s activity not found"
    assert wait_activity.started_at is not None, "started_at should be set"
    assert wait_activity.completed_at is not None, "completed_at should be set"

    started = datetime.fromisoformat(str(wait_activity.started_at))
    completed = datetime.fromisoformat(str(wait_activity.completed_at))
    elapsed = (completed - started).total_seconds()

    assert 0.5 <= elapsed <= 10.0, f"Expected ~1s elapsed, got {elapsed:.1f}s"


# ---------------------------------------------------------------------------
# Wait in conditional branch
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_wait_node_in_conditional_branch(syntara_api: SyntaraApiRegistry) -> None:
    """Only the wait node on the taken branch executes."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-wait-conditional",
        _wait_definition(
            nodes=[
                {
                    "id": "check",
                    "name": "Always True",
                    "type": "condition",
                    "parameters": {"condition": "1 == 1"},
                },
                {
                    "id": "wait_true_branch",
                    "name": "Wait True Branch",
                    "type": "wait",
                    "parameters": {"duration": 1},
                },
                {
                    "id": "wait_false_branch",
                    "name": "Wait False Branch",
                    "type": "wait",
                    "parameters": {"duration": 1},
                },
            ],
            edges=[
                {"from": "trigger", "to": "check"},
                {"from": "check", "to": "wait_true_branch", "from_port": "true"},
                {"from": "check", "to": "wait_false_branch", "from_port": "false"},
            ],
        ),
        timeout=WAIT_POLL_TIMEOUT,
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a for a in (result.activities or [])}
    assert activities["wait_true_branch"].status == "completed"
    if "wait_false_branch" in activities:
        assert activities["wait_false_branch"].status != "completed"


# ---------------------------------------------------------------------------
# Validation / Error handling
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_wait_node_zero_duration_fails(syntara_api: SyntaraApiRegistry) -> None:
    """A wait node with duration 0 fails validation."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-wait-zero",
        _wait_definition(
            nodes=[
                {
                    "id": "wait_zero",
                    "name": "Wait Zero",
                    "type": "wait",
                    "parameters": {"duration": 0},
                },
            ],
            edges=[{"from": "trigger", "to": "wait_zero"}],
        ),
        timeout=WAIT_POLL_TIMEOUT,
    )

    assert result.status == ExecutionStatus.FAILED, f"Expected failure but got: {result.status}"
    error_text = str(result.error_details or "")
    assert "duration" in error_text.lower(), f"Expected duration-related error, got: {result.error_details}"


@pytest.mark.e2e
def test_wait_node_negative_duration_fails(syntara_api: SyntaraApiRegistry) -> None:
    """A wait node with negative duration fails validation."""
    result = create_and_run_workflow(
        syntara_api,
        "e2e-wait-negative",
        _wait_definition(
            nodes=[
                {
                    "id": "wait_neg",
                    "name": "Wait Negative",
                    "type": "wait",
                    "parameters": {"duration": -5},
                },
            ],
            edges=[{"from": "trigger", "to": "wait_neg"}],
        ),
        timeout=WAIT_POLL_TIMEOUT,
    )

    assert result.status == ExecutionStatus.FAILED, f"Expected failure but got: {result.status}"
    error_text = str(result.error_details or "")
    assert "duration" in error_text.lower(), f"Expected duration-related error, got: {result.error_details}"
