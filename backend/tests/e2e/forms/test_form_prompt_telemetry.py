"""E2E coverage for Segment telemetry emitted after form-prompt submission."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from syntara_api_client.models import FormPromptStatus
from syntara_api_client.models.user_reference import UserReference

if TYPE_CHECKING:
    from collections.abc import Callable

    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.models import WorkflowCreate, WorkflowRead

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)
from ._helpers import (
    assert_consumer_completed,
    get_form_prompt,
    start_pending_form_prompt,
    submit_form_prompt,
    wait_for_form_prompt_paused,
)
from ._telemetry import (
    SEGMENT_EVENT_TIMEOUT_SECONDS,
    require_segment_server_url,
    wait_for_segment_event,
)
from ._workflows import APPROVAL_REASON_FIELD

_SEGMENT_SERVER_URL = require_segment_server_url()

pytestmark = [pytest.mark.e2e]

_RESPONSE = {"reason": "approved by e2e"}


class TestFormPromptTelemetry:
    """Telemetry emitted for a form-prompt response reaches the Segment backend."""

    def test_response_event_contains_execution_prompt_timing_and_identity(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
        form_execution_cleanup: Callable[[UUID], None],
    ) -> None:
        """The response is tracked with correlation, timing, and Segment identity.

        Procedure:
        1. Start a text-field workflow and wait until the prompt pauses execution.
        2. Submit a response through the form-prompt API.
        3. Read the captured Segment event for this workflow execution.

        Expected:
        - Segment receives a form_prompt_submitted track event.
        - The event identifies the workflow execution and prompt node, carries a response
          timestamp and non-negative wait duration, and includes the Segment anonymous identity.
        - It omits the submitted value and direct submitter identity.
        """
        execution_id, prompt_row = start_pending_form_prompt(
            syntara_api,
            workflow_factory,
            first_project_id,
            workflow_name_prefix="e2e-form-prompt-telemetry",
            description="E2E: form-prompt submission telemetry",
            track_execution=form_execution_cleanup,
            producer_output={},
            form_fields=[APPROVAL_REASON_FIELD],
        )
        prompt_id = UUID(str(prompt_row.id))
        wait_for_form_prompt_paused(syntara_api, execution_id)
        prompt_before_submit = get_form_prompt(syntara_api, prompt_id)

        response = submit_form_prompt(syntara_api, prompt_id, _RESPONSE)
        assert response.status_code == HTTPStatus.OK
        prompt_after_submit = get_form_prompt(syntara_api, prompt_id)
        assert prompt_after_submit.status == FormPromptStatus.SUBMITTED
        assert isinstance(prompt_after_submit.responded_at, datetime)
        assert isinstance(prompt_after_submit.responded_by, UserReference)
        assert isinstance(prompt_before_submit.created_at, datetime)

        assert_consumer_completed(syntara_api, execution_id)
        message = wait_for_segment_event(_SEGMENT_SERVER_URL, "form_prompt_submitted", execution_id)

        properties = message["properties"]
        assert properties["workflow_execution_id"] == str(execution_id)
        assert properties["prompt_node_id"] == "prompt"
        assert properties["field_count"] == len(_RESPONSE)
        assert properties["outcome"] == "submitted"
        assert isinstance(properties["wait_time_ms"], int)
        assert properties["wait_time_ms"] >= 0

        response_timestamp_value = message.get("timestamp")
        assert isinstance(response_timestamp_value, str)
        response_timestamp = datetime.fromisoformat(response_timestamp_value)
        assert response_timestamp >= prompt_after_submit.responded_at - timedelta(seconds=1)
        assert (response_timestamp - prompt_after_submit.responded_at).total_seconds() < SEGMENT_EVENT_TIMEOUT_SECONDS

        expected_wait_ms = int(
            (prompt_after_submit.responded_at - prompt_before_submit.created_at).total_seconds() * 1000
        )
        assert abs(properties["wait_time_ms"] - expected_wait_ms) <= 1000

        anonymous_id = message.get("anonymousId")
        assert isinstance(anonymous_id, str)
        assert anonymous_id

        serialized_event = json.dumps(message)
        assert _RESPONSE["reason"] not in serialized_event
        assert str(prompt_after_submit.responded_by.id) not in serialized_event
        assert prompt_after_submit.responded_by.name not in serialized_event
        assert "response_data" not in properties
        assert "responded_by" not in properties
        assert "submitted_by" not in properties
        assert "user_id" not in properties
        assert "username" not in properties
        assert "email" not in properties
        assert message.get("userId") is None
