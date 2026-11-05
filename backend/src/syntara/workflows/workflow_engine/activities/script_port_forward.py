"""Development transport for workers outside the OpenShift pod network."""

import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from temporalio import activity
from temporalio.exceptions import ApplicationError

from .common import HEARTBEAT_STOP_MONITOR

_FORWARDING = re.compile(rb"Forwarding from 127\.0\.0\.1:(\d+) -> 50051")


async def _target(process: asyncio.subprocess.Process) -> str:
    """Read the ephemeral port selected by oc, without reserving a racy local port."""
    if process.stdout is None:
        msg = "Script port-forward has no output stream"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True)
    async with asyncio.timeout(15):
        while True:
            activity.heartbeat({HEARTBEAT_STOP_MONITOR: True})
            try:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=1)
            except TimeoutError:
                continue
            if not line:
                msg = "oc port-forward failed; check local oc login and create permission on pods/portforward"
                raise ApplicationError(msg, type="OpenShiftScriptError", non_retryable=True)
            match = _FORWARDING.search(line)
            if match:
                return f"127.0.0.1:{int(match[1])}"


async def _stop(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()
    except ProcessLookupError:
        await process.wait()


@asynccontextmanager
async def script_port_forward(server: str, namespace: str, pod_name: str) -> AsyncIterator[str]:
    """Tunnel gRPC using local kubeconfig; never send script inputs through oc."""
    try:
        process = await asyncio.create_subprocess_exec(
            "oc",
            "port-forward",
            f"--server={server}",
            f"--namespace={namespace}",
            "--address=127.0.0.1",
            f"pod/{pod_name}",
            ":50051",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        msg = "Development script port-forward requires oc on the worker PATH and an active oc login"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None
    try:
        yield await _target(process)
    finally:
        cleanup = asyncio.create_task(_stop(process))
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            await cleanup
            raise
