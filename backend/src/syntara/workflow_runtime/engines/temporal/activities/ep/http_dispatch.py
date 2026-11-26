"""Opt-in HTTP dispatch through the installed Execution Plane Action."""

from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.workflow_core.models import APIExecutorParameters, ExecutionTargetProfile
from syntara.workflow_runtime.engines.temporal.activities.ep.ep_dispatch_activity import _dispatch_to_ep
from syntara.workflow_runtime.engines.temporal.constants import ENGINE_TIMEOUT_SECONDS_KEY


def is_uncredentialed_http(inputs: dict[str, Any]) -> bool:
    """Identify credential forms unsupported by the HTTP EP contract."""
    if any(
        inputs.get(key) for key in ("credential_id", "credential_bindings", "credential_name", "_resolved_credentials")
    ):
        return False
    if isinstance(inputs.get("url"), str):
        try:
            if urlsplit(inputs["url"]).username is not None:
                return False
        except ValueError:
            return False
    headers = inputs.get("headers") or {}
    return not any(
        str(name).lower() in {"authorization", "proxy-authorization", "cookie", "x-api-key"} for name in headers
    )


def http_workload_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Convert only the public HTTP contract, never resolved credential payloads."""
    if not is_uncredentialed_http(inputs):
        message = "HTTP EP does not support credentials yet; remove the execution profile to use the existing executor"
        raise ApplicationError(message, type="ConfigError", non_retryable=True)
    result = {key: inputs[key] for key in ("url", "method", "body", "follow_redirects") if key in inputs}
    for field in ("headers", "query_params"):
        values = inputs.get(field) or {}
        if not isinstance(values, dict) or any(not isinstance(value, str) for value in values.values()):
            message = f"HTTP {field} values must be strings for EP"
            raise ApplicationError(message, type="ConfigError", non_retryable=True)
        result[field] = values
    timeout = inputs.get(ENGINE_TIMEOUT_SECONDS_KEY, 30)
    result["timeout_seconds"] = timeout
    result[ENGINE_TIMEOUT_SECONDS_KEY] = timeout
    return result


async def dispatch_http_to_ep(
    inputs: dict[str, Any],
    output_config: dict[str, str] | None,
    execution_id: str,
    config: APIExecutorParameters,
) -> dict[str, Any]:
    """Execute an explicitly selected HTTP target without a native fallback."""
    if output_config is not None:
        message = "HTTP EP currently requires default full outputs; remove output selection or use the native executor"
        raise ApplicationError(message, type="ConfigError", non_retryable=True)
    if not isinstance(config.execution_profile, ExecutionTargetProfile):
        message = "HTTP EP requires an execution target"
        raise ApplicationError(message, type="ConfigError", non_retryable=True)
    if not config.url:
        message = "HTTP EP requires a public URL"
        raise ApplicationError(message, type="ConfigError", non_retryable=True)
    try:
        execution_uuid = UUID(execution_id)
    except ValueError:
        message = "Invalid execution ID"
        raise ApplicationError(message, type="ConfigError", non_retryable=True) from None
    workload_inputs = http_workload_inputs(inputs)
    # Use validated model defaults and enum values, not the unvalidated activity payload.
    workload_inputs.update(url=config.url, method=config.method.value, body=config.body)
    result = await _dispatch_to_ep(
        workload_inputs, output_config, execution_uuid, config.execution_profile.execution_target_id, "http-request"
    )
    if result is None:
        activity.raise_complete_async()
    return result or {}
