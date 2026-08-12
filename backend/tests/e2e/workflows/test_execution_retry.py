"""E2E tests for POST /executions/{execution_id}/retry endpoint.

Tests retry of completed and failed executions with real Temporal execution,
and verifies that test executions cannot be retried.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import create_and_run_workflow, poll_execution_until_complete
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


def _script_workflow_def(name: str, code: str) -> dict[str, object]:
    return {
        "name": name,
        "schema_version": "2.0.0",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {
                "id": "script_node",
                "name": "Script",
                "type": "script",
                "parameters": {"language": "bash", "code": code},
            },
        ],
        "edges": [{"from": "trigger", "to": "script_node"}],
    }


class TestRetryExecution:
    """Retry execution E2E tests with real Temporal."""

    def test_retry_completed_execution(
        self,
        syntara_api: SyntaraApiRegistry,
        first_project_id: UUID,
    ) -> None:
        """Retry a successfully completed execution creates a new execution with same version and inputs."""
        name = unique_name("e2e-retry-completed")
        original = create_and_run_workflow(
            syntara_api, name, _script_workflow_def(name, "echo ok"), project_id=first_project_id
        )
        assert str(original.status) == "completed"

        retry_response = syntara_api.executions.retry(execution_id=original.id)
        assert retry_response.status_code == HTTPStatus.CREATED

        retried = retry_response.assert_and_get()
        assert retried.retried_from_execution_id == original.id
        assert retried.workflow_version_id == original.workflow_version_id
        assert retried.workflow_id == original.workflow_id
        assert retried.input_data == original.input_data
        assert str(retried.status) == "pending"

        final = poll_execution_until_complete(syntara_api, retried.id)
        assert str(final.status) == "completed"

    def test_retry_failed_execution(
        self,
        syntara_api: SyntaraApiRegistry,
        first_project_id: UUID,
    ) -> None:
        """Retry a failed execution creates a new execution that also runs (and fails with same script)."""
        name = unique_name("e2e-retry-failed")
        original = create_and_run_workflow(
            syntara_api, name, _script_workflow_def(name, "exit 1"), project_id=first_project_id
        )
        assert str(original.status) == "failed"

        retry_response = syntara_api.executions.retry(execution_id=original.id)
        assert retry_response.status_code == HTTPStatus.CREATED

        retried = retry_response.assert_and_get()
        assert retried.retried_from_execution_id == original.id
        assert retried.workflow_version_id == original.workflow_version_id
        assert retried.input_data == original.input_data

        final = poll_execution_until_complete(syntara_api, retried.id)
        assert str(final.status) == "failed"

    def test_retry_test_execution_returns_409(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
    ) -> None:
        """Test executions (mode=test) cannot be retried."""
        name = unique_name("e2e-retry-test-exec")
        workflow = workflow_factory(
            WorkflowCreate(
                name=name,
                description="Workflow for retry-test-execution test",
                project_id=first_project_id,
                workflow_definition=WorkflowDefinition.from_dict(
                    {
                        "name": name,
                        "schema_version": "2.0.0",
                        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
                        "nodes": [
                            {
                                "id": "node_a",
                                "name": "Node A",
                                "type": "script",
                                "parameters": {"language": "bash", "code": "echo a"},
                            },
                            {
                                "id": "node_b",
                                "name": "Node B",
                                "type": "script",
                                "parameters": {"language": "bash", "code": "echo b"},
                            },
                        ],
                        "edges": [
                            {"from": "trigger", "to": "node_a"},
                            {"from": "node_a", "to": "node_b"},
                        ],
                    }
                ),
            )
        )

        pre_resolved = TestExecutionCreatePreResolvedNodes.from_dict({"node_a": {"output": {"stdout": "mocked"}}})
        test_response = syntara_api.workflows.test_node(
            workflow_id=workflow.id,
            body=TestExecutionCreate(
                target_node_id="node_b",
                pre_resolved_nodes=pre_resolved,
                trigger_node_id="trigger",
            ),
        )
        test_execution = test_response.assert_and_get()
        poll_execution_until_complete(syntara_api, test_execution.id)

        retry_response = syntara_api.executions.retry(execution_id=test_execution.id)
        assert retry_response.status_code == HTTPStatus.CONFLICT
