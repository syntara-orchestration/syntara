"""Unit tests for the AAP workflow Execution Plane dispatch activity."""

from collections.abc import Generator
from types import SimpleNamespace
from typing import ClassVar, Self
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from execution_plane_client.commands.results import TransportReceipt
from execution_plane_client.protocol import MessageEnvelope, ResourceReference
from temporalio.exceptions import ApplicationError

from syntara.workflow_runtime.engines.temporal.activities.ep import (
    aap_workflow_dispatch_activity as aap_module,
)
from syntara.workflow_runtime.engines.temporal.activities.ep import ep_dispatch_activity as dispatch_module
from syntara.workflow_runtime.engines.temporal.activities.ep.aap_workflow_dispatch_activity import (
    execute_aap_workflow_ep_activity,
)

ACTIVITY_INFO_PATH = "syntara.workflow_runtime.engines.temporal.activities.ep.ep_dispatch_activity.activity.info"
EXECUTION_ID = "00000000-0000-0000-0000-000000000010"


class _FakeEPClient:
    """Minimal async transport double for an already-completed work item."""

    responses: ClassVar[list[dict[str, object] | Exception]] = []
    submissions: ClassVar[list[MessageEnvelope]] = []

    def __init__(self, *, timeout: float | None = None) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def submit_command(self, message: MessageEnvelope) -> TransportReceipt:
        self.submissions.append(message)
        if isinstance(self.responses[0], Exception):
            error = self.responses.pop(0)
            assert isinstance(error, Exception)
            raise error
        return TransportReceipt(
            message_id=message.message_id,
            resource=ResourceReference(
                kind="work_item", resource_id=UUID(str(message.command.payload["work_item_id"]))
            ),
        )

    async def get_work_item(self, *, work_item_id: UUID) -> dict[str, object]:
        response = self.responses.pop(0)
        assert isinstance(response, dict)
        return response


class _FakePluginSession:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def _aap_plugin() -> SimpleNamespace:
    return SimpleNamespace(
        name="aap-workflow",
        image_reference="quay.io/example/aap-workflow:test",
        step_identity="syntara.aap-workflow.aap-workflow",
        manifest={
            "spec": {
                "integrationType": "syntara.aap",
                "input": {
                    "kind": "inline",
                    "value": {
                        "type": "object",
                        "additionalProperties": False,
                        "anyOf": [
                            {"required": ["workflow_job_template_id"]},
                            {"required": ["workflow_job_template_name", "organization_name"]},
                        ],
                        "properties": {
                            "workflow_job_template_id": {"type": "integer", "minimum": 1},
                            "workflow_job_template_name": {"type": "string", "minLength": 1},
                            "organization_id": {"type": "integer"},
                            "organization_name": {"type": "string"},
                            "extra_vars": {"type": "object"},
                            "limit": {"type": "string"},
                            "scm_branch": {"type": "string"},
                            "tags": {"type": "string"},
                            "skip_tags": {"type": "string"},
                            "labels": {"type": "array", "items": {"type": "string"}},
                            "inventory_id": {"type": "integer"},
                            "inventory_name": {"type": "string"},
                            "timeout": {"type": "integer", "minimum": 1},
                        },
                    },
                },
            }
        },
    )


def _valid_input_config() -> dict[str, object]:
    return {
        "workflow_job_template_id": 7,
        "integration_id": "00000000-0000-0000-0000-000000000099",
        "credential_id": "00000000-0000-0000-0000-000000000098",
        "_resolved_integration": {
            "base_url": "https://aap.example.com",
            "verify_ssl": False,
            "ca_certificate": "-----BEGIN CERTIFICATE-----",
        },
        "_resolved_credentials": {"extra_vars": {"aap_oauth_token": "secret"}},
    }


@pytest.fixture(autouse=True)
def mock_activity_context() -> Generator[MagicMock, None, None]:
    """Provide stable Temporal metadata without an activity worker."""
    info = MagicMock()
    info.attempt = 1
    info.workflow_id = "unit-workflow"
    info.workflow_run_id = "unit-run"
    info.activity_id = "unit-activity"
    info.task_token = b"opaque-temporal-token"
    with (
        patch(ACTIVITY_INFO_PATH, return_value=info) as activity_info,
        patch("temporalio.activity.heartbeat"),
        patch.object(dispatch_module, "ExecutionPlaneHttpClient", _FakeEPClient),
        patch.object(dispatch_module, "AsyncSessionLocal", _FakePluginSession),
        patch.object(dispatch_module, "get_execution_plane_plugin", AsyncMock(return_value=_aap_plugin())),
        patch.object(
            dispatch_module,
            "execution_plane_plugin_credential_recipe_ids",
            AsyncMock(return_value=("syntara.aap.credential",)),
        ),
        patch.object(
            dispatch_module,
            "_work_runtime_context",
            AsyncMock(return_value={"execution_id": EXECUTION_ID, "project_id": "test-project"}),
        ),
    ):
        _FakeEPClient.responses = []
        _FakeEPClient.submissions = []
        yield activity_info


class TestAAPWorkflowDispatchValidation:
    """Reject invalid requests before making an HTTP call to EP."""

    @pytest.mark.asyncio
    async def test_missing_integration_is_non_retryable(self) -> None:
        input_config = _valid_input_config()
        input_config.pop("_resolved_integration")

        with pytest.raises(ApplicationError) as exc_info:
            await execute_aap_workflow_ep_activity(input_config, None, EXECUTION_ID)

        assert exc_info.value.type == "ConfigError"
        assert exc_info.value.non_retryable is True
        assert _FakeEPClient.submissions == []

    @pytest.mark.asyncio
    async def test_missing_base_url_is_non_retryable(self) -> None:
        input_config = _valid_input_config()
        input_config["_resolved_integration"] = {"base_url": "", "verify_ssl": True}

        with pytest.raises(ApplicationError) as exc_info:
            await execute_aap_workflow_ep_activity(input_config, None, EXECUTION_ID)

        assert exc_info.value.type == "ConfigError"
        assert exc_info.value.non_retryable is True
        assert _FakeEPClient.submissions == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "input_config",
        [
            {},
            {"workflow_job_template_name": "only-name"},
        ],
    )
    async def test_invalid_node_config_is_non_retryable(self, input_config: dict[str, object]) -> None:
        input_config["_resolved_integration"] = {"base_url": "https://aap.example.com", "verify_ssl": True}

        with pytest.raises(ApplicationError) as exc_info:
            await execute_aap_workflow_ep_activity(input_config, None, EXECUTION_ID)

        assert exc_info.value.type == "ConfigError"
        assert exc_info.value.non_retryable is True
        assert _FakeEPClient.submissions == []

    @pytest.mark.asyncio
    async def test_missing_execution_id_is_non_retryable(self) -> None:
        with pytest.raises(ApplicationError) as exc_info:
            await execute_aap_workflow_ep_activity(_valid_input_config(), None, None)

        assert exc_info.value.type == "ConfigError"
        assert exc_info.value.non_retryable is True
        assert _FakeEPClient.submissions == []


class TestAAPWorkflowDispatch:
    """Exercise the integration projection and result translation."""

    @pytest.mark.asyncio
    async def test_completed_result_projects_integration_into_runtime_context(self) -> None:
        _FakeEPClient.responses = [
            {
                "status": "completed",
                "result": {
                    "status": "completed",
                    "workflow_job_id": 42,
                    "workflow_job_url": "https://aap.example.com/execution/jobs/workflow/42/output",
                    "workflow_job_status": "successful",
                    "artifacts": {"key": "value"},
                    "created": "2026-01-01T00:00:00Z",
                    "started": "2026-01-01T00:00:01Z",
                    "finished": "2026-01-01T00:00:02Z",
                },
            }
        ]

        result = await execute_aap_workflow_ep_activity(_valid_input_config(), None, EXECUTION_ID)

        assert result == {
            "output": {
                "workflow_job_id": 42,
                "workflow_job_url": "https://aap.example.com/execution/jobs/workflow/42/output",
                "workflow_job_status": "successful",
                "artifacts": {"key": "value"},
                "created": "2026-01-01T00:00:00Z",
                "started": "2026-01-01T00:00:01Z",
                "finished": "2026-01-01T00:00:02Z",
            }
        }
        assert len(_FakeEPClient.submissions) == 1
        payload = _FakeEPClient.submissions[0].command.payload
        runtime_context = payload["runtime_context"]
        assert runtime_context["aapEndpoint"] == "https://aap.example.com"
        assert runtime_context["aapVerifySsl"] is False
        assert runtime_context["aapCaCertificate"] == "-----BEGIN CERTIFICATE-----"

    @pytest.mark.asyncio
    async def test_ao_only_identifiers_are_not_forwarded_as_inputs(self) -> None:
        _FakeEPClient.responses = [{"status": "completed", "result": {"status": "completed", "workflow_job_id": 1}}]

        await execute_aap_workflow_ep_activity(_valid_input_config(), None, EXECUTION_ID)

        payload = _FakeEPClient.submissions[0].command.payload
        inputs = payload["invocation"]["inputs"]
        assert "integration_id" not in inputs
        assert "credential_id" not in inputs
        assert "workflow_job_template_id" in inputs
        bindings = payload["invocation"]["credential_bindings"]
        assert bindings == [
            {
                "credential_recipe_id": "syntara.aap.credential",
                "credential_ref": "00000000-0000-0000-0000-000000000098",
            }
        ]

    @pytest.mark.asyncio
    async def test_failed_status_raises_non_retryable_with_output(self) -> None:
        _FakeEPClient.responses = [
            {
                "status": "completed",
                "result": {
                    "status": "failed",
                    "error": "workflow job failed",
                    "workflow_job_id": 42,
                    "workflow_job_status": "failed",
                },
            }
        ]

        with pytest.raises(ApplicationError) as exc_info:
            await execute_aap_workflow_ep_activity(_valid_input_config(), None, EXECUTION_ID)

        assert exc_info.value.type == "AAPWorkflowJobExecutionError"
        assert exc_info.value.non_retryable is True
        assert exc_info.value.details[0]["output"]["workflow_job_id"] == 42


class TestAAPWorkflowAuditEvents:
    """Audit events are derived from the projected result."""

    @pytest.mark.asyncio
    async def test_completed_result_emits_launched_and_completed(self) -> None:
        _FakeEPClient.responses = [
            {
                "status": "completed",
                "result": {
                    "status": "completed",
                    "workflow_job_id": 42,
                    "workflow_job_url": "https://aap.example.com/execution/jobs/workflow/42/output",
                    "workflow_job_status": "successful",
                    "artifacts": {"key": "value"},
                },
            }
        ]

        with (
            patch.object(aap_module, "emit_launched") as emit_launched,
            patch.object(aap_module, "emit_completed") as emit_completed,
        ):
            await execute_aap_workflow_ep_activity(
                _valid_input_config(), None, EXECUTION_ID, "00000000-0000-0000-0000-000000000077"
            )

        assert emit_launched.call_count == 1
        assert emit_launched.call_args.args[1] == 7  # template id from node config
        assert emit_launched.call_args.kwargs["job_id"] == 42
        assert emit_launched.call_args.kwargs["base_url"] == "https://aap.example.com"
        assert emit_launched.call_args.kwargs["actor_id"].bytes == UUID("00000000-0000-0000-0000-000000000077").bytes
        assert emit_completed.call_count == 1
        assert emit_completed.call_args.kwargs["final_status"] == "successful"

    @pytest.mark.asyncio
    async def test_failed_result_emits_launched_and_failed(self) -> None:
        _FakeEPClient.responses = [
            {
                "status": "completed",
                "result": {
                    "status": "failed",
                    "error": "child job failed",
                    "workflow_job_id": 42,
                    "workflow_job_status": "failed",
                },
            }
        ]

        with (
            patch.object(aap_module, "emit_launched") as emit_launched,
            patch.object(aap_module, "emit_failed") as emit_failed,
            patch.object(aap_module, "emit_completed") as emit_completed,
        ):
            with pytest.raises(ApplicationError):
                await execute_aap_workflow_ep_activity(_valid_input_config(), None, EXECUTION_ID)

        assert emit_launched.call_count == 1
        assert emit_failed.call_count == 1
        assert emit_failed.call_args.kwargs["job_status"] == "failed"
        assert emit_failed.call_args.kwargs["error_message"] == "child job failed"
        assert emit_completed.call_count == 0

    @pytest.mark.asyncio
    async def test_name_based_template_skips_audit_events(self) -> None:
        """Emitters no-op without a template ID, matching in-process behavior."""
        input_config = _valid_input_config()
        input_config.pop("workflow_job_template_id")
        input_config["workflow_job_template_name"] = "deploy"
        input_config["organization_name"] = "org"
        _FakeEPClient.responses = [{"status": "completed", "result": {"status": "completed", "workflow_job_id": 42}}]

        with (
            patch.object(aap_module, "emit_launched") as emit_launched,
            patch.object(aap_module, "emit_completed") as emit_completed,
        ):
            await execute_aap_workflow_ep_activity(input_config, None, EXECUTION_ID)

        # emit_launched/emit_completed no-op on template_id=None; the activity
        # still calls them, but the emitters drop the events.
        assert emit_launched.call_args.args[1] is None
        assert emit_completed.call_args.args[1] is None
