"""Submit script execution to the standalone Execution Plane HTTP service."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from typing import Any

import structlog
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.core.config.base import get_settings
from syntara.execution_plane.bridge import mark_dispatch_accepted, persist_dispatch_binding
from syntara.execution_plane.client import (
    ExecutionPlaneHttpClient,
    ExecutionPlaneRejectedError,
    ExecutionPlaneUnavailableError,
)
from syntara.workflows.workflow_engine.activities.common import HEARTBEAT_STOP_MONITOR
from syntara.workflows.workflow_engine.constants import ENGINE_TIMEOUT_SECONDS_KEY
from syntara.workflows.workflow_engine.models.workflow_definition import (
    ActivityName,
    ScriptExecutorParameters,
)

logger = structlog.stdlib.get_logger(__name__)

INITIAL_RETRY_DELAY_SECONDS = 0.5
MAX_RETRY_DELAY_SECONDS = 10.0


def _stable_request_id(*, workflow_id: str, run_id: str, activity_id: str, namespace: str) -> str:
    identity = f"{namespace}:{workflow_id}:{run_id}:{activity_id}:generation:1"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


async def _dispatch_to_ep(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
    project_id: uuid.UUID,
) -> dict[str, Any] | None:
    """Persist AO's dispatch intent, then idempotently submit it to EP over HTTP."""
    settings = get_settings()
    info = activity.info()
    request_id = _stable_request_id(
        workflow_id=info.workflow_id,
        run_id=info.workflow_run_id,
        activity_id=info.activity_id,
        namespace=settings.temporal_namespace,
    )
    work_correlation_id = uuid.uuid5(uuid.NAMESPACE_URL, request_id)
    payload = {"input_config": input_config, "output_config": output_config}

    await persist_dispatch_binding(
        request_id=request_id,
        project_id=project_id,
        workflow_id=info.workflow_id,
        run_id=info.workflow_run_id,
        activity_id=info.activity_id,
        activity_attempt=info.attempt,
        task_token=info.task_token,
        payload=payload,
    )

    timeout_seconds = float(input_config.get(ENGINE_TIMEOUT_SECONDS_KEY, 300))
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    retry_delay = INITIAL_RETRY_DELAY_SECONDS

    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            msg = f"Execution Plane did not accept the script before its deadline (request {request_id})"
            raise ApplicationError(msg, type="ExecutionPlaneUnavailable")

        try:
            async with ExecutionPlaneHttpClient(timeout=min(settings.ep_request_timeout_seconds, remaining)) as client:
                response = await client.submit_work_item(
                    project_id=project_id,
                    request_id=request_id,
                    work_correlation_id=work_correlation_id,
                    payload=payload,
                )
        except ExecutionPlaneRejectedError as exc:
            raise ApplicationError(str(exc), type="ExecutionPlaneRejected", non_retryable=True) from exc
        except ExecutionPlaneUnavailableError as exc:
            remaining = deadline - loop.time()
            if remaining <= 0:
                msg = f"Execution Plane remained unavailable until the script deadline (request {request_id})"
                raise ApplicationError(msg, type="ExecutionPlaneUnavailable") from exc
            delay = min(retry_delay, remaining)
            activity.logger.warning(
                "Execution Plane unavailable; retrying with the same request ID in %.1fs",
                delay,
            )
            await asyncio.sleep(delay)
            retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY_SECONDS)
            continue

        work_item_id = uuid.UUID(str(response["id"]))
        state = str(response["status"])
        await mark_dispatch_accepted(
            request_id,
            work_item_id,
            terminal=state in {"completed", "failed", "cancelled"},
        )
        if state == "completed":
            result = response.get("result")
            return result if isinstance(result, dict) else {}
        if state in {"failed", "cancelled"}:
            result = response.get("result") or {}
            error_message = str(result.get("error", "Execution Plane work failed"))
            error_type = str(result.get("error_type", "ExecutionPlaneWorkFailed"))
            if state == "cancelled":
                error_message = "Execution Plane work was cancelled before execution"
                error_type = "ExecutionPlaneWorkCancelled"
            raise ApplicationError(error_message, type=error_type, non_retryable=True)
        if state not in {
            "pending",
            "claimed",
            "dispatched",
            "cancel_requested",
            "reconciliation_required",
        }:
            msg = f"Execution Plane returned unsupported work state '{state}'"
            raise ApplicationError(msg, type="ExecutionPlaneProtocolError", non_retryable=True)

        activity.logger.info("Script accepted by Execution Plane work_id=%s request_id=%s", work_item_id, request_id)
        return None


@activity.defn(name=ActivityName.SCRIPT)
async def execute_script_activity(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
    project_id: str,
) -> dict[str, Any]:
    """Validate and submit a script, then await AO-owned callback completion."""
    activity.heartbeat({HEARTBEAT_STOP_MONITOR: True})

    if not get_settings().script_nodes_enabled:
        msg = "Script node execution is not enabled."
        raise ApplicationError(msg, type="ScriptNodeDisabled", non_retryable=True)

    try:
        ScriptExecutorParameters.model_validate(input_config)
        project_uuid = uuid.UUID(project_id)
    except Exception:  # noqa: BLE001
        msg = "Script activity configuration or project scope is invalid"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None

    result = await _dispatch_to_ep(input_config, output_config, project_uuid)
    if result is None:
        activity.raise_complete_async()
        return {}
    return result
