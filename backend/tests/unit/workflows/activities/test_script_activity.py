"""Unit tests for AO's authenticated Execution Plane dispatch activity."""

from collections.abc import Generator
from typing import ClassVar, Self
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid5

import pytest
from execution_plane_client.protocol import MessageEnvelope, ResourceReference, TransportReceipt
from temporalio.exceptions import ApplicationError

from syntara.core.config.base import get_settings
from syntara.execution_plane.client import ExecutionPlaneRejectedError, ExecutionPlaneUnavailableError
from syntara.workflows.workflow_engine.activities.ep import ep_dispatch_activity as activity_module

ACTIVITY_INFO_PATH = "syntara.workflows.workflow_engine.activities.ep.ep_dispatch_activity.activity.info"
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
            message_id=message.message_id, resource=ResourceReference(kind="work_item", resource_id=message.command_id)
        )

    async def get_work_item(self, *, work_item_id: UUID) -> dict[str, object]:
        assert work_item_id == WORK_ITEM_ID
        response = self.responses.pop(0)
        assert isinstance(response, dict)
        return response


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
            {"language": "bash", "code": ""},
            {"language": "ruby", "code": "puts 'hello'"},
            {"language": "bash"},
            {"code": "echo hello"},
        ],
    )
    async def test_invalid_config_is_non_retryable(self, input_config: dict[str, str]) -> None:
        """Invalid script fields fail before AO contacts the remote service."""
        with pytest.raises(ApplicationError) as exc_info:
            await activity_module.execute_script_activity(input_config, None, EXECUTION_ID)
        assert exc_info.value.type == "ConfigError"
        assert exc_info.value.non_retryable is True
        assert _FakeEPClient.submissions == []

    @pytest.mark.asyncio
    async def test_invalid_execution_id_is_non_retryable(self) -> None:
        with pytest.raises(ApplicationError) as exc_info:
            await activity_module.execute_script_activity({"language": "bash", "code": ":"}, None, "invalid")
        assert exc_info.value.type == "ConfigError"
        assert _FakeEPClient.submissions == []


class TestScriptActivityDispatch:
    """Exercise the service boundary and stable idempotency behavior."""

    @pytest.mark.asyncio
    async def test_completed_response_returns_ep_result(self) -> None:
        expected = {"output": {"return_code": 0, "stdout": "ok\n"}}
        _FakeEPClient.responses = [
            {"id": "00000000-0000-0000-0000-000000000002", "status": "completed", "result": expected}
        ]

        result = await activity_module.execute_script_activity(
            {"language": "bash", "code": "echo ok"}, None, EXECUTION_ID
        )

        assert result == expected
        assert len(_FakeEPClient.submissions) == 1
        assert _FakeEPClient.submissions[0].command_id == WORK_ITEM_ID

    @pytest.mark.asyncio
    async def test_temporal_retry_reuses_work_item_id(self, mock_activity_context: MagicMock) -> None:
        """Task attempts share an identity without an AO row lookup."""
        _FakeEPClient.responses = [{"status": "completed", "result": {}} for _ in range(2)]
        for attempt in (1, 2):
            mock_activity_context.return_value.attempt = attempt
            await activity_module.execute_script_activity({"language": "bash", "code": ":"}, None, EXECUTION_ID)

        assert [message.command_id for message in _FakeEPClient.submissions] == [WORK_ITEM_ID, WORK_ITEM_ID]

    @pytest.mark.asyncio
    async def test_execution_target_profile_is_sent_as_ep_selector(self) -> None:
        """The selected Execution Target profile is routed through WorkExecute selectors."""

    async def test_execution_target_profile_uses_sdk_workload_contract(self) -> None:
        """Route selected targets while submitting the SDK container invocation."""
        _FakeEPClient.responses = [{"id": str(WORK_ITEM_ID), "status": "completed", "result": {"output": {}}}]

        await activity_module.execute_script_activity(
            {
                "language": "bash",
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
            "workflow_run_id": "unit-run",
            "step_revision_id": "script.v1",
            "inputs": {"language": "bash", "code": ":"},
            "runtime_context": {},
            "timeout_seconds": 300,
        }

    @pytest.mark.asyncio
    async def test_pending_response_is_accepted_for_async_completion(self) -> None:
        _FakeEPClient.responses = [{"id": "00000000-0000-0000-0000-000000000002", "status": "pending", "result": None}]
        with patch.object(activity_module.activity, "raise_complete_async") as complete_async:
            result = await activity_module.execute_script_activity(
                {"language": "bash", "code": "sleep 1"}, None, EXECUTION_ID
            )
        assert result == {}
        complete_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejected_request_is_non_retryable(self) -> None:
        _FakeEPClient.responses = [ExecutionPlaneRejectedError("request rejected")]
        with pytest.raises(ApplicationError) as exc_info:
            await activity_module.execute_script_activity({"language": "bash", "code": ":"}, None, EXECUTION_ID)
        assert exc_info.value.type == "ExecutionPlaneRejected"
        assert exc_info.value.non_retryable is True

    @pytest.mark.asyncio
    async def test_service_unavailability_retries_same_work_item_id(self) -> None:
        _FakeEPClient.responses = [
            ExecutionPlaneUnavailableError(),
            {"id": "00000000-0000-0000-0000-000000000002", "status": "completed", "result": {}},
        ]
        with patch.object(activity_module.asyncio, "sleep", new_callable=AsyncMock):
            await activity_module.execute_script_activity({"language": "bash", "code": ":"}, None, EXECUTION_ID)
        assert len(_FakeEPClient.submissions) == 2
        assert _FakeEPClient.submissions[1] == _FakeEPClient.submissions[0]


class TestScriptNodesGate:
    """Keep the AO feature gate ahead of EP dispatch."""

    @pytest.mark.asyncio
    async def test_disabled_raises_application_error(self) -> None:
        settings = get_settings()
        original = settings.script_nodes_enabled
        object.__setattr__(settings, "script_nodes_enabled", False)
        try:
            with pytest.raises(ApplicationError) as exc_info:
                await activity_module.execute_script_activity(
                    {"language": "bash", "code": "echo hi"}, None, EXECUTION_ID
                )
            assert exc_info.value.non_retryable is True
            assert exc_info.value.type == "ScriptNodeDisabled"
            assert _FakeEPClient.submissions == []
        finally:
            object.__setattr__(settings, "script_nodes_enabled", original)


@pytest.mark.asyncio
async def test_conflict_recovers_existing_work_instead_of_failing_activity():
    conflict = ExecutionPlaneRejectedError("already exists")
    conflict.status_code = 409
    expected = {"output": {"stdout": "recovered"}}
    _FakeEPClient.responses = [conflict, {"id": str(WORK_ITEM_ID), "status": "completed", "result": expected}]
    result = await activity_module.execute_script_activity({"language": "bash", "code": ":"}, None, EXECUTION_ID)
    assert result == expected
    assert len(_FakeEPClient.submissions) == 1
    assert _FakeEPClient.submissions[0].command_id == WORK_ITEM_ID
    assert _FakeEPClient.submissions[0].command.command_type == "work.execute"
