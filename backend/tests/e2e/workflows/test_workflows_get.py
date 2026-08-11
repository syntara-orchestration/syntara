"""E2E tests for GET /api/v1/workflows endpoints.

Tests for listing workflows and retrieving individual workflows.
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


class TestWorkflowListing:
    """E2E tests for listing workflows."""

    def test_list_workflows_empty(self, syntara_api: SyntaraApiRegistry) -> None:
        """Test listing workflows with filter that matches nothing.

        Uses a unique name filter that won't match any workflow to guarantee
        empty results in E2E environment.

        Expected: 200 OK with empty workflows array
        """
        # Use a random UUID in name filter that won't match any workflow
        non_existent_name = f"nonexistent-{uuid4().hex}"
        result = syntara_api.workflows.list(additional_params={"name[contains]": non_existent_name}).assert_and_get()

        assert result.resources is not None
        assert len(result.resources) == 0

    def test_list_all_workflows(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Test listing workflows with name filter.

        Expected: 200 OK with workflows matching the name filter
        """
        # Generate unique test identifier for filtering
        test_id = uuid4().hex[:8]

        # Create test workflows
        created_workflows = []
        for i in range(3):
            workflow_name = unique_name(f"workflow-{test_id}-{i}")
            workflow = workflow_factory(
                WorkflowCreate(
                    name=workflow_name,
                    description=f"Workflow {i}",
                    workflow_definition=WorkflowDefinition.from_dict(
                        create_minimal_workflow_definition(
                            name=workflow_name,
                            description=f"Workflow {i}",
                        )
                    ),
                    project_id=first_project_id,
                )
            )
            created_workflows.append(workflow)
        created_workflow_ids = [wf.id for wf in created_workflows]

        # List workflows filtered by test_id to isolate our test workflows
        result = syntara_api.workflows.list(additional_params={"name[contains]": test_id}).assert_and_get()

        # Verify exactly our 3 created workflows are in the list
        returned_ids = {wf.id for wf in result.resources}
        assert len(returned_ids) == 3
        assert all(wf_id in returned_ids for wf_id in created_workflow_ids)

    def test_filter_workflows_by_created_by(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Test filtering workflows by creator.

        Note: Uses additional_params to pass created_by filter since it's not
        explicitly defined in the generated client's method signature.

        Expected: 200 OK with only workflows from specified creator
        """
        # Create workflows
        workflow_name1 = unique_name("workflow-creator-1")
        workflow1 = workflow_factory(
            WorkflowCreate(
                name=workflow_name1,
                description="Creator test workflow 1",
                workflow_definition=WorkflowDefinition.from_dict(
                    create_minimal_workflow_definition(
                        name=workflow_name1,
                        description="Creator test workflow 1",
                    )
                ),
                project_id=first_project_id,
            )
        )

        workflow_name2 = unique_name("workflow-creator-2")
        workflow2 = workflow_factory(
            WorkflowCreate(
                name=workflow_name2,
                description="Creator test workflow 2",
                workflow_definition=WorkflowDefinition.from_dict(
                    create_minimal_workflow_definition(
                        name=workflow_name2,
                        description="Creator test workflow 2",
                    )
                ),
                project_id=first_project_id,
            )
        )

        creator_id = workflow1.created_by

        # Filter by creator using additional_params
        result = syntara_api.workflows.list(
            include_total=True, additional_params={"created_by": str(creator_id)}
        ).assert_and_get()

        # Verify our created workflows are in the filtered results
        returned_ids = {wf.id for wf in result.resources}
        assert workflow1.id in returned_ids
        assert workflow2.id in returned_ids
        # Can't assert exact total in E2E as other tests may have created workflows by same user
        assert result.total >= 2

    def test_filter_workflows_by_enabled_status(self, syntara_api: SyntaraApiRegistry) -> None:
        """Test filtering workflows by enabled status.

        Note: Uses additional_params to pass is_enabled filter since it's not
        explicitly defined in the generated client's method signature.

        Expected: 200 OK with filtered workflows
        """
        result = syntara_api.workflows.list(additional_params={"is_enabled": "true"}).assert_and_get()

        # Verify all returned workflows are enabled (if any)
        for workflow in result.resources:
            assert workflow.is_enabled is True

    def test_workflows_pagination(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Test cursor-based pagination with name filtering for deterministic results.

        Expected: 200 OK with paginated results and next/prev cursors
        """
        # Generate unique test identifier for filtering
        test_id = uuid4().hex[:8]

        # Create 10 workflows
        for i in range(10):
            workflow_name = unique_name(f"paginated-workflow-{test_id}-{i}")
            workflow_factory(
                WorkflowCreate(
                    name=workflow_name,
                    description=f"Paginated workflow {i}",
                    workflow_definition=WorkflowDefinition.from_dict(
                        create_minimal_workflow_definition(
                            name=workflow_name,
                            description=f"Paginated workflow {i}",
                        )
                    ),
                    project_id=first_project_id,
                )
            )

        # Get first page filtered by our test workflows
        page1 = syntara_api.workflows.list(
            limit=5, include_total=True, additional_params={"name[contains]": test_id}
        ).assert_and_get()

        assert len(page1.resources) == 5
        assert page1.total == 10  # Exactly our 10 workflows
        assert page1.next_ is not None
        assert page1.prev is None

        # Get second page using cursor
        next_cursor = page1.next_
        page2 = syntara_api.workflows.list(
            limit=5, cursor=next_cursor, additional_params={"name[contains]": test_id}
        ).assert_and_get()

        assert len(page2.resources) == 5
        assert page2.prev is not None

    def test_list_excludes_soft_deleted_workflows(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Test that soft-deleted workflows are excluded.

        Expected: Deleted workflows not in results
        """
        # Generate unique test identifier for filtering
        test_id = uuid4().hex[:8]

        # Create workflow
        workflow_name = unique_name(f"to-be-deleted-{test_id}")
        workflow = workflow_factory(
            WorkflowCreate(
                name=workflow_name,
                description="Workflow to be deleted",
                workflow_definition=WorkflowDefinition.from_dict(
                    create_minimal_workflow_definition(
                        name=workflow_name,
                        description="Workflow to be deleted",
                    )
                ),
                project_id=first_project_id,
            )
        )

        # Delete workflow
        delete_response = syntara_api.workflows.delete(workflow_id=workflow.id)
        assert delete_response.status_code == HTTPStatus.NO_CONTENT

        # List workflows filtered by test_id - should not include deleted one
        workflows_list = syntara_api.workflows.list(additional_params={"name[contains]": test_id}).assert_and_get()

        assert len(workflows_list.resources) == 0  # No workflows with this name (deleted)

    def test_filter_workflows_by_labels(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Test filtering workflows by labels with unique values for deterministic results.

        Note: Uses additional_params to pass labels filter since it's not
        explicitly defined in the generated client's method signature.

        Expected: 200 OK with workflows matching label criteria
        """
        # Use unique label values to avoid pagination issues in E2E environment
        prod_label_value = f"production-{uuid4().hex[:8]}"
        dev_label_value = f"development-{uuid4().hex[:8]}"

        # Create workflows with different labels
        from syntara_api_client.models.workflow_create_labels import WorkflowCreateLabels

        prod_workflow_name = unique_name("prod-workflow")
        prod_workflow = workflow_factory(
            WorkflowCreate(
                name=prod_workflow_name,
                description="Production workflow",
                workflow_definition=WorkflowDefinition.from_dict(
                    create_minimal_workflow_definition(
                        name=prod_workflow_name,
                        description="Production workflow",
                    )
                ),
                labels=WorkflowCreateLabels.from_dict({"environment": prod_label_value}),
                project_id=first_project_id,
            )
        )

        dev_workflow_name = unique_name("dev-workflow")
        workflow_factory(
            WorkflowCreate(
                name=dev_workflow_name,
                description="Development workflow",
                workflow_definition=WorkflowDefinition.from_dict(
                    create_minimal_workflow_definition(
                        name=dev_workflow_name,
                        description="Development workflow",
                    )
                ),
                labels=WorkflowCreateLabels.from_dict({"environment": dev_label_value}),
                project_id=first_project_id,
            )
        )

        # Filter by unique label value using additional_params (bracket notation)
        result = syntara_api.workflows.list(
            additional_params={"labels[environment]": prod_label_value}
        ).assert_and_get()

        # Verify only the production workflow is in the results
        returned_ids = {wf.id for wf in result.resources}
        assert len(returned_ids) == 1
        assert prod_workflow.id in returned_ids

    def test_list_default_page_size(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Test default page size is 20 items with name filtering for deterministic results.

        Expected: 200 OK with maximum 20 workflows when more exist
        """
        # Generate unique test identifier for filtering
        test_id = uuid4().hex[:8]

        # Create 25 workflows
        for i in range(25):
            workflow_name = unique_name(f"workflow-page-{test_id}-{i}")
            workflow_factory(
                WorkflowCreate(
                    name=workflow_name,
                    description=f"Workflow page {i}",
                    workflow_definition=WorkflowDefinition.from_dict(
                        create_minimal_workflow_definition(
                            name=workflow_name,
                            description=f"Workflow page {i}",
                        )
                    ),
                    project_id=first_project_id,
                )
            )

        # Get workflows without limit parameter (should default to 20) filtered by our test workflows
        result = syntara_api.workflows.list(
            include_total=True, additional_params={"name[contains]": test_id}
        ).assert_and_get()

        assert len(result.resources) == 20  # Default page size
        assert result.total == 25  # Exactly our 25 workflows
