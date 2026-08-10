"""Approval activity executor for workflow human approval integration.

This module provides functionality to create, expire, and cancel approval
requests within workflows via the Approvals API client.
"""

from typing import Any, NoReturn
from uuid import UUID

import structlog
from temporalio import activity, workflow
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from syntara.approvals.audit.approval import ApprovalExpiredEvent
    from syntara.audit.dispatcher import AuditEventDispatcher
    from syntara.workflows.clients.approvals_client import (
        ApprovalsApiClient,
        ApprovalsApiClientError,
    )
    from syntara.workflows.workflow_engine import constants
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

from .common import HEARTBEAT_STOP_MONITOR, ActivityExecutionError

logger = structlog.stdlib.get_logger(__name__)


class ApprovalActivityError(ActivityExecutionError):
    """Base exception for approval activity errors."""


@activity.defn(name=ActivityName.APPROVAL)
async def create_approval_request_activity(
    execution_id: str,
    approval_node_id: str,
    name: str,
    next_step_approved: dict[str, Any] | None,
    workflow_context: dict[str, Any],
    timeout_at: str | None = None,
    next_step_rejected: dict[str, Any] | None = None,
    approver_user_ids: list[str] | None = None,
    approver_group_ids: list[str] | None = None,
    project_id: str = "",
) -> NoReturn:
    """Create an approval request via the Approvals API.

    Called as a Temporal activity with async completion. Creates the approval
    request in the database, then calls raise_complete_async() so the activity
    stays STARTED in Temporal until externally completed via the callback endpoint.

    Args:
        execution_id: Parent workflow execution ID (UUID string).
        approval_node_id: Activity ID from workflow definition.
        name: Display name for the approval request.
        next_step_approved: First activity if approved (id, name, type), or None.
        workflow_context: Context dict (workflow_version_id, workflow_name, inputs, previous_step).
        timeout_at: ISO datetime string when the request expires, or None.
        next_step_rejected: First activity if rejected (id, name, type), or None.
        approver_user_ids: List of user UUIDs who can approve (None = any user with permission).
        approver_group_ids: List of group UUIDs whose members can approve.
        project_id: Project ID for the approval request (from parent execution).

    Raises:
        ApprovalActivityError: If approval request creation fails.

    """
    activity.heartbeat({HEARTBEAT_STOP_MONITOR: True})

    if not project_id:
        msg = "Approval activity requires non-empty 'project_id'"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True)

    logger.info(
        "Creating approval request via Approvals API",
        base_url=constants.APPROVALS_API_BASE_URL,
        execution_id=execution_id,
        approval_node_id=approval_node_id,
        name=name,
    )

    request_data: dict[str, Any] = {
        "execution_id": execution_id,
        "project_id": project_id,
        "approval_node_id": approval_node_id,
        "name": name,
        "next_step_approved": next_step_approved,
        "workflow_context": workflow_context,
        "timeout_at": timeout_at,
        "next_step_rejected": next_step_rejected,
        "approver_user_ids": approver_user_ids,
        "approver_group_ids": approver_group_ids,
    }

    try:
        async with ApprovalsApiClient(
            base_url=constants.APPROVALS_API_BASE_URL,
        ) as client:
            await client.create_approval(request_data)
    except ApprovalsApiClientError as e:
        logger.exception(
            "Approval request creation failed",
            execution_id=execution_id,
            approval_node_id=approval_node_id,
            error=str(e),
        )
        raise ApprovalActivityError(str(e)) from e
    except Exception as e:
        msg = f"Unexpected error creating approval request: {e}"
        logger.exception(msg, execution_id=execution_id, approval_node_id=approval_node_id)
        raise ApprovalActivityError(msg) from e

    activity.raise_complete_async()


async def _batch_update_approvals(
    execution_id: str,
    operation: str,
    batch_method_name: str,
    result_key: str,
    node_id: str | None = None,
) -> dict[str, Any]:
    """Shared helper for batch expire/cancel of pending approval requests.

    Args:
        execution_id: Parent workflow execution ID (UUID string).
        operation: Human-readable operation name for logging (e.g. "expire", "cancel").
        batch_method_name: Name of the ApprovalsApiClient method to call.
        result_key: Key for the count in the return dict (e.g. "expired_count").
        node_id: Optional node filter. When set, only approvals for this node are affected.

    Returns:
        Dict with {result_key: int} and optional error.

    """
    logger.info(
        "Batch %s approval requests",
        operation,
        execution_id=execution_id,
        node_id=node_id,
    )

    try:
        async with ApprovalsApiClient(
            base_url=constants.APPROVALS_API_BASE_URL,
        ) as client:
            pending = await client.list_approvals_by_execution(UUID(execution_id), status="pending")
            if node_id:
                pending = [a for a in pending if a.get("approval_node_id") == node_id]

            if not pending:
                logger.info("No pending approvals to %s", operation, execution_id=execution_id, node_id=node_id)
                return {result_key: 0}

            approval_ids = [UUID(a["id"]) for a in pending]
            batch_fn = getattr(client, batch_method_name)
            result = await batch_fn(approval_ids)

            count = result.get("total_success", 0)
            logger.info(
                "Batch %s approvals completed",
                operation,
                execution_id=execution_id,
                node_id=node_id,
                success_count=count,
                failed_count=result.get("total_failed", 0),
            )
            return {result_key: count, "_approval_ids": approval_ids}

    except ApprovalsApiClientError as e:
        logger.warning("Failed to %s approval requests", operation, execution_id=execution_id, error=str(e))
        return {result_key: 0, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        logger.warning("Unexpected error during %s", operation, execution_id=execution_id, error=str(e))
        return {result_key: 0, "error": str(e)}


@activity.defn(name=ActivityName.EXPIRE_APPROVAL)
async def expire_approval_requests_activity(
    execution_id: str,
    node_id: str,
) -> dict[str, Any]:
    """Expire pending approval requests for a specific node after its decision window."""
    result = await _batch_update_approvals(execution_id, "expire", "batch_expire", "expired_count", node_id=node_id)

    for approval_id in result.pop("_approval_ids", []):
        AuditEventDispatcher.dispatch(
            ApprovalExpiredEvent(
                approval_id=approval_id,
                execution_id=UUID(execution_id),
                approval_node_id=node_id,
            )
        )

    return result


@activity.defn(name=ActivityName.CANCEL_APPROVAL)
async def cancel_approval_requests_activity(
    execution_id: str,
) -> dict[str, Any]:
    """Cancel all pending approval requests when a workflow is cancelled."""
    result = await _batch_update_approvals(execution_id, "cancel", "batch_cancel", "cancelled_count")
    result.pop("_approval_ids", None)
    return result
