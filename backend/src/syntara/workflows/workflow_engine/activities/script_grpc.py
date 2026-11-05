"""Invoke the versioned script container contract without importing image internals."""

import asyncio
from typing import Any

import grpc
from syntara_plugin.runtime import (
    ContainerClient,
    ContainerInvocation,
    ContainerRemoteError,
    ContainerResult,
    FailureCode,
)
from temporalio import activity
from temporalio.exceptions import ApplicationError

from .common import HEARTBEAT_STOP_MONITOR

SCRIPT_STEP_ID = "syntara.script.script"


async def invoke_script(target: str, invocation: ContainerInvocation) -> dict[str, Any]:
    """Use the SDK's health, stream validation and cancellation over a cluster-local channel.

    The image currently serves plaintext HTTP/2. This channel must remain on the
    trusted cluster workload network, never an externally exposed route.
    Synchronous SDK operations run in threads so heartbeats remain responsive.
    """
    channel = grpc.insecure_channel(
        target,
        options=[("grpc.max_receive_message_length", 2 * 1024 * 1024)],
    )
    client = ContainerClient(channel)
    execute_task: asyncio.Task[Any] | None = None
    cancel_requested = False
    try:
        await _wait_for_health(client)

        execute_task = asyncio.create_task(asyncio.to_thread(_execute_stream, client, invocation))
        async with asyncio.timeout(invocation.timeout_seconds):
            while not execute_task.done():
                activity.heartbeat({HEARTBEAT_STOP_MONITOR: True})
                await asyncio.wait({execute_task}, timeout=1)
            result = execute_task.result()
        return _script_output(result)
    except (TimeoutError, asyncio.CancelledError):
        cancel_requested = True
        raise
    except ContainerRemoteError as error:
        if error.code == FailureCode.TIMEOUT:
            cancel_requested = True
            raise TimeoutError from None
        # Failure events contain no script output. Never fabricate an exit code or logs.
        msg = f"Script container failed ({error.code.value})"
        raise ApplicationError(msg, type="ScriptContainerError", non_retryable=not error.retryable) from None
    finally:
        if execute_task is not None and (cancel_requested or not execute_task.done()):
            invocation.cancellation.set()
            try:
                await asyncio.shield(asyncio.to_thread(client.cancel, invocation.invocation_id, timeout_seconds=5))
            except (ContainerRemoteError, asyncio.CancelledError):
                activity.logger.warning("Script gRPC cancellation was not acknowledged")
        await asyncio.to_thread(channel.close)
        if execute_task is not None:
            await asyncio.gather(execute_task, return_exceptions=True)


async def _wait_for_health(client: ContainerClient) -> None:
    """Wait for startup and verify the required ABI and step identity."""
    async with asyncio.timeout(30):
        while True:
            activity.heartbeat({HEARTBEAT_STOP_MONITOR: True})
            try:
                revisions = await asyncio.to_thread(client.health, timeout_seconds=2)
                break
            except ContainerRemoteError as error:
                if error.source != "transport" or not error.retryable:
                    raise
                await asyncio.sleep(1)
    if SCRIPT_STEP_ID not in revisions:
        msg = "Script container does not advertise the required step identity"
        raise ApplicationError(msg, type="ScriptContainerProtocolError", non_retryable=True)


def _script_output(result: ContainerResult) -> dict[str, Any]:
    """Validate the script-specific business output after SDK envelope validation."""
    if result.output is None or result.object_reference:
        msg = "Script container must return inline script output"
        raise ApplicationError(msg, type="ScriptContainerProtocolError", non_retryable=True)
    output = dict(result.output)
    if (
        not isinstance(output.get("return_code"), int)
        or isinstance(output.get("return_code"), bool)
        or not all(isinstance(output.get(key), str) for key in ("stdout", "stderr"))
    ):
        msg = "Invalid script container output"
        raise ApplicationError(msg, type="ScriptContainerProtocolError", non_retryable=True)
    if result.status_code and output["return_code"] == 0:
        msg = "Script container returned inconsistent failure status"
        raise ApplicationError(msg, type="ScriptContainerProtocolError", non_retryable=True)
    return output


def _execute_stream(client: ContainerClient, invocation: ContainerInvocation) -> ContainerResult:
    """Consume the whole stream so duplicate or missing terminal events are rejected."""
    result = None
    for event in client.stream(invocation):
        if isinstance(event, ContainerResult):
            result = event
    if result is None:
        msg = "Script container did not return a result"
        raise ApplicationError(msg, type="ScriptContainerProtocolError", non_retryable=True)
    return result
