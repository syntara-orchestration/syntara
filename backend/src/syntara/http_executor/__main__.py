"""JSON Lines command loop for the standalone HTTP executor."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from .executor import CommandError, execute_command, parse_command

_MAX_INPUT_LINE_BYTES = 1_048_576


def _invalid_environment(name: str) -> RuntimeError:
    return RuntimeError(f"{name} must be a positive integer")


def _positive_environment_int(name: str, default: int) -> int:
    value = os.environ.get(name, str(default))
    try:
        parsed = int(value)
    except ValueError as exc:
        raise _invalid_environment(name) from exc
    if parsed <= 0:
        raise _invalid_environment(name)
    return parsed


def _result_for_error(error: CommandError) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": False, "error_type": error.error_type, "message": str(error)}
    if error.status_code is not None:
        result["status_code"] = error.status_code
    return result


async def _run_line(line: bytes, *, max_timeout_seconds: int, max_response_bytes: int) -> dict[str, Any]:
    if len(line) > _MAX_INPUT_LINE_BYTES:
        return _result_for_error(CommandError("ValidationError", "command exceeds the 1 MiB input limit"))
    try:
        command = parse_command(json.loads(line), max_timeout_seconds=max_timeout_seconds)
        return await execute_command(command, max_response_bytes=max_response_bytes)
    except json.JSONDecodeError:
        return _result_for_error(CommandError("ValidationError", "command must be valid JSON"))
    except CommandError as exc:
        return _result_for_error(exc)


async def main() -> None:
    """Read and process one JSON object per stdin line."""
    max_timeout_seconds = _positive_environment_int("HTTP_EXECUTOR_MAX_TIMEOUT_SECONDS", 60)
    max_response_bytes = _positive_environment_int("HTTP_EXECUTOR_MAX_RESPONSE_BYTES", 1_048_576)
    for line in sys.stdin.buffer:
        if not line.strip():
            continue
        result = await _run_line(
            line,
            max_timeout_seconds=max_timeout_seconds,
            max_response_bytes=max_response_bytes,
        )
        sys.stdout.write(json.dumps(result, separators=(",", ":"), allow_nan=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(main())
