"""E2E tests for DELETE /api/v1/workflows/{id} endpoint.

Tests for soft-deleting workflows.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from orchestrator_test_sdk.e2e import unique_name
from syntara_api_client.models.workflow_create import WorkflowCreate
from syntara_api_client.models.workflow_definition import WorkflowDefinition

from tests.helpers.workflow import create_minimal_workflow_definition

if TYPE_CHECKING:
    from collections.abc import Callable

    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.models.workflow_read import WorkflowRead

    WorkflowFactory = Callable[[WorkflowCreate], WorkflowRead]

pytestmark = [pytest.mark.e2e]


class TestWorkflowDeletion:
    """E2E tests for deleting workflows.

    Note: Basic delete success is covered in test_workflow_crud.py::test_delete_workflow.
    Deleted workflows exclusion from list is covered in
    test_workflows_get.py::test_list_excludes_soft_deleted_workflows.
    These tests focus on edge cases not covered elsewhere.
    """

    def test_delete_nonexistent_workflow(self, syntara_api: SyntaraApiRegistry) -> None:
        """Test deleting a non-existent workflow.

        Expected: 404 Not Found
        """
        fake_id = uuid4()
        response = syntara_api.workflows.delete(workflow_id=fake_id)

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_delete_already_deleted_workflow(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Test deleting an already soft-deleted workflow.

        Expected: 404 Not Found
        """
        # Create workflow
        workflow_name = unique_name("double-delete")
        workflow = workflow_factory(
            WorkflowCreate(
                name=workflow_name,
                description="Double delete test",
                workflow_definition=WorkflowDefinition.from_dict(
                    create_minimal_workflow_definition(
                        name=workflow_name,
                        description="Double delete test",
                    )
                ),
                project_id=first_project_id,
            )
        )

        # First deletion
        first_delete = syntara_api.workflows.delete(workflow_id=workflow.id)
        assert first_delete.status_code == HTTPStatus.NO_CONTENT

        # Try to delete again
        second_delete = syntara_api.workflows.delete(workflow_id=workflow.id)
        assert second_delete.status_code == HTTPStatus.NOT_FOUND


class TestDeleteCancelsInProgressRuns:
    """AAP-87750: deleting a workflow must stop its in-progress runs.

    Mirrors ``test_workflow_execution.py::test_cancel_execution_with_pending_approval``,
    which already builds a workflow that reliably parks on a pending approval — the
    same fixture shape, reached through DELETE instead of the cancel endpoint.

    Before the fix, DELETE returned 204 while the approval stayed 'pending' (and was
    still decidable, with no effect) and the execution stayed 'paused' forever.
    """

    def test_delete_cancels_pending_approval_and_execution(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        import time

        from orchestrator_test_sdk.e2e.helpers import poll_for_pending_approval
        from syntara_api_client.models import ApprovalDecisionRequest, ExecutionCreate
        from syntara_api_client.models.approval_decision_status import ApprovalDecisionStatus
        from syntara_api_client.models.approval_request_status import ApprovalRequestStatus

        workflow_name = unique_name("e2e-delete-approval")
        workflow = workflow_factory(
            WorkflowCreate(
                name=workflow_name,
                description="Workflow for testing delete with a pending approval",
                project_id=first_project_id,
                workflow_definition=_approval_gate_definition(workflow_name),
            )
        )

        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger_manual")
        ).assert_and_get()
        execution_id = UUID(str(execution.id))

        approval = poll_for_pending_approval(syntara_api, execution_id, timeout=30)
        assert approval.status == ApprovalRequestStatus.PENDING
        approval_id = UUID(str(approval.id))

        delete_response = syntara_api.workflows.delete(workflow_id=workflow.id)
        assert delete_response.status_code == HTTPStatus.NO_CONTENT, (
            f"Expected 204, got {delete_response.status_code}: {delete_response.content!r}"
        )

        # The approval is cancelled synchronously, so it is already decided here.
        approval_after = syntara_api.approvals.get(approval_id=approval_id).assert_and_get()
        assert approval_after.status == ApprovalRequestStatus.CANCELLED, (
            f"Approval should be cancelled, got {approval_after.status}"
        )

        # Deciding it now conflicts instead of silently doing nothing.
        decide_response = syntara_api.approvals.decide(
            approval_id=approval_id,
            body=ApprovalDecisionRequest(status=ApprovalDecisionStatus.APPROVED),
        )
        assert decide_response.status_code == HTTPStatus.CONFLICT, (
            f"Expected 409 for a cancelled approval, got {decide_response.status_code}"
        )

        # The execution reaches a terminal state rather than staying paused forever.
        # Status is driven asynchronously by the Temporal cancellation event.
        for _ in range(20):
            current = syntara_api.executions.get(execution_id=execution_id).assert_and_get()
            if str(current.status) == "cancelled":
                break
            time.sleep(1)
        else:
            pytest.fail(f"Execution never reached 'cancelled'; last status: {current.status!s}")


def _approval_gate_definition(workflow_name: str) -> WorkflowDefinition:
    """Trigger → approval_gate → post_approval_script."""
    return WorkflowDefinition.from_dict(
        {
            "schema_version": "2.0.0",
            "name": workflow_name,
            "description": "Approval gate workflow",
            "triggers": [{"id": "trigger_manual", "type": "manual_trigger"}],
            "nodes": [
                {"id": "approval_gate", "name": "Review Gate", "type": "approval", "parameters": {}},
                {
                    "id": "post_approval_script",
                    "name": "Post-Approval Step",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "echo 'approved path executed'"},
                },
            ],
            "edges": [
                {"from": "trigger_manual", "to": "approval_gate"},
                {"from": "approval_gate", "to": "post_approval_script", "from_port": "approved"},
            ],
        }
    )
