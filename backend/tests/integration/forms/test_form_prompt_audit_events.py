"""Integration coverage for prompt lifecycle events reaching the audit pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.audit.outbox.worker import get_outbox_worker

if TYPE_CHECKING:
    from httpx import AsyncClient

    from syntara.audit.models.audit_event import AuditEvent
    from syntara.workflows.models.execution import Execution


FORM_PROMPTS_URL = "/api/v1/form_prompts"
_FORM_DEFINITION = {"fields": [{"value_name": "reason", "type": "text", "label": "Reason", "required": True}]}


def _prompt_payload(execution: Execution, prompt_node_id: str) -> dict[str, object]:
    return {
        "execution_id": str(execution.id),
        "project_id": str(execution.project_id),
        "prompt_node_id": prompt_node_id,
        "name": "Audit test form",
        "form_definition": _FORM_DEFINITION,
        "temporal_activity_id": prompt_node_id,
    }


def _events_for_action(mock_build_otel_log_record: MagicMock, event_action: str) -> list[AuditEvent]:
    return [
        call.args[0] for call in mock_build_otel_log_record.call_args_list if call.args[0].event_action == event_action
    ]


@pytest.mark.integration
@pytest.mark.asyncio
@patch("syntara.audit.outbox.worker._build_otel_log_record")
async def test_prompt_created_responded_and_expired_events_reach_outbox_export(
    mock_build_otel_log_record: MagicMock,
    jwt_client: AsyncClient,
    test_execution: Execution,
) -> None:
    """Exercise lifecycle APIs and inspect the events exported from the audit outbox."""
    responded_node_id = f"respond-{uuid4().hex[:8]}"
    expired_node_id = f"expire-{uuid4().hex[:8]}"

    created_response = await jwt_client.post(FORM_PROMPTS_URL, json=_prompt_payload(test_execution, responded_node_id))
    expired_create_response = await jwt_client.post(
        FORM_PROMPTS_URL,
        json=_prompt_payload(test_execution, expired_node_id),
    )
    assert created_response.status_code == 201, created_response.text
    assert expired_create_response.status_code == 201, expired_create_response.text
    responded_prompt_id = created_response.json()["id"]
    expired_prompt_id = expired_create_response.json()["id"]

    with patch("syntara.forms.clients.workflow_client.WorkflowApiClient") as client_class:
        workflow_client = client_class.return_value.__aenter__.return_value
        workflow_client.send_form_signal = AsyncMock()
        response = await jwt_client.post(
            f"{FORM_PROMPTS_URL}/{responded_prompt_id}/submit",
            json={"response_data": {"reason": "approved"}},
        )
    assert response.status_code == 200, response.text

    expiry_response = await jwt_client.post(
        f"{FORM_PROMPTS_URL}/batch",
        json={"updates": [{"prompt_id": expired_prompt_id, "status": "expired"}]},
    )
    assert expiry_response.status_code == 200, expiry_response.text
    assert expiry_response.json()["total_success"] == 1

    await get_outbox_worker().drain()

    created_events = _events_for_action(mock_build_otel_log_record, "form_prompt_created")
    submitted_events = _events_for_action(mock_build_otel_log_record, "form_prompt_submitted")
    expired_events = _events_for_action(mock_build_otel_log_record, "form_prompt_expired")

    created_for_prompts = {str(event.resource_urn).rsplit(":", maxsplit=1)[-1]: event for event in created_events}
    assert len(created_events) == 2
    assert len(created_for_prompts) == 2
    assert responded_prompt_id in created_for_prompts
    assert expired_prompt_id in created_for_prompts
    assert len(submitted_events) == 1
    assert len(expired_events) == 1

    created_event = created_for_prompts[responded_prompt_id]
    submitted_event = submitted_events[0]
    expired_event = expired_events[0]
    assert created_event.workflow_id == test_execution.workflow_id
    assert created_event.execution_id == test_execution.id
    assert created_event.activity_id == responded_node_id
    assert created_event.structured_data.model_dump()["initiated_by"] == str(test_execution.created_by)
    assert created_event.structured_data.model_dump()["created_at"] is not None
    assert submitted_event.workflow_id == test_execution.workflow_id
    assert submitted_event.execution_id == test_execution.id
    assert submitted_event.activity_id == responded_node_id
    assert submitted_event.actor_id == test_execution.created_by
    assert submitted_event.structured_data.model_dump()["submitted_at"] is not None
    assert submitted_event.structured_data.model_dump()["field_count"] == 1
    assert expired_event.workflow_id == test_execution.workflow_id
    assert expired_event.execution_id == test_execution.id
    assert expired_event.activity_id == expired_node_id
    assert expired_event.structured_data.model_dump()["initiated_by"] == str(test_execution.created_by)
    assert expired_event.structured_data.model_dump()["expired_at"] is not None

    exported_payloads = str(
        [event.model_dump(mode="json") for event in [created_event, submitted_event, expired_event]]
    )
    assert "approved" not in exported_payloads
