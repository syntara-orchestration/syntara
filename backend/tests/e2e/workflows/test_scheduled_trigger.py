"""E2E tests for the scheduled trigger lifecycle.

Verifies that workflows with ``scheduled_trigger`` nodes can be published
successfully (i.e. Temporal accepts the schedule configuration).  We do
**not** wait for a schedule to fire — that is already unit-tested.  Instead
we confirm:

- A workflow with a cron-based scheduled trigger publishes without error.
- A workflow with an interval-based scheduled trigger publishes without error.

The underlying ``ScheduledTriggerService`` creates a Temporal Schedule on
publish (format ``nexus-sched-{workflow_id}-{trigger_node_id}``) and deletes
it on unpublish/delete.  The ``workflow_factory`` fixture handles cleanup.

Run with:
    APP_BASE_URL=http://localhost:8000 make test-e2e
"""

from collections.abc import Callable
from http import HTTPStatus
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import WorkflowCreate, WorkflowDefinition, WorkflowRead
from syntara_api_client.models.publish_version_request import PublishVersionRequest

pytestmark = [pytest.mark.e2e]


class TestScheduledTrigger:
    """Scheduled trigger lifecycle E2E tests."""

    def test_scheduled_trigger_workflow_publishes_successfully(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """A workflow with a cron-based scheduled trigger publishes without error.

        Test Procedure:
        1. Create a workflow with a ``scheduled_trigger`` using a cron expression.
        2. Publish the workflow.
        3. Assert that the publish succeeds — confirming the scheduled trigger
           configuration is valid and Temporal accepted the schedule.
        """
        workflow_name = unique_name("e2e-sched-cron")

        workflow_data = WorkflowCreate(
            name=workflow_name,
            description="E2E test: scheduled trigger with cron",
            project_id=first_project_id,
            workflow_definition=WorkflowDefinition.from_dict(
                {
                    "name": workflow_name,
                    "schema_version": "2.0.0",
                    "triggers": [
                        {
                            "id": "nightly_trigger",
                            "type": "scheduled_trigger",
                            "parameters": {
                                "schedule_type": "cron",
                                "cron": "0 2 * * *",
                                "missed_schedule_policy": "skip",
                            },
                        },
                    ],
                    "nodes": [
                        {
                            "id": "nightly_task",
                            "name": "Nightly Task",
                            "type": "script",
                            "parameters": {"language": "bash", "code": "echo 'nightly run'"},
                        },
                    ],
                    "edges": [{"from": "nightly_trigger", "to": "nightly_task"}],
                }
            ),
        )
        workflow = workflow_factory(workflow_data)
        assert workflow.id is not None

        # Publish — this creates the Temporal Schedule.  If the trigger config
        # is invalid, publish will fail with a validation error.
        pub_resp = syntara_api.workflows.publish_version(
            workflow_id=workflow.id,
            version=1,
            body=PublishVersionRequest(),
        )
        assert pub_resp.status_code == HTTPStatus.OK, (
            f"Failed to publish cron-scheduled workflow: {pub_resp.status_code} {pub_resp.content!r}"
        )

    def test_scheduled_trigger_workflow_with_interval(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
    ):
        """A workflow with an interval-based scheduled trigger publishes without error.

        Test Procedure:
        1. Create a workflow with a ``scheduled_trigger`` using an ISO 8601 interval.
        2. Publish the workflow.
        3. Assert that the publish succeeds — confirming the interval config
           is valid and Temporal accepted the schedule.
        """
        workflow_name = unique_name("e2e-sched-interval")

        workflow_data = WorkflowCreate(
            name=workflow_name,
            description="E2E test: scheduled trigger with interval",
            project_id=first_project_id,
            workflow_definition=WorkflowDefinition.from_dict(
                {
                    "name": workflow_name,
                    "schema_version": "2.0.0",
                    "triggers": [
                        {
                            "id": "interval_trigger",
                            "type": "scheduled_trigger",
                            "parameters": {
                                "schedule_type": "interval",
                                "interval": "R/2024-01-01T00:00:00Z/PT1H",
                            },
                        },
                    ],
                    "nodes": [
                        {
                            "id": "hourly_task",
                            "name": "Hourly Task",
                            "type": "script",
                            "parameters": {"language": "bash", "code": "echo 'hourly run'"},
                        },
                    ],
                    "edges": [{"from": "interval_trigger", "to": "hourly_task"}],
                }
            ),
        )
        workflow = workflow_factory(workflow_data)
        assert workflow.id is not None

        pub_resp = syntara_api.workflows.publish_version(
            workflow_id=workflow.id,
            version=1,
            body=PublishVersionRequest(),
        )
        assert pub_resp.status_code == HTTPStatus.OK, (
            f"Failed to publish interval-scheduled workflow: {pub_resp.status_code} {pub_resp.content!r}"
        )
