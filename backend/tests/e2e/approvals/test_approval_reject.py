"""E2E tests: Approval reject signal flow (API-22).

Validates that rejecting a HitL approval node in a running workflow:
- Sends the Temporal async-complete signal that resumes the paused execution
- Does NOT execute the downstream node connected on the "approved" port
- Does execute the downstream node connected on the "rejected" port (when configured)
- Records the deciding user and rejection notes on the approval record

Requirements: AAP-79xxx (API-22)

Run with:
    make test-e2e
"""

from collections.abc import Callable
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import TERMINAL_STATUSES, poll_execution, poll_for_pending_approval
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
from syntara_api_client.types import Unset

pytestmark = [pytest.mark.e2e]

_APPROVAL_POLL_TIMEOUT = 90  # seconds to wait for Temporal to reach the approval node under load
_EXECUTION_POLL_TIMEOUT = 90  # seconds to wait for execution to reach terminal after signal


def _reject_only_workflow(name: str) -> WorkflowDefinition:
    """Workflow with approval node and an approved-path downstream only.

    Rejection has no successor, so the execution terminates after rejection.
    """
    return WorkflowDefinition.from_dict(
        {
            "name": name,
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "approval_gate",
                    "name": "Review Gate",
                    "type": "approval",
                    "parameters": {},
                },
                {
                    "id": "approved_action",
                    "name": "Approved Action",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "approved path"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "approval_gate"},
                {"from": "approval_gate", "to": "approved_action", "from_port": "approved"},
            ],
        }
    )


def _branched_workflow(name: str) -> WorkflowDefinition:
    """Workflow with both approved and rejected path successors.

    Structure:
        trigger → approval_gate → approved_action  (approved port)
                               → rejected_handler  (rejected port)
    """
    return WorkflowDefinition.from_dict(
        {
            "name": name,
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [
                {
                    "id": "approval_gate",
                    "name": "Review Gate",
                    "type": "approval",
                    "parameters": {},
                },
                {
                    "id": "approved_action",
                    "name": "Approved Action",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "approved path"'},
                },
                {
                    "id": "rejected_handler",
                    "name": "Rejection Handler",
                    "type": "script",
                    "parameters": {"language": "bash", "code": 'echo "rejected path"'},
                },
            ],
            "edges": [
                {"from": "trigger", "to": "approval_gate"},
                {"from": "approval_gate", "to": "approved_action", "from_port": "approved"},
                {"from": "approval_gate", "to": "rejected_handler", "from_port": "rejected"},
            ],
        }
    )


class TestRejectSignal:
    """API-22: Reject signal terminates the approved path and routes to the rejected path."""

    def test_reject_terminates_execution_and_approved_path_not_executed(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ) -> None:
        """Rejecting ends the execution and does not run the approved-path node.

        Procedure:
        1. Create workflow: trigger → approval_gate → approved_action (approved port only).
        2. Run, wait for PENDING approval, reject with a reason.
        3. Poll to terminal.

        Expected:
        - Execution reaches a terminal status (rejected path has no successor).
        - 'approved_action' is absent from activities or was not completed.
        - The approval record shows decision=rejected, decided_by set, and rejection notes.
        """
        name = unique_name("e2e-reject-terminates")
        workflow = workflow_factory(
            WorkflowCreate(
                name=name,
                description="E2E: reject signal terminates execution",
                workflow_definition=_reject_only_workflow(name),
                project_id=first_project_id,
            )
        )

        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger")
        ).assert_and_get()
        exec_id = UUID(str(execution.id))

        approval = poll_for_pending_approval(syntara_api, exec_id, timeout=_APPROVAL_POLL_TIMEOUT)
        assert approval.status == ApprovalRequestStatus.PENDING
        assert approval.approval_node_id == "approval_gate"

        rejection_notes = "Blocked by policy — rejecting for E2E test"
        decide_response = syntara_api.approvals.decide(
            approval_id=UUID(str(approval.id)),
            body=ApprovalDecisionRequest(
                status=ApprovalDecisionStatus.REJECTED,
                notes=rejection_notes,
            ),
        ).assert_and_get()

        # Verify the approval record is updated immediately after deciding
        assert decide_response.status == ApprovalRequestStatus.REJECTED, (
            f"Approval status should be rejected, got: {decide_response.status}"
        )
        assert decide_response.decided_by is not None, "decided_by must be set after rejection"
        assert not isinstance(decide_response.decided_by, Unset), "decided_by must not be Unset after rejection"
        notes_on_record = decide_response.decision_notes
        assert notes_on_record == rejection_notes, (
            f"decision_notes should be {rejection_notes!r}, got: {notes_on_record!r}"
        )

        # Execution reaches terminal — rejection with no successor ends the workflow
        final = poll_execution(syntara_api, str(exec_id), timeout=_EXECUTION_POLL_TIMEOUT)
        assert final.status in TERMINAL_STATUSES, f"Execution did not reach terminal status, got: {final.status}"

        # Approved-path node must not have completed
        activities = {a.activity_id: a for a in (final.activities or [])}
        if "approved_action" in activities:
            assert activities["approved_action"].status != "completed", (
                "approved_action should NOT have completed after rejection"
            )

    def test_reject_executes_rejected_path_node(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ) -> None:
        """The node connected on the 'rejected' port executes after rejection.

        Procedure:
        1. Create workflow with both approved and rejected path successors.
        2. Run, wait for pending approval, reject.
        3. Poll to terminal.

        Expected:
        - 'rejected_handler' activity is present and completed.
        - 'approved_action' activity is absent or was not completed.
        """
        name = unique_name("e2e-reject-path")
        workflow = workflow_factory(
            WorkflowCreate(
                name=name,
                description="E2E: rejected-path node executes on rejection",
                workflow_definition=_branched_workflow(name),
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
            body=ApprovalDecisionRequest(status=ApprovalDecisionStatus.REJECTED),
        ).assert_and_get()

        final = poll_execution(syntara_api, str(exec_id), timeout=_EXECUTION_POLL_TIMEOUT)
        assert final.status in TERMINAL_STATUSES, f"Execution did not reach terminal status, got: {final.status}"

        activities = {a.activity_id: a for a in (final.activities or [])}

        assert "rejected_handler" in activities, (
            f"Rejected-path node 'rejected_handler' missing from activities: {list(activities)}"
        )
        assert activities["rejected_handler"].status == "completed", (
            f"'rejected_handler' should be completed, got: {activities['rejected_handler'].status}"
        )

        if "approved_action" in activities:
            assert activities["approved_action"].status != "completed", (
                "'approved_action' should NOT have completed after rejection"
            )

    def test_reject_output_contains_required_fields(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ) -> None:
        """Rejection records decision, decided_by, and decided_at in the activity output.

        Procedure:
        1. Create workflow with approval node only.
        2. Run, wait for pending approval, reject with notes.
        3. Poll to terminal.

        Expected:
        - 'approval_gate' activity output_data contains:
          - decision == 'rejected'
          - decided_by (non-empty string)
          - decided_at (non-empty ISO string)
          - decision_notes == the rejection notes text
        """
        name = unique_name("e2e-reject-output")
        workflow = workflow_factory(
            WorkflowCreate(
                name=name,
                description="E2E: reject signal output field verification",
                workflow_definition=_reject_only_workflow(name),
                project_id=first_project_id,
            )
        )

        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger")
        ).assert_and_get()
        exec_id = UUID(str(execution.id))

        approval = poll_for_pending_approval(syntara_api, exec_id, timeout=_APPROVAL_POLL_TIMEOUT)
        rejection_notes = "Rejected for E2E output test"

        syntara_api.approvals.decide(
            approval_id=UUID(str(approval.id)),
            body=ApprovalDecisionRequest(
                status=ApprovalDecisionStatus.REJECTED,
                notes=rejection_notes,
            ),
        ).assert_and_get()

        final = poll_execution(syntara_api, str(exec_id), timeout=_EXECUTION_POLL_TIMEOUT)
        assert final.status in TERMINAL_STATUSES

        activities = {a.activity_id: a for a in (final.activities or [])}
        assert "approval_gate" in activities, f"'approval_gate' activity missing: {list(activities)}"

        gate = activities["approval_gate"]
        assert gate.status == "completed", f"approval_gate should be completed, got: {gate.status}"
        assert gate.output_data is not None, "approval_gate activity must have output_data"

        output = gate.output_data.to_dict()
        assert output.get("decision") == "rejected", (
            f"output.decision should be 'rejected', got: {output.get('decision')!r}"
        )
        assert output.get("decided_by"), (
            f"output.decided_by must be a non-empty string, got: {output.get('decided_by')!r}"
        )
        assert output.get("decided_at"), f"output.decided_at must be set, got: {output.get('decided_at')!r}"
        assert output.get("decision_notes") == rejection_notes, (
            f"output.decision_notes should be {rejection_notes!r}, got: {output.get('decision_notes')!r}"
        )
        assert output.get("status") == "completed", (
            f"output.status should be 'completed', got: {output.get('status')!r}"
        )
