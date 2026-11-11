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
@pytest.mark.parametrize("scenario", ["success", "failed", "timeout", "api_error", "cancel", "port_forward"])
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
        if scenario == "cancel":
            raise asyncio.CancelledError
        return httpx.Response(
            200, json={"status": {"phase": "Failed" if scenario == "failed" else "Running", "podIP": "10.0.0.2"}}
        )

    config = OpenShiftConfiguration(
        base_url="https://cluster.example.com",
        namespace="script-step-2523",
        script_image="registry.example/script:test",
    )
    client = httpx.AsyncClient(base_url=config.base_url, transport=httpx.MockTransport(handler))
    forward = MagicMock()
    forward.__aenter__ = AsyncMock(return_value="127.0.0.1:43210")
    forward.__aexit__ = AsyncMock(return_value=False)
    with (
        patch.object(remote, "get_settings") as settings,
        patch.object(remote, "script_port_forward", return_value=forward) as port_forward,
        patch.object(remote, "_connection", new=AsyncMock(return_value=(config, "secret-token"))),
        patch.object(remote.httpx, "AsyncClient", return_value=client),
        patch.object(remote.activity, "info", return_value=MagicMock()),
        patch.object(remote.activity, "heartbeat"),
        patch.object(
            remote,
            "invoke_script",
            new=AsyncMock(
                side_effect=TimeoutError if scenario == "timeout" else None,
                return_value={"return_code": 0, "stdout": "hello", "stderr": ""},
            ),
        ) as invoke,
    ):
        settings.return_value.script_openshift_port_forward = scenario == "port_forward"
        if scenario in {"success", "port_forward"}:
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
    container = pod["spec"]["containers"][0]
    assert "command" not in container
    assert "env" not in container
    if scenario in {"success", "port_forward"}:
        expected = "127.0.0.1:43210" if scenario == "port_forward" else "10.0.0.2:50051"
        assert invoke.await_args.args[0] == expected
        invocation = invoke.await_args.args[1]
        assert invocation.inputs["code"] == "echo hello"
        assert "language" not in invocation.inputs
        assert invocation.step_revision_id == "syntara.script-bash.script-bash"
    if scenario == "port_forward":
        assert port_forward.call_args.args[:2] == (config.base_url, config.namespace)
        forward.__aexit__.assert_awaited_once()
    else:
        port_forward.assert_not_called()


@pytest.mark.asyncio
async def test_no_integration_configured_queries_db():
    """When integration_id is None, DB is queried for a fallback; raises if none found."""

    async def mock_exec(_stmt) -> MagicMock:
        result = MagicMock()
        result.first.return_value = None
        return result

    session_ctx = AsyncMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session_ctx)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    session_ctx.exec = AsyncMock(side_effect=mock_exec)

    with (
        patch.object(remote, "get_settings") as settings,
        patch.object(remote, "AsyncSessionLocal", return_value=session_ctx),
    ):
        settings.return_value.script_openshift_integration_id = None
        with pytest.raises(ApplicationError, match="No enabled OpenShift integration"):
            await remote._connection()
        session_ctx.exec.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(("timeout_seconds", "limit"), [(601, 1024), (1, 1024 * 1024 + 1)])
async def test_unsupported_image_limits_fail_before_pod_creation(timeout_seconds, limit):
    config = OpenShiftConfiguration(
        base_url="https://cluster.example.com", namespace="scripts", script_image="registry.example/script:test"
    )
    with (
        patch.object(remote, "_connection", new=AsyncMock(return_value=(config, "secret"))),
        patch.object(remote.activity, "info", return_value=MagicMock()),
        patch.object(remote.httpx, "AsyncClient") as client,
    ):
        with pytest.raises(ApplicationError, match="supports timeouts"):
            await remote.execute_openshift_script("python", "print(1)", {}, timeout_seconds, limit)
        client.assert_not_called()


@pytest.mark.asyncio
async def test_container_failure_keeps_output_fields_without_fabricating_logs():
    with (
        patch.object(remote.activity, "heartbeat"),
        patch("syntara.workflows.workflow_engine.activities.script_activity.get_settings") as settings,
        patch(
            "syntara.workflows.workflow_engine.activities.script_activity.execute_openshift_script",
            new=AsyncMock(
                side_effect=ApplicationError("Container failed", type="ScriptContainerError", non_retryable=True),
            ),
        ),
    ):
        settings.return_value.script_nodes_enabled = True
        with pytest.raises(ApplicationError) as error:
            await execute_script_activity({"language": "python", "code": "raise Exception()"}, None)
        assert error.value.type == "ScriptContainerError"
        output = error.value.details[0]["output"]
        for field in ("return_code", "stdout", "stderr", "stdout_json"):
            assert output[field] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["python", "bash"])
async def test_language_selects_image_and_contract(language):
    config = OpenShiftConfiguration(
        base_url="https://cluster.example.com",
        namespace="scripts",
        script_image="quay.io/example/syntara-node-script-{language}:test",
    )
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": {"phase": "Running", "podIP": "10.0.0.2"}})

    client = httpx.AsyncClient(base_url=config.base_url, transport=httpx.MockTransport(handler))
    with (
        patch.object(remote, "_connection", new=AsyncMock(return_value=(config, "secret"))),
        patch.object(remote.httpx, "AsyncClient", return_value=client),
        patch.object(remote.activity, "info", return_value=MagicMock()),
        patch.object(remote.activity, "heartbeat"),
        patch.object(remote, "get_settings") as settings,
        patch.object(remote, "invoke_script", new=AsyncMock(return_value={})) as invoke,
    ):
        settings.return_value.script_openshift_port_forward = False
        await remote.execute_openshift_script(language, "code", {"KEY": "value"}, 5, 1000)
    import json

    pod = json.loads(requests[0].content)
    assert pod["spec"]["containers"][0]["image"] == f"quay.io/example/syntara-node-script-{language}:test"
    invocation = invoke.await_args.args[1]
    assert invocation.step_revision_id == f"syntara.script-{language}.script-{language}"
    assert invocation.inputs == {"code": "code", "environment": {"KEY": "value"}, "max_output_bytes": 1000}


@pytest.mark.asyncio
async def test_unsupported_language_fails_before_pod_creation():
    config = OpenShiftConfiguration(base_url="https://cluster.example.com", namespace="scripts", script_image="image")
    with (
        patch.object(remote, "_connection", new=AsyncMock(return_value=(config, "secret"))),
        patch.object(remote.activity, "info", return_value=MagicMock()),
        patch.object(remote.httpx, "AsyncClient") as client,
    ):
        with pytest.raises(ApplicationError, match="Unsupported script language"):
            await remote.execute_openshift_script("ruby", "puts 1", {}, 5, 1000)
        client.assert_not_called()
