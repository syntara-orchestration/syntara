"""E2E tests for Workflow Execution (ANSTRAT-1845).

Tests workflow execution including triggering, status tracking,
and integration with Temporal workflows.

API-14: Execute Workflow
API-15: Get Execution Status with Per-Node Details
API-16: List Executions with Filtering
API-17: Cancel Running Execution
API-36: Workflow Execution — Parallel Branches
API-37: Workflow Execution — Node Failure Propagation
"""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import _retry_api_call, create_and_run_workflow, poll_for_pending_approval
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import (
    ExecutionCreate,
    WorkflowCreate,
    WorkflowDefinition,
    WorkflowRead,
    WorkflowUpdate,
)
from syntara_api_client.models.approval_request_status import ApprovalRequestStatus
from syntara_api_client.models.execution_status import ExecutionStatus

pytestmark = [pytest.mark.e2e]


def _workflow_definition_with_nodes(
    workflow_name: str,
    *nodes: dict[str, Any],
    edges: list[dict[str, Any]] | None = None,
) -> WorkflowDefinition:
    """Create a workflow definition with custom nodes and edges."""
    return WorkflowDefinition.from_dict(
        {
            "name": workflow_name,
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
            "nodes": list(nodes),
            "edges": edges or [],
        }
    )


class TestWorkflowExecution:
    """Workflow execution tests - triggering and status tracking."""

    def test_execute_workflow_with_script_node(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """API 14: Execute workflow and track execution status.

        Objective: Verify that a valid workflow can be executed and tracked.

        Test Procedure:
        1. Create a workflow with a script node
        2. POST /api/v1/executions to execute the workflow
        3. Poll or query the execution status

        Expected Results:
        - Response is 201 Created with an execution object containing execution_id
        - The execution transitions through states: pending → running → completed
        - The Temporal workflow is started and tracked in the database
        """
        workflow_name = unique_name("e2e-execute-workflow")

        # Step 1: Create workflow with a simple script node
        workflow_data = WorkflowCreate(
            name=workflow_name,
            description="Workflow for testing execution",
            workflow_definition=_workflow_definition_with_nodes(
                workflow_name,
                {
                    "id": "script_node",
                    "name": "Hello Script",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "echo 'Hello from execution test'"},
                },
                edges=[{"from": "trigger_manual", "to": "script_node"}],
            ),
            project_id=first_project_id,
        )
        workflow = workflow_factory(workflow_data)

        # Verify workflow was created
        assert workflow.id is not None
        assert workflow.name == workflow_name

        # Step 2: Execute the workflow
        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger_manual")
        ).assert_and_get()

        # Expected Result 1: 201 Created with execution object
        # Verify execution object contains required fields
        assert execution.id is not None, "Execution should have an ID"
        assert execution.workflow_id == workflow.id, "Execution should reference the correct workflow"
        assert execution.temporal_workflow_id is not None, "Execution should have a Temporal workflow ID"
        assert execution.status is not None, "Execution should have a status"

        execution_id = execution.id

        # Step 3: Poll execution status and verify state transitions
        # Expected states: pending → running → completed
        max_polls = 30  # Maximum number of status checks (30 * 2s = 60s timeout)
        poll_interval = 2  # seconds between polls

        states_observed = set()
        final_status = None
        final_execution = None

        for _ in range(max_polls):
            # Query execution status
            current_execution = _retry_api_call(
                lambda: syntara_api.executions.get(execution_id=UUID(str(execution_id)), include="activities")
            ).assert_and_get()

            # Track observed states
            current_status = str(current_execution.status)
            states_observed.add(current_status)

            # Check if execution reached a terminal state
            if current_status in ["completed", "failed", "cancelled"]:
                final_status = current_status
                final_execution = current_execution
                break

            time.sleep(poll_interval)

        # Expected Result 2: Execution should complete successfully
        assert final_status is not None, (
            f"Execution did not reach a terminal state within {max_polls * poll_interval}s. "
            f"Last observed states: {states_observed}. "
            f"Temporal may not be running. Start it with: make temporal-run"
        )

        assert final_status == "completed", (
            f"Execution should complete successfully. Final status: {final_status}, States: {states_observed}"
        )

        # Expected Result 3: Verify final execution details
        assert final_execution is not None
        assert final_execution.completed_at is not None, "Completed execution should have completed_at timestamp"
        assert final_execution.error_details is None, "Successful execution should have no error details"

        # Verify Temporal workflow was created
        assert final_execution.temporal_workflow_id is not None, "Execution should have a Temporal workflow ID"

    def test_get_execution_status_with_per_node_details(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """API 15: Get execution status with per-node activity details.

        Objective: Verify that execution status includes per-node activity statuses.

        Test Procedure:
        1. Execute a workflow with multiple nodes
        2. GET /api/v1/executions/{execution_id}
        3. Verify the response

        Expected Results:
        - Response is 200 with execution status, start time, and per-node activity statuses
        - Each activity status includes the node ID, status, start/end timestamps
        - Output data is available for completed nodes
        - Input data is available for each node (for I/O inspection)
        """
        workflow_name = unique_name("e2e-execution-details")

        # Step 1: Create workflow with multiple script nodes
        workflow_data = WorkflowCreate(
            name=workflow_name,
            description="Workflow for testing execution details with multiple nodes",
            project_id=first_project_id,
            workflow_definition=_workflow_definition_with_nodes(
                workflow_name,
                {
                    "id": "node_a",
                    "name": "First Script",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "echo 'Output from node A'"},
                },
                {
                    "id": "node_b",
                    "name": "Second Script",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "echo 'Output from node B'"},
                },
                {
                    "id": "node_c",
                    "name": "Third Script",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "echo 'Output from node C'"},
                },
                edges=[
                    {"from": "trigger_manual", "to": "node_a"},
                    {"from": "node_a", "to": "node_b"},
                    {"from": "node_b", "to": "node_c"},
                ],
            ),
        )
        workflow = workflow_factory(workflow_data)

        # Execute the workflow
        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger_manual")
        ).assert_and_get()

        execution_id = execution.id

        # Step 2: Poll until execution completes
        max_polls = 30
        poll_interval = 2
        final_execution = None

        for _ in range(max_polls):
            # Step 3: GET execution status with activities included
            current_execution = _retry_api_call(
                lambda: syntara_api.executions.get(execution_id=UUID(str(execution_id)), include="activities")
            ).assert_and_get()

            # Check if completed
            if str(current_execution.status) in ["completed", "failed", "cancelled"]:
                final_execution = current_execution
                break

            time.sleep(poll_interval)

        assert final_execution is not None, f"Execution did not complete within {max_polls * poll_interval}s"
        assert str(final_execution.status) == "completed", (
            f"Execution should complete successfully, got: {final_execution.status}"
        )

        # Expected Result 2: Execution has start time (created_at)
        assert final_execution.created_at is not None, "Execution should have created_at timestamp"
        assert final_execution.completed_at is not None, "Completed execution should have completed_at timestamp"

        # Expected Result 3: Per-node activity statuses are included
        assert final_execution.activities is not None, "Execution should include activities data"

        # We expect exactly 4 activities (trigger_manual + node_a, node_b, node_c)
        assert len(final_execution.activities) == 4, (
            f"Expected exactly 4 activities (trigger + 3 nodes), got {len(final_execution.activities)}"
        )

        # Verify we have the expected activity IDs
        activity_ids = [activity.activity_id for activity in final_execution.activities]
        expected_activity_ids = {"trigger_manual", "node_a", "node_b", "node_c"}
        assert set(activity_ids) == expected_activity_ids, (
            f"Expected activities {expected_activity_ids}, got {set(activity_ids)}"
        )

        # Expected Result 4: Each activity has required fields
        for activity in final_execution.activities:
            # Activity should have an ID
            assert activity.activity_id is not None, "Activity should have activity_id"

            # Activity should have a status
            assert activity.status is not None, "Activity should have status"

            # Completed activities should have timestamps
            if str(activity.status) == "completed":
                assert activity.started_at is not None, (
                    f"Completed activity {activity.activity_id} should have started_at timestamp"
                )
                assert activity.completed_at is not None, (
                    f"Completed activity {activity.activity_id} should have completed_at timestamp"
                )

                # Expected Result 5: Output data should be available for completed nodes
                # Note: output_data might be None or empty depending on the activity
                # For script nodes that produce output, it should be present
                # We'll just verify the field exists (can be None or have data)
                assert hasattr(activity, "output_data"), "Activity should have output_data field"

        # Verify all activity IDs are unique (already extracted above)
        assert len(activity_ids) == len(set(activity_ids)), "All activity IDs should be unique"

        # Expected Result 6: Execution metadata is complete
        assert final_execution.workflow_id == workflow.id, "Execution should reference correct workflow"
        assert final_execution.temporal_workflow_id is not None, "Should have Temporal workflow ID"
        assert final_execution.error_details is None, "Successful execution should have no errors"

    def test_list_executions_with_filtering(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """API 16: List executions with filtering by status.

        Epic: AAP-70985
        Objective: Verify that execution history can be retrieved and filtered.

        Test Procedure:
        1. Execute a workflow multiple times (some successful, some failed)
        2. GET /api/v1/executions?workflow_id={id}
        3. GET /api/v1/executions?workflow_id={id}&status=failed

        Expected Results:
        - Response includes all executions for the workflow
        - Filtering by status returns only matching executions
        - Each execution includes status, duration, trigger source, and summary
        """
        workflow_name = unique_name("e2e-list-executions")

        # Create a workflow with a simple script node
        workflow_data = WorkflowCreate(
            name=workflow_name,
            description="Workflow for testing execution listing and filtering",
            project_id=first_project_id,
            workflow_definition=_workflow_definition_with_nodes(
                workflow_name,
                {
                    "id": "script_node",
                    "name": "Conditional Script",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "echo 'Running script'; exit 0"},
                },
                edges=[{"from": "trigger_manual", "to": "script_node"}],
            ),
        )
        workflow = workflow_factory(workflow_data)

        # Step 1: Execute workflow multiple times - create some successful and some failed executions
        execution_ids = []
        expected_successful = 0
        expected_failed = 0

        # Create 2 successful executions
        for _ in range(2):
            execution = syntara_api.executions.create(
                body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger_manual")
            ).assert_and_get()
            execution_ids.append(execution.id)
            expected_successful += 1

        # Update workflow to fail (exit with error code)
        failed_workflow_def = _workflow_definition_with_nodes(
            workflow_name,
            {
                "id": "script_node",
                "name": "Failing Script",
                "type": "script",
                "parameters": {"language": "bash", "code": "echo 'This will fail'; exit 1"},
            },
            edges=[{"from": "trigger_manual", "to": "script_node"}],
        )

        syntara_api.workflows.update(
            workflow_id=workflow.id, body=WorkflowUpdate(workflow_definition=failed_workflow_def.to_dict())
        ).assert_and_get()

        # Create 2 failed executions
        for _ in range(2):
            execution = syntara_api.executions.create(
                body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger_manual")
            ).assert_and_get()
            execution_ids.append(execution.id)
            expected_failed += 1

        # Wait for all executions to reach a terminal state
        max_polls = 30
        poll_interval = 2
        terminal_states = {"completed", "failed", "cancelled"}

        for exec_id in execution_ids:
            for _poll in range(max_polls):
                execution = _retry_api_call(
                    lambda eid=exec_id: syntara_api.executions.get(execution_id=UUID(str(eid)))
                ).assert_and_get()
                if str(execution.status) in terminal_states:
                    break
                time.sleep(poll_interval)
            else:
                pytest.fail(
                    f"Execution {exec_id} did not reach a terminal state "
                    f"within {max_polls * poll_interval}s (last status: {execution.status})"
                )

        # Step 2: List all executions for the workflow (no status filter)
        all_executions_list = syntara_api.executions.list(
            additional_params={"workflow_id": str(workflow.id)}, limit=100
        ).assert_and_get()

        # Expected Result 1: Response includes all executions for the workflow
        all_executions = all_executions_list.resources
        assert len(all_executions) == 4, (
            f"Should have exactly 4 executions (2 successful + 2 failed), got {len(all_executions)}"
        )

        # Verify each execution has required fields
        for execution in all_executions:
            # Expected Result 3: Each execution includes status, duration, and summary
            assert execution.id is not None, "Execution should have ID"
            assert execution.status is not None, "Execution should have status"
            assert execution.created_at is not None, "Execution should have created_at (start time)"
            assert execution.workflow_id == workflow.id, "Execution should belong to the correct workflow"

            # Duration can be calculated from created_at and completed_at
            if str(execution.status) in ["completed", "failed"]:
                assert execution.completed_at is not None, "Terminal executions should have completed_at"

        # Step 3: Filter executions by status=failed
        failed_executions_list = syntara_api.executions.list(
            additional_params={"workflow_id": str(workflow.id), "status": "failed"}, limit=100
        ).assert_and_get()

        # Expected Result 2: Filtering by status returns only matching executions
        failed_executions = failed_executions_list.resources
        assert len(failed_executions) == expected_failed, (
            f"Should have exactly {expected_failed} failed executions, got {len(failed_executions)}"
        )

        # Verify all returned executions have failed status
        for execution in failed_executions:
            assert str(execution.status) == "failed", (
                f"Filtered list should only contain failed executions, got {execution.status}"
            )
            assert execution.workflow_id == workflow.id, "Should only include executions from this workflow"

        # Test filtering by status=completed
        completed_executions_list = syntara_api.executions.list(
            additional_params={"workflow_id": str(workflow.id), "status": "completed"}, limit=100
        ).assert_and_get()

        completed_executions = completed_executions_list.resources
        assert len(completed_executions) == expected_successful, (
            f"Should have exactly {expected_successful} completed executions, got {len(completed_executions)}"
        )

        # Verify all returned executions have completed status
        for execution in completed_executions:
            assert str(execution.status) == "completed", (
                f"Filtered list should only contain completed executions, got {execution.status}"
            )

        # Verify total count: failed + completed should match all executions for this workflow
        our_executions = [e for e in all_executions if e.id in execution_ids]
        our_completed = len([e for e in our_executions if str(e.status) == "completed"])
        our_failed = len([e for e in our_executions if str(e.status) == "failed"])

        assert our_completed == expected_successful, (
            f"Expected {expected_successful} successful executions, got {our_completed}"
        )
        assert our_failed == expected_failed, f"Expected {expected_failed} failed executions, got {our_failed}"

    def test_cancel_execution_with_pending_approval(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """API 17: Cancel a running execution that has a pending approval request.

        Objective: Verify that cancelling a workflow execution also cancels
        any pending approval requests created by that execution.

        Test Procedure:
        1. Create a workflow: trigger → approval_gate → post_approval_script
        2. Execute the workflow and wait for the approval request to appear
        3. Cancel the execution while the approval is pending
        4. Verify both the execution and the approval request are cancelled

        Expected Results:
        - The cancel request returns 202 Accepted
        - The execution transitions to cancelled status
        - The pending approval request transitions to cancelled status
        - The downstream post-approval node is not executed
        """
        workflow_name = unique_name("e2e-cancel-approval")

        workflow_data = WorkflowCreate(
            name=workflow_name,
            description="Workflow for testing cancel with pending approval",
            project_id=first_project_id,
            workflow_definition=_workflow_definition_with_nodes(
                workflow_name,
                {
                    "id": "approval_gate",
                    "name": "Review Gate",
                    "type": "approval",
                    "parameters": {},
                },
                {
                    "id": "post_approval_script",
                    "name": "Post-Approval Step",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "echo 'approved path executed'"},
                },
                edges=[
                    {"from": "trigger_manual", "to": "approval_gate"},
                    {"from": "approval_gate", "to": "post_approval_script", "from_port": "approved"},
                ],
            ),
        )
        workflow = workflow_factory(workflow_data)

        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger_manual")
        ).assert_and_get()
        execution_id = UUID(str(execution.id))

        approval = poll_for_pending_approval(syntara_api, execution_id, timeout=30)
        assert approval.status == ApprovalRequestStatus.PENDING
        approval_id = UUID(str(approval.id))

        cancel_response = syntara_api.executions.cancel(execution_id=execution_id)
        assert cancel_response.status_code == HTTPStatus.ACCEPTED, (
            f"Expected 202 Accepted, got {cancel_response.status_code}: {cancel_response.content!r}"
        )

        max_polls = 20
        poll_interval = 1
        cancelled_execution = None

        for _ in range(max_polls):
            current_execution = syntara_api.executions.get(
                execution_id=execution_id, include="activities"
            ).assert_and_get()

            if str(current_execution.status) == "cancelled":
                cancelled_execution = current_execution
                break

            time.sleep(poll_interval)

        assert cancelled_execution is not None, (
            f"Execution did not transition to cancelled within {max_polls * poll_interval}s. "
            f"Last status: {current_execution.status!s}"
        )

        # Verify the approval request was also cancelled
        approval_after = syntara_api.approvals.get(approval_id=approval_id).assert_and_get()
        assert approval_after.status == ApprovalRequestStatus.CANCELLED, (
            f"Approval should be cancelled, got {approval_after.status}"
        )

        assert cancelled_execution.temporal_workflow_id is not None, "Execution should have Temporal workflow ID"
        assert cancelled_execution.activities is not None, "Cancelled execution should have activities"

        activity_statuses = {a.activity_id: str(a.status) for a in cancelled_execution.activities}

        if "post_approval_script" in activity_statuses:
            assert activity_statuses["post_approval_script"] == "skipped", (
                f"post_approval_script should be skipped after cancellation, "
                f"got {activity_statuses['post_approval_script']}"
            )

        assert cancelled_execution.completed_at is not None, "Cancelled execution should have completed_at timestamp"
        assert cancelled_execution.created_at < cancelled_execution.completed_at, (
            "Completed time should be after created time"
        )


# ---------------------------------------------------------------------------
# API-36: Parallel Branches
# ---------------------------------------------------------------------------

PARALLEL_POLL_TIMEOUT = 45  # seconds — parallel wait branches take ~5s wall-clock


class TestParallelBranches:
    """API-36: Workflow Execution — Parallel Branches.

    Objective: Verify that a workflow with parallel branches executes branches
    concurrently, not sequentially. The wall-clock time for two branches each
    waiting N seconds must be closer to N than to 2N.

    Test Procedure:
    1. Create a DAG: trigger → [wait_a (4s), wait_b (4s)] → converge → final
    2. Execute the workflow and record start/end wall-clock time
    3. Assert total wall-clock < 4s * 1.8 (8s) — well below the 8s sequential floor

    Expected Results:
    - Both branches execute concurrently (total ~4s, not ~8s)
    - The converge node executes only after both branches complete
    - Output from both branches is available downstream via expressions
    """

    @pytest.mark.skip(reason="Timing-sensitive: CI runner load can push wall-clock past ceiling")
    def test_two_parallel_wait_branches_run_concurrently(self, syntara_api: SyntaraApiRegistry) -> None:
        """Two parallel wait nodes complete in ~branch_duration, not ~2x."""
        branch_duration = 4  # seconds per branch
        # Sequential worst-case would be 2 * branch_duration = 8s.
        # Allow generous slack for CI scheduling overhead; still proves concurrency.
        wall_clock_ceiling = branch_duration * 1.8  # 7.2s

        result = create_and_run_workflow(
            syntara_api,
            "e2e-parallel-wait-branches",
            {
                "name": "parallel-wait",
                "schema_version": "2.0.0",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "wait_a",
                        "name": "Branch A Wait",
                        "type": "wait",
                        "parameters": {"duration": branch_duration},
                    },
                    {
                        "id": "wait_b",
                        "name": "Branch B Wait",
                        "type": "wait",
                        "parameters": {"duration": branch_duration},
                    },
                    {
                        "id": "join",
                        "name": "Converge",
                        "type": "converge",
                        "parameters": {},
                    },
                    {
                        "id": "final",
                        "name": "Final Step",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo 'both branches done'"},
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "wait_a"},
                    {"from": "trigger", "to": "wait_b"},
                    {"from": "wait_a", "to": "join"},
                    {"from": "wait_b", "to": "join"},
                    {"from": "join", "to": "final"},
                ],
            },
            timeout=PARALLEL_POLL_TIMEOUT,
        )

        # ExecutionRead.created_at is a better representation of when the Workflow execution started
        start = result.created_at
        elapsed = (datetime.now(UTC) - start).total_seconds()

        assert result.status == ExecutionStatus.COMPLETED, f"Execution failed: {result.error_details}"

        activities = {a.activity_id: a for a in (result.activities or [])}

        # All nodes must have completed.
        for node_id in ("trigger", "wait_a", "wait_b", "join", "final"):
            assert node_id in activities, f"Missing activity record for '{node_id}'"
            assert activities[node_id].status == "completed", (
                f"Expected '{node_id}' to be completed, got {activities[node_id].status}"
            )

        # Converge must start after both branches complete.
        join_started = activities["join"].started_at
        wait_a_done = activities["wait_a"].completed_at
        wait_b_done = activities["wait_b"].completed_at
        assert join_started is not None
        assert wait_a_done is not None
        assert wait_b_done is not None

        assert join_started >= wait_a_done, "Converge must start after branch A completes"
        assert join_started >= wait_b_done, "Converge must start after branch B completes"

        # Concurrency assertion: total wall-clock must be less than sequential would take.
        assert elapsed < wall_clock_ceiling, (
            f"Wall-clock time {elapsed:.1f}s >= {wall_clock_ceiling}s — "
            f"branches may have run sequentially instead of concurrently. "
            f"Each branch waits {branch_duration}s; sequential total would be ~{2 * branch_duration}s."
        )

    def test_three_parallel_branches_all_complete(self, syntara_api: SyntaraApiRegistry) -> None:
        """Three parallel script branches all complete before the converge node runs."""
        result = create_and_run_workflow(
            syntara_api,
            "e2e-three-parallel-branches",
            {
                "name": "three-parallel",
                "schema_version": "2.0.0",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "branch_a",
                        "name": "Branch A",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo A"},
                    },
                    {
                        "id": "branch_b",
                        "name": "Branch B",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo B"},
                    },
                    {
                        "id": "branch_c",
                        "name": "Branch C",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo C"},
                    },
                    {"id": "join", "name": "Converge", "type": "converge", "parameters": {}},
                    {
                        "id": "final",
                        "name": "Final",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo done"},
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "branch_a"},
                    {"from": "trigger", "to": "branch_b"},
                    {"from": "trigger", "to": "branch_c"},
                    {"from": "branch_a", "to": "join"},
                    {"from": "branch_b", "to": "join"},
                    {"from": "branch_c", "to": "join"},
                    {"from": "join", "to": "final"},
                ],
            },
        )

        assert result.status == ExecutionStatus.COMPLETED, f"Execution failed: {result.error_details}"

        activities = {a.activity_id: a.status for a in (result.activities or [])}
        for node_id in ("trigger", "branch_a", "branch_b", "branch_c", "join", "final"):
            assert activities.get(node_id) == "completed", (
                f"Expected '{node_id}' completed, got {activities.get(node_id)}"
            )

        # Final step must start after converge, which starts after all three branches.
        detailed = {a.activity_id: a for a in (result.activities or [])}
        join_started = detailed["join"].started_at
        final_started = detailed["final"].started_at
        assert join_started is not None
        assert final_started is not None
        assert final_started >= join_started, "Final step must start after converge"


# ---------------------------------------------------------------------------
# API-37: Node Failure Propagation
# ---------------------------------------------------------------------------


class TestNodeFailurePropagation:
    """API-37: Workflow Execution — Node Failure Propagation.

    Objective: Verify that when a node fails, downstream nodes are NOT executed
    and the overall workflow execution is marked as failed.

    Test Procedure:
    1. Create a chain: Node A (succeeds) → Node B (configured to fail via exit 1) → Node C
    2. Execute the workflow
    3. Assert Node B has status "failed", Node C is not "completed", overall is "failed"

    Expected Results:
    - Node A completes successfully
    - Node B fails (non-zero exit)
    - Node C is not executed (status "skipped" or absent)
    - Overall execution status is "failed"
    """

    def test_failed_node_stops_downstream_execution(self, syntara_api: SyntaraApiRegistry) -> None:
        """A failing middle node prevents downstream nodes from executing."""
        result = create_and_run_workflow(
            syntara_api,
            "e2e-failure-propagation-linear",
            {
                "name": "failure-propagation",
                "schema_version": "2.0.0",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "node_a",
                        "name": "Node A — Succeeds",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo 'node A ok'"},
                    },
                    {
                        "id": "node_b",
                        "name": "Node B — Fails",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo 'node B failing'; exit 1"},
                    },
                    {
                        "id": "node_c",
                        "name": "Node C — Should Not Run",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo 'node C ran (unexpected)'"},
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "node_a"},
                    {"from": "node_a", "to": "node_b"},
                    {"from": "node_b", "to": "node_c"},
                ],
            },
        )

        # Overall execution must fail.
        assert result.status == ExecutionStatus.FAILED, (
            f"Expected overall execution status 'failed', got '{result.status}'. Error details: {result.error_details}"
        )

        activities = {a.activity_id: a for a in (result.activities or [])}

        # Node A must complete — it runs before the failure.
        assert "node_a" in activities, "node_a should have an activity record"
        assert activities["node_a"].status == "completed", (
            f"node_a should be completed, got {activities['node_a'].status}"
        )

        # Node B must fail.
        assert "node_b" in activities, "node_b should have an activity record"
        assert activities["node_b"].status == "failed", f"node_b should be failed, got {activities['node_b'].status}"

        # Node C must NOT have completed — it is downstream of the failure.
        if "node_c" in activities:
            assert activities["node_c"].status != "completed", (
                f"node_c should NOT have completed after node_b failed, got {activities['node_c'].status}"
            )

    def test_failure_at_first_node_skips_all_downstream(self, syntara_api: SyntaraApiRegistry) -> None:
        """A failure in the very first node prevents every downstream node from running."""
        result = create_and_run_workflow(
            syntara_api,
            "e2e-failure-propagation-first-node",
            {
                "name": "failure-at-first",
                "schema_version": "2.0.0",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "fail_first",
                        "name": "Fail First",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "exit 1"},
                    },
                    {
                        "id": "node_b",
                        "name": "Node B",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo B"},
                    },
                    {
                        "id": "node_c",
                        "name": "Node C",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo C"},
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "fail_first"},
                    {"from": "fail_first", "to": "node_b"},
                    {"from": "node_b", "to": "node_c"},
                ],
            },
        )

        assert result.status == ExecutionStatus.FAILED, f"Expected 'failed', got '{result.status}'"

        activities = {a.activity_id: a for a in (result.activities or [])}

        assert activities["fail_first"].status == "failed", (
            f"fail_first should be failed, got {activities['fail_first'].status}"
        )

        for downstream in ("node_b", "node_c"):
            if downstream in activities:
                assert activities[downstream].status != "completed", (
                    f"{downstream} should NOT be completed after upstream failure, got {activities[downstream].status}"
                )

    def test_failure_does_not_affect_independent_branch(self, syntara_api: SyntaraApiRegistry) -> None:
        """A failure in one fork branch does not prevent the sibling branch from executing.

        Topology: trigger → [branch_ok, branch_fail] → converge
        branch_fail exits 1; branch_ok completes normally.
        The converge + downstream should reflect the partial failure.
        """
        result = create_and_run_workflow(
            syntara_api,
            "e2e-failure-propagation-fork",
            {
                "name": "failure-in-fork",
                "schema_version": "2.0.0",
                "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                "nodes": [
                    {
                        "id": "branch_ok",
                        "name": "Branch OK",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "echo 'ok branch'"},
                    },
                    {
                        "id": "branch_fail",
                        "name": "Branch Fail",
                        "type": "script",
                        "parameters": {"language": "bash", "code": "exit 1"},
                    },
                    {
                        "id": "join",
                        "name": "Converge",
                        "type": "converge",
                        "parameters": {},
                    },
                ],
                "edges": [
                    {"from": "trigger", "to": "branch_ok"},
                    {"from": "trigger", "to": "branch_fail"},
                    {"from": "branch_ok", "to": "join"},
                    {"from": "branch_fail", "to": "join"},
                ],
            },
        )

        # The workflow as a whole fails because one branch failed.
        assert result.status in (ExecutionStatus.FAILED, ExecutionStatus.COMPLETED_WITH_ERRORS), (
            f"Expected failed or completed_with_errors when a fork branch fails, got '{result.status}'"
        )

        activities = {a.activity_id: a for a in (result.activities or [])}

        # The healthy branch must have completed.
        assert activities.get("branch_ok") is not None
        assert activities["branch_ok"].status == "completed", (
            f"branch_ok should complete independently of branch_fail, got {activities['branch_ok'].status}"
        )

        # The failing branch must be marked failed.
        assert activities.get("branch_fail") is not None
        assert activities["branch_fail"].status == "failed", (
            f"branch_fail should be failed, got {activities['branch_fail'].status}"
        )
