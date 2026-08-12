"""E2E tests for POST /api/v1/workflows/{workflow_id}/test endpoint.

Tests single-node execution with mocked predecessor data.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import connected_definition, poll_execution_until_complete
from syntara_api_client.models.publish_version_request import PublishVersionRequest
from syntara_api_client.models.test_execution_create import TestExecutionCreate
from syntara_api_client.models.test_execution_create_pre_resolved_nodes import TestExecutionCreatePreResolvedNodes
from syntara_api_client.models.workflow_create import WorkflowCreate
from syntara_api_client.models.workflow_definition import WorkflowDefinition

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.models.workflow_read import WorkflowRead

    WorkflowFactory = Callable[[WorkflowCreate], WorkflowRead]

pytestmark = [pytest.mark.e2e]


class TestWorkflowTestNode:
    """E2E tests for single-node test execution with mock input."""

    def test_single_step_with_mock_input(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """API-38: Test a single node with mocked predecessor data."""
        # Step 1: Create a workflow with connected nodes
        workflow_name = unique_name("e2e-test-node")
        workflow = workflow_factory(
            WorkflowCreate(
                name=workflow_name,
                description="Workflow for testing single-node execution with mock input",
                project_id=first_project_id,
                workflow_definition=WorkflowDefinition.from_dict(
                    {
                        "name": workflow_name,
                        "schema_version": "2.0.0",
                        "triggers": [
                            {"id": "trigger_manual", "type": "manual_trigger", "parameters": {}},
                        ],
                        "nodes": [
                            {
                                "id": "node_a",
                                "name": "Node A",
                                "type": "script",
                                "parameters": {
                                    "language": "bash",
                                    "code": 'echo "node a output"',
                                },
                            },
                            {
                                "id": "node_b",
                                "name": "Node B",
                                "type": "script",
                                "parameters": {
                                    "language": "bash",
                                    "code": 'echo "${node_a.stdout}"',
                                },
                            },
                        ],
                        "edges": [
                            {"from": "trigger_manual", "to": "node_a"},
                            {"from": "node_a", "to": "node_b"},
                        ],
                    }
                ),
            )
        )

        # Step 2: POST /workflows/{workflow_id}/test with mock input data
        pre_resolved = TestExecutionCreatePreResolvedNodes.from_dict(
            {
                "node_a": {
                    "output": {"stdout": "mocked node a output"},
                },
            }
        )
        response = syntara_api.workflows.test_node(
            workflow_id=workflow.id,
            body=TestExecutionCreate(
                target_node_id="node_b",
                pre_resolved_nodes=pre_resolved,
                trigger_node_id="trigger_manual",
            ),
        )

        execution = response.assert_and_get()
        assert execution.id is not None
        assert execution.workflow_id == workflow.id

        # Step 3: Verify the response
        final_execution = poll_execution_until_complete(syntara_api, execution.id)

        # Expected 1: The node executes with the provided mock data
        assert final_execution.activities is not None, "Execution should include activities"
        activities_by_id = {a.activity_id: a for a in final_execution.activities}
        assert activities_by_id["node_a"].status == "skipped", (
            f"pre-resolved node_a should be skipped, got: {activities_by_id['node_a'].status}"
        )
        assert "node_b" in activities_by_id, "node_b activity should exist"
        assert activities_by_id["node_b"].status == "completed", (
            f"node_b should complete with mocked predecessor, got: {activities_by_id['node_b'].status}"
        )

        # Expected 2: The response includes the node's output with resolved mock data
        node_b_output = activities_by_id["node_b"].output_data
        assert node_b_output is not None, "node_b should have output data"
        output_dict = (
            node_b_output if isinstance(node_b_output, dict) else getattr(node_b_output, "additional_properties", {})
        )
        assert "stdout" in output_dict, f"node_b output should contain stdout, got: {output_dict}"
        assert "mocked node a output" in output_dict["stdout"], (
            f"node_b should echo the mocked node_a output, got: {output_dict['stdout']!r}"
        )

        # Expected 3: No full workflow execution record is created
        assert str(final_execution.mode) == "test", f"Execution mode should be 'test', got: {final_execution.mode}"


class TestTestExecutionWithConditionNode:
    """Test execution with mocked action outputs.

    Given a published workflow, when POST /workflows/{id}/test is called
    with a target node and pre-resolved mock outputs, then the execution
    is created with mode=TEST and execution_metadata containing the
    target node and mocked predecessor outputs.
    """

    def test_test_execution_returns_test_mode(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Publish a workflow and run a test execution with mocked action outputs."""
        workflow = workflow_factory(
            WorkflowCreate(
                name=unique_name("e2e-ac5-test-exec"),
                workflow_definition=WorkflowDefinition.from_dict(connected_definition()),
                project_id=first_project_id,
            )
        )

        publish_resp = syntara_api.workflows.publish_version(
            workflow_id=workflow.id,
            version=workflow.current_version,
            body=PublishVersionRequest(name="for-testing"),
        )
        assert publish_resp.status_code == HTTPStatus.OK

        test_resp = syntara_api.workflows.test_node(
            workflow_id=workflow.id,
            body=TestExecutionCreate.from_dict(
                {
                    "target_node_id": "action_node",
                    "pre_resolved_nodes": {
                        "condition_node": {
                            "output": {"result": "mocked-condition-pass"},
                            "control": {"next_port": "true"},
                        },
                    },
                    "trigger_inputs": {"test_key": "test_value"},
                    "trigger_node_id": "trigger",
                }
            ),
        )

        assert test_resp.status_code == HTTPStatus.CREATED, (
            f"Expected 201 for test execution, got {test_resp.status_code}: {test_resp.content!r}"
        )

        execution = test_resp.parsed
        assert execution is not None
        assert str(execution.mode) == "test", f"Expected mode='test', got '{execution.mode}'"
        assert execution.execution_metadata is not None
        assert execution.execution_metadata["target_node_id"] == "action_node"
        assert "pre_resolved_nodes" in execution.execution_metadata, (
            "Mocked pre_resolved_nodes should be in execution metadata"
        )
        assert "condition_node" in execution.execution_metadata["pre_resolved_nodes"], (
            "Mocked condition_node output should be in pre_resolved_nodes"
        )

        input_data = execution.input_data
        assert input_data is not None, "trigger_inputs should be persisted as input_data"
        input_dict = input_data if isinstance(input_data, dict) else getattr(input_data, "additional_properties", {})
        assert input_dict.get("test_key") == "test_value", (
            f"Expected trigger_inputs to contain test_key=test_value, got: {input_dict}"
        )

        final_execution = poll_execution_until_complete(syntara_api, execution.id)
        assert str(final_execution.status) == "completed", f"Expected completed status, got {final_execution.status}"

        assert final_execution.activities is not None, "Execution should include activities"
        activities_by_id = {a.activity_id: a for a in final_execution.activities}
        assert activities_by_id["condition_node"].status == "skipped", (
            f"Pre-resolved condition_node should be skipped, got: {activities_by_id['condition_node'].status}"
        )
        assert activities_by_id["action_node"].status == "completed", (
            f"Target action_node should be completed, got: {activities_by_id['action_node'].status}"
        )
