"""E2E tests: Approval approve signal flow (API-21).

Validates that approving a HitL approval node in a running workflow:
- Creates a PENDING approval record visible via GET /approvals?execution_id=...
- Sends the Temporal async-complete signal that resumes the paused execution
- Executes the downstream node connected on the "approved" port
- Records decision, decided_by, decided_at, and decision_notes in the activity output

Requirements: AAP-79xxx (API-21)

Run with:
    make test-e2e
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import poll_execution, poll_for_pending_approval
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import (
    ExecutionCreate,
    WorkflowCreate,
    WorkflowDefinition,
    WorkflowRead,
)
from syntara_api_client.models.approval_decision_request import ApprovalDecisionRequest
from syntara_api_client.models.approval_decision_status import ApprovalDecisionStatus
from syntara_api_client.models.approval_request_status import ApprovalRequestStatus
from syntara_api_client.models.execution_status import ExecutionStatus

pytestmark = [pytest.mark.e2e]

_APPROVAL_POLL_TIMEOUT = 60  # seconds to wait for Temporal to reach the approval node
_EXECUTION_POLL_TIMEOUT = 90  # seconds to wait for execution to reach terminal after signal


def _approval_workflow(name: str, *, with_approved_downstream: bool = True) -> WorkflowDefinition:
    nodes: list[dict[str, Any]] = [
        {
            "id": "approval_gate",
            "name": "Review Gate",
            "type": "approval",
            "parameters": {},
        },
    ]
    edges: list[dict[str, Any]] = [{"from": "trigger", "to": "approval_gate"}]

    if with_approved_downstream:
        nodes.append(
            {
                "id": "post_approval",
                "name": "Post-Approval Step",
                "type": "script",
                "parameters": {"language": "bash", "code": 'echo "approved path executed"'},
            }
        )
        edges.append({"from": "approval_gate", "to": "post_approval", "from_port": "approved"})

    return WorkflowDefinition.from_dict(
        {
            "name": name,
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": nodes,
            "edges": edges,
        }
    )


class TestApproveSignal:
    """API-21: Approve signal resumes workflow and executes the approved-path downstream."""

    def test_approve_resumes_execution_to_completed(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ) -> None:
        """Approving an approval node resumes the paused Temporal execution.

        Procedure:
        1. Create workflow with an approval node followed by a downstream script.
        2. Start an execution — Temporal pauses at the approval node.
        3. Wait for a PENDING approval record to appear via GET /approvals.
        4. PATCH /approvals/{id} with status=approved.
        5. Poll execution until terminal.

        Expected:
        - Execution reaches COMPLETED status.
        """
        name = unique_name("e2e-approve-resumes")
        workflow = workflow_factory(
            WorkflowCreate(
                name=name,
                description="E2E: approve signal resumes execution",
                workflow_definition=_approval_workflow(name),
                project_id=first_project_id,
            )
        )

        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger")
        ).assert_and_get()
        exec_id = UUID(str(execution.id))

        approval = poll_for_pending_approval(syntara_api, exec_id, timeout=_APPROVAL_POLL_TIMEOUT)
        assert approval.status == ApprovalRequestStatus.PENDING
        assert approval.execution_id == exec_id
        assert approval.approval_node_id == "approval_gate"

        syntara_api.approvals.decide(
            approval_id=UUID(str(approval.id)),
            body=ApprovalDecisionRequest(status=ApprovalDecisionStatus.APPROVED),
        ).assert_and_get()

        final = poll_execution(syntara_api, str(exec_id), timeout=_EXECUTION_POLL_TIMEOUT)
        assert final.status == ExecutionStatus.COMPLETED, (
            f"Expected COMPLETED after approve, got {final.status}: {final.error_details}"
        )

    def test_approve_executes_downstream_node_on_approved_path(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ) -> None:
        """The node connected on the 'approved' port executes after approval.

        Procedure:
        1. Create workflow: trigger → approval_gate → post_approval (approved port).
        2. Run, wait for pending approval, approve.
        3. Poll to terminal.

        Expected:
        - 'post_approval' activity is present and has status 'completed'.
        """
        name = unique_name("e2e-approve-downstream")
        workflow = workflow_factory(
            WorkflowCreate(
                name=name,
                description="E2E: approved-path downstream executes",
                workflow_definition=_approval_workflow(name, with_approved_downstream=True),
                project_id=first_project_id,
            )
        )

        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger")
        ).assert_and_get()
        exec_id = UUID(str(execution.id))

        approval = poll_for_pending_approval(syntara_api, exec_id, timeout=_APPROVAL_POLL_TIMEOUT)
        syntara_api.approvals.decide(
            approval_id=UUID(str(approval.id)),
            body=ApprovalDecisionRequest(status=ApprovalDecisionStatus.APPROVED),
        ).assert_and_get()

        final = poll_execution(syntara_api, str(exec_id), timeout=_EXECUTION_POLL_TIMEOUT)
        assert final.status == ExecutionStatus.COMPLETED, (
            f"Expected COMPLETED, got {final.status}: {final.error_details}"
        )

        activities = {a.activity_id: a for a in (final.activities or [])}
        assert "post_approval" in activities, (
            f"Approved-path node 'post_approval' missing from activities: {list(activities)}"
        )
        assert activities["post_approval"].status == "completed", (
            f"'post_approval' should be completed, got: {activities['post_approval'].status}"
        )

    def test_approve_output_contains_required_fields(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ) -> None:
        """Approval node output includes decision, decided_by, decided_at, and decision_notes.

        Procedure:
        1. Create workflow with an approval node only (no downstream for simplicity).
        2. Run, wait for pending approval, approve with notes.
        3. Poll to terminal.

        Expected:
        - 'approval_gate' activity output_data contains:
          - decision == 'approved'
          - decided_by (non-empty string — the deciding user's username)
          - decided_at (non-empty ISO string)
          - decision_notes == the notes text supplied in the decision
        """
        name = unique_name("e2e-approve-output")
        workflow = workflow_factory(
            WorkflowCreate(
                name=name,
                description="E2E: approval output field verification",
                workflow_definition=_approval_workflow(name, with_approved_downstream=True),
                project_id=first_project_id,
            )
        )

        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger")
        ).assert_and_get()
        exec_id = UUID(str(execution.id))

        approval = poll_for_pending_approval(syntara_api, exec_id, timeout=_APPROVAL_POLL_TIMEOUT)
        notes_text = "LGTM — approving for E2E test"

        syntara_api.approvals.decide(
            approval_id=UUID(str(approval.id)),
            body=ApprovalDecisionRequest(
                status=ApprovalDecisionStatus.APPROVED,
                notes=notes_text,
            ),
        ).assert_and_get()

        final = poll_execution(syntara_api, str(exec_id), timeout=_EXECUTION_POLL_TIMEOUT)
        assert final.status == ExecutionStatus.COMPLETED

        activities = {a.activity_id: a for a in (final.activities or [])}
        assert "approval_gate" in activities, f"'approval_gate' activity missing: {list(activities)}"

        gate = activities["approval_gate"]
        assert gate.status == "completed", f"approval_gate should be completed, got: {gate.status}"
        assert gate.output_data is not None, "approval_gate activity must have output_data"

        output = gate.output_data.to_dict()
        assert output.get("decision") == "approved", (
            f"output.decision should be 'approved', got: {output.get('decision')!r}"
        )
        assert output.get("decided_by"), (
            f"output.decided_by must be a non-empty string, got: {output.get('decided_by')!r}"
        )
        assert output.get("decided_at"), f"output.decided_at must be set, got: {output.get('decided_at')!r}"
        assert output.get("decision_notes") == notes_text, (
            f"output.decision_notes should be {notes_text!r}, got: {output.get('decision_notes')!r}"
        )
        assert output.get("status") == "completed", (
            f"output.status should be 'completed', got: {output.get('status')!r}"
        )


def _approval_in_loop_workflow(name: str) -> WorkflowDefinition:
    """Manual trigger → for_each loop → approval → script (body) → script (after loop)."""
    return WorkflowDefinition.from_dict(
        {
            "name": name,
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "loop",
                    "name": "For each server",
                    "type": "loop",
                    "parameters": {
                        "type": "for_each",
                        "items": '["server-1", "server-2"]',
                    },
                },
                {
                    "id": "a1",
                    "name": "Approve server",
                    "type": "approval",
                    "parameters": {},
                },
                {
                    "id": "body_script",
                    "name": "Act on server",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "iteration body"'},
                },
                {
                    "id": "after_loop",
                    "name": "After loop",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "loop complete"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "loop"},
                {"from": "loop", "to": "a1", "from_port": "iterate"},
                {"from": "a1", "to": "body_script", "from_port": "approved"},
                {"from": "body_script", "to": "loop", "to_port": "iterate"},
                {"from": "loop", "to": "after_loop", "from_port": "complete"},
            ],
        }
    )


class TestApproveInLoop:
    """Each loop iteration creates a distinct approval request."""

    def test_each_iteration_creates_unique_approval(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ) -> None:
        """Approving inside a two-item for_each loop succeeds on every iteration.

        Procedure:
        1. Create workflow: trigger → loop(for_each, 2 items) → approval → script → after-loop.
        2. Run. Approve the first pending request (iteration 0).
        3. Approve the second pending request (iteration 1).
        4. Poll until terminal.

        Expected:
        - Two distinct rows with approval_node_id ``a1`` and paths [0] then [1].
        - Execution COMPLETED; body_script and after_loop completed.
        """
        name = unique_name("e2e-approve-in-loop")
        workflow = workflow_factory(
            WorkflowCreate(
                name=name,
                description="E2E: approval node inside a for_each loop",
                workflow_definition=_approval_in_loop_workflow(name),
                project_id=first_project_id,
            )
        )

        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger")
        ).assert_and_get()
        exec_id = UUID(str(execution.id))

        first = poll_for_pending_approval(syntara_api, exec_id, timeout=_APPROVAL_POLL_TIMEOUT)
        assert first.approval_node_id == "a1", (
            f"First iteration approval_node_id should be a1, got: {first.approval_node_id!r}"
        )
        assert first.loop_iteration_path == [0], (
            f"First iteration loop_iteration_path should be [0], got: {first.loop_iteration_path!r}"
        )
        syntara_api.approvals.decide(
            approval_id=UUID(str(first.id)),
            body=ApprovalDecisionRequest(status=ApprovalDecisionStatus.APPROVED),
        ).assert_and_get()

        second = poll_for_pending_approval(syntara_api, exec_id, timeout=_APPROVAL_POLL_TIMEOUT)
        assert second.approval_node_id == "a1", (
            f"Second iteration approval_node_id should be a1, got: {second.approval_node_id!r}"
        )
        assert second.loop_iteration_path == [1], (
            f"Second iteration loop_iteration_path should be [1], got: {second.loop_iteration_path!r}"
        )
        assert second.id != first.id
        syntara_api.approvals.decide(
            approval_id=UUID(str(second.id)),
            body=ApprovalDecisionRequest(status=ApprovalDecisionStatus.APPROVED),
        ).assert_and_get()

        final = poll_execution(syntara_api, str(exec_id), timeout=_EXECUTION_POLL_TIMEOUT)
        assert final.status == ExecutionStatus.COMPLETED, (
            f"Expected COMPLETED after two loop approvals, got {final.status}: {final.error_details}"
        )

        activities = {a.activity_id: a.status for a in (final.activities or [])}
        assert activities.get("body_script") == "completed", (
            f"Loop body script should complete, activities={activities}"
        )
        assert activities.get("after_loop") == "completed", (
            f"After-loop script should complete, activities={activities}"
        )
        assert activities.get("loop") == "completed"
