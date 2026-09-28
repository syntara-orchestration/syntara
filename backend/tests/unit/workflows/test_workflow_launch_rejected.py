"""Stable problem-details and audit shape for rejected workflow launches."""

import json
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from syntara.workflows.audit.launch_rejected import WorkflowLaunchRejectedEvent, WorkflowLaunchRejectedHandler
from syntara.workflows.error_handlers import workflow_launch_rejected_handler
from syntara.workflows.exceptions import WorkflowLaunchRejectedError
from syntara.workflows.node_launch_checks import WorkflowLaunchRejection


def _rejection() -> WorkflowLaunchRejection:
    return WorkflowLaunchRejection(
        reason="step_type_denied",
        principal_id=uuid4(),
        project_id=uuid4(),
        trigger_type="webhook_trigger",
        denied_steps=[{"node_id": "step-a", "kind": "script", "denied_by": "deny-script"}],
    )


def test_problem_details_includes_triggered_execution_id() -> None:
    rejection = _rejection()
    execution_id = uuid4()
    request = MagicMock(spec=Request)
    request.url = "https://localhost/api/v1/webhooks/example"

    response = workflow_launch_rejected_handler(request, WorkflowLaunchRejectedError(rejection, execution_id))

    assert isinstance(response, JSONResponse)
    assert response.status_code == 403
    body = json.loads(bytes(response.body))
    assert body["code"] == "WORKFLOW_LAUNCH_REJECTED"
    assert body["reason"] == "step_type_denied"
    assert body["principal_id"] == str(rejection.principal_id)
    assert body["project_id"] == str(rejection.project_id)
    assert body["trigger_type"] == "webhook_trigger"
    assert body["denied_steps"] == rejection.denied_steps
    assert body["execution_id"] == str(execution_id)


def test_rejection_audit_is_one_event_with_all_denied_steps() -> None:
    rejection = _rejection()
    event = WorkflowLaunchRejectedHandler().handle(WorkflowLaunchRejectedEvent(rejection))
    data = event.structured_data.model_dump()

    assert event.event_action == "workflow.launch_rejected"
    assert event.actor_id == rejection.principal_id
    assert data["reason"] == rejection.reason
    assert data["principal_id"] == str(rejection.principal_id)
    assert data["project_id"] == str(rejection.project_id)
    assert data["trigger_type"] == rejection.trigger_type
    assert data["denied_steps"] == rejection.denied_steps
