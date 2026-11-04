"""OpenShift execution boundary and script output compatibility."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from temporalio.exceptions import ApplicationError

from syntara.integrations.models.integration_configuration import OpenShiftConfiguration
from syntara.workflows.workflow_engine.activities import openshift_script as remote
from syntara.workflows.workflow_engine.activities.script_activity import execute_script_activity


@pytest.mark.asyncio
@pytest.mark.parametrize("return_code", [0, 7])
async def test_activity_dispatch_preserves_outputs(return_code):
    result = {"return_code": return_code, "stdout": '{"x": 1}\n', "stderr": "failure" if return_code else ""}
    with (
        patch("syntara.workflows.workflow_engine.activities.script_activity.get_settings") as settings,
        patch.object(remote.activity, "heartbeat"),
        patch(
            "syntara.workflows.workflow_engine.activities.script_activity.execute_openshift_script",
            new=AsyncMock(return_value=result),
        ) as execute,
        patch("asyncio.create_subprocess_exec", side_effect=AssertionError("worker executed user code")),
    ):
        settings.return_value.script_nodes_enabled = True
        if return_code:
            with pytest.raises(ApplicationError) as error:
                await execute_script_activity({"language": "python", "code": "print(1)"}, None)
            assert error.value.type == "ScriptExecutionError"
            output = error.value.details[0]["output"]
        else:
            output = (await execute_script_activity({"language": "python", "code": "print(1)"}, None))["output"]
            assert output["stdout_json"] == {"x": 1}
        assert output["return_code"] == return_code
        assert output["stdout"] == result["stdout"]
        assert output["stderr"] == result["stderr"]
        execute.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["success", "failed", "timeout", "api_error", "cancel", "invalid_result"])
async def test_remote_lifecycle(scenario):
    import asyncio

    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            if scenario == "api_error":
                return httpx.Response(403)
            return httpx.Response(201, json={})
        if request.method == "DELETE":
            return httpx.Response(200, json={})
        if request.url.path.endswith("/log"):
            if scenario == "invalid_result":
                return httpx.Response(200, json=["unexpected result"])
            return httpx.Response(
                200,
                json={"timed_out": True}
                if scenario == "timeout"
                else {"return_code": 0, "stdout": "hello", "stderr": "", "stdout_json": None},
            )
        if scenario == "cancel":
            raise asyncio.CancelledError
        return httpx.Response(200, json={"status": {"phase": "Failed" if scenario == "failed" else "Succeeded"}})

    config = OpenShiftConfiguration(base_url="https://cluster.example.com", namespace="script-step-2523")
    client = httpx.AsyncClient(base_url=config.base_url, transport=httpx.MockTransport(handler))
    with (
        patch.object(remote, "_connection", new=AsyncMock(return_value=(config, "secret-token"))),
        patch.object(remote.httpx, "AsyncClient", return_value=client),
        patch.object(remote.activity, "info", return_value=MagicMock()),
        patch.object(remote.activity, "heartbeat"),
    ):
        if scenario == "success":
            result = await remote.execute_openshift_script("bash", "echo hello", {}, 5, 1000)
            assert result["stdout"] == "hello"
        else:
            exception = {"timeout": TimeoutError, "cancel": asyncio.CancelledError}.get(scenario, ApplicationError)
            with pytest.raises(exception):
                await remote.execute_openshift_script("bash", "echo hello", {}, 5, 1000)
    assert requests[-1].method == "DELETE"
    import json

    pod = json.loads(requests[0].content)
    assert pod["spec"]["automountServiceAccountToken"] is False
    assert "secret-token" not in requests[0].content.decode()
    assert pod["spec"]["restartPolicy"] == "Never"


@pytest.mark.asyncio
async def test_missing_default_integration_fails_before_connection():
    with patch.object(remote, "get_settings") as settings, patch.object(remote, "AsyncSessionLocal") as sessions:
        settings.return_value.script_openshift_integration_id = None
        with pytest.raises(ApplicationError, match="APP_SCRIPT_OPENSHIFT_INTEGRATION_ID"):
            await remote._connection()
        sessions.assert_not_called()
