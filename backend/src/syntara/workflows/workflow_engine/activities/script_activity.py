"""Script activity executors for bash and Python.

This module provides functionality to execute bash and Python scripts as workflow activities.
Scripts run in isolated subprocesses with timeout and error handling.
"""

import asyncio
import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.core.exceptions import SafeValueError
from syntara.workflows.workflow_engine import constants
from syntara.workflows.workflow_engine.models.workflow_definition import (
    ActivityName,
    ScriptExecutorParameters,
    ScriptOutput,
)

from .common import HEARTBEAT_STOP_MONITOR, ActivityExecutionError

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


class ScriptExecutionError(ActivityExecutionError):
    """Raised when script execution fails."""

    exit_code: int
    stdout: str
    stderr: str

    def __init__(self, message: str, exit_code: int, stdout: str, stderr: str) -> None:
        """Initialize script execution error.

        Args:
            message: Error message
            exit_code: Script exit code
            stdout: Standard output
            stderr: Standard error output

        """
        super().__init__(message)
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


def _raise_script_error(return_code: int, stdout: str, stderr: str) -> None:
    """Raise ScriptExecutionError with formatted message.

    Args:
        return_code: Script exit code
        stdout: Standard output
        stderr: Standard error output

    Raises:
        ScriptExecutionError: Always raised with formatted error details

    """
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
    """Clean up subprocess by ensuring it has terminated.

    Args:
        process: The subprocess to clean up

    """
    if process.returncode is None:
        # Process still running, terminate it gracefully
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=constants.SCRIPT_CLEANUP_TERMINATE_TIMEOUT)
            activity.logger.debug("Process terminated gracefully")
        except TimeoutError:
            activity.logger.warning("Process didn't terminate gracefully, force killing")
            try:
                process.kill()
                await asyncio.wait_for(process.wait(), timeout=constants.SCRIPT_CLEANUP_KILL_TIMEOUT)
                activity.logger.info("Process force killed successfully")
            except TimeoutError:
                activity.logger.error("Process didn't die after kill signal, may be zombie")
            except ProcessLookupError:
                activity.logger.debug("Process already terminated after kill attempt")
        except ProcessLookupError:
            activity.logger.debug("Process already terminated before cleanup")

    # Close all streams to prevent event loop warnings
    # This ensures transport cleanup happens before event loop closes
    if process.stdin and not process.stdin.is_closing():
        process.stdin.close()
        with contextlib.suppress(Exception):
            await process.stdin.wait_closed()

    # Close the subprocess transport to prevent delayed cleanup warnings
    # We need to access _transport directly because Python's asyncio doesn't provide
    # a public API to close subprocess transports. Without this, the transport's __del__
    # method attempts cleanup after the event loop closes, causing "Event loop is closed"
    # warnings. This is a known asyncio limitation when subprocesses outlive the event loop.
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
    """Read from an asyncio stream up to max_bytes, draining any excess.

    After max_bytes have been buffered, continues reading and discarding
    data so the subprocess pipe doesn't block.

    Returns:
        Tuple of (buffered_bytes, was_truncated)

    """
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
        # When truncated, we still read (drain) but discard

    return b"".join(chunks), truncated


async def _communicate_limited(
    process: asyncio.subprocess.Process,
    max_output_bytes: int,
) -> tuple[bytes, bytes, bool, bool]:
    """Read stdout/stderr concurrently with size limits, then wait for exit.

    Reads both streams in parallel to avoid deadlock when both pipe buffers
    fill up. Each stream is independently capped at max_output_bytes.

    Returns:
        Tuple of (stdout_bytes, stderr_bytes, stdout_truncated, stderr_truncated)

    """
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
    max_bytes: int = constants.TEMPORAL_PAYLOAD_MAX_BYTES,
) -> dict[str, Any]:
    """Truncate stdout/stderr so the serialized activity result fits within Temporal's payload limit.

    Temporal's server-side limit.blobSize.error (default 2MB) rejects oversized
    activity results. The SDK treats the rejection as retryable, causing futile
    retries until the activity times out. This check prevents that by truncating
    before the payload leaves the worker.

    Returns a new dict (does not mutate the input).

    Truncation operates on raw UTF-8 bytes, not the JSON-escaped form. JSON
    escaping can expand certain characters (e.g. newlines, quotes), so the
    truncated payload may be slightly larger than ``max_bytes`` after
    re-serialization. The 10% headroom in TEMPORAL_PAYLOAD_MAX_BYTES absorbs
    this expansion.
    """
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

    Args:
        value: Value to sanitize

    Returns:
        Sanitized string value

    Raises:
        ValueError: If value contains null bytes or exceeds max length

    """
    # Convert dicts and lists to JSON for proper serialization
    # Python's str() uses single quotes and Python-specific syntax (True/False/None)
    # which is not valid JSON. json.dumps() produces valid JSON with double quotes.
    str_value = json.dumps(value) if isinstance(value, dict | list) else str(value)

    # Check for null bytes (not allowed in environment variables)
    if "\0" in str_value:
        msg = "Environment variable values cannot contain null bytes"
        raise SafeValueError(msg)

    # Limit environment variable size to prevent resource exhaustion
    # Note: Systems have limits on total env size (all vars combined), typically 128-256KB
    # We limit individual vars to prevent resource exhaustion and leave room for system variables
    if len(str_value) > constants.MAX_ENV_VAR_LENGTH:
        msg = f"Environment variable value exceeds maximum length ({constants.MAX_ENV_VAR_LENGTH} bytes)"
        raise SafeValueError(msg)

    return str_value


def _prepare_script_env(environment: dict[str, str] | None = None) -> dict[str, str]:
    """Prepare environment variables for script execution.

    Args:
        environment: Optional environment variables from parameters.environment

    Returns:
        Environment dict with allowlisted system vars and user-defined vars

    """
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
    """Process script execution result.

    Args:
        returncode: Process return code
        stdout_bytes: Standard output bytes
        stderr_bytes: Standard error bytes

    Returns:
        Result dict with stdout, stderr, and return_code

    Raises:
        RuntimeError: If returncode is None
        ScriptExecutionError: If script exited with non-zero code

    """
    stdout = stdout_bytes.decode("utf-8") if stdout_bytes else ""
    stderr = stderr_bytes.decode("utf-8") if stderr_bytes else ""

    # returncode should never be None after communicate()
    if returncode is None:
        msg = "Process returncode is None after communicate()"
        raise RuntimeError(msg)

    # Check for script errors
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
    max_output_bytes: int = constants.DEFAULT_MAX_OUTPUT_BYTES,
) -> dict[str, Any]:
    """Execute a script with common subprocess handling logic (DRY).

    Args:
        command: Command to execute (e.g., ["bash", "-c", script] or ["python", "-c", script])
        environment: Optional environment variables from parameters.environment
        timeout_seconds: Optional timeout in seconds (uses default if not provided)
        max_output_bytes: Max bytes to capture per stream (stdout/stderr independently)

    Returns:
        dict with keys:
            - stdout: Standard output from script
            - stderr: Standard error output
            - return_code: Exit code (0 = success)

    Raises:
        ScriptExecutionError: If script exits with non-zero code
        TimeoutError: If script execution times out
        ValueError: If input values contain null bytes or exceed maximum length

    """
    env = _prepare_script_env(environment)
    process = None

    try:
        # Execute script asynchronously with custom environment
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        # Read stdout/stderr with size limits to prevent worker OOM,
        # then wait for process exit — all within the timeout window.
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

    except (ScriptExecutionError, RuntimeError, SafeValueError):
        # Re-raise these errors as-is
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
        # Ensure process cleanup to avoid event loop warnings
        if process:
            await _cleanup_process(process)


@activity.defn(name=ActivityName.SCRIPT)
async def execute_script_activity(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
) -> dict[str, Any]:
    """Execute a script for V2 workflows (unified bash/python activity).

    This activity handles both bash and python scripts based on the 'language'
    field in config, delegating to the appropriate helper function.

    Returns normalized structure with output portion (no control needed for executor nodes).
    Output mapping is applied internally before returning to avoid storing suppressed fields in Temporal.

    Args:
        input_config: Script configuration (already template-resolved in V2)
                      Expected keys: 'code', 'language' (optional, defaults to 'python'),
                      'environment' (optional), 'timeout' (optional)
        output_config: Output mapping configuration (field_name -> template expression)
                       None = return full result, {} = suppress all, {...} = extract specific fields

    Returns:
        {
            "output": {
                "status": "completed",
                "return_code": 0,
                "stdout": "...",
                "stderr": "...",
                "stdout_json": {...}  // Only for Python scripts with JSON output
            }
        }

    """
    activity.heartbeat({HEARTBEAT_STOP_MONITOR: True})

    try:
        # Validate config via Pydantic model
        try:
            config = ScriptExecutorParameters.model_validate(input_config)
        except Exception:  # noqa: BLE001
            msg = "Script activity configuration validation failed"
            raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None

        # Read values from the validated model
        language = config.language.value
        code = config.code
        environment = dict(config.environment)

        timeout = int(input_config.get(constants.ENGINE_TIMEOUT_SECONDS_KEY, 300))
        max_output_bytes = int(
            input_config.get(constants.ENGINE_MAX_OUTPUT_BYTES_KEY, constants.DEFAULT_MAX_OUTPUT_BYTES)
        )

        # Inject subprocess memory limit from the container's cgroup limit
        cgroup_limit = _get_cgroup_memory_limit()
        if cgroup_limit:
            code = _prepend_memory_limit(code, language, int(cgroup_limit * 0.75))

        # Build command based on language
        command = ["bash", "-c", code] if language == "bash" else [sys.executable, "-c", code]

        # Execute script
        result = await _execute_script_common(command, environment, timeout, max_output_bytes)

        # For Python scripts, try to parse stdout as JSON
        if language == "python" and result["stdout"].strip():
            # First, try parsing entire stdout as JSON
            try:
                result["output"] = json.loads(result["stdout"])
            except json.JSONDecodeError:
                # Fallback: try parsing the last non-empty line as JSON
                # This allows debug prints before the final JSON output
                lines = [line for line in result["stdout"].strip().split("\n") if line.strip()]
                if lines:
                    with contextlib.suppress(json.JSONDecodeError):
                        result["output"] = json.loads(lines[-1])

        output = ScriptOutput(
            return_code=result["return_code"],
            stdout=result["stdout"],
            stderr=result["stderr"],
            stdout_json=result.get("output"),
        )
        return _enforce_payload_limit({"output": output.dump(output_config)})

    except ApplicationError:
        raise
    except ScriptExecutionError as e:
        output = ScriptOutput(return_code=e.exit_code, stdout=e.stdout, stderr=e.stderr)
        detail = _enforce_payload_limit({"output": output.dump(output_config)})
        raise ApplicationError(str(e), detail, type="ScriptExecutionError", non_retryable=True) from None
    except TimeoutError:
        output = ScriptOutput()
        msg = f"Script execution timed out after {timeout} seconds"
        raise ApplicationError(
            msg, {"output": output.dump(output_config)}, type="TimeoutError", non_retryable=True
        ) from None
    except Exception as e:  # noqa: BLE001
        output = ScriptOutput()
        msg = "Script activity failed unexpectedly"
        raise ApplicationError(
            msg, {"output": output.dump(output_config)}, type=type(e).__name__, non_retryable=True
        ) from None
