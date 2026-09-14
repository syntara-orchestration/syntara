"""Script execution utilities for the Execution Plane worker.

Everything a TE worker needs to run a script and produce a Temporal-compatible
activity result. No dependencies on the main syntara package.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import structlog

logger = structlog.stdlib.get_logger(__name__)

# --- Constants ---

SAFE_ENV_ALLOWLIST: frozenset[str] = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LOGNAME",
        "PATH",
        "SHELL",
        "TEMP",
        "TERM",
        "TMP",
        "TMPDIR",
        "TZ",
        "USER",
    }
)

ENGINE_TIMEOUT_SECONDS_KEY = "_engine_timeout_seconds"
ENGINE_MAX_OUTPUT_BYTES_KEY = "_engine_max_output_bytes"
DEFAULT_MAX_OUTPUT_BYTES = 1_048_576  # 1 MB
# Temporal's server-side limit.blobSize.error (must match development-sql.yaml).
_TEMPORAL_BLOB_SIZE_ERROR = 2_097_152  # 2 MB
# 10% headroom covers JSON escaping expansion and protobuf envelope overhead.
TEMPORAL_PAYLOAD_MAX_BYTES = int(_TEMPORAL_BLOB_SIZE_ERROR * 0.9)

# These match the Syntara settings defaults; override via environment if needed.
SCRIPT_CLEANUP_TERMINATE_TIMEOUT = 1.0
SCRIPT_CLEANUP_KILL_TIMEOUT = 0.5
MAX_ENV_VAR_LENGTH = 32768  # 32 KB


# --- Errors ---


class ScriptExecutionError(Exception):
    """Raised when script execution fails."""

    exit_code: int
    stdout: str
    stderr: str

    def __init__(self, message: str, exit_code: int, stdout: str, stderr: str) -> None:
        """Initialize with error message and script output."""
        super().__init__(message)
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


# --- Subprocess utilities ---


def _raise_script_error(return_code: int, stdout: str, stderr: str) -> None:
    """Raise ScriptExecutionError with formatted message."""
    error_msg = f"Script failed with exit code {return_code}"
    if stderr:
        error_msg += f": {stderr.strip()}"
    raise ScriptExecutionError(
        message=error_msg,
        exit_code=return_code,
        stdout=stdout,
        stderr=stderr,
    )


async def _cleanup_process(process: asyncio.subprocess.Process) -> None:
    """Ensure subprocess has terminated and all streams are closed."""
    if process.returncode is None:
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=SCRIPT_CLEANUP_TERMINATE_TIMEOUT)
            logger.debug("Process terminated gracefully")
        except TimeoutError:
            logger.warning("Process didn't terminate gracefully, force killing")
            try:
                process.kill()
                await asyncio.wait_for(process.wait(), timeout=SCRIPT_CLEANUP_KILL_TIMEOUT)
                logger.info("Process force killed successfully")
            except TimeoutError:
                logger.warning("Process didn't die after kill signal, may be zombie")
            except ProcessLookupError:
                logger.debug("Process already terminated after kill attempt")
        except ProcessLookupError:
            logger.debug("Process already terminated before cleanup")

    if process.stdin and not process.stdin.is_closing():
        process.stdin.close()
        with contextlib.suppress(Exception):
            await process.stdin.wait_closed()

    # Close subprocess transport to prevent delayed cleanup warnings after event loop close.
    # Python's asyncio has no public API for this; _transport is the only handle.
    if hasattr(process, "_transport") and process._transport is not None:  # noqa: SLF001
        with contextlib.suppress(Exception):
            process._transport.close()  # noqa: SLF001


def _get_cgroup_memory_limit() -> int | None:
    """Read the container's cgroup memory limit, returning None if unavailable."""
    for cgroup_path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            value = Path(cgroup_path).read_text().strip()
            if value == "max":
                return None
            return int(value)
        except (ValueError, OSError):
            continue
    return None


def _prepend_memory_limit(code: str, language: str, max_bytes: int) -> str:
    """Prepend a memory limit preamble to the script code."""
    if language == "python":
        return f"import resource as __r; __r.setrlimit(__r.RLIMIT_AS, ({max_bytes}, {max_bytes}))\n{code}"
    return f"ulimit -v $(({max_bytes} / 1024))\n{code}"


async def _read_stream_limited(
    stream: asyncio.StreamReader,
    max_bytes: int,
) -> tuple[bytes, bool]:
    """Read from an asyncio stream up to max_bytes, draining any excess."""
    chunks: list[bytes] = []
    total_buffered = 0
    truncated = False

    while True:
        chunk = await stream.read(65536)
        if not chunk:
            break
        if not truncated:
            remaining = max_bytes - total_buffered
            if len(chunk) <= remaining:
                chunks.append(chunk)
                total_buffered += len(chunk)
            else:
                chunks.append(chunk[:remaining])
                total_buffered += remaining
                truncated = True
        # When truncated, continue reading (drain) but discard

    return b"".join(chunks), truncated


async def _communicate_limited(
    process: asyncio.subprocess.Process,
    max_output_bytes: int,
) -> tuple[bytes, bytes, bool, bool]:
    """Read stdout/stderr concurrently with size limits, then wait for exit."""
    if process.stdout is None or process.stderr is None:
        msg = "subprocess created without PIPE for stdout/stderr"
        raise RuntimeError(msg)
    (stdout_bytes, stdout_truncated), (stderr_bytes, stderr_truncated) = await asyncio.gather(
        _read_stream_limited(process.stdout, max_output_bytes),
        _read_stream_limited(process.stderr, max_output_bytes),
    )
    await process.wait()
    return stdout_bytes, stderr_bytes, stdout_truncated, stderr_truncated


def _enforce_payload_limit(
    result_dict: dict[str, Any],
    max_bytes: int = TEMPORAL_PAYLOAD_MAX_BYTES,
) -> dict[str, Any]:
    """Truncate stdout/stderr so the serialized activity result fits within Temporal's payload limit."""
    serialized = json.dumps(result_dict)
    payload_size = len(serialized.encode("utf-8"))
    if payload_size <= max_bytes:
        return result_dict

    excess = payload_size - max_bytes
    output = dict(result_dict.get("output", {}))

    stdout = output.get("stdout") or ""
    stderr = output.get("stderr") or ""

    notice = (
        f"\n[Payload truncated: serialized activity result ({payload_size} bytes)"
        f" exceeded Temporal payload limit ({max_bytes} bytes)]"
    )
    notice_bytes = len(notice.encode("utf-8"))
    trim_needed = excess + notice_bytes

    stdout_bytes = stdout.encode("utf-8")
    stderr_bytes = stderr.encode("utf-8")

    if len(stdout_bytes) >= trim_needed:
        output["stdout"] = stdout_bytes[: len(stdout_bytes) - trim_needed].decode("utf-8", errors="ignore")
    else:
        trim_needed -= len(stdout_bytes)
        output["stdout"] = ""
        output["stderr"] = stderr_bytes[: max(0, len(stderr_bytes) - trim_needed)].decode("utf-8", errors="ignore")

    output["stderr"] = (output.get("stderr") or "") + notice
    return {**result_dict, "output": output}


def _sanitize_env_value(value: object) -> str:
    """Sanitize value for use in environment variable.

    Raises:
        ValueError: If value contains null bytes or exceeds max length

    """
    str_value = json.dumps(value) if isinstance(value, dict | list) else str(value)

    if "\0" in str_value:
        msg = "Environment variable values cannot contain null bytes"
        raise ValueError(msg)

    if len(str_value) > MAX_ENV_VAR_LENGTH:
        msg = f"Environment variable value exceeds maximum length ({MAX_ENV_VAR_LENGTH} bytes)"
        raise ValueError(msg)

    return str_value


def _prepare_script_env(environment: dict[str, str] | None = None) -> dict[str, str]:
    """Prepare environment variables for script execution."""
    env = {k: v for k, v in os.environ.items() if k in SAFE_ENV_ALLOWLIST}
    if environment:
        for key, value in environment.items():
            env[key] = _sanitize_env_value(value)
    return env


def _process_script_result(
    returncode: int | None,
    stdout_bytes: bytes | None,
    stderr_bytes: bytes | None,
) -> dict[str, Any]:
    """Process script execution result into a normalized dict."""
    stdout = stdout_bytes.decode("utf-8") if stdout_bytes else ""
    stderr = stderr_bytes.decode("utf-8") if stderr_bytes else ""

    if returncode is None:
        msg = "Process returncode is None after communicate()"
        raise RuntimeError(msg)

    if returncode != 0:
        _raise_script_error(returncode, stdout, stderr)

    return {
        "stdout": stdout,
        "stderr": stderr,
        "return_code": returncode,
    }


async def _execute_script_common(
    command: list[str],
    environment: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> dict[str, Any]:
    """Execute a script with common subprocess handling logic.

    Returns dict with stdout, stderr, return_code.
    Raises ScriptExecutionError on non-zero exit, TimeoutError on timeout.
    """
    env = _prepare_script_env(environment)
    process = None

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        stdout_bytes, stderr_bytes, stdout_truncated, stderr_truncated = await asyncio.wait_for(
            _communicate_limited(process, max_output_bytes),
            timeout=timeout_seconds,
        )
        result = _process_script_result(process.returncode, stdout_bytes, stderr_bytes)
        if stdout_truncated or stderr_truncated:
            truncation_notice = (
                f"\n[Output truncated: exceeded {max_output_bytes} byte limit"
                f" (stdout: {'truncated' if stdout_truncated else 'complete'}"
                f", stderr: {'truncated' if stderr_truncated else 'complete'})]"
            )
            result["stderr"] = result["stderr"] + truncation_notice
        return result

    except (ScriptExecutionError, RuntimeError, ValueError):
        raise

    except TimeoutError as e:
        msg = "Script execution timed out"
        raise TimeoutError(msg) from e

    except subprocess.SubprocessError as e:
        raise ScriptExecutionError(
            message=f"Subprocess error: {e}",
            exit_code=-1,
            stdout="",
            stderr=str(e),
        ) from e

    except Exception as e:
        raise ScriptExecutionError(
            message=f"Unexpected error executing script: {e}",
            exit_code=-1,
            stdout="",
            stderr=str(e),
        ) from e

    finally:
        if process:
            await _cleanup_process(process)


async def execute_script(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
) -> dict[str, Any]:
    """Run a script from a WorkItem payload and return a Temporal activity result dict.

    Parses language/code/environment directly from the payload dict (no Pydantic validation).
    Applies cgroup memory limits, executes the subprocess, parses JSON output for Python scripts,
    and enforces the Temporal payload size limit before returning.

    Raises ScriptExecutionError on non-zero exit, TimeoutError on timeout.
    """
    language = input_config.get("language", "python")
    code = input_config["code"]
    environment = dict(input_config.get("environment") or {})

    timeout = int(input_config.get(ENGINE_TIMEOUT_SECONDS_KEY, 300))
    max_output_bytes = int(input_config.get(ENGINE_MAX_OUTPUT_BYTES_KEY, DEFAULT_MAX_OUTPUT_BYTES))

    cgroup_limit = _get_cgroup_memory_limit()
    if cgroup_limit:
        code = _prepend_memory_limit(code, language, int(cgroup_limit * 0.75))

    command = ["bash", "-c", code] if language == "bash" else [sys.executable, "-c", code]

    result = await _execute_script_common(command, environment, timeout, max_output_bytes)

    if language == "python" and result["stdout"].strip():
        try:
            result["output"] = json.loads(result["stdout"])
        except json.JSONDecodeError:
            lines = [line for line in result["stdout"].strip().split("\n") if line.strip()]
            if lines:
                with contextlib.suppress(json.JSONDecodeError):
                    result["output"] = json.loads(lines[-1])

    raw_output: dict[str, Any] = {
        "return_code": result["return_code"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "stdout_json": result.get("output"),
    }

    # Apply basic output_config mapping.
    # Full template-based mapping (output_config with keys) requires NamespaceResolver from
    # syntara. When execution_plane becomes a standalone service, that support can be added.
    if output_config is None:
        mapped_output: dict[str, Any] = raw_output
    elif not output_config:
        mapped_output = {}
    else:
        mapped_output = raw_output

    return _enforce_payload_limit({"output": mapped_output})
