"""Plugin action execution for v2 workflows (Syntara plugin marketplace POC).

Executes ``plugin_action`` nodes. The action contract comes from the
installed plugin's stored descriptor: inputs are validated against the
action's declared JSON Schema and the origin-less ``http.v1`` operation path
is resolved with the input values.

Per the plugin SDK's model, a plugin never declares an origin (base URL) —
the platform resolves connections after installation. This POC stands in for
that resolution with an optional per-step ``origin`` parameter:

- With ``origin``: a real HTTP request is made (declared method, resolved
  path) and its status, timing, and body are reported.
- Without ``origin``: a simulated execution returns an honest envelope
  describing what would run — it never fabricates the action's business
  outcome.
"""

import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
import jsonschema
import structlog
from sqlmodel import col, select
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.core.database.session import AsyncSessionLocal
from syntara.plugins.models.installed_plugin import InstalledPlugin
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

logger = structlog.stdlib.get_logger(__name__)

_MAX_HTTP_BODY_BYTES = 8 * 1024
_DEFAULT_HTTP_TIMEOUT_SECONDS = 10.0
_IMPLEMENTATION_TIMEOUT_SECONDS = 30.0
_PATH_TEMPLATE_PREFIX = "{input."


@activity.defn(name=ActivityName.PLUGIN_ACTION)
async def execute_plugin_action_activity(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,  # noqa: ARG001
) -> dict[str, Any]:
    """Execute one installed plugin action step.

    Returns the normalized ``{"output": {...}}`` structure used by executor
    nodes. Raises a non-retryable ApplicationError when the plugin is not
    installed, the action is unknown, or the configured inputs do not satisfy
    the action's declared input schema.
    """
    activity.heartbeat()
    plugin_identity = str(input_config.get("plugin", ""))
    action_identity = str(input_config.get("action", ""))
    step_inputs = input_config.get("inputs") or {}
    origin = input_config.get("origin")
    if not isinstance(step_inputs, dict):
        msg = "plugin action 'inputs' must be an object"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True)

    action = await _load_action(plugin_identity, action_identity)

    schema = action.get("input_schema")
    if isinstance(schema, dict) and schema:
        try:
            jsonschema.validate(instance=step_inputs, schema=schema)
        except jsonschema.ValidationError as error:
            msg = f"plugin action inputs failed schema validation at '{error.json_path}': {error.message}"
            raise ApplicationError(msg, type="ConfigError", non_retryable=True) from error

    # Real code execution: when the action carries an embedded implementation,
    # extract it from the artifact and run it in a Python subprocess.
    implementation_source = action.get("implementation_source")
    if isinstance(implementation_source, str) and implementation_source:
        return await _execute_implementation(plugin_identity, action_identity, implementation_source, step_inputs)

    # Custom-runner actions execute in their own container on the Execution
    # Plane; this POC's in-process executor cannot run them. Return an honest
    # envelope describing the dispatch that would happen — never a fabricated
    # business outcome.
    if action.get("runtime_kind") == "custom-runner" or action.get("entry_point"):
        return _execution_plane_required(plugin_identity, action_identity, action, step_inputs)

    method = str(action.get("method") or "GET").upper()
    path_template = str(action.get("path") or "/")
    resolved_path = _resolve_path(path_template, step_inputs)

    if isinstance(origin, str) and origin:
        return await _execute_http(origin, method, resolved_path, step_inputs)

    elapsed_ms = 0
    output = {
        "status": "completed",
        "executed_via": "simulated",
        "plugin": plugin_identity,
        "action": action_identity,
        "method": method,
        "resolved_path": resolved_path,
        "inputs": step_inputs,
        "detail": "Simulated platform-runner execution (no origin configured); "
        "set the step's origin to a base URL for real HTTP execution.",
        "elapsed_ms": elapsed_ms,
    }
    logger.info(
        "plugin action simulated",
        plugin=plugin_identity,
        action=action_identity,
        resolved_path=resolved_path,
    )
    return {"output": output}


async def _load_action(plugin_identity: str, action_identity: str) -> dict[str, Any]:
    """Load the action summary for one installed plugin action."""
    async with AsyncSessionLocal() as session:
        namespace, _, name = plugin_identity.partition("/")
        installed = (
            await session.exec(
                select(InstalledPlugin).where(
                    col(InstalledPlugin.namespace) == namespace,
                    col(InstalledPlugin.plugin_name) == name,
                )
            )
        ).first()
    if installed is None:
        msg = f"Plugin '{plugin_identity}' is not installed"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True)

    for candidate in installed.actions or []:
        if candidate.get("identity") == action_identity or candidate.get("name") == action_identity:
            return candidate
    msg = f"Action '{action_identity}' not found in installed plugin '{plugin_identity}'"
    raise ApplicationError(msg, type="ConfigError", non_retryable=True)


def _execution_plane_required(
    plugin_identity: str,
    action_identity: str,
    action: dict[str, Any],
    step_inputs: dict[str, Any],
) -> dict[str, Any]:
    """Describe the Execution Plane dispatch a custom-runner action needs.

    The marketplace POC executes embedded implementations in a subprocess, but
    custom-runner steps ship as container workloads: they run only on the
    Execution Plane, which receives the digest-pinned image and the step
    identity in a ``work.execute`` command. This envelope reports that
    dispatch without fabricating the action's business outcome.
    """
    output = {
        "status": "completed",
        "executed_via": "execution-plane-required",
        "plugin": plugin_identity,
        "action": action_identity,
        "step_revision_id": action.get("identity"),
        "entry_point": action.get("entry_point"),
        "abi": action.get("abi"),
        "workload_image": action.get("workload_image"),
        "inputs": step_inputs,
        "detail": "Custom-runner step: dispatches to the Execution Plane "
        "(work.execute with the digest-pinned image and step_revision_id). "
        "This POC does not wire that dispatch; run the step through the "
        "Execution Plane's work submission tool.",
    }
    logger.info(
        "plugin action requires execution plane",
        plugin=plugin_identity,
        action=action_identity,
        workload_image=action.get("workload_image"),
    )
    return {"output": output}


def _resolve_path(path_template: str, inputs: dict[str, Any]) -> str:
    """Substitute ``{input.X}`` placeholders with the configured input values."""
    resolved = path_template
    for key, value in inputs.items():
        resolved = resolved.replace(f"{{input.{key}}}", str(value))
    return resolved


async def _execute_http(origin: str, method: str, resolved_path: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Perform the real HTTP request described by the action operation."""
    url = f"{origin.rstrip('/')}/{resolved_path.lstrip('/')}"
    timeout = inputs.get("timeout_seconds")
    timeout_seconds = float(timeout) if isinstance(timeout, (int, float)) else _DEFAULT_HTTP_TIMEOUT_SECONDS
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
            response = await client.request(method, url)
    except httpx.HTTPError as error:
        failed: dict[str, Any] = {
            "status": "failed",
            "executed_via": "http",
            "url": url,
            "method": method,
            "error": f"request failed: {error}",
        }
        logger.warning("plugin action http request failed", url=url, error=str(error))
        return {"output": failed}

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    body = response.text[:_MAX_HTTP_BODY_BYTES]
    output: dict[str, Any] = {
        "status": "completed",
        "executed_via": "http",
        "url": url,
        "method": method,
        "status_code": response.status_code,
        "response_time_ms": elapsed_ms,
        "body": body,
    }
    logger.info(
        "plugin action executed",
        url=url,
        method=method,
        status_code=response.status_code,
        elapsed_ms=elapsed_ms,
    )
    return {"output": output}


async def _execute_implementation(
    plugin_identity: str,
    action_identity: str,
    source: str,
    step_inputs: dict[str, Any],
) -> dict[str, Any]:
    """Run the plugin's embedded Python implementation in a subprocess.

    The implementation reads JSON from stdin and writes JSON to stdout.
    Executed with a bounded timeout in an isolated temporary directory.
    """
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="syntara-plugin-") as workdir:
        impl_path = Path(workdir) / "implementation.py"
        impl_path.write_text(source, encoding="utf-8")
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(impl_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(json.dumps(step_inputs).encode("utf-8")),
                timeout=_IMPLEMENTATION_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            output: dict[str, Any] = {
                "status": "failed",
                "executed_via": "implementation",
                "plugin": plugin_identity,
                "action": action_identity,
                "error": f"implementation timed out after {_IMPLEMENTATION_TIMEOUT_SECONDS}s",
            }
            logger.warning("plugin implementation timed out", plugin=plugin_identity, action=action_identity)
            return {"output": output}
        except OSError as error:
            output = {
                "status": "failed",
                "executed_via": "implementation",
                "plugin": plugin_identity,
                "action": action_identity,
                "error": f"failed to execute implementation: {error}",
            }
            logger.warning("plugin implementation failed to start", plugin=plugin_identity, error=str(error))
            return {"output": output}

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if process.returncode != 0:
        error_text = stderr.decode("utf-8", errors="replace")[:_MAX_HTTP_BODY_BYTES]
        failure: dict[str, Any] = {
            "status": "failed",
            "executed_via": "implementation",
            "plugin": plugin_identity,
            "action": action_identity,
            "error": f"implementation exited with code {process.returncode}: {error_text}",
            "elapsed_ms": elapsed_ms,
        }
        logger.warning(
            "plugin implementation failed",
            plugin=plugin_identity,
            action=action_identity,
            returncode=process.returncode,
            stderr=error_text[:200],
        )
        return {"output": failure}

    try:
        result = json.loads(stdout)
    except (ValueError, UnicodeDecodeError) as error:
        output = {
            "status": "failed",
            "executed_via": "implementation",
            "plugin": plugin_identity,
            "action": action_identity,
            "error": f"implementation produced invalid JSON output: {error}",
            "elapsed_ms": elapsed_ms,
        }
        return {"output": output}

    if not isinstance(result, dict):
        result = {"result": result}

    completed: dict[str, Any] = {
        "status": "completed",
        "executed_via": "implementation",
        "plugin": plugin_identity,
        "action": action_identity,
        "elapsed_ms": elapsed_ms,
        **result,
    }
    logger.info(
        "plugin implementation executed",
        plugin=plugin_identity,
        action=action_identity,
        elapsed_ms=elapsed_ms,
    )
    return {"output": completed}
