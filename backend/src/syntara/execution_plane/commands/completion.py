"""Completion command handling for work dispatched to Execution Plane."""

from typing import Any
from uuid import UUID

import structlog
from execution_plane_client.commands.base import CommandPayload
from execution_plane_client.commands.control import Completion, CompletionStatus
from execution_plane_client.errors import ProtocolConflict
from execution_plane_client.handlers import HandlingResult
from execution_plane_client.protocol import MessageEnvelope, ResourceReference
from sqlmodel import col, select
from temporalio.exceptions import ApplicationError

from syntara.execution_plane.commands.context import AOCommandContext
from syntara.execution_plane.commands.errors import CommandDependencyUnavailableError
from syntara.workflows.models.activity_execution import ActivityExecution
from syntara.workflows.models.execution import Execution

logger = structlog.stdlib.get_logger(__name__)


class CompletionCommandHandler:
    """Deliver a completion command to its originating Temporal activity."""

    @staticmethod
    def _failure_error(status: CompletionStatus, result: dict[str, Any]) -> ApplicationError:
        """Translate a non-completed EP status into a non-retryable activity failure."""
        if status is CompletionStatus.CANCELLED:
            return ApplicationError(
                "Execution Plane work was cancelled before execution",
                result,
                type="ExecutionPlaneWorkCancelled",
                non_retryable=True,
            )
        if status is CompletionStatus.RECONCILIATION_REQUIRED:
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
        status: CompletionStatus,
        result: dict[str, Any],
    ) -> None:
        """Complete or fail the async activity named by a work-item UUID."""
        row = (
            await context.session.exec(
                select(Execution.temporal_workflow_id, ActivityExecution.temporal_activity_id)
                .join(Execution, col(ActivityExecution.execution_id) == col(Execution.id))
                .where(col(ActivityExecution.id) == work_id)
            )
        ).first()
        if row is None:
            logger.warning(
                "Ignoring Execution Plane completion without a matching AO activity",
                work_id=work_id,
            )
            return
        temporal_workflow_id, temporal_activity_id = row
        temporal_service = context.temporal_service
        if temporal_service is None:
            raise CommandDependencyUnavailableError

        if status is CompletionStatus.COMPLETED:
            await temporal_service.complete_async_activity(
                temporal_workflow_id=temporal_workflow_id,
                activity_id=temporal_activity_id,
                result=result,
            )
        elif status is CompletionStatus.CANCELLED:
            await temporal_service.report_cancellation_async_activity(
                temporal_workflow_id=temporal_workflow_id,
                activity_id=temporal_activity_id,
            )
        else:
            await temporal_service.fail_async_activity(
                temporal_workflow_id=temporal_workflow_id,
                activity_id=temporal_activity_id,
                error=self._failure_error(status, result),
            )

    async def handle(
        self, message: MessageEnvelope, payload: CommandPayload, context: AOCommandContext
    ) -> HandlingResult:
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

        await self._complete_activity(
            context=context,
            work_id=work_id,
            status=payload.status,
            result=payload.result,
        )
        logger.info(
            "Delivered Execution Plane completion command",
            command_id=str(message.command_id),
            status=payload.status,
        )
        resource = ResourceReference(kind="work_item", resource_id=work_id)
        return HandlingResult(resource=resource)
