"""Small test double for the EP HTTP contract; never imported by application code."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
from typing import TYPE_CHECKING, Any, Self

from execution_plane_client.commands.results import TransportReceipt
from execution_plane_client.commands.work import WorkExecute
from execution_plane_client.protocol import MessageEnvelope, ResourceReference

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from uuid import UUID


class FakeExecutionPlaneHttpClient:
    """Accept commands, then deliver script results through Temporal async completion."""

    def __init__(
        self,
        *,
        on_completion: Callable[[UUID, str, dict[str, Any]], Coroutine[Any, Any, None]],
        completion_tasks: list[asyncio.Task[None]],
        timeout: float | None = None,
    ) -> None:
        """Use the fixture's completion handler and retain background completion tasks."""
        self.timeout = timeout
        self.on_completion = on_completion
        self.completion_tasks = completion_tasks

    async def __aenter__(self) -> Self:
        """Mirror the production client's async context-manager contract."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Close no resources because the test transport is in-process."""

    async def submit_command(self, message: MessageEnvelope) -> TransportReceipt:
        """Return acceptance without work state; complete the activity independently."""
        payload = WorkExecute.model_validate(message.command.payload)

        async def complete() -> None:
            result, status = await execute_fixture_script(payload.model_dump(mode="json"))
            await self.on_completion(payload.work_item_id, status, result)

        self.completion_tasks.append(asyncio.create_task(complete()))
        return TransportReceipt(
            message_id=message.message_id,
            resource=ResourceReference(kind="work_item", resource_id=payload.work_item_id),
        )


async def execute_fixture_script(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Run a test script as a local stand-in for a separately deployed EP service."""
    if "invocation" in payload:
        invocation = payload["invocation"]
        input_config = invocation["inputs"]
        language = "bash" if invocation.get("step_revision_id", "").endswith(".script-bash") else "python"
    else:
        input_config = payload["input_config"]
        language = input_config.get("language", "python")
    code = input_config["code"]
    command = ["bash", "-c", code] if language == "bash" else [sys.executable, "-c", code]
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"HOME", "LANG", "LC_ALL", "LC_CTYPE", "PATH", "SHELL", "TEMP", "TERM", "TMPDIR", "TZ", "USER"}
    }
    environment.update({key: str(value) for key, value in (input_config.get("environment") or {}).items()})
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=environment,
    )
    timeout = max(
        1, int(payload.get("invocation", {}).get("timeout_seconds", input_config.get("_engine_timeout_seconds", 300)))
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        return {"error": "Script execution timed out", "error_type": "TimeoutError"}, "failed"
    stdout = stdout_bytes[: 1024 * 1024].decode("utf-8", errors="replace")
    stderr = stderr_bytes[: 1024 * 1024].decode("utf-8", errors="replace")
    if process.returncode:
        return {
            "error": f"Script failed with exit code {process.returncode}",
            "error_type": "ScriptExecutionError",
            "exit_code": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }, "failed"

    stdout_json: Any = None
    if language == "python" and stdout.strip():
        try:
            stdout_json = json.loads(stdout)
        except json.JSONDecodeError:
            with contextlib.suppress(json.JSONDecodeError):
                stdout_json = json.loads([line for line in stdout.splitlines() if line.strip()][-1])
    output = {
        "return_code": process.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }
    if language == "python":
        output["stdout_json"] = stdout_json
    output_config = payload.get("output_config")
    if output_config is not None:
        output = {key: output[key] for key in output_config if key in output}
    return {"output": output}, "completed"
