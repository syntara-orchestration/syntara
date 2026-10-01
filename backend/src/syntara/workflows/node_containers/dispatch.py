"""Compatibility bridge from Temporal activities to SDK node containers."""

from __future__ import annotations

import asyncio
import queue
import threading
from contextlib import suppress
from typing import Any
from uuid import UUID

from sqlmodel import select
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.services.secret_service import create_secret_service
from syntara.integrations.lib.url_validation import validate_integration_configuration_no_ssrf
from syntara.integrations.models.integration import Integration, IntegrationProjectAssignment, IntegrationType
from syntara.integrations.models.integration_configuration import OpenShiftConfiguration
from syntara.workflows.audit import aap_job_execution
from syntara.workflows.models.execution import Execution
from syntara.workflows.node_containers.transport import TransportError, run_pod
from syntara.workflows.utils.output_mapping import apply_output_mapping
from syntara.workflows.workflow_engine.activities.credential_resolution_activity import _resolve_single_credential

MAX_STATUS_CODE = 255

NODE_IMAGES = {
    "http_request": "http-request",
    "agentic": "agent",
    "script": "script",
    "aap_job_template": "aap-job",
    "aap_workflow_job_template": "aap-workflow",
}


async def resolve_target(integration_id: str, execution_id: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve management credentials with the workflow project's authorization."""
    async with AsyncSessionLocal() as session:
        if execution_id:
            execution = await session.get(Execution, UUID(execution_id))
        else:
            execution = (
                await session.exec(
                    select(Execution).where(Execution.temporal_workflow_id == activity.info().workflow_id)
                )
            ).one_or_none()
        integration = await session.get(Integration, UUID(integration_id))
        if (
            execution is None
            or integration is None
            or not integration.enabled
            or integration.integration_type != IntegrationType.OPENSHIFT
        ):
            message = "OpenShift execution target is unavailable"
            raise ApplicationError(message, type="ConfigError", non_retryable=True)
        assignment = (
            await session.exec(
                select(IntegrationProjectAssignment).where(
                    IntegrationProjectAssignment.integration_id == integration.id,
                    IntegrationProjectAssignment.project_id == execution.project_id,
                )
            )
        ).first()
        if (
            assignment is None
            or not integration.management_credential_id
            or not isinstance(integration.configuration, OpenShiftConfiguration)
        ):
            message = "OpenShift integration is not configured for the workflow project"
            raise ApplicationError(
                message,
                type="ConfigError",
                non_retryable=True,
            )
        config = integration.configuration
        validate_integration_configuration_no_ssrf(config)
        resolved = await _resolve_single_credential(
            session,
            create_secret_service(session),
            activity.info().activity_id,
            str(integration.management_credential_id),
            # Infrastructure identity is authorized through the integration assignment.
            None,
        )
        token = resolved.get("extra_vars", {}).get("bearer_token")
        if not token:
            message = "OpenShift bearer credential is missing"
            raise ApplicationError(message, type="ConfigError", non_retryable=True)
        return {
            "base_url": config.base_url,
            "namespace": config.namespace,
            "ca_certificate": config.ca_certificate,
            "token": token,
        }, {
            "execution_id": str(execution.id),
            "project_id": str(execution.project_id),
            "created_by_user_id": str(execution.created_by) if execution.created_by else None,
        }


def map_result(frame: dict[str, Any], output_config: dict[str, str] | None, node_type: str) -> dict[str, Any]:
    """Keep the SDK envelope internal to the container boundary."""
    result = frame.get("result", {})
    if (
        not isinstance(result, dict)
        or type(result.get("StatusCode")) is not int
        or not 0 <= result["StatusCode"] <= MAX_STATUS_CODE
    ):
        message = "Invalid SDK result"
        raise ApplicationError(message, type="NodeProtocolError", non_retryable=True)
    raw = result.get("Result")
    if raw is not None and not isinstance(raw, dict):
        message = "Invalid node output"
        raise ApplicationError(message, type="NodeProtocolError", non_retryable=True)
    # Preserve the EP's current field selection for script outputs.
    if node_type == "script":
        output = (
            raw if output_config is None else {key: (raw or {})[key] for key in output_config if key in (raw or {})}
        )
    else:
        output = apply_output_mapping(raw or {}, output_config)
    if result["StatusCode"] != 0:
        failure = frame.get("error") or {}
        raise ApplicationError(
            result.get("ErrorMessage") or result.get("StatusMessage") or "Node failed",
            {"output": output},
            type=failure.get("type", "NodeExecutionError"),
            non_retryable=failure.get("retryable") is not True,
        )
    return {"output": output}


async def dispatch(  # noqa: C901, PLR0915 - compatibility boundary
    node_type: str,
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
    *,
    context: dict[str, Any] | None = None,
    operation: str = "execute",
) -> dict[str, Any]:
    """Run a disposable pod while keeping Temporal heartbeat/audit handling local."""
    settings = get_settings()
    route = input_config["_container_route"]
    if not route.get("integration_id") or not route.get("image"):
        message = "Container routing requires an OpenShift integration and image"
        raise ApplicationError(message, type="ConfigError", non_retryable=True)
    if node_type == "agentic" and settings.s2s_tls_enabled and not settings.node_container_agent_tls_secret:
        message = "Agent container requires its service TLS secret"
        raise ApplicationError(message, type="ConfigError", non_retryable=True)
    target, execution_context = await resolve_target(route["integration_id"], (context or {}).get("execution_id"))
    ctx = {
        **execution_context,
        **{key: value for key, value in (context or {}).items() if value is not None},
        "workflow_id": activity.info().workflow_id,
        "activity_id": activity.info().activity_id,
        "integration": input_config.get("_resolved_integration"),
    }
    resolved = input_config.get("_resolved_credentials")
    if node_type.startswith("aap_") and not resolved:
        resolved = {
            "extra_vars": {
                "aap_oauth_token": settings.aap_token.get_secret_value() if settings.aap_token else None,
                "aap_username": settings.aap_username,
                "aap_password": settings.aap_password.get_secret_value() if settings.aap_password else None,
            }
        }
    if node_type == "agentic":
        resolved = None  # AO resolves credential references; never export model/tool secrets.
        ctx.update(agent_base_url=settings.node_container_agent_base_url, agent_tls_enabled=settings.s2s_tls_enabled)
    invocation = {
        "version": 1,
        "operation": operation,
        "inputs": {key: value for key, value in input_config.items() if not key.startswith("_")},
        "credentials": {"resolved": resolved or {}},
        "workflow_context": ctx,
        "settings": {
            "workflow_http_request_allowed_hosts": settings.workflow_http_request_allowed_hosts,
            "aap_poll_interval_seconds": settings.aap_poll_interval_seconds,
        },
        "timeout_seconds": int(input_config.get("_engine_timeout_seconds", input_config.get("timeout", 300))),
        "max_output_bytes": int(input_config.get("_engine_max_output_bytes", 1048576)),
    }
    events: queue.Queue[dict[str, Any]] = queue.Queue()
    cancelled = threading.Event()
    partial: dict[str, Any] = {}

    def drain() -> None:
        while not events.empty():
            event = events.get_nowait()
            data = event.get("data", {})
            if event.get("event") == "heartbeat":
                partial.update(data.get("partial_output", {}))
            elif event.get("event") == "cleanup_failed":
                activity.logger.warning("Node pod cleanup failed: %s", data.get("pod"))
            elif event.get("event") in {"aap_launched", "aap_failed", "aap_completed"}:
                data = dict(data)
                template_id = data.pop("template_id", None)
                data.pop("actor_id", None)
                emit = getattr(aap_job_execution, "emit_" + event["event"].removeprefix("aap_"))
                actor = ctx.get("created_by_user_id")
                emit(UUID(ctx["execution_id"]), template_id, actor_id=UUID(actor) if actor else None, **data)
        activity.heartbeat({"stop_monitor": True, "partial_output": partial})

    task = asyncio.create_task(
        asyncio.to_thread(
            run_pod,
            target=target,
            image=route["image"],
            invocation=invocation,
            identity=f"{activity.info().workflow_id}:{activity.info().workflow_run_id}:{activity.info().activity_id}:{activity.info().attempt}",
            startup=route["startup_seconds"],
            grace=route["grace_seconds"],
            cancelled=cancelled,
            progress=events.put,
            tls_secret=settings.node_container_agent_tls_secret
            if node_type == "agentic" and settings.s2s_tls_enabled
            else None,
        )
    )
    try:
        while not task.done():
            drain()
            await asyncio.wait({task}, timeout=1)
        frame = task.result()
        drain()
        return map_result(frame, output_config, node_type)
    except asyncio.CancelledError:
        cancelled.set()
        with suppress(TimeoutError, TransportError):
            await asyncio.wait_for(asyncio.shield(task), timeout=route["grace_seconds"] + 35)
        raise
    except TransportError as exc:
        raise ApplicationError(
            str(exc),
            {"output": apply_output_mapping(partial, output_config)},
            type="NodeTransportError",
            non_retryable=not exc.retryable,
        ) from None
    finally:
        cancelled.set()
