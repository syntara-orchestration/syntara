"""Unit tests for AO's authenticated Execution Plane dispatch activity."""

from collections.abc import Generator
from typing import ClassVar, Self
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from temporalio.exceptions import ApplicationError

from syntara.core.config.base import get_settings
from syntara.execution_plane.client import ExecutionPlaneRejectedError, ExecutionPlaneUnavailableError
from syntara.workflows.workflow_engine.activities.ep import ep_dispatch_activity as activity_module

ACTIVITY_INFO_PATH = "syntara.workflows.workflow_engine.activities.ep.ep_dispatch_activity.activity.info"
EXECUTION_ID = "00000000-0000-0000-0000-000000000010"
WORK_ITEM_ID = UUID("00000000-0000-0000-0000-000000000020")


class _FakeEPClient:
    """Minimal async transport double for an already-completed work item."""

    responses: ClassVar[list[dict[str, object] | Exception]] = []
    submissions: ClassVar[list[dict[str, object]]] = []

    def __init__(self, *, timeout: float | None = None) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def submit_work_item(self, **request: object) -> dict[str, object]:
        self.submissions.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def _mock_activity_context() -> Generator[MagicMock, None, None]:
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
        patch.object(
            activity_module,
            "_lookup_activity_execution_id",
            new_callable=lambda: AsyncMock(return_value=WORK_ITEM_ID),
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
        assert _FakeEPClient.submissions[0]["item_id"] == WORK_ITEM_ID

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
        first_id = _FakeEPClient.submissions[0]["item_id"]
        assert _FakeEPClient.submissions[1]["item_id"] == first_id


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
