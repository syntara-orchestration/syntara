"""Form prompt activity executor for workflow human-in-the-loop integration.

This module provides functionality to create, expire, and cancel form
prompts within workflows via the Forms API client.
"""

from typing import Any, NoReturn
from uuid import UUID

import structlog
from temporalio import activity, workflow
from temporalio.exceptions import ApplicationError
from temporalio.service import RPCError

with workflow.unsafe.imports_passed_through():
    from syntara.workflows.clients.form_prompts_client import (
        FormPromptsApiClient,
        FormPromptsApiClientError,
    )
    from syntara.workflows.workflow_engine import constants
    from syntara.workflows.workflow_engine.services.activity_sync_registry import get_activity_sync_service
from syntara.workflows.workflow_engine.models.form_prompt import FormPromptActivityInput
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName
from syntara.workflows.workflow_engine.utils.loop_iteration_ids import matches_loop_iteration_id

from .common import HEARTBEAT_STOP_MONITOR, ActivityExecutionError

logger = structlog.stdlib.get_logger(__name__)


def _is_form_prompt_for_node(stored_node_id: str, node_id: str) -> bool:
    """Return True if ``stored_node_id`` is this canvas node, including loop iterations.

    New rows store the canvas ID. Legacy rows may still have
    ``{node_id}_iter_{outer}_iter_{inner}...``. Exact match covers a specific
    iteration; suffix matching covers expire-by-canvas-id and leftover suffixes.
    """
    return matches_loop_iteration_id(stored_node_id, node_id)


class FormPromptActivityError(ActivityExecutionError):
    """Base exception for form prompt activity errors."""


@activity.defn(name=ActivityName.FORM_PROMPT)
async def create_form_prompt_activity(activity_input: FormPromptActivityInput) -> NoReturn:
    """Create a form prompt from a named, typed input object."""
    activity.heartbeat({HEARTBEAT_STOP_MONITOR: True})

    if not activity_input["project_id"]:
        msg = "Form prompt activity requires non-empty 'project_id'"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True)

    logger.info(
        "Creating form prompt via Forms API",
        base_url=constants.FORMS_API_BASE_URL,
        execution_id=activity_input["execution_id"],
        prompt_node_id=activity_input["prompt_node_id"],
        name=activity_input["name"],
    )

    request_data: dict[str, Any] = {
        "execution_id": activity_input["execution_id"],
        "project_id": activity_input["project_id"],
        "prompt_node_id": activity_input["prompt_node_id"],
        "name": activity_input["name"],
        "form_definition": activity_input["form_definition"],
        "timeout_at": activity_input["timeout_at"],
        "responder_user_ids": activity_input["responder_user_ids"],
        "responder_group_ids": activity_input["responder_group_ids"],
        "loop_iteration_path": activity_input["loop_iteration_path"] or [],
        "temporal_activity_id": activity_input["temporal_activity_id"],
        "message": activity_input["message"],
        "submit_label": activity_input["submit_label"],
        "success_message": activity_input["success_message"],
        "css_override": activity_input["css_override"],
    }

    try:
        async with FormPromptsApiClient(
            base_url=constants.FORMS_API_BASE_URL,
        ) as client:
            await client.create_form_prompt(request_data)
    except FormPromptsApiClientError as e:
        logger.exception(
            "Form prompt creation failed",
            execution_id=activity_input["execution_id"],
            prompt_node_id=activity_input["prompt_node_id"],
            error=str(e),
        )
        raise FormPromptActivityError(str(e)) from e
    except Exception as e:
        msg = f"Unexpected error creating form prompt: {e}"
        logger.exception(
            msg,
            execution_id=activity_input["execution_id"],
            prompt_node_id=activity_input["prompt_node_id"],
        )
        raise FormPromptActivityError(msg) from e

    activity.raise_complete_async()


async def _batch_update_form_prompts(
    execution_id: str,
    operation: str,
    batch_method_name: str,
    result_key: str,
    node_id: str | None = None,
) -> dict[str, Any]:
    """Shared helper for batch expire/cancel of pending form prompts.

    Args:
        execution_id: Parent workflow execution ID (UUID string).
        operation: Human-readable operation name for logging (e.g. "expire", "cancel").
        batch_method_name: Name of the FormPromptsApiClient method to call.
        result_key: Key for the count in the return dict (e.g. "expired_count").
        node_id: Optional node filter. When set, only prompts for this node are affected.

    Returns:
        Dict with {result_key: int} and optional error.

    """
    logger.info(
        "Batch %s form prompts",
        operation,
        execution_id=execution_id,
        node_id=node_id,
    )

    try:
        async with FormPromptsApiClient(
            base_url=constants.FORMS_API_BASE_URL,
        ) as client:
            pending = await client.list_form_prompts_by_execution(UUID(execution_id), status="pending")
            if node_id:
                pending = [p for p in pending if _is_form_prompt_for_node(str(p.get("prompt_node_id", "")), node_id)]

            if not pending:
                logger.info("No pending form prompts to %s", operation, execution_id=execution_id, node_id=node_id)
                return {result_key: 0}

            prompt_ids = [UUID(p["id"]) for p in pending]
            # Chunk requests to respect 100-item limit per batch
            batch_fn = getattr(client, batch_method_name)
            chunk_size = 100
            total_success = 0
            total_failed = 0

            for i in range(0, len(prompt_ids), chunk_size):
                chunk = prompt_ids[i : i + chunk_size]
                batch_result = await batch_fn(chunk)
                total_success += batch_result.get("total_success", 0)
                total_failed += batch_result.get("total_failed", 0)

            logger.info(
                "Batch %s form prompts completed",
                operation,
                execution_id=execution_id,
                node_id=node_id,
                success_count=total_success,
                failed_count=total_failed,
                total_prompts=len(prompt_ids),
            )
            return {result_key: total_success}

    except FormPromptsApiClientError as e:
        logger.warning("Failed to %s form prompts", operation, execution_id=execution_id, error=str(e))
        return {result_key: 0, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        logger.warning("Unexpected error during %s", operation, execution_id=execution_id, error=str(e))
        return {result_key: 0, "error": str(e)}


@activity.defn(name=ActivityName.EXPIRE_FORM_PROMPT)
async def expire_form_prompts_activity(
    execution_id: str,
    node_id: str | None = None,
) -> dict[str, Any]:
    """Expire pending form prompts.

    When node_id is given, only that node's pending prompts are expired (its own
    response window timed out). When node_id is None, all pending prompts for the
    execution are expired (the workflow reached a terminal state while other form
    prompt nodes were still awaiting a response).
    """
    return await _batch_update_form_prompts(execution_id, "expire", "batch_expire", "expired_count", node_id=node_id)


@activity.defn(name=ActivityName.CANCEL_FORM_PROMPT)
async def cancel_form_prompts_activity(
    execution_id: str,
) -> dict[str, Any]:
    """Cancel all pending form prompts when a workflow is cancelled."""
    return await _batch_update_form_prompts(execution_id, "cancel", "batch_cancel", "cancelled_count")


@activity.defn(name=ActivityName.FAIL_DETACHED_FORM_PROMPT)
async def fail_detached_form_prompt_activity(
    workflow_id: str,
    run_id: str | None,
    activity_id: str,
) -> None:
    """Fail the async-completion FORM_PROMPT activity for a detached form prompt node.

    Called as a local activity from the workflow when it completes while an
    approval branch is still pending. Resolves the dangling Temporal activity
    so it doesn't keep waiting forever.

    Args:
        workflow_id: Temporal workflow ID
        run_id: Temporal run ID
        activity_id: Temporal activity ID to fail

    """
    logger.info(
        "Failing detached form prompt activity",
        workflow_id=workflow_id,
        run_id=run_id,
        activity_id=activity_id,
    )

    sync_service = get_activity_sync_service()
    if sync_service is None:
        logger.warning(
            "Activity sync service not available; cannot fail detached form prompt activity",
            activity_id=activity_id,
            workflow_id=workflow_id,
        )
        return

    error = ApplicationError(
        "Form prompt abandoned: workflow completed via another path",
        type="FormPromptDetachedError",
        non_retryable=True,
    )

    try:
        handle = sync_service.temporal_client.get_async_activity_handle(
            workflow_id=workflow_id,
            run_id=run_id,
            activity_id=activity_id,
        )
        await handle.fail(error)
        logger.info(
            "Successfully failed detached form prompt activity",
            workflow_id=workflow_id,
            activity_id=activity_id,
        )
    except RPCError as rpc_err:
        # If the activity already completed or was cancelled elsewhere, swallow
        # the error. Common phrases from Temporal server responses:
        if any(phrase in str(rpc_err).lower() for phrase in ["not found", "already completed", "cannot find"]):
            logger.info(
                "Detached form prompt activity already resolved",
                workflow_id=workflow_id,
                activity_id=activity_id,
                error=str(rpc_err),
            )
        else:
            logger.warning(
                "Failed to fail detached form prompt activity",
                workflow_id=workflow_id,
                activity_id=activity_id,
                error=str(rpc_err),
            )
            raise
