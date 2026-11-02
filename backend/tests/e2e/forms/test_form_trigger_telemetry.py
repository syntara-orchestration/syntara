"""E2E coverage for Segment telemetry emitted after Form Trigger submissions."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from orchestrator_test_sdk.e2e import unique_name
from syntara_api_client.models import WorkflowCreate

if TYPE_CHECKING:
    from collections.abc import Callable

    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.models import WorkflowRead

if not os.environ.get("APP_BASE_URL"):
    pytest.skip("APP_BASE_URL not set — full stack required", allow_module_level=True)
from ._helpers import (
    assert_consumer_completed,
    submit_form_trigger_and_track,
)
from ._telemetry import (
    SEGMENT_EVENT_TIMEOUT_SECONDS,
    require_segment_server_url,
    wait_for_segment_event,
)
from ._workflows import form_trigger_consumer_workflow

_SEGMENT_SERVER_URL = require_segment_server_url()

pytestmark = [pytest.mark.e2e]

_FIELD_LABEL = "PRIVATE_APPROVAL_REASON_LABEL_97126"
_OPTIONAL_FIELD_LABEL = "PRIVATE_OPTIONAL_COUNT_LABEL_97126"
_FIELD_VALUE = "PRIVATE_APPROVAL_REASON_VALUE_97126"


def _create_form_trigger_workflow(
    workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
    project_id: UUID,
    *,
    name_prefix: str,
) -> WorkflowRead:
    """Create a telemetry test workflow with one required and one optional field."""
    name = unique_name(name_prefix)
    return workflow_factory(
        WorkflowCreate(
            name=name,
            description="E2E: form-trigger submission telemetry",
            project_id=project_id,
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


class TestFormTriggerTelemetry:
    """Telemetry emitted for a form-trigger submission reaches Segment without submitted data."""

    def test_submission_event_contains_bounded_metadata_only(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
        form_execution_cleanup: Callable[[UUID], None],
    ) -> None:
        """A real form-trigger submission emits bounded metadata without submitted data.

        Procedure:
        1. Create a workflow with one required text field and one optional number field.
        2. Submit valid data and wait for the consumer to complete.
        3. Read the captured Segment event and check its metadata, identity, timestamp, and privacy.

        Expected:
        - The event identifies the execution, contains field metadata, and omits submitted data
          and direct submitter identity.
        """
        workflow = _create_form_trigger_workflow(
            workflow_factory,
            first_project_id,
            name_prefix="e2e-form-trigger-telemetry",
        )
        execution = submit_form_trigger_and_track(
            syntara_api,
            workflow,
            {"reason": _FIELD_VALUE},
            form_execution_cleanup,
        )
        execution_id = UUID(str(execution.id))
        assert_consumer_completed(syntara_api, execution_id)
        message = wait_for_segment_event(_SEGMENT_SERVER_URL, "form_trigger_submitted", execution_id)
        properties = message["properties"]

        assert properties["workflow_execution_id"] == str(execution_id)
        assert properties["trigger_node_id"] == "form"
        assert properties["field_count"] == 2
        assert properties["field_types"] == ["number", "text"]
        # Segment uses an anonymous installation identity; the audit record identifies the submitter.
        anonymous_id = message.get("anonymousId")
        assert isinstance(anonymous_id, str)
        assert anonymous_id
        assert message.get("userId") is None

        timestamp_value = message.get("timestamp")
        assert isinstance(timestamp_value, str)
        event_timestamp = datetime.fromisoformat(timestamp_value)
        assert isinstance(execution.created_at, datetime)
        assert event_timestamp.tzinfo is not None
        assert event_timestamp >= execution.created_at - timedelta(seconds=1)
        assert event_timestamp <= execution.created_at + timedelta(seconds=SEGMENT_EVENT_TIMEOUT_SECONDS)

        for key in ("input_data", "response_data", "submitted_by", "user_id", "username", "email"):
            assert key not in properties

        # Search the full message so form labels or values cannot leak outside properties either.
        serialized_event = json.dumps(message)
        assert _FIELD_LABEL not in serialized_event
        assert _OPTIONAL_FIELD_LABEL not in serialized_event
        assert _FIELD_VALUE not in serialized_event
