"""End-to-end tests for converge node strategies and timeout behaviors.

Tests converge node execution with different strategies (all, any),
timeout configurations, and branch failure scenarios using the full
Syntara stack (API, Temporal worker, containers).

Run with:
    APP_BASE_URL=http://localhost:8000 make test-e2e
"""

from http import HTTPStatus

import pytest
from orchestrator_test_sdk.e2e.helpers import create_and_run_workflow
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import WorkflowDefinition
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.models.workflow_validate_request import WorkflowValidateRequest

# ---------------------------------------------------------------------------
# Converge validation
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_converge_with_single_branch_rejected(syntara_api: SyntaraApiRegistry) -> None:
    """A converge node with only one incoming branch produces a validation error."""
    definition = WorkflowDefinition.from_dict(
        {
            "name": "converge-validation",
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "action_node",
                    "name": "Run Action",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "echo 'hello'"},
                },
                {"id": "converge_node", "name": "Join", "type": "converge", "parameters": {}},
            ],
            "edges": [
                {"from": "trigger", "to": "action_node"},
                {"from": "action_node", "to": "converge_node"},
            ],
        }
    )

    response = syntara_api.workflows.validate_definition(body=WorkflowValidateRequest(workflow_definition=definition))

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, (
        f"Expected 422 for converge with single branch, got {response.status_code}"
    )

    body = response.parsed
    assert body is not None

    validation_result = getattr(body, "validation_result", None)
    assert validation_result is not None
    assert not validation_result.is_valid

    findings = validation_result.findings or []
    categories = [f.category for f in findings]
    assert "converge_configuration" in categories, (
        f"Expected converge_configuration finding, got categories: {categories}"
    )


# ---------------------------------------------------------------------------
# Converge execution strategies
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_converge_any_2_of_3_strategy(syntara_api: SyntaraApiRegistry):
    """Test any-2-of-3 converge strategy where one branch fails.

    Branches A and B succeed, meeting the any-2-of-3 threshold. Branch C
    fails immediately. The converge fires with the 2 successful branches.
    The workflow status is COMPLETED_WITH_ERRORS because the converge
    succeeded (handling the branch failure) but a failure is still recorded.
    """
    result = create_and_run_workflow(
        syntara_api,
        "e2e-converge-any-2-of-3",
        {
            "name": "converge",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "branch_a",
                    "name": "Branch A",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "Branch A completed"'},
                },
                {
                    "id": "branch_b",
                    "name": "Branch B",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "Branch B completed"'},
                },
                {
                    "id": "branch_c",
                    "name": "Branch C (fails)",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "exit 1"},
                },
                {
                    "id": "converge_node",
                    "name": "Converge Any 2 of 3",
                    "type": "converge",
                    "parameters": {
                        "strategy": "any",
                        "n_required": 2,
                    },
                },
                {
                    "id": "final_action",
                    "name": "Final Action",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "Final action executed"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "branch_a"},
                {"from": "trigger", "to": "branch_b"},
                {"from": "trigger", "to": "branch_c"},
                {"from": "branch_a", "to": "converge_node"},
                {"from": "branch_b", "to": "converge_node"},
                {"from": "branch_c", "to": "converge_node"},
                {"from": "converge_node", "to": "final_action"},
            ],
        },
    )

    assert result.status == ExecutionStatus.COMPLETED_WITH_ERRORS
    activities = {a.activity_id: a for a in (result.activities or [])}

    assert activities["branch_a"].status == "completed"
    assert activities["branch_b"].status == "completed"
    assert activities["branch_c"].status == "failed"
    assert activities["converge_node"].status == "completed"
    assert activities["final_action"].status == "completed"


@pytest.mark.e2e
def test_converge_timeout_continue_on_failure(syntara_api: SyntaraApiRegistry):
    """Test converge timeout with continue_on_failure=true.

    The slow branch (sleep 2) feeds through slow_intermediate before
    reaching converge. The fast branch connects directly. When the 1s
    timeout fires, slow_intermediate has not been scheduled yet (slow_branch
    is still in-flight), so it is skipped. With continue_on_failure=true
    the converge is marked as failed but downstream continues.

    Trigger -> fast_branch ----------------------> converge -> final_action
            -> slow_branch -> slow_intermediate ->
    """
    result = create_and_run_workflow(
        syntara_api,
        "e2e-converge-timeout-cof",
        {
            "name": "converge",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "fast_branch",
                    "name": "Fast Branch",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "Fast branch done"'},
                },
                {
                    "id": "slow_branch",
                    "name": "Slow Branch",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'sleep 2 && echo "Slow branch done"'},
                },
                {
                    "id": "slow_intermediate",
                    "name": "Slow Intermediate (should be skipped)",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "Intermediate"'},
                },
                {
                    "id": "converge_node",
                    "name": "Converge with timeout",
                    "type": "converge",
                    "parameters": {"wait_duration": 1},
                    "settings": {"continue_on_failure": True},
                },
                {
                    "id": "final_action",
                    "name": "Final Action",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "Executed after CoF"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "fast_branch"},
                {"from": "trigger", "to": "slow_branch"},
                {"from": "fast_branch", "to": "converge_node"},
                {"from": "slow_branch", "to": "slow_intermediate"},
                {"from": "slow_intermediate", "to": "converge_node"},
                {"from": "converge_node", "to": "final_action"},
            ],
        },
        timeout=10,
    )

    activities = {a.activity_id: a for a in (result.activities or [])}

    assert result.status == ExecutionStatus.COMPLETED_WITH_ERRORS
    assert activities["fast_branch"].status == "completed"
    assert activities["slow_branch"].status == "cancelled"  # was in-flight when timeout fired
    assert activities["slow_intermediate"].status == "skipped"  # never scheduled
    assert activities["converge_node"].status == "failed"
    assert activities["final_action"].status == "completed"


@pytest.mark.e2e
def test_converge_all_strategy(syntara_api: SyntaraApiRegistry):
    """Test converge 'all' strategy (regression test).

    Verifies existing 'wait for all' behavior is not regressed.
    All branches must complete before converge executes.
    """
    result = create_and_run_workflow(
        syntara_api,
        "e2e-converge-all-strategy",
        {
            "name": "converge",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "branch_a",
                    "name": "Branch A",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "Branch A"'},
                },
                {
                    "id": "branch_b",
                    "name": "Branch B",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "Branch B"'},
                },
                {
                    "id": "branch_c",
                    "name": "Branch C",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "Branch C"'},
                },
                {
                    "id": "converge_node",
                    "name": "Converge All",
                    "type": "converge",
                    "parameters": {"strategy": "all"},
                },
                {
                    "id": "final_action",
                    "name": "Final Action",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "All branches completed"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "branch_a"},
                {"from": "trigger", "to": "branch_b"},
                {"from": "trigger", "to": "branch_c"},
                {"from": "branch_a", "to": "converge_node"},
                {"from": "branch_b", "to": "converge_node"},
                {"from": "branch_c", "to": "converge_node"},
                {"from": "converge_node", "to": "final_action"},
            ],
        },
    )

    assert result.status == ExecutionStatus.COMPLETED, f"Failed: {result.error_details}"
    activities = {a.activity_id: a for a in (result.activities or [])}

    # Verify all branches completed
    assert activities["branch_a"].status == "completed"
    assert activities["branch_b"].status == "completed"
    assert activities["branch_c"].status == "completed"

    # Verify converge and final action executed
    assert activities["converge_node"].status == "completed"
    assert activities["final_action"].status == "completed"


# ---------------------------------------------------------------------------
# Timeout Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_converge_timeout_fail_and_skip_downstream(syntara_api: SyntaraApiRegistry):
    """Test converge timeout marks node as failed and skips downstream.

    A fast branch completes instantly, triggering the converge to start
    waiting (and the timeout handler). The slow branch feeds through an
    intermediate. When the 1s timeout fires, the intermediate has not
    been scheduled, so it is skipped. The converge is marked as failed
    and downstream is skipped.

    Trigger -> fast_branch ----------------------> converge -> downstream
            -> slow_branch -> intermediate ->
    """
    result = create_and_run_workflow(
        syntara_api,
        "e2e-converge-timeout-fail",
        {
            "name": "converge",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "fast_branch",
                    "name": "Fast Branch",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "Fast"'},
                },
                {
                    "id": "slow_branch",
                    "name": "Slow Branch",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'sleep 2 && echo "Slow"'},
                },
                {
                    "id": "intermediate",
                    "name": "Intermediate (should be skipped)",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "Intermediate"'},
                },
                {
                    "id": "converge_node",
                    "name": "Converge with fail on timeout",
                    "type": "converge",
                    "parameters": {"wait_duration": 1},
                },
                {
                    "id": "downstream_action",
                    "name": "Downstream Action (should be skipped)",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "This should not execute"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "fast_branch"},
                {"from": "trigger", "to": "slow_branch"},
                {"from": "fast_branch", "to": "converge_node"},
                {"from": "slow_branch", "to": "intermediate"},
                {"from": "intermediate", "to": "converge_node"},
                {"from": "converge_node", "to": "downstream_action"},
            ],
        },
        timeout=10,
    )

    assert result.status == ExecutionStatus.FAILED
    activities = {a.activity_id: a for a in (result.activities or [])}

    assert activities["fast_branch"].status == "completed"
    assert activities["slow_branch"].status == "cancelled"  # was in-flight when timeout fired
    assert activities["intermediate"].status == "skipped"  # never scheduled
    assert activities["converge_node"].status == "failed"
    assert activities["downstream_action"].status == "skipped"


@pytest.mark.e2e
def test_converge_cof_any_strategy_threshold_not_met(syntara_api: SyntaraApiRegistry):
    """Test converge CoF with ANY strategy when n_required threshold is not met.

    With any-2-of-3 and continue_on_failure=true, 2 branches fail and only
    1 succeeds. The threshold cannot be met, so converge is marked as failed
    via _evaluate_converge_failure, but continue_on_failure allows the
    downstream node to execute.

    Trigger -> success_branch -----> converge (any 2/3, CoF) -> final_action
            -> failing_branch_a ->
            -> failing_branch_b ->
    """
    result = create_and_run_workflow(
        syntara_api,
        "e2e-converge-cof-any-threshold",
        {
            "name": "converge",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "success_branch",
                    "name": "Success Branch",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'sleep 1 && echo "success"'},
                },
                {
                    "id": "failing_branch_a",
                    "name": "Failing Branch A",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "exit 1"},
                },
                {
                    "id": "failing_branch_b",
                    "name": "Failing Branch B",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "exit 1"},
                },
                {
                    "id": "converge_node",
                    "name": "Converge (any 2/3, CoF)",
                    "type": "converge",
                    "parameters": {"strategy": "any", "n_required": 2},
                    "settings": {"continue_on_failure": True},
                },
                {
                    "id": "final_action",
                    "name": "Final Action",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "downstream executed"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "success_branch"},
                {"from": "trigger", "to": "failing_branch_a"},
                {"from": "trigger", "to": "failing_branch_b"},
                {"from": "success_branch", "to": "converge_node"},
                {"from": "failing_branch_a", "to": "converge_node"},
                {"from": "failing_branch_b", "to": "converge_node"},
                {"from": "converge_node", "to": "final_action"},
            ],
        },
    )

    assert result.status == ExecutionStatus.COMPLETED_WITH_ERRORS
    activities = {a.activity_id: a for a in (result.activities or [])}

    assert activities["success_branch"].status == "completed"
    assert activities["failing_branch_a"].status == "failed"
    assert activities["failing_branch_b"].status == "failed"
    assert activities["converge_node"].status == "failed"
    assert activities["final_action"].status == "completed"


@pytest.mark.e2e
def test_converge_no_timeout_when_all_complete(syntara_api: SyntaraApiRegistry):
    """Test converge timeout doesn't fire when all branches complete in time.

    Verifies that if all branches complete before the timeout, the timeout
    handler doesn't fire and the workflow completes normally.
    """
    result = create_and_run_workflow(
        syntara_api,
        "e2e-converge-no-timeout",
        {
            "name": "converge",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "branch_a",
                    "name": "Branch A",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "A"'},
                },
                {
                    "id": "branch_b",
                    "name": "Branch B",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "B"'},
                },
                {
                    "id": "converge_node",
                    "name": "Converge with long timeout",
                    "type": "converge",
                    "parameters": {"wait_duration": 1},
                },
                {
                    "id": "final_action",
                    "name": "Final Action",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "Completed normally"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "branch_a"},
                {"from": "trigger", "to": "branch_b"},
                {"from": "branch_a", "to": "converge_node"},
                {"from": "branch_b", "to": "converge_node"},
                {"from": "converge_node", "to": "final_action"},
            ],
        },
    )

    assert result.status == ExecutionStatus.COMPLETED
    activities = {a.activity_id: a for a in (result.activities or [])}

    # Verify all branches completed
    assert activities["branch_a"].status == "completed"
    assert activities["branch_b"].status == "completed"

    # Verify converge and final action executed normally
    assert activities["converge_node"].status == "completed"
    assert activities["final_action"].status == "completed"


@pytest.mark.e2e
def test_converge_timeout_multihop_starts_at_fork(syntara_api: SyntaraApiRegistry):
    """Test timeout starts at fork completion when ALL branches are multi-hop.

    Both branches have intermediate nodes. The 1s timeout must start when
    the fork completes (step1 nodes are scheduled), not when step1 nodes
    complete and step2 nodes are scheduled.

    With fork detection: timeout fires at ~1s (from fork completion).
    Without fork detection: timeout would fire at ~3s (2s step1 + 1s wait).

    Trigger -> branch_a_step1 (2s) -> branch_a_step2 -> converge (1s) -> downstream
            -> branch_b_step1 (2s) -> branch_b_step2 -> ↗
    """
    result = create_and_run_workflow(
        syntara_api,
        "e2e-converge-timeout-multihop",
        {
            "name": "converge",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "branch_a_step1",
                    "name": "Branch A Step 1 (2s)",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'sleep 2 && echo "A1 done"'},
                },
                {
                    "id": "branch_a_step2",
                    "name": "Branch A Step 2",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "A2 done"'},
                },
                {
                    "id": "branch_b_step1",
                    "name": "Branch B Step 1 (2s)",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'sleep 2 && echo "B1 done"'},
                },
                {
                    "id": "branch_b_step2",
                    "name": "Branch B Step 2",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "B2 done"'},
                },
                {
                    "id": "converge_node",
                    "name": "Converge (1s timeout)",
                    "type": "converge",
                    "parameters": {"wait_duration": 1},
                },
                {
                    "id": "downstream",
                    "name": "Downstream",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "downstream"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "branch_a_step1"},
                {"from": "trigger", "to": "branch_b_step1"},
                {"from": "branch_a_step1", "to": "branch_a_step2"},
                {"from": "branch_b_step1", "to": "branch_b_step2"},
                {"from": "branch_a_step2", "to": "converge_node"},
                {"from": "branch_b_step2", "to": "converge_node"},
                {"from": "converge_node", "to": "downstream"},
            ],
        },
        timeout=10,
    )

    assert result.status == ExecutionStatus.FAILED
    activities = {a.activity_id: a for a in (result.activities or [])}

    # Timeout fires at ~1s (from fork start). In-flight step1 nodes are detached
    # and reported as cancelled. step2 nodes are never scheduled, so they stay skipped.
    assert activities["branch_a_step1"].status == "cancelled"
    assert activities["branch_b_step1"].status == "cancelled"
    assert activities["branch_a_step2"].status == "skipped"
    assert activities["branch_b_step2"].status == "skipped"
    assert activities["converge_node"].status == "failed"
    assert activities["downstream"].status == "skipped"


# ---------------------------------------------------------------------------
# Branch Failure Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_converge_one_branch_fails_all_strategy(syntara_api: SyntaraApiRegistry):
    """Test converge behavior when one branch fails with 'all' strategy.

    The success branches sleep briefly so the failure is processed first.
    ALL strategy is strict: any predecessor failure fails the converge
    and skips downstream nodes. In-flight parallel branches are not
    cancelled — they run to completion while the converge node fails.
    """
    result = create_and_run_workflow(
        syntara_api,
        "e2e-converge-branch-fail-all",
        {
            "name": "converge",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "success_branch_a",
                    "name": "Success Branch A",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'sleep 1 && echo "Success A"'},
                },
                {
                    "id": "success_branch_b",
                    "name": "Success Branch B",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'sleep 1 && echo "Success B"'},
                },
                {
                    "id": "failing_branch",
                    "name": "Failing Branch",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "exit 1"},
                },
                {
                    "id": "converge_node",
                    "name": "Converge All",
                    "type": "converge",
                    "parameters": {"strategy": "all"},
                },
                {
                    "id": "final_action",
                    "name": "Final Action",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "Executed"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "success_branch_a"},
                {"from": "trigger", "to": "success_branch_b"},
                {"from": "trigger", "to": "failing_branch"},
                {"from": "success_branch_a", "to": "converge_node"},
                {"from": "success_branch_b", "to": "converge_node"},
                {"from": "failing_branch", "to": "converge_node"},
                {"from": "converge_node", "to": "final_action"},
            ],
        },
        timeout=10,
    )

    assert result.status == ExecutionStatus.FAILED
    activities = {a.activity_id: a for a in (result.activities or [])}

    # success_branch_a and _b were in-flight (sleeping) when the failing_branch
    # triggered _fail_converge_node — they are detached and reported as cancelled.
    assert activities["success_branch_a"].status == "cancelled"
    assert activities["success_branch_b"].status == "cancelled"
    assert activities["failing_branch"].status == "failed"
    assert activities["converge_node"].status == "failed"
    assert activities["final_action"].status == "skipped"


@pytest.mark.e2e
def test_converge_branch_failure_any_strategy(syntara_api: SyntaraApiRegistry):
    """Test converge 'any' strategy with branch failures.

    With any-2-of-3 strategy, 2 branches fail and only 1 succeeds.
    The threshold of 2 completions cannot be met, so the converge
    should be skipped along with downstream nodes.
    """
    result = create_and_run_workflow(
        syntara_api,
        "e2e-converge-branch-failure-any",
        {
            "name": "converge",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "success_branch",
                    "name": "Success Branch (slow to ensure failures processed first)",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'sleep 1 && echo "Success"'},
                },
                {
                    "id": "failing_branch_a",
                    "name": "Failing Branch A",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "exit 1"},
                },
                {
                    "id": "failing_branch_b",
                    "name": "Failing Branch B",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "exit 1"},
                },
                {
                    "id": "converge_node",
                    "name": "Converge Any 2 of 3",
                    "type": "converge",
                    "parameters": {
                        "strategy": "any",
                        "n_required": 2,
                    },
                },
                {
                    "id": "final_action",
                    "name": "Final Action (should not execute)",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "Should not run"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "success_branch"},
                {"from": "trigger", "to": "failing_branch_a"},
                {"from": "trigger", "to": "failing_branch_b"},
                {"from": "success_branch", "to": "converge_node"},
                {"from": "failing_branch_a", "to": "converge_node"},
                {"from": "failing_branch_b", "to": "converge_node"},
                {"from": "converge_node", "to": "final_action"},
            ],
        },
    )

    assert result.status == ExecutionStatus.FAILED
    activities = {a.activity_id: a for a in (result.activities or [])}

    assert activities["success_branch"].status == "completed"
    assert activities["failing_branch_a"].status == "failed"
    assert activities["failing_branch_b"].status == "failed"
    assert activities["converge_node"].status == "failed"
    assert activities["final_action"].status == "skipped"


@pytest.mark.e2e
def test_converge_all_branches_fail(syntara_api: SyntaraApiRegistry):
    """Test converge when all branches fail.

    Verifies that if all branches fail, the converge node is marked
    as failed (not skipped) because predecessor failures caused it.
    """
    result = create_and_run_workflow(
        syntara_api,
        "e2e-converge-all-fail",
        {
            "name": "converge",
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "trigger", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [
                {
                    "id": "failing_branch_a",
                    "name": "Failing Branch A",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "exit 1"},
                },
                {
                    "id": "failing_branch_b",
                    "name": "Failing Branch B",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "exit 1"},
                },
                {
                    "id": "failing_branch_c",
                    "name": "Failing Branch C",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "exit 1"},
                },
                {
                    "id": "converge_node",
                    "name": "Converge",
                    "type": "converge",
                    "parameters": {},
                },
                {
                    "id": "final_action",
                    "name": "Final Action (should not execute)",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "Should not run"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "failing_branch_a"},
                {"from": "trigger", "to": "failing_branch_b"},
                {"from": "trigger", "to": "failing_branch_c"},
                {"from": "failing_branch_a", "to": "converge_node"},
                {"from": "failing_branch_b", "to": "converge_node"},
                {"from": "failing_branch_c", "to": "converge_node"},
                {"from": "converge_node", "to": "final_action"},
            ],
        },
    )

    assert result.status == ExecutionStatus.FAILED
    activities = {a.activity_id: a for a in (result.activities or [])}

    # Under ALL strategy the engine short-circuits when the first branch
    # fails.  Remaining branches that are still in-flight become detached
    # and are reported as "cancelled"; branches that never started are "skipped".
    # Only the branch whose failure triggered the converge is guaranteed "failed".
    branch_statuses = [
        activities["failing_branch_a"].status,
        activities["failing_branch_b"].status,
        activities["failing_branch_c"].status,
    ]
    assert any(s == "failed" for s in branch_statuses), f"At least one branch must have failed: {branch_statuses}"
    assert all(s in ("failed", "skipped", "cancelled") for s in branch_statuses), (
        f"Unexpected branch status: {branch_statuses}"
    )

    assert activities["converge_node"].status in ("failed", "skipped")
    assert activities["final_action"].status == "skipped"
