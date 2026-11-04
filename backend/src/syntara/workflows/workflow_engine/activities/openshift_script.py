"""Run script containers through the Kubernetes API from a Temporal activity."""

import asyncio
import hashlib
import ipaddress
from typing import Any

import httpx
from sqlmodel import select
from syntara_plugin.runtime import ContainerInvocation
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.lib.tls_utils import build_integration_httpx_verify
from syntara.core.services.secret_service import create_secret_service
from syntara.credentials.lib.injector_resolver import InjectorResolver
from syntara.integrations.lib.credential_resolver import fetch_credential_with_type
from syntara.integrations.lib.url_validation import validate_integration_configuration_no_ssrf
from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.integration_configuration import OpenShiftConfiguration

from .common import HEARTBEAT_STOP_MONITOR
from .script_grpc import SCRIPT_STEP_ID, invoke_script

MAX_SCRIPT_TIMEOUT_SECONDS = 600
MAX_SCRIPT_OUTPUT_BYTES = 1024 * 1024


async def _connection() -> tuple[OpenShiftConfiguration, str]:
    """Resolve the worker's integration and credential locally, outside Temporal history."""
    integration_id = get_settings().script_openshift_integration_id
    async with AsyncSessionLocal() as session:
        if integration_id is not None:
            integration = await session.get(Integration, integration_id)
        else:
            result = await session.exec(
                select(Integration)
                .where(Integration.integration_type == IntegrationType.OPENSHIFT)
                .where(Integration.enabled == True)  # noqa: E712
                .limit(1)
            )
            integration = result.first()
        if integration is None or not integration.enabled or integration.integration_type != IntegrationType.OPENSHIFT:
            msg = "No enabled OpenShift integration found; configure APP_SCRIPT_OPENSHIFT_INTEGRATION_ID or add one"
            raise ApplicationError(
                msg,
                type="ConfigError",
                non_retryable=True,
            )
        config = integration.configuration
        if not isinstance(config, OpenShiftConfiguration) or not integration.management_credential_id:
            msg = "Script OpenShift integration requires configuration and a management credential"
            raise ApplicationError(
                msg,
                type="ConfigError",
                non_retryable=True,
            )
        validate_integration_configuration_no_ssrf(config)
        credential, credential_type = await fetch_credential_with_type(session, integration.management_credential_id)
        if not credential.enabled:
            msg = "OpenShift credential is disabled"
            raise ApplicationError(msg, type="ConfigError", non_retryable=True)
        secret = await create_secret_service(session).retrieve_secret(credential.secret_id)  # type: ignore[arg-type]
        resolved = InjectorResolver.resolve(credential_type.injectors or {}, secret)
        token = resolved.extra_vars.get("bearer_token")
        if not isinstance(token, str) or not token.strip():
            msg = "OpenShift credential requires a bearer token"
            raise ApplicationError(msg, type="ConfigError", non_retryable=True)
        return config, token


def _pod(name: str, timeout_seconds: int, image: str) -> dict[str, Any]:
    """Build a single-use pod compatible with OpenShift restricted admission."""
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": name, "labels": {"app.kubernetes.io/name": "syntara-script"}},
        "spec": {
            "restartPolicy": "Never",
            "nodeSelector": {"kubernetes.io/arch": "amd64"},
            "automountServiceAccountToken": False,
            "activeDeadlineSeconds": timeout_seconds + 75,
            "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
            "containers": [
                {
                    "name": "script",
                    "image": image,
                    "ports": [{"name": "grpc", "containerPort": 50051}],
                    "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}},
                    "resources": {
                        "requests": {"cpu": "100m", "memory": "128Mi"},
                        "limits": {"cpu": "1", "memory": "512Mi"},
                    },
                }
            ],
        },
    }


async def execute_openshift_script(  # noqa: C901, PLR0915
    language: str,
    code: str,
    environment: dict[str, str],
    timeout_seconds: int,
    max_output_bytes: int,
) -> dict[str, Any]:
    """Create, monitor, collect output, and delete an isolated script pod."""
    config, token = await _connection()
    info = activity.info()
    identity = f"{info.workflow_id}/{info.workflow_run_id}/{info.activity_id}/{info.attempt}"
    name = "syntara-script-" + hashlib.sha256(identity.encode()).hexdigest()[:40]
    path = f"/api/v1/namespaces/{config.namespace}/pods"
    image = config.script_image
    if not image:
        msg = "Configure script_image on the OpenShift integration"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True)
    if not 1 <= timeout_seconds <= MAX_SCRIPT_TIMEOUT_SECONDS or not 1 <= max_output_bytes <= MAX_SCRIPT_OUTPUT_BYTES:
        msg = "Script container supports timeouts up to 600 seconds and output limits up to 1024 KB"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True)
    if not info.workflow_run_id:
        msg = "Script execution requires a workflow run identity"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True)
    invocation = ContainerInvocation(
        invocation_id=name,
        workflow_run_id=info.workflow_run_id,
        step_revision_id=SCRIPT_STEP_ID,
        inputs={"language": language, "code": code, "environment": environment, "max_output_bytes": max_output_bytes},
        credential_file_paths={},
        timeout_seconds=timeout_seconds,
    )
    async with httpx.AsyncClient(
        base_url=config.base_url,
        headers={"Authorization": f"Bearer {token}"},
        verify=build_integration_httpx_verify(ca_certificate=config.ca_certificate),
        timeout=15,
        follow_redirects=False,
    ) as client:
        try:
            async with asyncio.timeout(timeout_seconds + 75):
                response = await client.post(path, json=_pod(name, timeout_seconds, image))
                if response.status_code != httpx.codes.CONFLICT:
                    response.raise_for_status()
                while True:
                    activity.heartbeat({HEARTBEAT_STOP_MONITOR: True})
                    response = await client.get(f"{path}/{name}")
                    response.raise_for_status()
                    status = response.json().get("status", {})
                    if status.get("phase") in {"Succeeded", "Failed"}:
                        msg = "Script container terminated before gRPC execution"
                        raise ApplicationError(msg, type="OpenShiftScriptError", non_retryable=True)
                    if status.get("phase") == "Running" and status.get("podIP"):
                        # Pod IP comes from the authenticated cluster API, not workflow input.
                        address = ipaddress.ip_address(status["podIP"])
                        host = f"[{address}]" if isinstance(address, ipaddress.IPv6Address) else str(address)
                        return await invoke_script(f"{host}:50051", invocation)
                    await asyncio.sleep(1)
        except httpx.HTTPError:
            msg = "OpenShift API request failed"
            raise ApplicationError(msg, type="OpenShiftScriptError", non_retryable=True) from None
        finally:
            # Cancellation must not leave user code running in the cluster.
            cleanup = asyncio.create_task(client.request("DELETE", f"{path}/{name}", json={"gracePeriodSeconds": 0}))
            try:
                response = await asyncio.shield(cleanup)
                if response.status_code not in {200, 202, 404}:
                    activity.logger.warning("OpenShift rejected script pod cleanup: %s", name)
            except asyncio.CancelledError:
                await cleanup
                raise
            except httpx.HTTPError:
                activity.logger.warning("Unable to delete script pod; activeDeadlineSeconds bounds execution: %s", name)
