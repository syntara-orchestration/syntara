"""Submit plugin actions to the standalone Execution Plane HTTP service."""

from __future__ import annotations

import asyncio
import uuid
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import structlog
from execution_plane_client.commands.work import WorkExecute, WorkloadInvocation
from execution_plane_client.models.work_item import WorkItemStatus
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError
from sqlmodel import col, select
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.execution_plane import utils as execution_plane_utils
from syntara.execution_plane.client import (
    EP_AUDIENCE,
    EP_CLIENT_ID,
    ExecutionPlaneHttpClient,
    ExecutionPlaneRejectedError,
    ExecutionPlaneUnavailableError,
)
from syntara.execution_plane.registry.bindings import legacy_credential_bindings
from syntara.execution_plane.registry.stub import PluginRegistryError, StubPluginRegistry
from syntara.execution_plane.utils import execution_plane_container_image
from syntara.workflow_core.models import (
    ActivityName,
    ExecutionPlaneExecutionProfile,
    ExecutionTargetProfile,
    NodeType,
)
from syntara.workflow_runtime.engines.temporal.activities.common import HEARTBEAT_STOP_MONITOR
from syntara.workflow_runtime.engines.temporal.constants import ENGINE_TIMEOUT_SECONDS_KEY
from syntara.workflows.models.execution import Execution

if TYPE_CHECKING:
    from execution_plane_client.protocol import MessageEnvelope

logger = structlog.stdlib.get_logger(__name__)

INITIAL_RETRY_DELAY_SECONDS = 0.5
MAX_RETRY_DELAY_SECONDS = 10.0
_DEFAULT_TIMEOUT_SECONDS = 300
_EXECUTION_PROFILE_FIELD = "execution_profile"
_EXECUTION_TARGET_SELECTOR_FIELD = "_execution_target_id"
_CREDENTIAL_BINDINGS_FIELD = "credential_bindings"
_CREDENTIAL_ID_FIELD = "credential_id"
_PLUGIN_REGISTRY = StubPluginRegistry()


def _workload_inputs(input_config: dict[str, Any]) -> dict[str, Any]:
    """Return only fields that belong to the plugin action contract."""
    return {
        key: value
        for key, value in input_config.items()
        if not key.startswith("_")
        and key not in {_EXECUTION_PROFILE_FIELD, _CREDENTIAL_BINDINGS_FIELD, _CREDENTIAL_ID_FIELD}
    }


def _build_invocation(input_config: dict[str, Any], node_type: str, step_revision_id: str) -> dict[str, Any]:
    """Build the versioned SDK request before AO freezes it for activity retries."""
    explicit_bindings = input_config.get(_CREDENTIAL_BINDINGS_FIELD)
    legacy_credential_id = input_config.get(_CREDENTIAL_ID_FIELD)
    if legacy_credential_id is not None and explicit_bindings:
        message = "Workflow node cannot combine a legacy credential with explicit credential bindings"
        raise PluginRegistryError(message)
    credential_bindings = explicit_bindings or legacy_credential_bindings(
        legacy_credential_id, node_type, _PLUGIN_REGISTRY
    )
    return {
        "step_revision_id": step_revision_id,
        "inputs": _workload_inputs(input_config),
        "credential_bindings": credential_bindings,
        "timeout_seconds": int(
            input_config.get(
                ENGINE_TIMEOUT_SECONDS_KEY,
                input_config.get("timeout") or _DEFAULT_TIMEOUT_SECONDS,
            )
        ),
    }


def _validate_input_schema(inputs: dict[str, Any], schema: dict[str, Any]) -> None:
    """Reject an action request before it reaches Execution Plane dispatch."""
    try:
        Draft202012Validator(schema).validate(inputs)
    except JsonSchemaValidationError as error:
        message = f"Plugin action input is invalid: {error.message}"
        raise ApplicationError(message, type="ConfigError", non_retryable=True) from None


async def _work_runtime_context(execution_id: uuid.UUID) -> dict[str, object]:
    """Build plugin-visible context from the persisted Execution and its owner IDs.

    Values are UUID strings for Execution.id, Project.id, and Workflow.id,
    used to correlate and filter work items in EP.
    """
    async with AsyncSessionLocal() as session:
        row = (
            await session.exec(
                select(Execution.project_id, Execution.workflow_id).where(col(Execution.id) == execution_id)
            )
        ).first()
    if row is None:
        message = "Execution does not exist"
        raise ApplicationError(message, type="ContextError", non_retryable=True)
    return {
        "execution_id": str(execution_id),
        "project_id": str(row[0]),
        "workflow_id": str(row[1]),
    }


async def _submit_and_read_work(
    client: ExecutionPlaneHttpClient, message: MessageEnvelope, work_item_id: uuid.UUID
) -> dict[str, Any]:
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
            or receipt.resource.resource_id != work_item_id
        ):
            msg = "Execution Plane receipt does not identify the submitted work"
            raise ExecutionPlaneRejectedError(msg)
    return await client.get_work_item(work_item_id=work_item_id)


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


def _action_contract(node_type: str) -> tuple[str, dict[str, Any]]:
    """Resolve the registry contract required to dispatch a plugin action."""
    try:
        manifest = _PLUGIN_REGISTRY.action_manifest(node_type)
        step_revision_id = _PLUGIN_REGISTRY.step_revision_id(node_type)
        input_schema = _PLUGIN_REGISTRY.input_schema(node_type)
    except PluginRegistryError as error:
        raise ApplicationError(str(error), type="ConfigError", non_retryable=True) from error

    runtime = manifest.get("spec", {}).get("runtime", {})
    if not isinstance(runtime, dict) or runtime.get("kind") != "custom-runner":
        message = f"Plugin action for node type '{node_type}' does not use the Execution Plane runtime"
        raise ApplicationError(message, type="ConfigError", non_retryable=True)
    return step_revision_id, input_schema


async def _dispatch_to_ep(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
    node_type: str,
    step_revision_id: str,
    execution_id: uuid.UUID,
    execution_target_id: uuid.UUID | None,
) -> None:
    """Submit a stable work command and recover existing work after an ambiguous retry."""
    settings = get_settings()
    info = activity.info()
    work_item_id = execution_plane_utils.execution_plane_work_item_id(execution_id, info.activity_id)
    selectors = _build_work_execute_selectors(execution_target_id)

    image = execution_plane_container_image(node_type)
    if image is None:
        msg = f"No Execution Plane container image configured for node type '{node_type}'"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True)
    try:
        message = WorkExecute(
            work_item_id=work_item_id,
            runtime_context=await _work_runtime_context(execution_id),
            invocation=WorkloadInvocation.model_validate(_build_invocation(input_config, node_type, step_revision_id)),
            image=image,
            selectors=selectors,
            output_config=output_config,
        ).to_message(
            source_id=EP_CLIENT_ID,
            destination_id=EP_AUDIENCE,
            client_id=EP_CLIENT_ID,
        )
    except (ValueError, PluginRegistryError):
        msg = "Plugin action invocation is invalid for the Execution Plane command protocol"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None

    timeout_seconds = float(input_config.get(ENGINE_TIMEOUT_SECONDS_KEY, 300))
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    retry_delay = INITIAL_RETRY_DELAY_SECONDS

    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            msg = f"Execution Plane did not accept the plugin action before its deadline (work_item_id={work_item_id})"
            raise ApplicationError(msg, type="ExecutionPlaneUnavailable")

        try:
            async with ExecutionPlaneHttpClient(timeout=min(settings.ep_request_timeout_seconds, remaining)) as client:
                response = await _submit_and_read_work(client, message, work_item_id)
        except ExecutionPlaneRejectedError as exc:
            raise ApplicationError(str(exc), type="ExecutionPlaneRejected", non_retryable=True) from exc
        except ExecutionPlaneUnavailableError as exc:
            remaining = deadline - loop.time()
            if remaining <= 0:
                msg = (
                    f"Execution Plane remained unavailable until the plugin action deadline "
                    f"(work_item_id={work_item_id})"
                )
                raise ApplicationError(msg, type="ExecutionPlaneUnavailable") from exc
            delay = min(retry_delay, remaining)
            activity.logger.warning(
                "Execution Plane unavailable; retrying with the same work_item_id in %.1fs",
                delay,
            )
            await asyncio.sleep(delay)
            retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY_SECONDS)
            continue

        try:
            WorkItemStatus(response["status"])
        except ValueError:
            msg = f"Execution Plane returned unsupported work state '{response['status']}'"
            raise ApplicationError(msg, type="ExecutionPlaneProtocolError", non_retryable=True) from None

        activity.logger.info("Plugin action accepted by Execution Plane work_item_id=%s", work_item_id)
        break


@activity.defn(name=ActivityName.PLUGIN)
async def execute_plugin_action_activity(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
    node_type: str,
    execution_id: str,
) -> None:
    """Validate and submit a plugin action, then await AO-owned callback completion."""
    activity.heartbeat({HEARTBEAT_STOP_MONITOR: True})

    if node_type == NodeType.SCRIPT and not get_settings().script_nodes_enabled:
        msg = "Script node execution is not enabled."
        raise ApplicationError(msg, type="ScriptNodeDisabled", non_retryable=True)

    step_revision_id, input_schema = _action_contract(node_type)
    _validate_input_schema(_workload_inputs(input_config), input_schema)
    try:
        execution_profile = (
            ExecutionPlaneExecutionProfile.model_validate(input_config.get(_EXECUTION_PROFILE_FIELD))
            if input_config.get(_EXECUTION_PROFILE_FIELD) is not None
            else None
        )
        execution_uuid = uuid.UUID(execution_id)
    except (ValidationError, ValueError):
        msg = "Plugin action configuration or execution ID is invalid"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None

    await _dispatch_to_ep(
        input_config,
        output_config,
        node_type,
        step_revision_id,
        execution_uuid,
        _execution_target_id(execution_profile),
    )
    raise_complete_async = activity.raise_complete_async
    raise_complete_async()
