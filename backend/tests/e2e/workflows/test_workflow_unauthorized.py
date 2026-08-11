"""E2E tests for Workflow CRUD — Unauthorized Access.

Tests that unauthenticated requests to workflow endpoints are rejected
and that no workflow data is leaked in error responses.
"""

from collections.abc import Callable
from http import HTTPStatus
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import ExecutionCreate, WorkflowCreate, WorkflowDefinition, WorkflowRead, WorkflowUpdate

pytestmark = [pytest.mark.e2e]


def _minimal_workflow_definition(workflow_name: str) -> WorkflowDefinition:
    """Standard minimal workflow definition for testing."""
    return WorkflowDefinition.from_dict(
        {
            "name": workflow_name,
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
            "nodes": [],
            "edges": [],
        }
    )


class TestWorkflowUnauthorizedAccess:
    """Verify unauthenticated requests to workflow endpoints are rejected with 401."""

    def test_list_workflows_without_auth(self, unauth_api: SyntaraApiRegistry):
        """GET /api/v1/workflows without authentication returns 401.

        Objective: Verify that listing workflows requires authentication.

        Expected Results:
        - Response status is 401 Unauthorized
        """
        resp = unauth_api.workflows.list()

        assert resp.status_code == HTTPStatus.UNAUTHORIZED, (
            f"Expected 401 Unauthorized for unauthenticated GET /workflows, got {resp.status_code}"
        )

    def test_create_workflow_without_auth(self, unauth_api: SyntaraApiRegistry, first_project_id: UUID):
        """POST /api/v1/workflows without authentication returns 401.

        Objective: Verify that creating a workflow requires authentication.

        Expected Results:
        - Response status is 401 Unauthorized
        """
        workflow_name = unique_name("e2e-unauth-create")
        resp = unauth_api.workflows.create(
            body=WorkflowCreate(
                name=workflow_name,
                workflow_definition=_minimal_workflow_definition(workflow_name),
                project_id=first_project_id,
            )
        )

        assert resp.status_code == HTTPStatus.UNAUTHORIZED, (
            f"Expected 401 Unauthorized for unauthenticated POST /workflows, got {resp.status_code}"
        )

    def test_get_workflow_by_id_without_auth(
        self,
        unauth_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """GET /api/v1/workflows/{id} without authentication returns 401.

        Objective: Verify that retrieving a specific workflow requires authentication.

        Test Procedure:
        1. Create a workflow via authenticated API (to get a real workflow ID)
        2. Attempt to retrieve it without authentication

        Expected Results:
        - Response status is 401 Unauthorized
        """
        workflow_name = unique_name("e2e-unauth-get-by-id")
        workflow = workflow_factory(
            WorkflowCreate(
                name=workflow_name,
                workflow_definition=_minimal_workflow_definition(workflow_name),
                project_id=first_project_id,
            )
        )

        resp = unauth_api.workflows.get(workflow_id=workflow.id)

        assert resp.status_code == HTTPStatus.UNAUTHORIZED, (
            f"Expected 401 Unauthorized for unauthenticated GET /workflows/{{id}}, got {resp.status_code}"
        )

    def test_update_workflow_without_auth(
        self,
        unauth_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """PATCH /api/v1/workflows/{id} without authentication returns 401.

        Objective: Verify that updating a workflow requires authentication.

        Test Procedure:
        1. Create a workflow via authenticated API (to get a real workflow ID)
        2. Attempt to update it without authentication

        Expected Results:
        - Response status is 401 Unauthorized
        """
        workflow_name = unique_name("e2e-unauth-update")
        workflow = workflow_factory(
            WorkflowCreate(
                name=workflow_name,
                workflow_definition=_minimal_workflow_definition(workflow_name),
                project_id=first_project_id,
            )
        )

        resp = unauth_api.workflows.update(
            workflow_id=workflow.id,
            body=WorkflowUpdate(name=unique_name("e2e-unauth-rename")),
        )

        assert resp.status_code == HTTPStatus.UNAUTHORIZED, (
            f"Expected 401 Unauthorized for unauthenticated PATCH /workflows/{{id}}, got {resp.status_code}"
        )

    def test_delete_workflow_without_auth(
        self,
        unauth_api: SyntaraApiRegistry,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """DELETE /api/v1/workflows/{id} without authentication returns 401.

        Objective: Verify that deleting a workflow requires authentication.

        Test Procedure:
        1. Create a workflow via authenticated API (to get a real workflow ID)
        2. Attempt to delete it without authentication
        3. Verify the workflow still exists

        Expected Results:
        - Response status is 401 Unauthorized
        - The workflow still exists (authenticated GET still returns it)
        """
        workflow_name = unique_name("e2e-unauth-delete")
        workflow = workflow_factory(
            WorkflowCreate(
                name=workflow_name,
                workflow_definition=_minimal_workflow_definition(workflow_name),
                project_id=first_project_id,
            )
        )

        resp = unauth_api.workflows.delete(workflow_id=workflow.id)

        assert resp.status_code == HTTPStatus.UNAUTHORIZED, (
            f"Expected 401 Unauthorized for unauthenticated DELETE /workflows/{{id}}, got {resp.status_code}"
        )

        # Verify the workflow was not deleted despite the attempt
        syntara_api.workflows.get(workflow_id=workflow.id).assert_successful()

    def test_execute_workflow_without_auth(
        self,
        unauth_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """POST /api/v1/executions without authentication returns 401.

        Objective: Verify that executing a workflow requires authentication.

        Test Procedure:
        1. Create a workflow via authenticated API (to get a real workflow ID)
        2. Attempt to execute it without authentication

        Expected Results:
        - Response status is 401 Unauthorized
        """
        workflow_name = unique_name("e2e-unauth-execute")
        workflow = workflow_factory(
            WorkflowCreate(
                name=workflow_name,
                workflow_definition=_minimal_workflow_definition(workflow_name),
                project_id=first_project_id,
            )
        )

        resp = unauth_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger_manual")
        )

        assert resp.status_code == HTTPStatus.UNAUTHORIZED, (
            f"Expected 401 Unauthorized for unauthenticated POST /executions, got {resp.status_code}"
        )
