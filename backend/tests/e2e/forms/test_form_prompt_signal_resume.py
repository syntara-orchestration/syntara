"""E2E coverage for Temporal pause/resume on form-prompt submission."""

from __future__ import annotations

import os
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from syntara_api_client.models import FormPromptStatus
from syntara_api_client.models.activity_data_output_data_type_0 import ActivityDataOutputDataType0

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
from ._workflows import APPROVAL_REASON_FIELD, ENVIRONMENT_RECORDS, dynamic_option_field

pytestmark = [pytest.mark.e2e]

_SUBMITTED_VALUES = {"reason": "approved by e2e", "environment": "staging"}
_FORM_FIELDS = [
    APPROVAL_REASON_FIELD,
    dynamic_option_field("environment", "${producer.stdout_json.environments}"),
]
_CONSUMER_CODE = 'print("${prompt.response_data.reason}|${prompt.response_data.environment}")'


class TestFormPromptTemporalResume:
    """Form-prompt async completion pauses Temporal and resumes downstream execution."""

    def test_response_resumes_paused_workflow_with_prompt_output(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: Callable[[WorkflowCreate], WorkflowRead],
        first_project_id: UUID,
        form_prompt_execution_cleanup: Callable[[UUID], None],
    ) -> None:
        """The API response completes the async activity and feeds the consumer node.

        Procedure:
        1. Start a script executor → form-prompt → script executor workflow with text and dropdown fields.
        2. Verify the prompt record exists and the Temporal execution is paused on its waiting activity.
        3. Submit valid values and poll the execution to completion.

        Expected:
        - The prompt record is pending while Temporal is paused.
        - Submission resumes the execution and the prompt activity records response data and timestamp.
        - The downstream executor receives both submitted field values.
        """
        execution_id, prompt_row = start_pending_form_prompt(
            syntara_api,
            workflow_factory,
            first_project_id,
            workflow_name_prefix="e2e-form-prompt-signal-resume",
            description="E2E: pause and resume on a form-prompt response",
            track_execution=form_prompt_execution_cleanup,
            producer_output={"environments": ENVIRONMENT_RECORDS},
            form_fields=_FORM_FIELDS,
            consumer_code=_CONSUMER_CODE,
        )
        prompt_id = UUID(str(prompt_row.id))
        wait_for_form_prompt_paused(syntara_api, execution_id)

        prompt = get_form_prompt(syntara_api, prompt_id)
        assert prompt.status == FormPromptStatus.PENDING
        fields = prompt.form_definition.to_dict()["fields"]
        fields_by_name = {field["value_name"]: field for field in fields}
        assert fields_by_name["reason"]["type"] == "text"
        assert fields_by_name["environment"]["type"] == "dropdown"
        assert fields_by_name["environment"]["options"]["source"] == "dynamic_resolved"
        assert fields_by_name["environment"]["options"]["values"] == ENVIRONMENT_RECORDS

        response = submit_form_prompt(syntara_api, prompt_id, _SUBMITTED_VALUES)
        assert response.status_code == 200
        submitted_prompt = get_form_prompt(syntara_api, prompt_id)
        assert submitted_prompt.status == FormPromptStatus.SUBMITTED
        assert isinstance(submitted_prompt.responded_at, datetime)
        assert submitted_prompt.responded_by

        final_execution = assert_consumer_completed(syntara_api, execution_id)
        activities = {activity.activity_id: activity for activity in (final_execution.activities or [])}

        prompt_activity = activities["prompt"]
        assert isinstance(prompt_activity.output_data, ActivityDataOutputDataType0)
        prompt_output = prompt_activity.output_data.to_dict()
        assert prompt_output["outcome"] == "submitted"
        assert prompt_output["response_data"] == _SUBMITTED_VALUES
        assert prompt_output["prompt_id"] == str(prompt_id)
        assert datetime.fromisoformat(prompt_output["responded_at"]) == submitted_prompt.responded_at

        consumer_output = activities["consumer"].output_data
        assert consumer_output is not None
        consumer_data = (
            consumer_output
            if isinstance(consumer_output, dict)
            else getattr(consumer_output, "additional_properties", {})
        )
        assert consumer_data["stdout"].strip() == "approved by e2e|staging"
