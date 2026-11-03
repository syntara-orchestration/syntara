"""Run script containers through the Kubernetes API from a Temporal activity."""

import asyncio
import hashlib
import json
from typing import Any

import httpx
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

# Override the image's long-lived gRPC entrypoint for a single isolated execution.
# Only the image's executor runs user code; no subprocess is started on the worker.
_RUNNER = """
import asyncio, json, os
from syntara_node_script.executor import run_script_async, ScriptExecutionError
p = json.loads(os.environ.pop("SYNTARA_SCRIPT_INPUT"))
async def main():
    try:
        result = await asyncio.wait_for(run_script_async(
            p["language"], p["code"], p["environment"],
            max_output_bytes=p["max_output_bytes"]), p["timeout"])
    except ScriptExecutionError as e:
        result = dict(return_code=e.exit_code, stdout=e.stdout, stderr=e.stderr, stdout_json=None)
    except TimeoutError:
        result = dict(timed_out=True)
    print(json.dumps(result))
asyncio.run(main())
"""


async def _connection() -> tuple[OpenShiftConfiguration, str]:
    """Resolve the worker's integration and credential locally, outside Temporal history."""
    integration_id = get_settings().script_openshift_integration_id
    if integration_id is None:
        msg = "Configure APP_SCRIPT_OPENSHIFT_INTEGRATION_ID"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True)
    async with AsyncSessionLocal() as session:
        integration = await session.get(Integration, integration_id)
        if integration is None or not integration.enabled or integration.integration_type != IntegrationType.OPENSHIFT:
            msg = "Script OpenShift integration is missing, disabled, or has the wrong type"
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


def _pod(name: str, payload: dict[str, Any], image: str) -> dict[str, Any]:
    """Build a single-use pod compatible with OpenShift restricted admission."""
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": name, "labels": {"app.kubernetes.io/name": "syntara-script"}},
        "spec": {
            "restartPolicy": "Never",
            "nodeSelector": {"kubernetes.io/arch": "amd64"},
            "automountServiceAccountToken": False,
            "activeDeadlineSeconds": payload["timeout"] + 15,
            "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
            "containers": [
                {
                    "name": "script",
                    "image": image,
                    "command": ["python", "-c", _RUNNER],
                    "env": [{"name": "SYNTARA_SCRIPT_INPUT", "value": json.dumps(payload)}],
                    "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}},
                    "resources": {
                        "requests": {"cpu": "100m", "memory": "128Mi"},
                        "limits": {"cpu": "1", "memory": "512Mi"},
                    },
                }
            ],
        },
    }


async def execute_openshift_script(  # noqa: C901, PLR0912, PLR0915
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
    payload = {
        "language": language,
        "code": code,
        "environment": environment,
        "timeout": timeout_seconds,
        "max_output_bytes": max_output_bytes,
    }
    async with httpx.AsyncClient(
        base_url=config.base_url,
        headers={"Authorization": f"Bearer {token}"},
        verify=build_integration_httpx_verify(ca_certificate=config.ca_certificate),
        timeout=15,
        follow_redirects=False,
    ) as client:
        try:
            async with asyncio.timeout(timeout_seconds + 30):
                response = await client.post(path, json=_pod(name, payload, get_settings().script_openshift_image))
                if response.status_code != httpx.codes.CONFLICT:
                    response.raise_for_status()
                while True:
                    activity.heartbeat({HEARTBEAT_STOP_MONITOR: True})
                    response = await client.get(f"{path}/{name}")
                    response.raise_for_status()
                    status = response.json().get("status", {})
                    if status.get("phase") in {"Succeeded", "Failed"}:
                        break
                    await asyncio.sleep(1)
                if status.get("phase") != "Succeeded":
                    msg = "OpenShift script container failed"
                    raise ApplicationError(msg, type="OpenShiftScriptError", non_retryable=True)
                # Bound data consumed from the API, including malformed container logs.
                chunks = bytearray()
                async with client.stream("GET", f"{path}/{name}/log", params={"container": "script"}) as logs:
                    logs.raise_for_status()
                    async for chunk in logs.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > 18 * max_output_bytes + 100_000:
                            msg = "OpenShift script result exceeded output limit"
                            raise ApplicationError(
                                msg,
                                type="OpenShiftScriptError",
                                non_retryable=True,
                            )
                result = json.loads(chunks)
                if result.get("timed_out"):
                    raise TimeoutError
                if not isinstance(result.get("return_code"), int) or not all(
                    isinstance(result.get(key), str) for key in ("stdout", "stderr")
                ):
                    msg = "Invalid OpenShift script result"
                    raise ApplicationError(msg, type="OpenShiftScriptError", non_retryable=True)
                return result
        except httpx.HTTPError:
            msg = "OpenShift API request failed"
            raise ApplicationError(msg, type="OpenShiftScriptError", non_retryable=True) from None
        finally:
            # Cancellation must not leave user code running in the cluster.
            cleanup = asyncio.create_task(client.request("DELETE", f"{path}/{name}", json={"gracePeriodSeconds": 0}))
            try:
                response = await asyncio.shield(cleanup)
                if response.status_code not in {200, 202, 404}:
                    activity.logger.warning("OpenShift rejected script pod cleanup", pod=name)
            except asyncio.CancelledError:
                await cleanup
                raise
            except httpx.HTTPError:
                activity.logger.warning("Unable to delete script pod; activeDeadlineSeconds bounds execution", pod=name)
