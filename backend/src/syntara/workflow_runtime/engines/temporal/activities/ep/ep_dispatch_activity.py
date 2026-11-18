"""Submit script execution to the standalone Execution Plane HTTP service."""

from __future__ import annotations

import uuid
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, NoReturn

import structlog
from execution_plane_client.commands.work import WorkExecute, WorkloadInvocation
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from sqlmodel import col, select
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.execution_plane.client import (
    EP_AUDIENCE,
    EP_CLIENT_ID,
    ExecutionPlaneHttpClient,
    ExecutionPlaneRejectedError,
    ExecutionPlaneUnavailableError,
)
from syntara.execution_plane.registry.bindings import legacy_credential_bindings
from syntara.execution_plane.registry.repository import (
    execution_plane_plugin_credential_recipe_ids,
    execution_plane_plugin_input_schema,
    get_execution_plane_plugin,
)
from syntara.execution_plane.utils import execution_plane_work_item_id
from syntara.workflow_core.models import (
    ActivityName,
    BashScriptExecutorParameters,
    ExecutionPlaneExecutionProfile,
    ExecutionTargetProfile,
    PythonScriptExecutorParameters,
    ScriptExecutorParametersBase,
)
from syntara.workflow_runtime.engines.temporal.activities.common import HEARTBEAT_STOP_MONITOR
from syntara.workflow_runtime.engines.temporal.constants import ENGINE_MAX_OUTPUT_BYTES_KEY, ENGINE_TIMEOUT_SECONDS_KEY
from syntara.workflows.models.execution import Execution

if TYPE_CHECKING:
    from execution_plane_client.protocol import MessageEnvelope

logger = structlog.stdlib.get_logger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 300
_EXECUTION_PROFILE_FIELD = "execution_profile"
_EXECUTION_TARGET_SELECTOR_FIELD = "_execution_target_id"
_CREDENTIAL_BINDINGS_FIELD = "credential_bindings"
_CREDENTIAL_ID_FIELD = "credential_id"


def _workload_inputs(input_config: dict[str, Any]) -> dict[str, Any]:
    """Return only fields that belong to the plugin action contract."""
    return {
        key: value
        for key, value in input_config.items()
        if not key.startswith("_")
        and key not in {_EXECUTION_PROFILE_FIELD, _CREDENTIAL_BINDINGS_FIELD, _CREDENTIAL_ID_FIELD}
    }


def _build_invocation(
    input_config: dict[str, Any], step_identity: str, credential_recipe_ids: tuple[str, ...]
) -> dict[str, Any]:
    """Build the versioned SDK request before AO freezes it for activity retries."""
    explicit_bindings = input_config.get(_CREDENTIAL_BINDINGS_FIELD)
    legacy_credential_id = input_config.get(_CREDENTIAL_ID_FIELD)
    if legacy_credential_id is not None and explicit_bindings:
        message = "Workflow node cannot combine a legacy credential with explicit credential bindings"
        raise ApplicationError(message, type="ConfigError", non_retryable=True)
    try:
        credential_bindings = explicit_bindings or legacy_credential_bindings(
            legacy_credential_id, credential_recipe_ids
        )
    except ValueError as error:
        raise ApplicationError(str(error), type="ConfigError", non_retryable=True) from error

    inputs = _workload_inputs(input_config)
    max_output_bytes = input_config.get(ENGINE_MAX_OUTPUT_BYTES_KEY)
    if max_output_bytes is not None:
        inputs["max_output_bytes"] = max_output_bytes
    return {
        "step_revision_id": step_identity,
        "inputs": inputs,
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
        message = f"Script action input is invalid: {error.message}"
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


async def _submit_work(client: ExecutionPlaneHttpClient, message: MessageEnvelope, work_item_id: uuid.UUID) -> None:
    """Confirm acceptance of this UUID; completion is delivered only by callback."""
    try:
        receipt = await client.submit_command(message)
    except ExecutionPlaneRejectedError as exc:
        if exc.status_code != HTTPStatus.CONFLICT:
            raise
        # A duplicate confirms EP already owns this work. Its outcome belongs
        # to the completion callback, not the dispatch response.
    else:
        if (
            receipt.resource is None
            or receipt.resource.kind != "work_item"
            or receipt.resource.resource_id != work_item_id
        ):
            msg = "Execution Plane receipt does not identify the submitted work"
            raise ExecutionPlaneRejectedError(msg)


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


async def _dispatch_to_ep(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
    execution_id: uuid.UUID,
    execution_target_id: uuid.UUID | None,
    plugin_name: str,
) -> None:
    """Submit one stable command, treating duplicate acceptance as success."""
    settings = get_settings()
    if not settings.ep_api_url:
        msg = "Execution Plane API URL is not configured"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True)
    info = activity.info()
    work_item_id = execution_plane_work_item_id(execution_id, info.activity_id)
    selectors = _build_work_execute_selectors(execution_target_id)

    async with AsyncSessionLocal() as session:
        plugin = await get_execution_plane_plugin(session, plugin_name)
        if plugin is None:
            msg = f"No Execution Plane plugin is registered for Action '{plugin_name}'"
            raise ApplicationError(msg, type="ConfigError", non_retryable=True)
        image = plugin.image_reference
        step_identity = plugin.step_identity
        try:
            input_schema = execution_plane_plugin_input_schema(plugin)
            credential_recipe_ids = await execution_plane_plugin_credential_recipe_ids(session, plugin)
        except ValueError as error:
            raise ApplicationError(str(error), type="ConfigError", non_retryable=True) from error

    _validate_input_schema(_workload_inputs(input_config), input_schema)

    if not image:
        msg = f"No Execution Plane image is configured for Action '{plugin_name}'"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True)
    try:
        message = WorkExecute(
            work_item_id=work_item_id,
            runtime_context=await _work_runtime_context(execution_id),
            invocation=WorkloadInvocation.model_validate(
                _build_invocation(input_config, step_identity, credential_recipe_ids)
            ),
            image=image,
            selectors=selectors,
            output_config=output_config,
        ).to_message(
            source_id=EP_CLIENT_ID,
            destination_id=EP_AUDIENCE,
            client_id=EP_CLIENT_ID,
        )
    except ValueError:
        msg = "Script invocation is invalid for the Execution Plane command protocol"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None

    try:
        async with ExecutionPlaneHttpClient(timeout=settings.ep_request_timeout_seconds) as client:
            await _submit_work(client, message, work_item_id)
    except ExecutionPlaneRejectedError as exc:
        raise ApplicationError(str(exc), type="ExecutionPlaneRejected", non_retryable=True) from exc
    except ExecutionPlaneUnavailableError as exc:
        msg = f"Execution Plane is unavailable (work_item_id={work_item_id})"
        raise ApplicationError(msg, type="ExecutionPlaneUnavailable") from exc

    activity.logger.info("Script accepted by Execution Plane work_item_id=%s", work_item_id)


async def _execute_script_activity(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
    execution_id: str,
    *,
    parameters_model: type[ScriptExecutorParametersBase],
    plugin_name: str,
) -> NoReturn:
    """Validate and dispatch a script Action without returning its execution result.

    After EP accepts the command, raise_complete_async() exits this function while
    leaving the Temporal activity incomplete. The caller awaiting
    workflow.execute_activity() continues waiting. When EP later calls AO with the
    result, AO completes the activity through Temporal, resolving that caller's await.
    """
    activity.heartbeat({HEARTBEAT_STOP_MONITOR: True})

    if not get_settings().script_nodes_enabled:
        msg = "Script node execution is not enabled."
        raise ApplicationError(msg, type="ScriptNodeDisabled", non_retryable=True)

    try:
        # The workflow engine adds internal control fields to the activity
        # payload. They are consumed during dispatch but are not node parameters.
        parameters = {
            key: value for key, value in input_config.items() if not key.startswith("_") and key != _CREDENTIAL_ID_FIELD
        }
        config = parameters_model.model_validate(parameters)
        execution_uuid = uuid.UUID(execution_id)
    except Exception:  # noqa: BLE001
        msg = "Script activity configuration or execution ID is invalid"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None

    await _dispatch_to_ep(
        input_config,
        output_config,
        execution_uuid,
        _execution_target_id(config.execution_profile),
        plugin_name,
    )
    activity.raise_complete_async()


@activity.defn(name=ActivityName.SCRIPT_PYTHON)
async def execute_python_script_activity(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
    execution_id: str,
) -> NoReturn:
    """Dispatch a Python script and exit; EP's callback supplies the result to Temporal."""
    await _execute_script_activity(
        input_config,
        output_config,
        execution_id,
        parameters_model=PythonScriptExecutorParameters,
        plugin_name="script-python",
    )


@activity.defn(name=ActivityName.SCRIPT_BASH)
async def execute_bash_script_activity(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
    execution_id: str,
) -> NoReturn:
    """Dispatch a Bash script and exit; EP's callback supplies the result to Temporal."""
    await _execute_script_activity(
        input_config,
        output_config,
        execution_id,
        parameters_model=BashScriptExecutorParameters,
        plugin_name="script-bash",
    )
