"""Submit script execution to the standalone Execution Plane HTTP service."""

from __future__ import annotations

import asyncio
import uuid
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, cast

import structlog
from execution_plane_client.commands.work import WorkExecute, WorkloadInvocation
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.core.config.base import get_settings
from syntara.execution_plane.client import (
    EP_AUDIENCE,
    EP_CLIENT_ID,
    ExecutionPlaneHttpClient,
    ExecutionPlaneRejectedError,
    ExecutionPlaneUnavailableError,
)
from syntara.workflows.workflow_engine.activities.common import HEARTBEAT_STOP_MONITOR
from syntara.workflows.workflow_engine.constants import ENGINE_TIMEOUT_SECONDS_KEY
from syntara.workflows.workflow_engine.models.workflow_definition import (
    ActivityName,
    ExecutionPlaneExecutionProfile,
    ExecutionTargetProfile,
    ScriptExecutorParameters,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from execution_plane_client.protocol import MessageEnvelope

logger = structlog.stdlib.get_logger(__name__)

__all__ = ["activity", "asyncio", "execute_script_activity"]

INITIAL_RETRY_DELAY_SECONDS = 0.5
MAX_RETRY_DELAY_SECONDS = 10.0
_NODE_TYPE = "script"
_STEP_REVISION_ID = "script.v1"
_DEFAULT_TIMEOUT_SECONDS = 300
_EXECUTION_PROFILE_FIELD = "execution_profile"
_EXECUTION_TARGET_SELECTOR_FIELD = "_execution_target_id"


def _build_invocation(input_config: dict[str, Any], info: Any) -> dict[str, Any]:  # noqa: ANN401
    """Build the versioned SDK request before AO freezes it for activity retries."""
    return {
        "workflow_run_id": info.workflow_run_id,
        "step_revision_id": _STEP_REVISION_ID,
        "inputs": {
            key: value
            for key, value in input_config.items()
            if not key.startswith("_") and key != _EXECUTION_PROFILE_FIELD
        },
        "runtime_context": {},
        "timeout_seconds": int(
            input_config.get(
                ENGINE_TIMEOUT_SECONDS_KEY,
                input_config.get("timeout") or _DEFAULT_TIMEOUT_SECONDS,
            )
        ),
    }


async def _submit_and_read_work(client: ExecutionPlaneHttpClient, message: MessageEnvelope) -> dict[str, Any]:
    """Recover work after duplicate submission; receipts contain no work state."""
    try:
        receipt = await client.submit_command(message)
    except ExecutionPlaneRejectedError as exc:
        if exc.status_code != HTTPStatus.CONFLICT:
            raise
        # A prior POST may have committed before its response was lost.
        # The ActivityExecution UUID identifies the same work on every retry.
    else:
        if (
            receipt.resource is None
            or receipt.resource.kind != "work_item"
            or receipt.resource.resource_id != message.command_id
        ):
            msg = "Execution Plane receipt does not identify the submitted work"
            raise ExecutionPlaneRejectedError(msg)
    return await client.get_work_item(work_item_id=message.command_id)


def _build_work_execute_selectors(execution_target_id: uuid.UUID | None) -> dict[str, str]:
    """Build placement selectors for a selected Execution Target."""
    if execution_target_id is None:
        return {}
    return {_EXECUTION_TARGET_SELECTOR_FIELD: str(execution_target_id)}


def _execution_target_id(execution_profile: ExecutionPlaneExecutionProfile | None) -> uuid.UUID | None:
    """Resolve the target UUID when the current profile selects an Execution Target."""
    if isinstance(execution_profile, ExecutionTargetProfile):
        return execution_profile.execution_target_id
    return None


async def _dispatch_to_ep(  # noqa: C901, PLR0915 - service handoff and Temporal retry policy
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
    execution_id: uuid.UUID,
    execution_target_id: uuid.UUID | None,
) -> dict[str, Any] | None:
    """Submit a stable work command and recover existing work after an ambiguous retry."""
    settings = get_settings()
    info = activity.info()
    workflow_id = info.workflow_id
    run_id = info.workflow_run_id
    if workflow_id is None or run_id is None:
        msg = "Temporal activity context is missing workflow or run identity"
        raise ApplicationError(msg, type="ContextError", non_retryable=True)

    work_item_id = uuid.uuid5(execution_id, info.activity_id)
    selectors = _build_work_execute_selectors(execution_target_id)

    image = settings.node_container_images.get(_NODE_TYPE)
    if not image:
        msg = f"No Execution Plane container image configured for node type '{_NODE_TYPE}'"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True)
    try:
        message = WorkExecute(
            invocation=WorkloadInvocation.model_validate(_build_invocation(input_config, info)),
            image=image,
            selectors=selectors,
            output_config=output_config,
        ).to_message(
            source_id=EP_CLIENT_ID,
            destination_id=EP_AUDIENCE,
            client_id=EP_CLIENT_ID,
            command_id=work_item_id,
        )
    except ValueError:
        msg = "Script invocation is invalid for the Execution Plane command protocol"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None

    timeout_seconds = float(input_config.get(ENGINE_TIMEOUT_SECONDS_KEY, 300))
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    retry_delay = INITIAL_RETRY_DELAY_SECONDS

    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            msg = f"Execution Plane did not accept the script before its deadline (work_item_id={work_item_id})"
            raise ApplicationError(msg, type="ExecutionPlaneUnavailable")

        try:
            async with ExecutionPlaneHttpClient(timeout=min(settings.ep_request_timeout_seconds, remaining)) as client:
                response = await _submit_and_read_work(client, message)
        except ExecutionPlaneRejectedError as exc:
            raise ApplicationError(str(exc), type="ExecutionPlaneRejected", non_retryable=True) from exc
        except ExecutionPlaneUnavailableError as exc:
            remaining = deadline - loop.time()
            if remaining <= 0:
                msg = f"Execution Plane remained unavailable until the script deadline (work_item_id={work_item_id})"
                raise ApplicationError(msg, type="ExecutionPlaneUnavailable") from exc
            delay = min(retry_delay, remaining)
            activity.logger.warning(
                "Execution Plane unavailable; retrying with the same work_item_id in %.1fs",
                delay,
            )
            await asyncio.sleep(delay)
            retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY_SECONDS)
            continue

        state = str(response["status"])
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
            raise ApplicationError(error_message, result, type=error_type, non_retryable=True)
        if state not in {
            "pending",
            "claimed",
            "dispatched",
            "cancel_requested",
            "reconciliation_required",
        }:
            msg = f"Execution Plane returned unsupported work state '{state}'"
            raise ApplicationError(msg, type="ExecutionPlaneProtocolError", non_retryable=True)

        activity.logger.info("Script accepted by Execution Plane work_item_id=%s", work_item_id)
        return None


@activity.defn(name=ActivityName.SCRIPT)
async def execute_script_activity(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
    execution_id: str,
) -> dict[str, Any]:
    """Validate and submit a script, then await AO-owned callback completion."""
    activity.heartbeat({HEARTBEAT_STOP_MONITOR: True})

    if not get_settings().script_nodes_enabled:
        msg = "Script node execution is not enabled."
        raise ApplicationError(msg, type="ScriptNodeDisabled", non_retryable=True)

    try:
        config = ScriptExecutorParameters.model_validate(input_config)
        execution_uuid = uuid.UUID(execution_id)
    except Exception:  # noqa: BLE001
        msg = "Script activity configuration or execution ID is invalid"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None

    result = await _dispatch_to_ep(
        input_config,
        output_config,
        execution_uuid,
        _execution_target_id(config.execution_profile),
    )
    if result is None:
        raise_complete_async = cast("Callable[[], Any]", activity.raise_complete_async)
        raise_complete_async()
        return {}
    return result
