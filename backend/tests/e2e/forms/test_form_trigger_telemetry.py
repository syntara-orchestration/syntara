"""E2E coverage for Segment telemetry emitted after Form Trigger submissions."""

from __future__ import annotations

import json
import os
import time
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx
import pytest
from orchestrator_test_sdk.e2e import unique_name
from syntara_api_client.models import ExecutionCreate, WorkflowCreate

if TYPE_CHECKING:
    from collections.abc import Callable

    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.models import WorkflowRead

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)


def _require_segment_server_url() -> str:
    """Require the mock Segment URL configured by the full-stack E2E runner."""
    segment_server_url = os.environ.get("SEGMENT_SERVER_URL")
    if not segment_server_url:
        pytest.skip(
            "SEGMENT_SERVER_URL not set — telemetry E2E requires the mock Segment server",
            allow_module_level=True,
        )
    return segment_server_url


_SEGMENT_SERVER_URL = _require_segment_server_url()

from ._helpers import assert_and_get_with_502_skip  # noqa: E402
from ._workflows import form_trigger_consumer_workflow  # noqa: E402

pytestmark = [pytest.mark.e2e]

_SEGMENT_EVENT_TIMEOUT_SECONDS = 30
_FIELD_LABEL = "PRIVATE_APPROVAL_REASON_LABEL_97126"
_OPTIONAL_FIELD_LABEL = "PRIVATE_OPTIONAL_COUNT_LABEL_97126"
_FIELD_VALUE = "PRIVATE_APPROVAL_REASON_VALUE_97126"


def _wait_for_form_trigger_segment_event(execution_id: UUID) -> dict[str, Any]:
    """Poll Segment until it captures the form-trigger event for this execution."""
    deadline = time.monotonic() + _SEGMENT_EVENT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        response = httpx.get(
            f"{_SEGMENT_SERVER_URL.rstrip('/')}/captured-events",
            params={"event_type": "form_trigger_submitted", "execution_id": str(execution_id)},
            timeout=5,
        )
        assert response.status_code == HTTPStatus.OK, (
            f"Segment /captured-events returned {response.status_code}: {response.text}"
        )
        events = response.json()
        assert isinstance(events, list), f"Expected Segment events list, got {events!r}"
        if events:
            assert len(events) == 1, f"Expected one form-trigger event for {execution_id}, got {events!r}"
            assert isinstance(events[0], dict)
            return events[0]
        time.sleep(0.25)

    pytest.fail(f"Segment did not receive form_trigger_submitted for execution {execution_id}")


class TestFormTriggerTelemetry:
    """Telemetry emitted for a form-trigger submission reaches Segment without submitted data."""

    def test_submission_event_contains_bounded_metadata_only(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
        form_prompt_execution_cleanup: Callable[[UUID], None],
    ) -> None:
        """A real form-trigger submission emits its field metadata and omits PII and values."""
        name = unique_name("e2e-form-trigger-telemetry")
        workflow = workflow_factory(
            WorkflowCreate(
                name=name,
                description="E2E: form-trigger submission telemetry",
                project_id=first_project_id,
                workflow_definition=form_trigger_consumer_workflow(
                    name,
                    form_fields=[
                        {
                            "type": "text",
                            "value_name": "reason",
                            "label": _FIELD_LABEL,
                            "required": True,
                        },
                        {
                            "type": "number",
                            "value_name": "optional_count",
                            "label": _OPTIONAL_FIELD_LABEL,
                            "required": False,
                        },
                    ],
                ),
            )
        )
        execution = assert_and_get_with_502_skip(
            syntara_api.executions.create(
                body=ExecutionCreate.from_dict(
                    {
                        "workflow_id": str(workflow.id),
                        "trigger_node_id": "form",
                        "input_data": {"reason": _FIELD_VALUE},
                    }
                )
            )
        )
        execution_id = UUID(str(execution.id))
        form_prompt_execution_cleanup(execution_id)

        message = _wait_for_form_trigger_segment_event(execution_id)
        properties = message["properties"]

        assert properties["workflow_execution_id"] == str(execution_id)
        assert properties["trigger_node_id"] == "form"
        assert properties["field_count"] == 2
        assert properties["field_types"] == ["number", "text"]
        assert message.get("userId") is None
        for key in ("input_data", "response_data", "submitted_by", "user_id", "username", "email"):
            assert key not in properties

        serialized_event = json.dumps(message)
        assert _FIELD_LABEL not in serialized_event
        assert _OPTIONAL_FIELD_LABEL not in serialized_event
        assert _FIELD_VALUE not in serialized_event
