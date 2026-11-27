"""Completion command handling for work dispatched to Execution Plane."""

from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

import structlog
from execution_plane_client.commands.base import CommandPayload
from execution_plane_client.commands.control import Completion, CompletionStatus
from execution_plane_client.errors import ProtocolConflict
from execution_plane_client.handlers import HandlingResult
from execution_plane_client.protocol import MessageEnvelope, ResourceReference
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from sqlmodel import col, select
from temporalio.exceptions import ApplicationError

from syntara.execution_plane.commands.context import AOCommandContext
from syntara.execution_plane.commands.errors import CommandDependencyUnavailableError, CommandResourceNotFoundError
from syntara.execution_plane.registry.repository import (
    execution_plane_plugin_output_schema,
    get_execution_plane_plugin_by_node_type,
)
from syntara.execution_plane.utils import execution_plane_work_item_id
from syntara.workflow_core.models import NodeType
from syntara.workflow_runtime.engines.temporal.utils.loop_iteration_ids import strip_loop_iteration_suffixes
from syntara.workflows.models.activity_execution import ActivityExecution
from syntara.workflows.models.execution import Execution

logger = structlog.stdlib.get_logger(__name__)


class CompletionCommandHandler:
    """Deliver a completion command to its originating Temporal activity."""

    @staticmethod
    async def _output_validation_error(
        context: AOCommandContext, node_type: NodeType, result: dict[str, Any]
    ) -> ApplicationError | None:
        """Return an error when a completed result violates its action contract."""
        plugin = await get_execution_plane_plugin_by_node_type(context.session, node_type)
        if plugin is None:
            message = f"No Execution Plane plugin is registered for node type '{node_type}'"
            return ApplicationError(message, type="ExecutionPlaneProtocolError", non_retryable=True)

        try:
            schema = execution_plane_plugin_output_schema(plugin)
        except ValueError as error:
            message = f"Execution Plane completion has no plugin action output contract: {error}"
            return ApplicationError(message, type="ExecutionPlaneProtocolError", non_retryable=True)

        output = result.get("output")
        if not isinstance(output, dict):
            return ApplicationError(
                "Execution Plane result does not contain an output object",
                type="ExecutionPlaneProtocolError",
                non_retryable=True,
            )
        try:
            Draft202012Validator(schema).validate(output)
        except JsonSchemaValidationError as error:
            message = f"Execution Plane result violates the plugin action output schema: {error.message}"
            return ApplicationError(message, type="ExecutionPlaneProtocolError", non_retryable=True)
        return None

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
        runtime_context: Mapping[str, object] | None,
    ) -> bool:
        """Complete or fail the async activity named by a work-item UUID."""
        row = (
            await context.session.exec(
                select(
                    Execution.temporal_workflow_id, ActivityExecution.temporal_activity_id, ActivityExecution.node_type
                )
                .join(Execution, col(ActivityExecution.execution_id) == col(Execution.id))
                .where(col(ActivityExecution.id) == work_id)
            )
        ).first()
        if row is None:
            row = await self._correlate_activity_from_runtime_context(
                context=context,
                work_id=work_id,
                runtime_context=runtime_context,
            )
        if row is None:
            return False
        temporal_workflow_id, temporal_activity_id, raw_node_type = row
        node_type = NodeType(raw_node_type)
        if node_type is NodeType.AGENTIC:
            # AO Task Agent work is observed by InvocationExecutor, which persists
            # the AO invocation result before sending its established workflow signal.
            # Completing this async activity from EP would race that finalization.
            return True
        temporal_service = context.temporal_service
        if temporal_service is None:
            raise CommandDependencyUnavailableError

        output_validation_error = (
            await self._output_validation_error(context, node_type, result)
            if status is CompletionStatus.COMPLETED
            else None
        )
        if output_validation_error is not None:
            await temporal_service.fail_async_activity(
                temporal_workflow_id=temporal_workflow_id,
                activity_id=temporal_activity_id,
                error=output_validation_error,
            )
        elif status is CompletionStatus.COMPLETED:
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
        return True

    @staticmethod
    async def _correlate_activity_from_runtime_context(
        *,
        context: AOCommandContext,
        work_id: UUID,
        runtime_context: Mapping[str, object] | None,
    ) -> tuple[str, str, NodeType] | None:
        """Resolve loop-body work whose canvas row uses a different primary key."""
        execution_id = runtime_context.get("execution_id") if runtime_context else None
        temporal_activity_id = runtime_context.get("temporal_activity_id") if runtime_context else None
        if not isinstance(execution_id, str) or not isinstance(temporal_activity_id, str):
            return None
        try:
            execution_uuid = UUID(execution_id)
        except ValueError:
            return None
        if work_id != execution_plane_work_item_id(execution_uuid, temporal_activity_id):
            return None

        base_activity_id = strip_loop_iteration_suffixes(temporal_activity_id)
        row = (
            await context.session.exec(
                select(
                    Execution.temporal_workflow_id,
                    ActivityExecution.temporal_activity_id,
                    ActivityExecution.node_type,
                )
                .join(Execution, col(ActivityExecution.execution_id) == col(Execution.id))
                .where(
                    col(ActivityExecution.execution_id) == execution_uuid,
                    col(ActivityExecution.activity_name) == base_activity_id,
                )
            )
        ).first()
        if row is None:
            return None
        return cast("tuple[str, str, NodeType]", (row[0], temporal_activity_id, row[2]))

    async def handle(
        self, message: MessageEnvelope, payload: CommandPayload, context: AOCommandContext
    ) -> HandlingResult:
        """Complete or fail the activity addressed by the work-item identifier."""
        if not isinstance(payload, Completion):
            raise ProtocolConflict
        work_id = payload.work_item_id

        delivered = await self._complete_activity(
            context=context,
            work_id=work_id,
            status=payload.status,
            result=payload.result,
            runtime_context=payload.runtime_context,
        )
        if not delivered:
            raise CommandResourceNotFoundError
        logger.info(
            "Delivered Execution Plane completion command",
            work_item_id=str(work_id),
            message_id=str(message.message_id),
            status=payload.status,
        )
        resource = ResourceReference(kind="work_item", resource_id=work_id)
        return HandlingResult(resource=resource)
