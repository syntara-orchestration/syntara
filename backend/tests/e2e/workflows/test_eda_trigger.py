"""E2E tests for the EDA trigger.

Verifies that the ``/webhooks/eda/`` routing works end-to-end with service
account Bearer token authentication.  The ``eda_trigger`` activity delegates
to ``webhook_trigger`` internally, so these tests are intentionally
lightweight — just confirm the ``/eda/`` path prefix is routed correctly.

Run with:
    APP_BASE_URL=http://localhost:8000 make test-e2e
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
from syntara_api_client.models import WorkflowCreate, WorkflowDefinition, WorkflowRead
from syntara_api_client.models.publish_version_request import PublishVersionRequest

from tests.e2e.service_accounts import create_sa_with_credential, token_request

pytestmark = [pytest.mark.e2e]


def _get_sa_token(nexus_base_url: str, client_id: str, client_secret: str) -> str:
    """Obtain an SA access token via client credentials grant."""
    resp = token_request(nexus_base_url, client_id, client_secret)
    assert resp.status_code == HTTPStatus.OK, f"Token request failed: {resp.status_code}"
    return str(resp.parsed.access_token)


class TestEdaTrigger:
    """EDA trigger E2E tests — webhook-style trigger via the /eda/ endpoint."""

    def test_eda_trigger_full_flow(
        self,
        syntara_api: SyntaraApiRegistry,
        nexus_base_url: str,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """Create workflow with eda_trigger, publish, authenticate, POST, poll to completion."""
        workflow_name = unique_name("e2e-eda-trigger")
        webhook_path = unique_name("eda-hook")

        # Step 1: Create SA with credential
        sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)

        # Step 2: Create workflow with eda_trigger bound to the SA
        workflow_data = WorkflowCreate(
            name=workflow_name,
            description="E2E test: EDA trigger full flow",
            project_id=first_project_id,
            workflow_definition=WorkflowDefinition.from_dict(
                {
                    "name": workflow_name,
                    "schema_version": "2.0.0",
                    "triggers": [
                        {
                            "id": "eda_trigger_1",
                            "type": "eda_trigger",
                            "parameters": {
                                "webhook_path": webhook_path,
                                "authorized_service_account_ids": [str(sa.id)],
                            },
                            "outputs": {"event_data": "${result.event_type}"},
                        },
                    ],
                    "nodes": [
                        {
                            "id": "process_event",
                            "name": "Process EDA Event",
                            "type": "script",
                            "parameters": {"language": "bash", "code": "echo 'EDA event processed'"},
                        },
                    ],
                    "edges": [{"from": "eda_trigger_1", "to": "process_event"}],
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

        # Step 4: Get SA token and POST to the EDA webhook endpoint
        access_token = _get_sa_token(nexus_base_url, client_id, client_secret)
        eda_url = f"{nexus_base_url}/api/v1/webhooks/eda/{webhook_path}"
        payload = {"event_type": "host_unreachable", "host": "web-01.example.com"}
        webhook_response = httpx.post(
            eda_url,
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
            verify=e2e_ssl_context(),
            timeout=30,
        )
        assert webhook_response.status_code == HTTPStatus.ACCEPTED, (
            f"Expected 202, got {webhook_response.status_code}: {webhook_response.text!r}"
        )

        # Step 5: Poll to completion
        webhook_body = webhook_response.json()
        execution_id = UUID(webhook_body["execution_id"])
        execution = poll_execution_until_complete(syntara_api, execution_id)

        assert str(execution.status) == "completed"
        assert execution.activities is not None
        activity_ids = {a.activity_id for a in execution.activities}
        assert "eda_trigger_1" in activity_ids
        assert "process_event" in activity_ids

    def test_eda_trigger_401_without_token(
        self,
        nexus_base_url: str,
    ):
        """POST without Bearer token returns 401."""
        eda_url = f"{nexus_base_url}/api/v1/webhooks/eda/{unique_name('no-auth')}"
        response = httpx.post(
            eda_url,
            json={"event_type": "test"},
            verify=e2e_ssl_context(),
            timeout=30,
        )
        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_eda_trigger_404_for_unknown_path(
        self,
        syntara_api: SyntaraApiRegistry,
        nexus_base_url: str,
        first_project_id: UUID,
    ):
        """POST to an unknown EDA webhook path returns 404."""
        _sa, client_id, client_secret = create_sa_with_credential(syntara_api, first_project_id)
        access_token = _get_sa_token(nexus_base_url, client_id, client_secret)

        unknown_path = unique_name("nonexistent-eda-path")
        eda_url = f"{nexus_base_url}/api/v1/webhooks/eda/{unknown_path}"
        response = httpx.post(
            eda_url,
            json={"event_type": "test"},
            headers={"Authorization": f"Bearer {access_token}"},
            verify=e2e_ssl_context(),
            timeout=30,
        )
        assert response.status_code == HTTPStatus.NOT_FOUND
