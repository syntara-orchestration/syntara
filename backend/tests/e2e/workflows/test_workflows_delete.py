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
