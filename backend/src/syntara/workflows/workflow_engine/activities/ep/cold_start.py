"""Build image-backed WorkItems for the configured OpenShift integration."""
# ruff: noqa: EM101, TRY003

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from temporalio.exceptions import ApplicationError

from syntara.core.config.base import get_settings
from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.integration_configuration import OpenShiftConfiguration
from syntara.workflows.workflow_engine import constants

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from syntara.workflows.workflow_engine.models.workflow_definition import (
        APIExecutorParameters,
        ScriptExecutorParameters,
    )


async def resolve_target_id(session: AsyncSession) -> uuid.UUID:
    """Resolve the default integration without reading Execution Plane tables."""
    integration_id = get_settings().ep_openshift_integration_id
    if integration_id is None:
        raise ApplicationError(
            "APP_EP_OPENSHIFT_INTEGRATION_ID is required for cold-start workflow nodes",
            type="ExecutionIntegrationError",
            non_retryable=True,
        )
    integration = await session.get(Integration, integration_id)
    if (
        integration is None
        or integration.integration_type != IntegrationType.OPENSHIFT
        or not integration.enabled
        or not isinstance(integration.configuration, OpenShiftConfiguration)
    ):
        raise ApplicationError(
            "Configured OpenShift integration is missing, disabled, or invalid",
            type="ExecutionIntegrationError",
            non_retryable=True,
        )
    return integration.configuration.execution_target_id


def script_task(config: ScriptExecutorParameters, input_config: dict[str, Any]) -> dict[str, Any]:
    """Select the branch-derived Python or Bash image for a Script node."""
    settings = get_settings()
    image = (
        settings.ep_script_python_executor_image
        if config.language.value == "python"
        else settings.ep_script_bash_executor_image
    )
    if not image:
        raise ApplicationError(
            "No cold-start executor image is configured for this script language",
            type="ExecutionIntegrationError",
            non_retryable=True,
        )
    pod_command = (
        ["/usr/bin/python3", "-c", "import time; time.sleep(3600)"]
        if config.language.value == "python"
        else ["/bin/bash", "-c", "sleep 3600"]
    )
    timeout = min(max(int(input_config.get(constants.ENGINE_TIMEOUT_SECONDS_KEY, 300)), 1), 300)
    return {
        "image": image,
        "pod_command": pod_command,
        "command": ["/usr/local/bin/script-executor", "--once"],
        "input": {
            "code": config.code,
            "environment": config.environment,
            "timeout_seconds": timeout,
        },
        "timeout_seconds": min(timeout + 120, 3600),
        "image_pull_policy": "Always",
    }


def http_task(
    config: APIExecutorParameters,
    *,
    request_url: str,
    headers: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    """Adapt an HTTP workflow node to the original stdin HTTP image wire format."""
    request_timeout = min(max(timeout_seconds, 1), 60)
    return {
        "image": get_settings().ep_http_executor_image,
        "pod_command": ["/bin/sh", "-c", "sleep 3600"],
        "command": ["python", "-m", "syntara.http_executor"],
        "input": {
            "method": config.method.value,
            "url": request_url,
            "headers": {key: str(value) for key, value in headers.items()},
            "query_params": config.query_params,
            "body": config.body,
            "timeout_seconds": request_timeout,
        },
        "timeout_seconds": request_timeout + 120,
        "image_pull_policy": "Always",
    }
