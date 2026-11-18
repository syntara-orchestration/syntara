"""Unit tests for AO's authenticated Execution Plane dispatch activity."""

from collections.abc import Generator
from types import SimpleNamespace
from typing import ClassVar, Self
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid5

import pytest
from execution_plane_client.commands.results import TransportReceipt
from execution_plane_client.protocol import MessageEnvelope, ResourceReference
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.core.config.base import get_settings
from syntara.execution_plane.client import ExecutionPlaneRejectedError, ExecutionPlaneUnavailableError
from syntara.workflow_runtime.engines.temporal.activities.ep import ep_dispatch_activity as activity_module
from syntara.workflow_runtime.engines.temporal.constants import ENGINE_MAX_OUTPUT_BYTES_KEY, ENGINE_TIMEOUT_SECONDS_KEY

ACTIVITY_INFO_PATH = "syntara.workflow_runtime.engines.temporal.activities.ep.ep_dispatch_activity.activity.info"
EXECUTION_ID = "00000000-0000-0000-0000-000000000010"
WORK_ITEM_ID = uuid5(UUID(EXECUTION_ID), "unit-activity")
EXECUTION_TARGET_ID = UUID("00000000-0000-0000-0000-000000000030")


class _FakeEPClient:
    """Accept commands; any status lookup is a dispatch regression."""

    responses: ClassVar[list[TransportReceipt | Exception]] = []
    submissions: ClassVar[list[MessageEnvelope]] = []
    timeouts: ClassVar[list[float | None]] = []

    def __init__(self, *, timeout: float | None = None) -> None:
        self.timeout = timeout
        self.timeouts.append(timeout)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def submit_command(self, message: MessageEnvelope) -> TransportReceipt:
        self.submissions.append(message)
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        return TransportReceipt(
            message_id=message.message_id,
            resource=ResourceReference(
                kind="work_item", resource_id=UUID(str(message.command.payload["work_item_id"]))
            ),
        )

    async def get_work_item(self, *, work_item_id: UUID) -> dict[str, object]:
        message = "Dispatch must not fetch work status or results"
        raise AssertionError(message)


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
    settings = get_settings()
    original_ep_url = settings.ep_api_url
    object.__setattr__(settings, "ep_api_url", "https://ep.test")
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
        _FakeEPClient.timeouts = []
        try:
            yield activity_info
        finally:
            object.__setattr__(settings, "ep_api_url", original_ep_url)


class CompletionDeferred(BaseException):
    """Mirror Temporal completion deferral without completing the activity."""


@pytest.fixture(autouse=True)
def mock_async_completion() -> Generator[MagicMock, None, None]:
    with patch.object(activity, "raise_complete_async", side_effect=CompletionDeferred) as complete_async:
        yield complete_async


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
    async def test_missing_ep_url_is_non_retryable(self) -> None:
        with (
            patch.object(activity_module, "get_settings", return_value=SimpleNamespace(ep_api_url="")),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await activity_module._dispatch_to_ep({"code": ":"}, None, UUID(EXECUTION_ID), None, "script-bash")
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
    @pytest.mark.parametrize("activity_name", ["execute_bash_script_activity", "execute_python_script_activity"])
    @pytest.mark.parametrize("duplicate", [False, True])
    async def test_acceptance_waits_for_callback_without_reading_work(
        self, activity_name: str, mock_async_completion: MagicMock, *, duplicate: bool
    ) -> None:
        if duplicate:
            _FakeEPClient.responses = [ExecutionPlaneRejectedError("already exists", status_code=409)]
        with pytest.raises(CompletionDeferred):
            await getattr(activity_module, activity_name)({"code": "echo ok"}, None, EXECUTION_ID)
        mock_async_completion.assert_called_once()
        assert len(_FakeEPClient.submissions) == 1
        assert UUID(str(_FakeEPClient.submissions[0].command.payload["work_item_id"])) == WORK_ITEM_ID

    @pytest.mark.asyncio
    async def test_engine_control_fields_are_used_but_not_validated_as_parameters(self) -> None:
        with pytest.raises(CompletionDeferred):
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
    @pytest.mark.parametrize("workload_timeout", [1, 600])
    async def test_request_timeout_is_independent_of_workload_timeout(self, workload_timeout: int) -> None:
        with patch.object(
            activity_module,
            "get_settings",
            return_value=SimpleNamespace(ep_request_timeout_seconds=13, ep_api_url="https://ep.test"),
        ):
            await activity_module._dispatch_to_ep(
                {"code": ":", ENGINE_TIMEOUT_SECONDS_KEY: workload_timeout},
                None,
                UUID(EXECUTION_ID),
                None,
                "script-bash",
            )
        assert _FakeEPClient.timeouts == [13]
        payload = _FakeEPClient.submissions[0].command.payload
        invocation = payload["invocation"]
        assert isinstance(invocation, dict)
        assert invocation["timeout_seconds"] == workload_timeout

    @pytest.mark.asyncio
    async def test_temporal_retry_reuses_work_item_id(self, mock_activity_context: MagicMock) -> None:
        """Task attempts share an identity without an AO row lookup."""
        for attempt in (1, 2):
            mock_activity_context.return_value.attempt = attempt
            with pytest.raises(CompletionDeferred):
                await activity_module.execute_bash_script_activity({"code": ":"}, None, EXECUTION_ID)

        assert [UUID(str(message.command.payload["work_item_id"])) for message in _FakeEPClient.submissions] == [
            WORK_ITEM_ID,
            WORK_ITEM_ID,
        ]

    @pytest.mark.asyncio
    async def test_execution_target_profile_uses_sdk_workload_contract(self) -> None:
        """Route selected targets while submitting the SDK container invocation."""
        with pytest.raises(CompletionDeferred):
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
            with pytest.raises(CompletionDeferred):
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
    @pytest.mark.parametrize("resource", [None, ResourceReference(kind="work_item", resource_id=UUID(EXECUTION_ID))])
    async def test_invalid_receipt_is_non_retryable(
        self, resource: ResourceReference | None, mock_async_completion: MagicMock
    ) -> None:
        _FakeEPClient.responses = [TransportReceipt(message_id=UUID(EXECUTION_ID), resource=resource)]
        with pytest.raises(ApplicationError) as exc_info:
            await activity_module.execute_bash_script_activity({"code": ":"}, None, EXECUTION_ID)
        assert exc_info.value.type == "ExecutionPlaneRejected"
        assert exc_info.value.non_retryable is True
        mock_async_completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejected_request_is_non_retryable(self) -> None:
        _FakeEPClient.responses = [ExecutionPlaneRejectedError("request rejected")]
        with pytest.raises(ApplicationError) as exc_info:
            await activity_module.execute_bash_script_activity({"code": ":"}, None, EXECUTION_ID)
        assert exc_info.value.type == "ExecutionPlaneRejected"
        assert exc_info.value.non_retryable is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("plugin_name", ["script-python", "script-bash"])
    async def test_service_unavailability_propagates_without_internal_retry(self, plugin_name: str) -> None:
        unavailable = ExecutionPlaneUnavailableError()
        with (
            patch.object(_FakeEPClient, "submit_command", new_callable=AsyncMock, side_effect=unavailable) as request,
            pytest.raises(ApplicationError) as exc_info,
        ):
            await activity_module._dispatch_to_ep({"code": ":"}, None, UUID(EXECUTION_ID), None, plugin_name)

        request.assert_awaited_once()
        assert exc_info.value.type == "ExecutionPlaneUnavailable"
        assert exc_info.value.non_retryable is False
        assert exc_info.value.__cause__ is unavailable

    @pytest.mark.asyncio
    async def test_temporal_retry_recovers_accepted_work_after_lost_response(
        self, mock_activity_context: MagicMock, mock_async_completion: MagicMock
    ) -> None:
        _FakeEPClient.responses = [
            ExecutionPlaneUnavailableError(),
            ExecutionPlaneRejectedError("already exists", status_code=409),
        ]
        with pytest.raises(ApplicationError) as exc_info:
            await activity_module.execute_bash_script_activity({"code": ":"}, None, EXECUTION_ID)
        assert exc_info.value.non_retryable is False
        assert len(_FakeEPClient.submissions) == 1

        mock_async_completion.assert_not_called()
        mock_activity_context.return_value.attempt = 2
        with pytest.raises(CompletionDeferred):
            await activity_module.execute_bash_script_activity({"code": ":"}, None, EXECUTION_ID)

        mock_async_completion.assert_called_once()
        assert len(_FakeEPClient.submissions) == 2
        assert _FakeEPClient.submissions[0].command.payload == _FakeEPClient.submissions[1].command.payload
        assert UUID(str(_FakeEPClient.submissions[1].command.payload["work_item_id"])) == WORK_ITEM_ID


class TestScriptNodesGate:
    """Keep the AO feature gate ahead of EP dispatch."""

    @pytest.mark.asyncio
    async def test_disabled_raises_application_error(self) -> None:
        settings = get_settings()
        original = settings.script_nodes_enabled
        object.__setattr__(settings, "script_nodes_enabled", False)
        try:
            with pytest.raises(ApplicationError) as exc_info:
                await activity_module.execute_bash_script_activity({"code": "echo hi"}, None, EXECUTION_ID)
            assert exc_info.value.non_retryable is True
            assert exc_info.value.type == "ScriptNodeDisabled"
            assert _FakeEPClient.submissions == []
        finally:
            object.__setattr__(settings, "script_nodes_enabled", original)
