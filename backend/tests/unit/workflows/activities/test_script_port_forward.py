"""Local development tunnels preserve gRPC and clean up their subprocesses."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities import script_port_forward as tunnel


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "failure", "cancel", "startup_failure"])
async def test_tunnel_lifecycle(outcome):
    process = MagicMock()
    process.returncode = None
    process.stdout = asyncio.StreamReader()
    process.stdout.feed_data(b"Forwarding from 127.0.0.1:43210 -> 50051\n" if outcome != "startup_failure" else b"")
    process.stdout.feed_eof()
    process.wait = AsyncMock(return_value=0)
    with (
        patch.object(tunnel.asyncio, "create_subprocess_exec", new=AsyncMock(return_value=process)) as spawn,
        patch.object(tunnel.activity, "heartbeat"),
    ):

        async def run() -> None:
            async with tunnel.script_port_forward("https://cluster.example", "scripts", "script-test") as target:
                assert target == "127.0.0.1:43210"
                if outcome == "failure":
                    msg = "gRPC failure"
                    raise RuntimeError(msg)
                if outcome == "cancel":
                    raise asyncio.CancelledError

        if outcome == "success":
            await run()
        else:
            error_type = {
                "failure": RuntimeError,
                "cancel": asyncio.CancelledError,
                "startup_failure": ApplicationError,
            }[outcome]
            with pytest.raises(error_type):
                await run()
        process.terminate.assert_called_once()
        process.wait.assert_awaited_once()
        assert spawn.await_args.args == (
            "oc",
            "port-forward",
            "--server=https://cluster.example",
            "--namespace=scripts",
            "--address=127.0.0.1",
            "pod/script-test",
            ":50051",
        )


@pytest.mark.asyncio
async def test_missing_oc_is_configuration_error():
    with patch.object(tunnel.asyncio, "create_subprocess_exec", new=AsyncMock(side_effect=FileNotFoundError)):
        with pytest.raises(ApplicationError, match="requires oc"):
            async with tunnel.script_port_forward("https://cluster.example", "scripts", "script-test"):
                pytest.fail("Missing oc must not start gRPC")


@pytest.mark.asyncio
async def test_tunnel_kills_process_if_termination_stalls():
    process = MagicMock(returncode=None)
    process.wait = AsyncMock(side_effect=[TimeoutError, 0])
    await tunnel._stop(process)
    process.terminate.assert_called_once()
    process.kill.assert_called_once()


@pytest.mark.asyncio
async def test_startup_timeout_cleans_up_process():
    process = MagicMock(returncode=None)
    process.wait = AsyncMock(return_value=0)
    with (
        patch.object(tunnel.asyncio, "create_subprocess_exec", new=AsyncMock(return_value=process)),
        patch.object(tunnel, "_target", new=AsyncMock(side_effect=TimeoutError)),
    ):
        with pytest.raises(TimeoutError):
            async with tunnel.script_port_forward("https://cluster.example", "scripts", "script-test"):
                pytest.fail("Startup timeout must not start gRPC")
    process.terminate.assert_called_once()
