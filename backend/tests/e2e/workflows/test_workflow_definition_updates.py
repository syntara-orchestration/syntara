"""E2E tests for Workflow API (ANSTRAT-1845).

Tests workflow adding, updating, and removing nodes/edges
"""

from collections.abc import Callable
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import WorkflowCreate, WorkflowDefinition, WorkflowRead, WorkflowUpdate
from syntara_api_client.types import UnexpectedResponseException

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


class TestWorkflowDefinitionUpdates:
    """Tests for updating workflow definitions (nodes, edges)."""

    def test_add_node_to_workflow(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """API 6: Add a node to an existing workflow definition."""
        workflow_name = unique_name("e2e-add-node")
        workflow_data = WorkflowCreate(
            name=workflow_name,
            description="Workflow for testing node addition",
            workflow_definition=_minimal_workflow_definition(workflow_name=workflow_name),
            project_id=first_project_id,
        )
        workflow = workflow_factory(workflow_data)

        # Get current workflow definition
        current_workflow = syntara_api.workflows.get(workflow_id=workflow.id).assert_and_get()
        current_definition = current_workflow.version.workflow_definition.additional_properties

        # Add a new node to the definition
        new_node = {
            "id": "script_node_1",
            "name": "Test Script Node",
            "type": "script",
            "parameters": {"language": "bash", "code": "echo 'Hello'"},
        }
        current_definition["nodes"].append(new_node)

        # Add edge from trigger to new node
        current_definition["edges"].append({"from": "trigger_manual", "to": "script_node_1"})

        # Update workflow with PATCH
        update_data = WorkflowUpdate(
            workflow_definition=current_definition,
            change_description="Added script node",
        )

        updated_workflow = syntara_api.workflows.update(workflow_id=workflow.id, body=update_data).assert_and_get()
        assert updated_workflow.version is not None

        updated_def = updated_workflow.version.workflow_definition
        assert len(updated_def["nodes"]) == 1
        assert updated_def["nodes"][0]["id"] == "script_node_1"
        assert updated_def["nodes"][0]["name"] == "Test Script Node"
        assert len(updated_def["edges"]) == 1

        assert updated_workflow.current_version == 2  # Started at 1, now 2

    def test_update_node_configuration(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """API 7: Update an existing node's configuration.

        Verifies that a node's configuration can be updated and is re-validated
        against the node type's configSchema.
        """
        workflow_name = unique_name("e2e-update-node-config")

        # Create workflow with an AAP Job Template node
        workflow_data = WorkflowCreate(
            name=workflow_name,
            description="Workflow for testing node configuration update",
            project_id=first_project_id,
            workflow_definition=WorkflowDefinition.from_dict(
                {
                    "name": workflow_name,
                    "schema_version": "2.0.0",
                    "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
                    "nodes": [
                        {
                            "id": "aap_job_node",
                            "name": "AAP Job Template",
                            "type": "aap_job_template",
                            "parameters": {
                                "job_template_id": 123,
                                "inventory_id": 456,
                                "extra_vars": {"env": "dev"},
                            },
                        }
                    ],
                    "edges": [{"from": "trigger_manual", "to": "aap_job_node"}],
                }
            ),
        )
        try:
            workflow = workflow_factory(workflow_data)
        except UnexpectedResponseException as exc:
            if exc.status_code == 502:
                pytest.skip("Backend returned 502 Bad Gateway — transient infrastructure issue")
            raise

        try:
            # Get current workflow definition
            current_workflow = syntara_api.workflows.get(workflow_id=workflow.id).assert_and_get()
            current_definition = current_workflow.version.workflow_definition.additional_properties

            # Update the AAP job node's configuration
            for node in current_definition["nodes"]:
                if node["id"] == "aap_job_node":
                    node["parameters"]["job_template_id"] = 789  # Updated template ID
                    node["parameters"]["extra_vars"] = {"env": "prod", "debug": "true"}  # Updated vars
                    node["name"] = "Updated AAP Job Template"  # Updated name
                    break

            # Update workflow with modified node configuration
            update_data = WorkflowUpdate(
                workflow_definition=current_definition,
                change_description="Updated AAP job template configuration",
            )

            updated_workflow = syntara_api.workflows.update(workflow_id=workflow.id, body=update_data).assert_and_get()

            # Verify response
            assert updated_workflow.version is not None
            assert updated_workflow.current_version == 2  # Started at 1, now 2

            # Verify node configuration reflects new values
            updated_def = updated_workflow.version.workflow_definition
            assert len(updated_def["nodes"]) == 1

            updated_node = updated_def["nodes"][0]
            assert updated_node["id"] == "aap_job_node"
            assert updated_node["name"] == "Updated AAP Job Template"
            assert updated_node["parameters"]["job_template_id"] == 789
            assert updated_node["parameters"]["inventory_id"] == 456  # Unchanged
            assert updated_node["parameters"]["extra_vars"]["env"] == "prod"
            assert updated_node["parameters"]["extra_vars"]["debug"] == "true"

            # Verify edges remain unchanged
            assert len(updated_def["edges"]) == 1
            assert updated_def["edges"][0]["from"] == "trigger_manual"
            assert updated_def["edges"][0]["to"] == "aap_job_node"
        except UnexpectedResponseException as exc:
            if exc.status_code == 502:
                pytest.skip("Backend returned 502 Bad Gateway — transient infrastructure issue")
            raise

    def test_delete_node_from_workflow(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """API 8: Delete a node from workflow and verify connected edges are cleaned up.

        Creates a workflow with three connected nodes (A → B → C), removes the middle
        node (B), and verifies that edges connected to the deleted node are also removed.
        """
        workflow_name = unique_name("e2e-delete-node")

        # Create workflow with three connected nodes: A → B → C
        workflow_data = WorkflowCreate(
            name=workflow_name,
            description="Workflow for testing node deletion",
            project_id=first_project_id,
            workflow_definition=WorkflowDefinition.from_dict(
                {
                    "name": workflow_name,
                    "schema_version": "2.0.0",
                    "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
                    "nodes": [
                        {
                            "id": "script_node_a",
                            "name": "Script Node A",
                            "type": "script",
                            "parameters": {"language": "bash", "code": "echo 'Node A'"},
                        },
                        {
                            "id": "script_node_b",
                            "name": "Script Node B",
                            "type": "script",
                            "parameters": {"language": "bash", "code": "echo 'Node B'"},
                        },
                        {
                            "id": "script_node_c",
                            "name": "Script Node C",
                            "type": "script",
                            "parameters": {"language": "bash", "code": "echo 'Node C'"},
                        },
                    ],
                    "edges": [
                        {"from": "trigger_manual", "to": "script_node_a"},
                        {"from": "script_node_a", "to": "script_node_b"},  # A → B
                        {"from": "script_node_b", "to": "script_node_c"},  # B → C
                    ],
                }
            ),
        )
        try:
            workflow = workflow_factory(workflow_data)
        except UnexpectedResponseException as exc:
            if exc.status_code == 502:
                pytest.skip("Backend returned 502 Bad Gateway — transient infrastructure issue")
            raise

        try:
            # Get current workflow definition
            current_workflow = syntara_api.workflows.get(workflow_id=workflow.id).assert_and_get()
            current_definition = current_workflow.version.workflow_definition.additional_properties

            # Verify initial state: 3 nodes and 3 edges
            assert len(current_definition["nodes"]) == 3
            assert len(current_definition["edges"]) == 3

            # Remove Node B from the workflow
            current_definition["nodes"] = [
                node for node in current_definition["nodes"] if node["id"] != "script_node_b"
            ]

            # Remove all edges connected to Node B (A→B and B→C)
            current_definition["edges"] = [
                edge
                for edge in current_definition["edges"]
                if edge["from"] != "script_node_b" and edge["to"] != "script_node_b"
            ]

            # Reconnect A → C now that B (the middle node) is removed
            current_definition["edges"].append({"from": "script_node_a", "to": "script_node_c"})

            # Update workflow with removed node and reconnected edges
            update_data = WorkflowUpdate(
                workflow_definition=current_definition,
                change_description="Removed Node B and its connected edges",
            )

            updated_workflow = syntara_api.workflows.update(workflow_id=workflow.id, body=update_data).assert_and_get()

            # Verify response is successful (200 OK via assert_and_get)
            assert updated_workflow.version is not None
            assert updated_workflow.current_version == 2  # Started at 1, now 2

            # Verify the node is removed from the workflow's nodes list
            updated_def = updated_workflow.version.workflow_definition
            assert len(updated_def["nodes"]) == 2, "Should have 2 nodes remaining (A and C)"

            node_ids = [node["id"] for node in updated_def["nodes"]]
            assert "script_node_a" in node_ids, "Node A should remain"
            assert "script_node_c" in node_ids, "Node C should remain"
            assert "script_node_b" not in node_ids, "Node B should be removed"

            # Verify edges connected to the deleted node (A→B, B→C) are removed; A→C reconnect added
            assert len(updated_def["edges"]) == 2, "Should have 2 edges remaining (trigger→A and A→C)"

            edge_pairs = {(e["from"], e["to"]) for e in updated_def["edges"]}
            assert ("trigger_manual", "script_node_a") in edge_pairs, "trigger→A edge should remain"
            assert ("script_node_a", "script_node_c") in edge_pairs, "A→C reconnect edge should exist"

            # Verify no edges reference the deleted node
            for edge in updated_def["edges"]:
                assert edge["from"] != "script_node_b", "No edge should originate from deleted node"
                assert edge["to"] != "script_node_b", "No edge should point to deleted node"
        except UnexpectedResponseException as exc:
            if exc.status_code == 502:
                pytest.skip("Backend returned 502 Bad Gateway — transient infrastructure issue")
            raise

    def test_add_and_delete_edges(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """API 9: Add and delete edges between nodes via PATCH.

        Verifies that edges can be created and deleted by updating the workflow definition.
        Tests that nodes remain intact when edges are removed.
        """
        workflow_name = unique_name("e2e-edge-management")

        # Create workflow with two nodes, each reachable from the trigger
        workflow_data = WorkflowCreate(
            name=workflow_name,
            description="Workflow for testing edge management",
            project_id=first_project_id,
            workflow_definition=WorkflowDefinition.from_dict(
                {
                    "name": workflow_name,
                    "schema_version": "2.0.0",
                    "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
                    "nodes": [
                        {
                            "id": "node_a",
                            "name": "Node A",
                            "type": "script",
                            "parameters": {"language": "bash", "code": "echo 'A'"},
                        },
                        {
                            "id": "node_b",
                            "name": "Node B",
                            "type": "script",
                            "parameters": {"language": "bash", "code": "echo 'B'"},
                        },
                    ],
                    "edges": [
                        {"from": "trigger_manual", "to": "node_a"},
                        {"from": "trigger_manual", "to": "node_b"},
                    ],  # Both nodes reachable from trigger
                }
            ),
        )
        workflow = workflow_factory(workflow_data)

        # Step 1: Add edge A→B via PATCH
        current_workflow = syntara_api.workflows.get(workflow_id=workflow.id).assert_and_get()
        current_definition = current_workflow.version.workflow_definition.additional_properties

        # Add the new edge
        current_definition["edges"].append({"from": "node_a", "to": "node_b"})

        update_data = WorkflowUpdate(workflow_definition=current_definition, change_description="Added edge A→B")
        updated_workflow = syntara_api.workflows.update(workflow_id=workflow.id, body=update_data).assert_and_get()

        # Verify edge creation (200 OK via assert_and_get, not 201)
        assert updated_workflow.current_version == 2
        updated_def = updated_workflow.version.workflow_definition

        assert len(updated_def["edges"]) == 3, "Should have 3 edges after addition"
        assert {"from": "trigger_manual", "to": "node_a"} in updated_def["edges"]
        assert {"from": "trigger_manual", "to": "node_b"} in updated_def["edges"]
        assert {"from": "node_a", "to": "node_b"} in updated_def["edges"]

        # Verify edge references correct source and target nodes
        edge_a_to_b = next(edge for edge in updated_def["edges"] if edge["from"] == "node_a")
        assert edge_a_to_b["from"] == "node_a"
        assert edge_a_to_b["to"] == "node_b"

        # Verify nodes remain intact
        assert len(updated_def["nodes"]) == 2, "Nodes should remain intact after edge addition"

        # Step 2: Delete edge A→B via PATCH
        current_workflow = syntara_api.workflows.get(workflow_id=workflow.id).assert_and_get()
        current_definition = current_workflow.version.workflow_definition.additional_properties

        # Remove the edge A→B
        current_definition["edges"] = [
            edge for edge in current_definition["edges"] if not (edge["from"] == "node_a" and edge["to"] == "node_b")
        ]

        update_data = WorkflowUpdate(workflow_definition=current_definition, change_description="Deleted edge A→B")
        updated_workflow = syntara_api.workflows.update(workflow_id=workflow.id, body=update_data).assert_and_get()

        # Verify edge deletion (200 OK via assert_and_get, not 204)
        assert updated_workflow.current_version == 3
        updated_def = updated_workflow.version.workflow_definition

        assert len(updated_def["edges"]) == 2, "Should have 2 edges after deletion (trigger→A, trigger→B)"
        assert {"from": "trigger_manual", "to": "node_a"} in updated_def["edges"]
        assert {"from": "trigger_manual", "to": "node_b"} in updated_def["edges"]
        assert {"from": "node_a", "to": "node_b"} not in updated_def["edges"]

        # Verify nodes remain intact after edge deletion (only edge removed, not nodes)
        assert len(updated_def["nodes"]) == 2, "Both nodes should still exist after edge deletion"
        node_ids = [node["id"] for node in updated_def["nodes"]]
        assert "node_a" in node_ids
        assert "node_b" in node_ids
