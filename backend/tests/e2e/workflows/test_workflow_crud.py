"""E2E tests for Workflow API (ANSTRAT-1845).

Tests workflow CRUD operations including creation, retrieval,
updates, and deletion via the REST API.
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import _retry_api_call
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import WorkflowCreate, WorkflowDefinition, WorkflowRead, WorkflowUpdate

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


def _workflow_definition_with_nodes(
    *nodes: dict[str, Any],
    edges: list[dict[str, Any]] | None = None,
    workflow_name: str = "workflow_with_node",
) -> WorkflowDefinition:
    """Workflow definition with custom nodes and edges."""
    return WorkflowDefinition.from_dict(
        {
            "name": workflow_name,
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
            "nodes": list(nodes),
            "edges": edges or [],
        }
    )


class TestWorkflowAPI:
    """Workflow API tests - CRUD operations and validation."""

    def test_create_workflow_minimal(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """API 1: Create workflow with minimal definition (empty nodes/edges)."""
        workflow_name = unique_name("e2e-create-minimal")

        workflow_data = WorkflowCreate(
            name=workflow_name,
            description="E2E test workflow",
            workflow_definition=_minimal_workflow_definition(workflow_name=workflow_name),
            project_id=first_project_id,
        )

        workflow = workflow_factory(workflow_data)

        assert workflow.id is not None
        assert workflow.name == workflow_name
        assert workflow.description == "E2E test workflow"
        assert workflow.created_at is not None
        assert workflow.updated_at is not None
        assert workflow.is_enabled is False  # Workflows default to disabled until published
        assert workflow.current_version == 1

        workflow_with_version = syntara_api.workflows.get(workflow_id=workflow.id).assert_and_get()
        assert workflow_with_version.version is not None
        assert workflow_with_version.version.workflow_definition is not None

        definition = workflow_with_version.version.workflow_definition
        assert definition["schema_version"] == "2.0.0"
        assert definition["nodes"] == []
        assert definition["edges"] == []
        assert len(definition["triggers"]) == 1
        assert definition["triggers"][0]["type"] == "manual_trigger"

    def test_get_workflow_with_nodes_and_edges(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """API 2: Retrieve workflow by ID including its graph-based definition."""
        workflow_name = unique_name("e2e-get-with-nodes")

        workflow_data = WorkflowCreate(
            name=workflow_name,
            description="Workflow for testing retrieval with nodes",
            project_id=first_project_id,
            workflow_definition=_workflow_definition_with_nodes(
                {
                    "id": "script_node_1",
                    "name": "First Script",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "echo 'Hello from node 1'"},
                },
                {
                    "id": "script_node_2",
                    "name": "Second Script",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "echo 'Hello from node 2'"},
                },
                edges=[
                    {"from": "trigger_manual", "to": "script_node_1"},
                    {"from": "script_node_1", "to": "script_node_2"},
                ],
                workflow_name=workflow_name,
            ),
        )

        created_workflow = workflow_factory(workflow_data)

        workflow = syntara_api.workflows.get(workflow_id=created_workflow.id).assert_and_get()

        assert workflow.id == created_workflow.id
        assert workflow.name == workflow_name
        assert workflow.description == "Workflow for testing retrieval with nodes"
        assert workflow.is_enabled is False  # Workflows default to disabled until published
        assert workflow.created_at is not None
        assert workflow.updated_at is not None
        assert workflow.current_version == 1

        assert workflow.version is not None
        assert workflow.version.workflow_definition is not None

        definition = workflow.version.workflow_definition

        assert definition["schema_version"] == "2.0.0"

        assert "triggers" in definition
        assert len(definition["triggers"]) == 1
        assert definition["triggers"][0]["id"] == "trigger_manual"
        assert definition["triggers"][0]["type"] == "manual_trigger"

        assert "nodes" in definition
        assert len(definition["nodes"]) == 2, "Should have 2 nodes"

        node_1 = definition["nodes"][0]
        assert node_1["id"] == "script_node_1"
        assert node_1["name"] == "First Script"
        assert node_1["type"] == "script"
        assert node_1["parameters"]["language"] == "bash"
        assert node_1["parameters"]["code"] == "echo 'Hello from node 1'"

        node_2 = definition["nodes"][1]
        assert node_2["id"] == "script_node_2"
        assert node_2["name"] == "Second Script"
        assert node_2["type"] == "script"

        assert "edges" in definition
        assert len(definition["edges"]) == 2, "Should have 2 edges"

        edge_1 = definition["edges"][0]
        assert edge_1["from"] == "trigger_manual"
        assert edge_1["to"] == "script_node_1"

        edge_2 = definition["edges"][1]
        assert edge_2["from"] == "script_node_1"
        assert edge_2["to"] == "script_node_2"

    def test_get_workflow_not_found(self, syntara_api: SyntaraApiRegistry):
        """API 2: Verify 404 is returned for non-existent workflow ID."""
        non_existent_id = uuid4()

        # Verify 404 Not Found is returned
        syntara_api.workflows.get(workflow_id=non_existent_id).assert_error()

    def test_update_workflow_metadata(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """API 3: Update workflow metadata (name, description)."""
        # Create initial workflow
        workflow_name = unique_name("e2e-update-metadata")
        workflow_data = WorkflowCreate(
            name=workflow_name,
            description="Original description",
            workflow_definition=_minimal_workflow_definition(workflow_name=workflow_name),
            project_id=first_project_id,
        )

        workflow = workflow_factory(workflow_data)
        original_updated_at = workflow.updated_at

        # Update the workflow metadata
        updated_name = unique_name("e2e-updated-metadata")
        update_data = WorkflowUpdate(name=updated_name, description="Updated description")

        syntara_api.workflows.update(workflow_id=workflow.id, body=update_data).assert_successful()

        updated_workflow = syntara_api.workflows.get(workflow_id=workflow.id).assert_and_get()

        assert updated_workflow.name == updated_name
        assert updated_workflow.description == "Updated description"

        assert updated_workflow.updated_at is not None
        assert updated_workflow.updated_at > original_updated_at, (
            "updated_at should be later than the original timestamp"
        )

    def test_delete_workflow(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """API 4: Delete workflow and verify it's no longer accessible."""
        # Create a workflow with nodes and edges
        workflow_name = unique_name("e2e-delete")
        workflow_data = WorkflowCreate(
            name=workflow_name,
            description="Workflow to be deleted",
            project_id=first_project_id,
            workflow_definition=_workflow_definition_with_nodes(
                {
                    "id": "script_node_1",
                    "name": "Script Node",
                    "type": "script",
                    "parameters": {"language": "bash", "code": "echo 'test'"},
                },
                edges=[{"from": "trigger_manual", "to": "script_node_1"}],
                workflow_name=workflow_name,
            ),
        )

        workflow = workflow_factory(workflow_data)

        # Verify workflow exists before deletion
        syntara_api.workflows.get(workflow_id=workflow.id).assert_successful()

        _retry_api_call(lambda: syntara_api.workflows.delete(workflow_id=workflow.id)).assert_successful()

        # Verify workflow no longer exists (404 Not Found)
        syntara_api.workflows.get(workflow_id=workflow.id).assert_error()

    def test_list_workflows_with_pagination_filtering_sorting(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """API 5: List workflows with pagination, filtering, and sorting."""
        # Create multiple workflows with different names and statuses
        unique_suffix = uuid4().hex[:8]

        workflows_to_create = [
            {"name": f"e2e-list-alpha-{unique_suffix}"},
            {"name": f"e2e-list-beta-{unique_suffix}"},
            {"name": f"e2e-list-gamma-{unique_suffix}"},
            {"name": f"e2e-other-delta-{unique_suffix}"},
        ]

        # Create all test workflows
        for wf_config in workflows_to_create:
            workflow_data = WorkflowCreate(
                name=wf_config["name"],
                description="Test workflow for listing",
                workflow_definition=_minimal_workflow_definition(workflow_name=wf_config["name"]),
                project_id=first_project_id,
            )
            workflow_factory(workflow_data)

        # Test 1: Pagination with limit
        wf_list = syntara_api.workflows.list(limit=2).assert_and_get()
        assert len(wf_list.resources) <= 2, "Should respect limit parameter"

        # Test 2: Filtering by name substring using name[contains]
        # Filter for workflows containing "e2e-list" (should match alpha, beta, gamma but NOT delta)
        contains_filter_result = syntara_api.workflows.list(
            additional_params={"name[contains]": "e2e-list"}
        ).assert_and_get()

        # Filter the results to only our test workflows (by unique suffix)
        our_workflows_from_filter = [wf for wf in contains_filter_result.resources if unique_suffix in wf.name]

        # Should return 3 workflows: alpha, beta, gamma (not delta which has "e2e-other")
        assert len(our_workflows_from_filter) == 3, (
            f"name[contains] filter for 'e2e-list' should return 3 of our test workflows. "
            f"Got {len(our_workflows_from_filter)}: "
            f"{[wf.name for wf in our_workflows_from_filter]}"
        )

        # Verify delta is NOT in the results (it has "e2e-other" not "e2e-list")
        delta_name = workflows_to_create[3]["name"]  # e2e-other-delta
        assert delta_name not in [wf.name for wf in our_workflows_from_filter], (
            f"Delta workflow '{delta_name}' should NOT be in results (it doesn't contain 'e2e-list')"
        )

        # Test 3: Filtering by enabled status
        disabled_result = syntara_api.workflows.list(
            additional_params={"is_enabled": "false"}, limit=100
        ).assert_and_get()

        # Filter client-side to find our test workflows
        disabled_workflows = [
            wf for wf in disabled_result.resources if unique_suffix in wf.name and wf.is_enabled is False
        ]
        assert len(disabled_workflows) == 4, (
            f"Should find exactly 4 disabled test workflows. Found: {[wf.name for wf in disabled_workflows]}"
        )

        # Test 4: Sorting by name (ascending and descending)
        for sort_param, reverse in [("name", False), ("-name", True)]:
            sort_result = syntara_api.workflows.list(
                sort=sort_param, limit=100, additional_params={"name[contains]": unique_suffix}
            ).assert_and_get()

            test_workflows = list(sort_result.resources)
            assert len(test_workflows) == 4, "Should find all 4 test workflows in sorted list"

            # Verify correct sort order
            workflow_names = [wf.name for wf in test_workflows]
            expected_order = sorted(workflow_names, reverse=reverse)
            assert workflow_names == expected_order, (
                f"Workflows should be sorted {'descending' if reverse else 'ascending'}. "
                f"Got: {workflow_names}, Expected: {expected_order}"
            )
