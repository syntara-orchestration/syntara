"""E2E tests for the scheduled trigger lifecycle.

Verifies that workflows with ``scheduled_trigger`` nodes can be published
successfully (i.e. Temporal accepts the schedule configuration), and that an
interval schedule actually fires and runs the workflow to completion.

Publish-only coverage:

- A workflow with a cron-based scheduled trigger publishes without error.
- A workflow with an interval-based scheduled trigger publishes without error.

The underlying ``ScheduledTriggerService`` creates a Temporal Schedule on
publish (format ``orchestrator-sched-{workflow_id}-{trigger_node_id}``) and deletes
it on unpublish/delete.  The ``scheduled_workflow`` fixture unpublishes every
workflow it created on teardown — before the ``workflow_factory`` delete
(finalizers run LIFO) — so a failed test cannot leave a published workflow with
a live Temporal schedule firing into later tests.

Run with:
    APP_BASE_URL=http://localhost:8000 make test-e2e
"""

import time
from collections.abc import Callable, Generator
from http import HTTPStatus
from typing import Any
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import _retry_api_call, poll_execution
from syntara_api_client.api import SyntaraApiRegistry
from syntara_api_client.models import WorkflowCreate, WorkflowDefinition, WorkflowRead
from syntara_api_client.models.publish_version_request import PublishVersionRequest

pytestmark = [pytest.mark.e2e]

PUBLISH_DEADLINE_SECONDS = 10
FIRE_TIMEOUT_SECONDS = 180
FIRE_POLL_INTERVAL_SECONDS = 5


@pytest.fixture
def scheduled_workflow(
    syntara_api: SyntaraApiRegistry,
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    first_project_id: UUID,
) -> Generator[Callable[[str, dict[str, Any], dict[str, Any]], WorkflowRead], None, None]:
    """Factory creating a single scheduled-trigger workflow, unpublished on teardown.

    Unpublish deletes the Temporal schedule and runs before the
    ``workflow_factory`` delete (finalizers run LIFO) — delete refuses while
    executions are non-terminal, so the schedule must go first.  This holds
    even when a test fails after publishing.
    """
    created: list[WorkflowRead] = []

    def _make(name_prefix: str, trigger: dict[str, Any], node: dict[str, Any]) -> WorkflowRead:
        workflow_name = unique_name(name_prefix)
        workflow_data = WorkflowCreate(
            name=workflow_name,
            description=f"E2E test: scheduled trigger ({name_prefix})",
            project_id=first_project_id,
            workflow_definition=WorkflowDefinition.from_dict(
                {
                    "name": workflow_name,
                    "schema_version": "2.0.0",
                    "triggers": [trigger],
                    "nodes": [node],
                    "edges": [{"from": trigger["id"], "to": node["id"]}],
                }
            ),
        )
        workflow = workflow_factory(workflow_data)
        created.append(workflow)
        return workflow

    yield _make

    for workflow in created:
        try:
            syntara_api.workflows.unpublish(workflow_id=workflow.id)
        except Exception:
            pass  # Best effort — publish may have failed or never happened


CRON_TRIGGER = {
    "id": "nightly_trigger",
    "type": "scheduled_trigger",
    "parameters": {
        "schedule_type": "cron",
        "cron": "0 2 * * *",
        "missed_schedule_policy": "skip",
    },
}

HOURLY_TRIGGER = {
    "id": "interval_trigger",
    "type": "scheduled_trigger",
    "parameters": {
        "schedule_type": "interval",
        "interval": "R/2024-01-01T00:00:00Z/PT1H",
    },
}

MINUTE_TRIGGER = {
    "id": "fire_trigger",
    "type": "scheduled_trigger",
    "parameters": {
        "schedule_type": "interval",
        "interval": "R/2024-01-01T00:00:00Z/PT1M",
        "missed_schedule_policy": "skip",
    },
}


class TestScheduledTrigger:
    """Scheduled trigger lifecycle E2E tests."""

    def test_scheduled_trigger_workflow_publishes_successfully(
        self,
        syntara_api: SyntaraApiRegistry,
        scheduled_workflow: Callable[[str, dict[str, Any], dict[str, Any]], WorkflowRead],
    ):
        """A workflow with a cron-based scheduled trigger publishes without error.

        Test Procedure:
        1. Create a workflow with a ``scheduled_trigger`` using a cron expression.
        2. Publish the workflow.
        3. Assert that the publish succeeds — confirming the scheduled trigger
           configuration is valid and Temporal accepted the schedule.
        """
        workflow = scheduled_workflow(
            "e2e-sched-cron",
            CRON_TRIGGER,
            {
                "id": "nightly_task",
                "name": "Nightly Task",
                "type": "script",
                "parameters": {"language": "bash", "code": "echo 'nightly run'"},
            },
        )
        assert workflow.id is not None

        # Publish — this creates the Temporal Schedule.  If the trigger config
        # is invalid, publish will fail with a validation error.
        pub_resp = _retry_api_call(
            lambda: syntara_api.workflows.publish_version(
                workflow_id=workflow.id,
                version=1,
                body=PublishVersionRequest(),
            ),
            delay=5.0,
        )
        assert pub_resp.status_code == HTTPStatus.OK, (
            f"Failed to publish cron-scheduled workflow: {pub_resp.status_code} {pub_resp.content!r}"
        )

    def test_scheduled_trigger_workflow_with_interval(
        self,
        syntara_api: SyntaraApiRegistry,
        scheduled_workflow: Callable[[str, dict[str, Any], dict[str, Any]], WorkflowRead],
    ):
        """A workflow with an interval-based scheduled trigger publishes without error.

        Test Procedure:
        1. Create a workflow with a ``scheduled_trigger`` using an ISO 8601 interval.
        2. Publish the workflow.
        3. Assert that the publish succeeds — confirming the interval config
           is valid and Temporal accepted the schedule.
        """
        workflow = scheduled_workflow(
            "e2e-sched-interval",
            HOURLY_TRIGGER,
            {
                "id": "hourly_task",
                "name": "Hourly Task",
                "type": "script",
                "parameters": {"language": "bash", "code": "echo 'hourly run'"},
            },
        )
        assert workflow.id is not None

        pub_resp = _retry_api_call(
            lambda: syntara_api.workflows.publish_version(
                workflow_id=workflow.id,
                version=1,
                body=PublishVersionRequest(),
            ),
            delay=5.0,
        )
        assert pub_resp.status_code == HTTPStatus.OK, (
            f"Failed to publish interval-scheduled workflow: {pub_resp.status_code} {pub_resp.content!r}"
        )

    def test_scheduled_trigger_fires_and_completes(
        self,
        syntara_api: SyntaraApiRegistry,
        scheduled_workflow: Callable[[str, dict[str, Any], dict[str, Any]], WorkflowRead],
    ):
        """A published interval schedule fires and its execution completes.

        Test Procedure:
        1. Create a workflow whose only trigger is a one-minute interval
           ``scheduled_trigger`` feeding a single ``wait`` node.
        2. Publish and assert a fast, warning-free response — a warning means
           Temporal did not create the schedule, and a slow publish (~20s)
           means the Temporal server's internal frontend is unreachable.
        3. Wait for a ``scheduled_trigger`` execution to appear, then wait for
           it to reach a terminal state and assert it completed.
        """
        workflow = scheduled_workflow(
            "e2e-sched-fire",
            MINUTE_TRIGGER,
            {
                "id": "wait_1s",
                "name": "Wait 1 Second",
                "type": "wait",
                "parameters": {"duration": 1},
            },
        )
        assert workflow.id is not None

        start = time.monotonic()
        pub_resp = _retry_api_call(
            lambda: syntara_api.workflows.publish_version(
                workflow_id=workflow.id,
                version=1,
                body=PublishVersionRequest(),
            ),
            delay=5.0,
        )
        elapsed = time.monotonic() - start
        assert pub_resp.status_code == HTTPStatus.OK, (
            f"Failed to publish scheduled workflow: {pub_resp.status_code} {pub_resp.content!r}"
        )
        assert elapsed < PUBLISH_DEADLINE_SECONDS, (
            f"Publish took {elapsed:.1f}s (deadline {PUBLISH_DEADLINE_SECONDS}s) — "
            "the Temporal server's internal frontend is likely unreachable"
        )
        published = pub_resp.assert_and_get()
        assert not getattr(published, "warning", None), (
            f"Publish returned a warning, Temporal did not create the schedule: {published.warning!r}"
        )

        triggered = None
        deadline = time.monotonic() + FIRE_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            executions = syntara_api.executions.list(
                additional_params={"workflow_id": str(workflow.id)}, limit=100
            ).assert_and_get()
            triggered = next(
                (e for e in executions.resources if getattr(e, "trigger_type", None) == "scheduled_trigger"),
                None,
            )
            if triggered is not None:
                break
            time.sleep(FIRE_POLL_INTERVAL_SECONDS)
        assert triggered is not None, (
            f"No scheduled_trigger execution within {FIRE_TIMEOUT_SECONDS}s — the Temporal schedule never fired"
        )

        execution = poll_execution(syntara_api, str(triggered.id))
        assert str(execution.status) == "completed", (
            f"Scheduled execution ended in status {execution.status!r}, expected 'completed'"
        )
