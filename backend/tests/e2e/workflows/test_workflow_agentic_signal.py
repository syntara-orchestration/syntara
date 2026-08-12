"""E2E tests for AI Agent node signal-based completion (API-24).

Tests that an AI Agent node starts, blocks on a Temporal signal,
and resumes when the AI completes via the signal endpoint.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest
from orchestrator_test_sdk.e2e import unique_name
from orchestrator_test_sdk.e2e.helpers import poll_execution_until_complete, wait_for_agentic_activity
from syntara_api_client.models.activity_signal_payload import ActivitySignalPayload
from syntara_api_client.models.activity_signal_payload_signal_data import ActivitySignalPayloadSignalData
from syntara_api_client.models.execution_create import ExecutionCreate
from syntara_api_client.models.execution_status import ExecutionStatus
from syntara_api_client.models.workflow_create import WorkflowCreate
from syntara_api_client.models.workflow_definition import WorkflowDefinition

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from syntara_api_client.api import SyntaraApiRegistry
    from syntara_api_client.models.workflow_read import WorkflowRead

    WorkflowFactory = Callable[[WorkflowCreate], WorkflowRead]

pytestmark = [pytest.mark.e2e]

_MAX_POLLS = 30
_POLL_INTERVAL = 2


def _to_dict(output: object) -> dict[str, Any]:
    """Extract a plain dict from activity output_data."""
    return output if isinstance(output, dict) else getattr(output, "additional_properties", {})


class TestWorkflowAgenticSignal:
    """E2E tests for AI Agent node signal-based completion."""

    def test_agentic_signal_completion(
        self,
        syntara_api: SyntaraApiRegistry,
        workflow_factory: WorkflowFactory,
        first_project_id: UUID,
        llm_credential_id: str,
        llm_model_id: str,
    ) -> None:
        """API-24: AI Agent node starts, blocks on signal, resumes when completed."""
        # Step 1: Create a workflow with an agentic node and a downstream script
        workflow_name = unique_name("e2e-agentic-signal")
        workflow = workflow_factory(
            WorkflowCreate(
                name=workflow_name,
                description="E2E test: agentic node signal-based completion",
                project_id=first_project_id,
                workflow_definition=WorkflowDefinition.from_dict(
                    {
                        "name": workflow_name,
                        "schema_version": "2.0.0",
                        "triggers": [
                            {"id": "trigger_manual", "type": "manual_trigger", "parameters": {}},
                        ],
                        "nodes": [
                            {
                                "id": "name_via_ai",
                                "name": "Get Popular Job Template Name",
                                "type": "agentic",
                                "parameters": {
                                    "prompt": (
                                        "Find the Job Template that is installed out of the box "
                                        "in the majority of AAP installations. Return ONLY JSON: "
                                        '{"default_job_template": "template_name_here"}'
                                    ),
                                    "llm_model_id": llm_model_id,
                                    "credential_id": llm_credential_id,
                                },
                            },
                            {
                                "id": "echo_result",
                                "name": "Echo AI Result",
                                "type": "script",
                                "parameters": {
                                    "language": "bash",
                                    "code": 'echo "${name_via_ai.result.default_job_template}"',
                                },
                            },
                        ],
                        "edges": [
                            {"from": "trigger_manual", "to": "name_via_ai"},
                            {"from": "name_via_ai", "to": "echo_result"},
                        ],
                    }
                ),
            )
        )

        # Step 2: Execute the workflow
        execution = syntara_api.executions.create(
            body=ExecutionCreate(workflow_id=workflow.id, trigger_node_id="trigger_manual"),
        ).assert_and_get()
        assert execution.id is not None

        # Step 3: Poll until the agentic activity is in a waiting state
        wait_for_agentic_activity(syntara_api, execution.id, "name_via_ai")

        # Step 4: Send a completion signal with AI result
        signal_response = syntara_api.executions.signal_activity(
            execution_id=execution.id,
            activity_id="name_via_ai",
            body=ActivitySignalPayload(
                signal_data=ActivitySignalPayloadSignalData.from_dict(
                    {
                        "status": "completed",
                        "result": {"default_job_template": "Demo Job Template"},
                    }
                ),
            ),
        )
        assert signal_response.status_code == HTTPStatus.OK, (
            f"Signal endpoint returned {signal_response.status_code}: {signal_response.content!r}"
        )

        # Step 5: Verify the workflow resumes and completes
        final = poll_execution_until_complete(
            syntara_api,
            execution.id,
            max_polls=_MAX_POLLS,
            poll_interval=_POLL_INTERVAL,
        )

        assert final.status == ExecutionStatus.COMPLETED, (
            f"Expected COMPLETED but got {final.status}: {final.error_details}"
        )

        # Verify activity statuses
        activities = {a.activity_id: a for a in (final.activities or [])}
        assert activities["trigger_manual"].status == "completed"
        assert activities["name_via_ai"].status == "completed"
        assert activities["echo_result"].status == "completed"

        # Verify the agentic node's output contains the signal data
        agentic_output = activities["name_via_ai"].output_data
        assert agentic_output is not None, "name_via_ai should have output data"
        agentic_dict = _to_dict(agentic_output)
        assert "result" in agentic_dict, f"Agentic output should contain 'result' key, got: {list(agentic_dict.keys())}"

        # Verify downstream node received the output via ${...} expression
        echo_output = activities["echo_result"].output_data
        assert echo_output is not None, "echo_result should have output data"
        echo_dict = _to_dict(echo_output)
        assert "Demo Job Template" in echo_dict.get("stdout", ""), (
            f"Downstream node should resolve ${{name_via_ai.result.default_job_template}}, "
            f"got stdout: {echo_dict.get('stdout', '')!r}"
        )
