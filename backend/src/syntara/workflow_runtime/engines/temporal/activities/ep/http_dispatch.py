"""Opt-in HTTP dispatch through the installed Execution Plane Action."""

from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.core.database.session import AsyncSessionLocal
from syntara.execution_plane.commands.errors import CommandResourceStateError
from syntara.execution_plane.http_credentials import HTTP_BEARER_RECIPE, authorize_http_binding
from syntara.integrations.exceptions import IntegrationCredentialNotFoundError
from syntara.workflow_core.models import APIExecutorParameters, ExecutionTargetProfile
from syntara.workflow_runtime.engines.temporal.activities.ep.ep_dispatch_activity import _dispatch_to_ep
from syntara.workflow_runtime.engines.temporal.constants import ENGINE_TIMEOUT_SECONDS_KEY
from syntara.workflows.models.execution import Execution


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
        message = (
            "HTTP EP requires an authorized integration bearer binding; inline and legacy credentials are unsupported"
        )
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


async def _http_endpoint(config: APIExecutorParameters, execution_id: UUID) -> str | None:
    """Resolve an authorized integration using the persisted execution project."""
    if config.integration_id is None and not config.credential_bindings:
        return None
    if config.integration_id is None:
        message = "Credentialed HTTP requires an integration"
        raise ApplicationError(message, type="ConfigError", non_retryable=True)
    async with AsyncSessionLocal() as session:
        execution = await session.get(Execution, execution_id)
        if execution is None:
            message = "Execution does not exist"
            raise ApplicationError(message, type="ConfigError", non_retryable=True)
        try:
            return await authorize_http_binding(session, config, execution.project_id)
        except (CommandResourceStateError, IntegrationCredentialNotFoundError) as error:
            message = "HTTP integration or credential binding is not authorized"
            raise ApplicationError(message, type="ConfigError", non_retryable=True) from error


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
    endpoint = await _http_endpoint(config, execution_uuid)
    public_inputs = dict(inputs)
    if endpoint is not None:
        public_inputs.pop("credential_bindings", None)
    workload_inputs = http_workload_inputs(public_inputs)
    if endpoint is not None:
        workload_inputs["credential_name"] = HTTP_BEARER_RECIPE
        workload_inputs["credential_bindings"] = [
            binding.model_dump(mode="json") for binding in config.credential_bindings
        ]
    # Use validated model defaults and enum values, not the unvalidated activity payload.
    workload_inputs.update(url=config.url, method=config.method.value, body=config.body)
    dispatch_options = {"http_endpoint": endpoint} if endpoint is not None else {}
    result = await _dispatch_to_ep(
        workload_inputs,
        output_config,
        execution_uuid,
        config.execution_profile.execution_target_id,
        "http-request",
        **dispatch_options,
    )
    if result is None:
        activity.raise_complete_async()
    return result or {}
