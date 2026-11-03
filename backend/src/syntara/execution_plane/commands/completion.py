"""Completion command handling for work dispatched to Execution Plane."""

from typing import Any
from uuid import UUID

import structlog
from execution_plane_client.commands.base import CommandPayload
from execution_plane_client.commands.control import Completion
from execution_plane_client.errors import ProtocolConflict
from execution_plane_client.protocol import MessageEnvelope, ResourceReference, TransportReceipt
from sqlmodel import col, select
from temporalio.exceptions import ApplicationError

from syntara.execution_plane.commands.context import AOCommandContext
from syntara.execution_plane.commands.errors import (
    CommandDependencyUnavailableError,
    CommandResourceNotFoundError,
)
from syntara.execution_plane.commands.results import AOCommandResult
from syntara.workflows.models.activity_execution import ActivityExecution
from syntara.workflows.models.execution import Execution

logger = structlog.stdlib.get_logger(__name__)


class CompletionCommandHandler:
    """Deliver a completion command to its originating Temporal activity."""

    @staticmethod
    def _failure_error(status: str, result: dict[str, Any]) -> ApplicationError:
        """Translate a non-completed EP status into a non-retryable activity failure."""
        if status == "cancelled":
            return ApplicationError(
                "Execution Plane work was cancelled before execution",
                result,
                type="ExecutionPlaneWorkCancelled",
                non_retryable=True,
            )
        if status == "reconciliation_required":
            message = "Execution Plane could not determine the work outcome"
            # Surface the Execution Plane's reason (worker crash, lost callback,
            # conflicting cold-start Job, ...) so executions are self-diagnosing.
            reason = str(result.get("error", "")).strip()
            if reason:
                message = f"{message}: {reason}"
            return ApplicationError(
                message,
                result,
                type="ExecutionPlaneReconciliationRequired",
                non_retryable=True,
            )
        error_message = str(result.get("error", "Execution Plane work failed"))
        error_type = str(result.get("error_type", "ScriptExecutionError"))
        return ApplicationError(error_message, result, type=error_type, non_retryable=True)

    async def _complete_activity(
        self,
        *,
        context: AOCommandContext,
        work_id: UUID,
        status: str,
        result: dict[str, Any],
    ) -> bool:
        """Complete or fail the async activity named by a work-item UUID."""
        row = (
            await context.session.exec(
                select(Execution.temporal_workflow_id, ActivityExecution.temporal_activity_id)
                .join(Execution, col(ActivityExecution.execution_id) == col(Execution.id))
                .where(col(ActivityExecution.id) == work_id)
            )
        ).first()
        if row is None:
            return False
        temporal_workflow_id, temporal_activity_id = row
        temporal_service = context.temporal_service
        if temporal_service is None:
            raise CommandDependencyUnavailableError

        if status == "completed":
            await temporal_service.complete_async_activity(
                temporal_workflow_id=temporal_workflow_id,
                activity_id=temporal_activity_id,
                result=result,
            )
        else:
            await temporal_service.fail_async_activity(
                temporal_workflow_id=temporal_workflow_id,
                activity_id=temporal_activity_id,
                error=self._failure_error(status, result),
            )
        return True

    async def handle(
        self, message: MessageEnvelope, payload: CommandPayload, context: AOCommandContext
    ) -> AOCommandResult:
        """Complete or fail the activity addressed by the originating command."""
        if not isinstance(payload, Completion):
            raise ProtocolConflict
        work_id = message.command.parent_command_id
        if work_id is None:
            raise ProtocolConflict
        if payload.resource is not None and (
            payload.resource.kind != "work_item" or payload.resource.resource_id != work_id
        ):
            raise ProtocolConflict

        statuses = {
            "succeeded": "completed",
            "failed": "failed",
            "cancelled": "cancelled",
            "outcome_unknown": "reconciliation_required",
        }
        delivered = await self._complete_activity(
            context=context,
            work_id=work_id,
            status=statuses[payload.status],
            result=payload.result,
        )
        if not delivered:
            raise CommandResourceNotFoundError
        logger.info(
            "Delivered Execution Plane completion command",
            command_id=str(message.command_id),
            status=payload.status,
        )
        resource = ResourceReference(kind="work_item", resource_id=work_id)
        return AOCommandResult(
            resource=resource,
            body=TransportReceipt(message_id=message.message_id, resource=resource),
        )
