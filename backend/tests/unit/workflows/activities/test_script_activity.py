"""Unit tests for AO's authenticated Execution Plane dispatch activity."""

import asyncio
from collections.abc import Generator
from enum import Enum
from types import SimpleNamespace
from typing import ClassVar, Self
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid5

import pytest
from execution_plane_client.commands.results import TransportReceipt
from execution_plane_client.protocol import MessageEnvelope, ResourceReference
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.execution_plane.client import ExecutionPlaneRejectedError, ExecutionPlaneUnavailableError
from syntara.workflow_runtime.engines.temporal.activities.ep import ep_dispatch_activity as activity_module
from syntara.workflow_runtime.engines.temporal.constants import ENGINE_MAX_OUTPUT_BYTES_KEY, ENGINE_TIMEOUT_SECONDS_KEY

ACTIVITY_INFO_PATH = "syntara.workflow_runtime.engines.temporal.activities.ep.ep_dispatch_activity.activity.info"
EXECUTION_ID = "00000000-0000-0000-0000-000000000010"
WORK_ITEM_ID = uuid5(UUID(EXECUTION_ID), "unit-activity")
EXECUTION_TARGET_ID = UUID("00000000-0000-0000-0000-000000000030")


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
        assert work_item_id == WORK_ITEM_ID
        response = self.responses.pop(0)
        assert isinstance(response, dict)
        return response


class _FakePluginSession:
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def _plugin_manifest(*, require_environment: bool = False) -> dict[str, object]:
    required = ["code", "environment"] if require_environment else ["code"]
    return {
        "spec": {
            "input": {
                "kind": "inline",
                "value": {
                    "type": "object",
                    "required": required,
                    "additionalProperties": False,
                    "properties": {
                        "code": {"type": "string", "minLength": 1},
                        "environment": {"type": "object", "additionalProperties": {"type": "string"}},
                        "max_output_bytes": {"type": "integer", "minimum": 1},
                    },
                },
            }
        }
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
        patch.object(activity_module, "ExecutionPlaneHttpClient", _FakeEPClient),
        patch.object(activity_module, "AsyncSessionLocal", _FakePluginSession),
        patch.object(
            activity_module,
            "get_execution_plane_plugin",
            AsyncMock(
                return_value=SimpleNamespace(
                    name="script-bash",
                    image_reference="quay.io/example/script-bash:test",
                    step_identity="syntara.script-bash.script-bash",
                    manifest=_plugin_manifest(),
                )
            ),
        ),
        patch.object(
            activity_module,
            "_work_runtime_context",
            AsyncMock(return_value={"project_id": "test-project", "workflow_id": "test-workflow"}),
        ),
    ):
        _FakeEPClient.responses = []
        _FakeEPClient.submissions = []
        yield activity_info


class TestScriptActivityValidation:
    """Reject invalid requests before making an HTTP call to EP."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "input_config",
        [
            {},
            {"code": ""},
            {"code": "echo hello", "environment": "invalid"},
            {"language": "bash", "code": "echo hello"},
        ],
    )
    async def test_invalid_config_is_non_retryable(self, input_config: dict[str, str]) -> None:
        """Invalid script fields fail before AO contacts the remote service."""
        with pytest.raises(ApplicationError) as exc_info:
            await activity_module.execute_bash_script_activity(input_config, None, EXECUTION_ID)
        assert exc_info.value.type == "ConfigError"
        assert exc_info.value.non_retryable is True
        assert _FakeEPClient.submissions == []

    @pytest.mark.asyncio
    async def test_invalid_execution_id_is_non_retryable(self) -> None:
        with pytest.raises(ApplicationError) as exc_info:
            await activity_module.execute_bash_script_activity({"code": ":"}, None, "invalid")
        assert exc_info.value.type == "ConfigError"
        assert _FakeEPClient.submissions == []

    @pytest.mark.asyncio
    async def test_registry_input_contract_is_enforced_before_dispatch(self) -> None:
        """Registry input schemas constrain requests beyond the typed node model."""
        with patch.object(
            activity_module,
            "get_execution_plane_plugin",
            AsyncMock(
                return_value=SimpleNamespace(
                    name="script-bash",
                    image_reference="quay.io/example/script-bash:test",
                    step_identity="syntara.script-bash.script-bash",
                    manifest=_plugin_manifest(require_environment=True),
                )
            ),
        ):
            with pytest.raises(ApplicationError) as exc_info:
                await activity_module.execute_bash_script_activity({"code": ":"}, None, EXECUTION_ID)

        assert exc_info.value.type == "ConfigError"
        assert exc_info.value.non_retryable is True
        assert "environment" in str(exc_info.value)
        assert _FakeEPClient.submissions == []


class TestScriptActivityDispatch:
    """Exercise the service boundary and stable idempotency behavior."""

    @pytest.mark.asyncio
    async def test_completed_response_returns_ep_result(self) -> None:
        expected = {"output": {"return_code": 0, "stdout": "ok\n"}}
        _FakeEPClient.responses = [
            {"id": "00000000-0000-0000-0000-000000000002", "status": "completed", "result": expected}
        ]

        result = await activity_module.execute_bash_script_activity({"code": "echo ok"}, None, EXECUTION_ID)

        assert result == expected
        assert len(_FakeEPClient.submissions) == 1
        assert UUID(str(_FakeEPClient.submissions[0].command.payload["work_item_id"])) == WORK_ITEM_ID

    @pytest.mark.asyncio
    async def test_engine_control_fields_are_used_but_not_validated_as_parameters(self) -> None:
        _FakeEPClient.responses = [{"status": "completed", "result": {}}]

        await activity_module.execute_bash_script_activity(
            {
                "code": "echo ok",
                ENGINE_TIMEOUT_SECONDS_KEY: 17,
                ENGINE_MAX_OUTPUT_BYTES_KEY: 2048,
            },
            None,
            EXECUTION_ID,
        )

        payload = _FakeEPClient.submissions[0].command.payload
        assert isinstance(payload, dict)
        invocation = payload["invocation"]
        assert isinstance(invocation, dict)
        assert invocation["inputs"] == {"code": "echo ok", "max_output_bytes": 2048}
        assert invocation["timeout_seconds"] == 17

    @pytest.mark.asyncio
    async def test_temporal_retry_reuses_work_item_id(self, mock_activity_context: MagicMock) -> None:
        """Task attempts share an identity without an AO row lookup."""
        _FakeEPClient.responses = [{"status": "completed", "result": {}} for _ in range(2)]
        for attempt in (1, 2):
            mock_activity_context.return_value.attempt = attempt
            await activity_module.execute_bash_script_activity({"code": ":"}, None, EXECUTION_ID)

        assert [UUID(str(message.command.payload["work_item_id"])) for message in _FakeEPClient.submissions] == [
            WORK_ITEM_ID,
            WORK_ITEM_ID,
        ]

    @pytest.mark.asyncio
    async def test_execution_target_profile_is_sent_as_ep_selector(self) -> None:
        """The selected Execution Target profile is routed through WorkExecute selectors."""

    async def test_execution_target_profile_uses_sdk_workload_contract(self) -> None:
        """Route selected targets while submitting the SDK container invocation."""
        _FakeEPClient.responses = [{"id": str(WORK_ITEM_ID), "status": "completed", "result": {"output": {}}}]

        await activity_module.execute_bash_script_activity(
            {
                "code": ":",
                "execution_profile": {
                    "type": "execution_target",
                    "execution_target_id": str(EXECUTION_TARGET_ID),
                },
            },
            None,
            EXECUTION_ID,
        )

        assert len(_FakeEPClient.submissions) == 1
        command_payload = _FakeEPClient.submissions[0].command.payload
        assert isinstance(command_payload, dict)
        assert command_payload["selectors"] == {"_execution_target_id": str(EXECUTION_TARGET_ID)}
        assert command_payload["workload_type"] == "container"
        invocation = command_payload["invocation"]
        assert isinstance(invocation, dict)
        assert invocation == {
            "step_revision_id": "syntara.script-bash.script-bash",
            "inputs": {"code": ":"},
            "credential_bindings": [],
            "timeout_seconds": 300,
        }

    def test_legacy_credential_reference_becomes_ep_binding(self) -> None:
        credential_ref = "00000000-0000-0000-0000-000000000040"

        invocation = activity_module._build_invocation(
            {"credential_id": credential_ref}, "future-step.v1", ("future.plugin.token",)
        )

        assert invocation["inputs"] == {}
        assert invocation["credential_bindings"] == [
            {
                "credential_recipe_id": "future.plugin.token",
                "credential_ref": credential_ref,
            }
        ]

    def test_legacy_credential_cannot_combine_with_explicit_bindings(self) -> None:
        input_config = {
            "credential_id": "00000000-0000-0000-0000-000000000040",
            "credential_bindings": [
                {
                    "credential_recipe_id": "future.plugin.token",
                    "credential_ref": "00000000-0000-0000-0000-000000000041",
                }
            ],
        }

        with pytest.raises(ApplicationError) as exc_info:
            activity_module._build_invocation(input_config, "future-step.v1", ("future.plugin.token",))

        assert exc_info.value.type == "ConfigError"
        assert exc_info.value.non_retryable is True

    @pytest.mark.asyncio
    async def test_legacy_credential_is_resolved_from_registry(self) -> None:
        credential_ref = "00000000-0000-0000-0000-000000000040"
        _FakeEPClient.responses = [{"id": str(WORK_ITEM_ID), "status": "completed", "result": {}}]
        with (
            patch.object(
                activity_module,
                "get_execution_plane_plugin",
                AsyncMock(
                    return_value=SimpleNamespace(
                        name="script-bash",
                        image_reference="quay.io/example/script-bash:test",
                        step_identity="syntara.script-bash.script-bash",
                        manifest=_plugin_manifest(),
                    )
                ),
            ),
            patch.object(
                activity_module,
                "execution_plane_plugin_credential_recipe_ids",
                AsyncMock(return_value=("future.plugin.token",)),
            ),
        ):
            await activity_module.execute_bash_script_activity(
                {"code": ":", "credential_id": credential_ref}, None, EXECUTION_ID
            )

        invocation = _FakeEPClient.submissions[0].command.payload["invocation"]
        assert isinstance(invocation, dict)
        assert invocation["inputs"] == {"code": ":"}
        assert invocation["credential_bindings"] == [
            {
                "credential_recipe_id": "future.plugin.token",
                "credential_ref": credential_ref,
            }
        ]

    @pytest.mark.asyncio
    async def test_pending_response_is_accepted_for_async_completion(self) -> None:
        _FakeEPClient.responses = [{"id": "00000000-0000-0000-0000-000000000002", "status": "pending", "result": None}]
        with patch.object(activity, "raise_complete_async") as complete_async:
            result = await activity_module.execute_bash_script_activity({"code": "sleep 1"}, None, EXECUTION_ID)
        assert result == {}
        complete_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_work_states_are_validated_by_the_sdk_enum(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """New SDK work states remain accepted without duplicating the enum in AO."""

        class ExtendedWorkItemStatus(Enum):
            QUEUED = "queued"

        monkeypatch.setattr(activity_module, "WorkItemStatus", ExtendedWorkItemStatus)
        _FakeEPClient.responses = [{"id": str(WORK_ITEM_ID), "status": "queued", "result": None}]
        with patch.object(activity, "raise_complete_async") as complete_async:
            result = await activity_module.execute_bash_script_activity({"code": "sleep 1"}, None, EXECUTION_ID)

        assert result == {}
        complete_async.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", ["pending", "claimed", "dispatched", "running", "reconciliation_required"])
    @pytest.mark.parametrize("deletion_requested", [False, True])
    async def test_control_request_waits_for_confirmed_completion(
        self, status: str, *, deletion_requested: bool
    ) -> None:
        _FakeEPClient.responses = [
            {
                "id": "00000000-0000-0000-0000-000000000002",
                "status": status,
                "result": None,
                "cancellation_requested": True,
                "deletion_requested": deletion_requested,
            }
        ]
        with patch.object(activity, "raise_complete_async") as complete_async:
            result = await activity_module.execute_bash_script_activity({"code": "sleep 1"}, None, EXECUTION_ID)
        assert result == {}
        complete_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejected_request_is_non_retryable(self) -> None:
        _FakeEPClient.responses = [ExecutionPlaneRejectedError("request rejected")]
        with pytest.raises(ApplicationError) as exc_info:
            await activity_module.execute_bash_script_activity({"code": ":"}, None, EXECUTION_ID)
        assert exc_info.value.type == "ExecutionPlaneRejected"
        assert exc_info.value.non_retryable is True

    @pytest.mark.asyncio
    async def test_service_unavailability_retries_same_work_item_id(self) -> None:
        _FakeEPClient.responses = [
            ExecutionPlaneUnavailableError(),
            {"id": "00000000-0000-0000-0000-000000000002", "status": "completed", "result": {}},
        ]
        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            await activity_module.execute_bash_script_activity({"code": ":"}, None, EXECUTION_ID)
        assert len(_FakeEPClient.submissions) == 2
        assert _FakeEPClient.submissions[1] == _FakeEPClient.submissions[0]


@pytest.mark.asyncio
async def test_conflict_recovers_existing_work_instead_of_failing_activity():
    conflict = ExecutionPlaneRejectedError("already exists")
    conflict.status_code = 409
    expected = {"output": {"stdout": "recovered"}}
    _FakeEPClient.responses = [conflict, {"id": str(WORK_ITEM_ID), "status": "completed", "result": expected}]
    result = await activity_module.execute_bash_script_activity({"code": ":"}, None, EXECUTION_ID)
    assert result == expected
    assert len(_FakeEPClient.submissions) == 1
    assert UUID(str(_FakeEPClient.submissions[0].command.payload["work_item_id"])) == WORK_ITEM_ID
    assert _FakeEPClient.submissions[0].command.command_type == "work.execute"
