"""Translate standalone image responses into Syntara Temporal activity results."""
# ruff: noqa: ANN401, EM101, EM102, TRY003

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from execution_plane.config import get_script_executor_settings
from execution_plane.script_executor import _enforce_payload_limit

_TEMPLATE = re.compile(r"\$\{([^}]+)\}")
_RETRYABLE_HTTP_STATUSES = frozenset({429, 502, 503, 504})
_HTTP_ERROR_START = 400


@dataclass
class WorkflowResultError(Exception):
    """A node failure with Temporal error metadata and optional mapped output."""

    message: str
    error_type: str
    non_retryable: bool = True
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        """Return the safe node error message."""
        return self.message


def _lookup(path: str, result: dict[str, Any]) -> Any:
    parts = path.split(".")
    if not parts or parts[0] != "result":
        raise KeyError(path)
    value: Any = result
    for part in parts[1:]:
        if isinstance(value, dict):
            value = value[part]
        elif isinstance(value, list):
            value = value[int(part)]
        else:
            raise KeyError(path)
    return value


def _map_output(result: dict[str, Any], output_config: dict[str, str] | None) -> dict[str, Any]:
    """Mirror the workflow result namespace's output-template semantics."""
    if output_config is None:
        return result
    output: dict[str, Any] = {}
    for key, template in output_config.items():
        try:
            match = _TEMPLATE.fullmatch(template)
            if match:
                output[key] = _lookup(match.group(1), result)
            else:
                output[key] = _TEMPLATE.sub(lambda m: str(_lookup(m.group(1), result)), template)
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise WorkflowResultError(
                f"Failed to resolve output mapping '{template}': {type(exc).__name__}",
                "OutputMappingError",
            ) from exc
    return output


def _ensure_payload_fits(payload: dict[str, Any]) -> dict[str, Any]:
    if len(json.dumps(payload, ensure_ascii=False).encode()) > get_script_executor_settings().temporal_payload_max_bytes:
        raise WorkflowResultError("Workflow node output exceeds Temporal payload limit", "OutputTooLarge")
    return payload


def _normalize_http(raw: dict[str, Any], output_config: dict[str, str] | None) -> dict[str, Any]:
    output = {
        "status_code": raw.get("status_code"),
        "body": raw.get("body"),
        "headers": raw.get("headers"),
        "elapsed": raw.get("elapsed"),
    }
    mapped = _map_output(output, output_config)
    if not raw.get("ok"):
        status = raw.get("status_code")
        if isinstance(status, int) and status >= _HTTP_ERROR_START:
            raise WorkflowResultError(
                str(raw.get("message") or f"HTTP {status}"),
                "HTTPError",
                non_retryable=status not in _RETRYABLE_HTTP_STATUSES,
                details={"output": mapped},
            )
        raise WorkflowResultError(
            str(raw.get("message") or "HTTP worker failed"),
            str(raw.get("error_type") or "HTTPError"),
        )
    return _ensure_payload_fits({"output": mapped})


def _normalize_script(raw: dict[str, Any], output_config: dict[str, str] | None) -> dict[str, Any]:
    if not raw.get("ok"):
        raise WorkflowResultError(
            str(raw.get("message") or "Script worker failed"),
            str(raw.get("error_type") or "ScriptExecutionError"),
        )
    stdout = raw.get("stdout")
    stdout_json: Any = None
    if isinstance(stdout, str) and stdout.strip():
        try:
            stdout_json = json.loads(stdout)
        except json.JSONDecodeError:
            for line in reversed(stdout.strip().splitlines()):
                try:
                    stdout_json = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
    output = {
        "return_code": raw.get("return_code"),
        "stdout": stdout,
        "stderr": raw.get("stderr"),
        "stdout_json": stdout_json,
    }
    return _enforce_payload_limit({"output": _map_output(output, output_config)})


def normalize_workflow_result(
    node_type: str,
    response: dict[str, Any],
    output_config: dict[str, str] | None,
) -> dict[str, Any]:
    """Produce the same ``{output: ...}`` contract as the local activities."""
    raw = response.get("result")
    if not isinstance(raw, dict):
        raise WorkflowResultError("Worker returned no result object", "WorkerProtocolError")
    if node_type == "http_request":
        return _normalize_http(raw, output_config)
    if node_type == "script":
        return _normalize_script(raw, output_config)
    raise WorkflowResultError("Unknown workflow node type", "WorkerProtocolError")
