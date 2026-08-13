"""E2E tests for workflow version endpoints.

Tests for listing and retrieving workflow versions.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from syntara_api_client.models.workflow_create import WorkflowCreate
from syntara_api_client.models.workflow_definition import WorkflowDefinition
from syntara_api_client.models.workflow_update import WorkflowUpdate

from tests.helpers.workflow import (
    create_minimal_workflow_definition,
    create_workflow_definition_with_activities,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.models.workflow_read import WorkflowRead

    WorkflowFactory = Callable[[WorkflowCreate], WorkflowRead]

pytestmark = [pytest.mark.e2e]


class TestWorkflowVersionListing:
    """E2E tests for listing workflow versions."""

    def test_list_workflow_versions(
        self, syntara_api: SyntaraApiRegistry, workflow_factory: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """Test listing all versions for a workflow.

        Expected: 200 OK with versions array ordered by version DESC
        """
        # Create workflow
        workflow_def = WorkflowDefinition.from_dict(
            create_minimal_workflow_definition(
                name="multi-version",
                description="Test workflow for multi-version",
                activity_id="initial_activity",
            )
        )
        workflow_id = workflow_factory(
            WorkflowCreate(
                name="multi-version-workflow",
                workflow_definition=workflow_def,
                project_id=first_project_id,
            )
        ).id

        # Create version 2
        update_def_v2 = WorkflowDefinition.from_dict(
            create_minimal_workflow_definition(
                name="multi-version",
                description="Version 2",
                activity_id="step1",
            )
        )
        syntara_api.workflows.update(
            workflow_id=workflow_id,
            body=WorkflowUpdate(
                workflow_definition=update_def_v2,
                change_description="Version 2",
            ),
        )

        # Create version 3
        update_def_v3 = WorkflowDefinition.from_dict(
            create_workflow_definition_with_activities(
                name="multi-version",
                description="Version 3",
                activities=[
                    {
                        "id": "step1",
                        "name": "Step 1",
                        "type": "script",
                        "parameters": {
                            "language": "python",
                            "code": "print('step 1')",
                        },
                    },
                    {
                        "id": "step2",
                        "name": "Step 2",
                        "type": "script",
                        "parameters": {
                            "language": "python",
                            "code": "print('step 2')",
                        },
                    },
                ],
            )
        )
        syntara_api.workflows.update(
            workflow_id=workflow_id,
            body=WorkflowUpdate(
                workflow_definition=update_def_v3,
                change_description="Version 3",
            ),
        )

        # List all versions
        response = syntara_api.workflows.list_versions(workflow_id=workflow_id)

        versions_list = response.assert_and_get()
        assert len(versions_list.resources) == 3

        # Verify ordered by version DESC (newest first)
        versions = versions_list.resources
        assert versions[0].version == 3
        assert versions[1].version == 2
        assert versions[2].version == 1

    def test_list_workflow_versions_single_version(
        self, syntara_api: SyntaraApiRegistry, workflow_factory: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """Test listing versions for workflow with only initial version.

        Expected: 200 OK with single version (the initial one)
        """
        # Create workflow
        workflow_def = WorkflowDefinition.from_dict(
            create_minimal_workflow_definition(
                name="single-version",
                description="Test workflow for single version",
                activity_id="initial_activity",
            )
        )
        workflow_id = workflow_factory(
            WorkflowCreate(
                name="single-version-workflow",
                workflow_definition=workflow_def,
                project_id=first_project_id,
            )
        ).id

        # List versions
        response = syntara_api.workflows.list_versions(workflow_id=workflow_id)

        versions_list = response.assert_and_get()
        assert len(versions_list.resources) == 1
        assert versions_list.resources[0].version == 1

    def test_list_versions_nonexistent_workflow(self, syntara_api: SyntaraApiRegistry) -> None:
        """Test listing versions for non-existent workflow.

        Expected: 404 Not Found
        """
        fake_id = uuid4()
        response = syntara_api.workflows.list_versions(workflow_id=fake_id)

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_list_versions_includes_metadata(
        self, syntara_api: SyntaraApiRegistry, workflow_factory: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """Test that version list includes metadata.

        Expected: Each version includes schema_version, created_at, etc.
        """
        # Create workflow
        workflow_def = WorkflowDefinition.from_dict(
            create_minimal_workflow_definition(
                name="metadata-test",
                description="Test workflow for metadata",
                activity_id="metadata_activity",
            )
        )
        workflow_id = workflow_factory(
            WorkflowCreate(
                name="metadata-test",
                workflow_definition=workflow_def,
                project_id=first_project_id,
            )
        ).id

        # List versions
        response = syntara_api.workflows.list_versions(workflow_id=workflow_id)

        versions_list = response.assert_and_get()

        for version in versions_list.resources:
            assert version.id is not None
            assert version.version is not None
            assert version.schema_version is not None
            assert version.created_at is not None
            assert version.workflow_id is not None


class TestWorkflowVersionRetrieval:
    """E2E tests for retrieving specific workflow versions."""

    def test_get_workflow_version_by_number(
        self, syntara_api: SyntaraApiRegistry, workflow_factory: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """Test retrieving a specific version by number.

        Expected: 200 OK with version details including workflow definition
        """
        # Create workflow
        workflow_def = WorkflowDefinition.from_dict(
            create_minimal_workflow_definition(
                name="versioned-workflow",
                description="Test workflow for versioning",
                activity_id="initial_activity",
            )
        )
        workflow_id = workflow_factory(
            WorkflowCreate(
                name="versioned-workflow",
                workflow_definition=workflow_def,
                project_id=first_project_id,
            )
        ).id

        # Create version 2
        update_def = WorkflowDefinition.from_dict(
            create_minimal_workflow_definition(
                name="versioned-workflow",
                description="Added activity",
                activity_id="activity_1",
            )
        )
        syntara_api.workflows.update(
            workflow_id=workflow_id,
            body=WorkflowUpdate(
                workflow_definition=update_def,
                change_description="Added activity",
            ),
        )

        # Get version 2
        response = syntara_api.workflows.get_version(workflow_id=workflow_id, version=2)

        version_data = response.assert_and_get()
        assert version_data.version == 2
        assert version_data.workflow_id == workflow_id
        assert version_data.workflow_definition is not None

    def test_get_workflow_version_1(
        self, syntara_api: SyntaraApiRegistry, workflow_factory: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """Test retrieving version 1 (initial version).

        Expected: 200 OK with initial version details
        """
        # Create workflow
        workflow_def = WorkflowDefinition.from_dict(
            create_minimal_workflow_definition(
                name="version-1-test",
                description="Test workflow for version 1",
                activity_id="v1_activity",
            )
        )
        workflow_id = workflow_factory(
            WorkflowCreate(
                name="version-1-test",
                workflow_definition=workflow_def,
                project_id=first_project_id,
            )
        ).id

        # Get version 1
        response = syntara_api.workflows.get_version(workflow_id=workflow_id, version=1)

        version_data = response.assert_and_get()
        assert version_data.version == 1
        assert version_data.workflow_definition is not None

    def test_get_nonexistent_version(
        self, syntara_api: SyntaraApiRegistry, workflow_factory: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """Test retrieving a non-existent version number.

        Expected: 404 Not Found
        """
        # Create workflow
        workflow_def = WorkflowDefinition.from_dict(
            create_minimal_workflow_definition(
                name="test-workflow",
                description="Test workflow for nonexistent version",
                activity_id="test_activity",
            )
        )
        workflow_id = workflow_factory(
            WorkflowCreate(
                name="test-workflow",
                workflow_definition=workflow_def,
                project_id=first_project_id,
            )
        ).id

        # Try to get version 99 (doesn't exist)
        response = syntara_api.workflows.get_version(workflow_id=workflow_id, version=99)

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_get_version_nonexistent_workflow(self, syntara_api: SyntaraApiRegistry) -> None:
        """Test retrieving version for non-existent workflow.

        Expected: 404 Not Found
        """
        fake_id = uuid4()
        response = syntara_api.workflows.get_version(workflow_id=fake_id, version=1)

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_get_version_response_schema(
        self, syntara_api: SyntaraApiRegistry, workflow_factory: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """Test that response matches expected schema.

        Expected: All required fields present
        """
        # Create workflow
        workflow_def = WorkflowDefinition.from_dict(
            create_minimal_workflow_definition(
                name="schema-test",
                description="Test workflow for schema validation",
                activity_id="schema_activity",
            )
        )
        workflow_id = workflow_factory(
            WorkflowCreate(
                name="schema-test",
                workflow_definition=workflow_def,
                project_id=first_project_id,
            )
        ).id

        # Get version 1
        response = syntara_api.workflows.get_version(workflow_id=workflow_id, version=1)

        version = response.assert_and_get()

        # Verify required fields
        assert version.id is not None
        assert version.workflow_id is not None
        assert version.version is not None
        assert version.schema_version is not None
        assert version.workflow_definition is not None
        assert version.created_at is not None

    def test_get_version_includes_full_definition(
        self, syntara_api: SyntaraApiRegistry, workflow_factory: WorkflowFactory, first_project_id: UUID
    ) -> None:
        """Test that response includes complete workflow definition.

        Expected: workflow_definition field contains complete definition with all activities
        """
        # Create workflow with detailed definition
        workflow_def = WorkflowDefinition.from_dict(
            create_workflow_definition_with_activities(
                name="detailed-workflow",
                description="A workflow with detailed configuration",
                activities=[
                    {
                        "id": "task_1",
                        "name": "Task 1",
                        "type": "script",
                        "parameters": {
                            "language": "python",
                            "code": "print('task 1')",
                        },
                    },
                    {
                        "id": "task_2",
                        "name": "Task 2",
                        "type": "script",
                        "parameters": {
                            "language": "python",
                            "code": "print('task 2')",
                        },
                    },
                ],
            )
        )
        workflow_id = workflow_factory(
            WorkflowCreate(
                name="detailed-workflow",
                workflow_definition=workflow_def,
                project_id=first_project_id,
            )
        ).id

        # Get version 1
        response = syntara_api.workflows.get_version(workflow_id=workflow_id, version=1)

        version_data = response.assert_and_get()
        workflow_definition = version_data.workflow_definition
        assert workflow_definition is not None
        assert "nodes" in workflow_definition
        nodes = workflow_definition["nodes"]
        assert len(nodes) == 2
        assert nodes[0]["id"] == "task_1"
        assert nodes[1]["id"] == "task_2"
