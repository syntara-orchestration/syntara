"""Small test double for the EP HTTP contract; never imported by application code."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
from typing import Any, Self
from uuid import NAMESPACE_URL, uuid5


class FakeExecutionPlaneHttpClient:
    """Return completed EP responses while running representative scripts in tests."""

    def __init__(self, *, timeout: float | None = None) -> None:
        """Accept the production client's request timeout configuration."""
        self.timeout = timeout

    async def __aenter__(self) -> Self:
        """Mirror the production client's async context-manager contract."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Close no resources because the test transport is in-process."""

    async def submit_work_item(
        self,
        *,
        project_id: object,
        request_id: str,
        work_correlation_id: object,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the submitted fixture payload and return the public EP response shape."""
        result, status = await execute_fixture_script(payload)
        return {
            "id": str(uuid5(NAMESPACE_URL, request_id)),
            "project_id": str(project_id),
            "request_id": request_id,
            "work_correlation_id": str(work_correlation_id),
            "status": status,
            "result": result,
        }


async def execute_fixture_script(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Run a test script as a local stand-in for a separately deployed EP service."""
    invocation = payload["invocation"]
    input_config = invocation["inputs"]
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
    timeout = max(1, int(input_config.get("_engine_timeout_seconds", 300)))
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
        "stdout_json": stdout_json,
    }
    output_config = payload.get("output_config")
    if output_config is not None:
        output = {key: output[key] for key in output_config if key in output}
    return {"output": output}, "completed"
