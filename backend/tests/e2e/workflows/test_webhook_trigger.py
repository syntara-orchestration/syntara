"""E2E tests for Webhook Trigger full flow.

Tests that a workflow with a webhook_trigger can be created, published,
and triggered via the webhook endpoint with service account Bearer token
authentication, with the execution running to completion.
"""

from collections.abc import Callable
from http import HTTPStatus
from uuid import UUID

import httpx
import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import poll_execution_until_complete
from orchestrator_test_sdk.e2e.tls import e2e_ssl_context
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import (
    WorkflowCreate,
    WorkflowDefinition,
    WorkflowRead,
)
from syntara_api_client.models.publish_version_request import PublishVersionRequest

from tests.e2e.service_accounts import create_sa_with_credential, token_request

pytestmark = [pytest.mark.e2e]


def _get_sa_token(syntara_base_url: str, client_id: str, client_secret: str) -> str:
    """Obtain an SA access token via client credentials grant."""
    resp = token_request(syntara_base_url, client_id, client_secret)
    assert resp.status_code == HTTPStatus.OK, f"Token request failed: {resp.status_code}"
    return str(resp.parsed.access_token)


class TestWebhookTrigger:
    """Webhook trigger E2E tests -- create, publish, authenticate, POST, and verify execution."""

    def test_webhook_trigger_full_flow(
        self,
        syntara_api: SyntaraApiRegistry,
        syntara_base_url: str,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """Full webhook trigger flow: create SA, create workflow, publish, fire, verify.

        Test Procedure:
        1. Create a service account with credentials
        2. Create a workflow with a webhook_trigger bound to the SA
        3. Publish the workflow so the webhook trigger becomes active
        4. Obtain an SA access token and POST to the webhook endpoint
        5. Poll the execution until it reaches a terminal state

        Expected Results:
        - The webhook POST returns 202 Accepted with an execution_id
        - The execution completes successfully
        """
        webhook_path = unique_name("e2e-wh-path")
        workflow_name = unique_name("e2e-webhook-trigger")

        # Step 1: Create SA with credential
        sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)

        # Step 2: Create workflow with webhook_trigger bound to the SA
        workflow_data = WorkflowCreate(
            name=workflow_name,
            description="Workflow for testing webhook trigger full flow",
            project_id=first_project_id,
            workflow_definition=WorkflowDefinition.from_dict(
                {
                    "name": workflow_name,
                    "schema_version": "2.0.0",
                    "triggers": [
                        {
                            "id": "webhook_trigger_1",
                            "type": "webhook_trigger",
                            "parameters": {
                                "webhook_path": webhook_path,
                                "authorized_service_account_ids": [str(sa.id)],
                            },
                            "outputs": {
                                "test_value": "${result.test_key}",
                            },
                        }
                    ],
                    "nodes": [
                        {
                            "id": "echo_node",
                            "name": "Echo Trigger Data",
                            "type": "script",
                            "parameters": {
                                "language": "bash",
                                "code": "echo 'Webhook received'",
                            },
                        }
                    ],
                    "edges": [{"from": "webhook_trigger_1", "to": "echo_node"}],
                }
            ),
        )
        workflow = workflow_factory(workflow_data)
        assert workflow.id is not None

        # Step 3: Publish the workflow
        pub_resp = syntara_api.workflows.publish_version(
            workflow_id=workflow.id,
            version=1,
            body=PublishVersionRequest(),
        )
        assert pub_resp.status_code == HTTPStatus.OK

        # Step 4: Get SA token and POST to the webhook endpoint
        access_token = _get_sa_token(syntara_base_url, client_id, client_secret)
        webhook_url = f"{syntara_base_url}/api/v1/webhooks/{webhook_path}"
        webhook_response = httpx.post(
            webhook_url,
            json={"test_key": "hello"},
            headers={"Authorization": f"Bearer {access_token}"},
            verify=e2e_ssl_context(),
            timeout=30,
        )

        assert webhook_response.status_code == HTTPStatus.ACCEPTED
        response_body = webhook_response.json()
        assert "execution_id" in response_body
        execution_id = response_body["execution_id"]

        # Step 5: Poll execution to completion
        final_execution = poll_execution_until_complete(syntara_api, UUID(execution_id))

        assert str(final_execution.status) == "completed"
        assert final_execution.activities is not None
        activity_ids = {a.activity_id for a in final_execution.activities}
        assert "webhook_trigger_1" in activity_ids
        assert "echo_node" in activity_ids

    def test_webhook_trigger_401_without_token(
        self,
        syntara_base_url: str,
    ):
        """POST without Bearer token returns 401."""
        webhook_url = f"{syntara_base_url}/api/v1/webhooks/{unique_name('no-auth')}"
        response = httpx.post(
            webhook_url,
            json={"some": "data"},
            verify=e2e_ssl_context(),
            timeout=30,
        )
        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_webhook_trigger_404_for_unknown_path(
        self,
        syntara_api: SyntaraApiRegistry,
        syntara_base_url: str,
        first_project_id: UUID,
    ):
        """POST to a nonexistent webhook path returns 404."""
        _sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)
        access_token = _get_sa_token(syntara_base_url, client_id, client_secret)

        unknown_path = unique_name("e2e-wh-nonexistent")
        webhook_url = f"{syntara_base_url}/api/v1/webhooks/{unknown_path}"
        response = httpx.post(
            webhook_url,
            json={"some": "data"},
            headers={"Authorization": f"Bearer {access_token}"},
            verify=e2e_ssl_context(),
            timeout=30,
        )
        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_webhook_trigger_requires_published_workflow(
        self,
        syntara_api: SyntaraApiRegistry,
        syntara_base_url: str,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """Webhook trigger is not active until the workflow is published."""
        webhook_path = unique_name("e2e-wh-unpublished")
        workflow_name = unique_name("e2e-webhook-unpublished")

        sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)
        access_token = _get_sa_token(syntara_base_url, client_id, client_secret)

        workflow_data = WorkflowCreate(
            name=workflow_name,
            description="Workflow for testing unpublished webhook trigger",
            project_id=first_project_id,
            workflow_definition=WorkflowDefinition.from_dict(
                {
                    "name": workflow_name,
                    "schema_version": "2.0.0",
                    "triggers": [
                        {
                            "id": "webhook_trigger_1",
                            "type": "webhook_trigger",
                            "parameters": {
                                "webhook_path": webhook_path,
                                "authorized_service_account_ids": [str(sa.id)],
                            },
                        }
                    ],
                    "nodes": [
                        {
                            "id": "echo_node",
                            "name": "Echo Node",
                            "type": "script",
                            "parameters": {"language": "bash", "code": "echo 'Should not run'"},
                        }
                    ],
                    "edges": [{"from": "webhook_trigger_1", "to": "echo_node"}],
                }
            ),
        )
        workflow = workflow_factory(workflow_data)
        assert workflow.id is not None

        webhook_url = f"{syntara_base_url}/api/v1/webhooks/{webhook_path}"
        response = httpx.post(
            webhook_url,
            json={"test_key": "should_not_trigger"},
            headers={"Authorization": f"Bearer {access_token}"},
            verify=e2e_ssl_context(),
            timeout=30,
        )
        assert response.status_code == HTTPStatus.NOT_FOUND
