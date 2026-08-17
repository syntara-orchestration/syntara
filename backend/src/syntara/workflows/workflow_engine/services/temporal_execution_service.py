"""Execution service for managing workflow executions.

This service provides high-level operations for starting, monitoring, and managing
workflow executions via Temporal.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import structlog
from temporalio.client import Client
from temporalio.service import RPCError

from syntara.core.config.base import TEMPORAL_DEFAULT_BACKGROUND_TASK_QUEUE, get_settings
from syntara.core.exceptions import SafeValueError
from syntara.core.tls.temporal import build_temporal_tls_config
from syntara.metrics.dependencies import get_metrics_recorder
from syntara.metrics.types import ComponentLabel, MetricType
from syntara.workflows.workflow_engine.client_interceptor import WorkflowAuthClientInterceptor
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow
from syntara.workflows.workflow_engine.models.responses import (
    WorkflowStartResponse,
)
from syntara.workflows.workflow_engine.models.workflow_definition import resolve_trigger_node

logger = structlog.stdlib.get_logger(__name__)


class TemporalExecutionService:
    """Service for managing workflow executions."""

    def __init__(
        self,
        temporal_client: Client,
        task_queue: str,
        background_task_queue: str = TEMPORAL_DEFAULT_BACKGROUND_TASK_QUEUE,
    ) -> None:
        """Initialize temporal execution service.

        Note:
            For most use cases, use create_temporal_execution_service() factory function instead,
            which provides sensible defaults for temporal_address, namespace, and task_queue.

        Args:
            temporal_client: Temporal client for workflow operations
            task_queue: Task queue name for user workflow execution
            background_task_queue: Task queue name for builtin workflow execution.

        """
        self.temporal_client = temporal_client
        self.task_queue = task_queue
        self.background_task_queue = background_task_queue

    async def start_workflow(
        self,
        workflow_def: dict[str, Any],
        workflow_name: str,
        trigger_node_id: str,
        input_data: dict[str, Any] | None = None,
        workflow_id: str | None = None,
        request_id: UUID | None = None,
        *,
        pre_resolved_outputs: dict[str, dict[str, Any]] | None = None,
        stop_after_nodes: list[str] | None = None,
        include_node_results: bool = False,
        workflow_metadata: dict[str, Any] | None = None,
        execution_id: str | None = None,
        is_builtin: bool = False,
    ) -> WorkflowStartResponse:
        """Start a V2 workflow from dict definition.

        Args:
            workflow_def: V2 workflow definition as dict (triggers + nodes + edges)
            workflow_name: Name for this workflow execution
            input_data: Input parameters for the workflow trigger
            workflow_id: Optional workflow ID (auto-generated if not provided)
            request_id: Optional X-Request-Id (UUID) from the originating HTTP request
            trigger_node_id: Trigger node ID to start from
            pre_resolved_outputs: Mock outputs for predecessor nodes (for test executions)
            stop_after_nodes: Stop execution after these nodes complete (for test executions)
            include_node_results: Include node results in workflow response (for test executions)
            workflow_metadata: Optional workflow/execution metadata for expression resolution
            execution_id: Optional pre-generated execution ID (auto-generated if not provided)
            is_builtin: When True, routes the workflow to the background task queue instead of
                the user workflow queue. Built-in workflows (Document Conversion, Agent
                Execution) run on a dedicated deployment to prevent worker starvation.

        Returns:
            WorkflowStartResponse containing:
                - execution_id: Internal execution ID (database record ID)
                - workflow_id: Internal workflow ID
                - temporal_workflow_id: Temporal workflow ID (for Temporal API calls)
                - temporal_run_id: Temporal run ID (specific execution run)
                - status: Execution status
                - started_at: ISO 8601 timestamp when workflow started

        Raises:
            SafeValueError: If workflow definition is invalid (missing required fields)
            Exception: If workflow fails to start

        Example:
            >>> service = TemporalExecutionService(client)
            >>> result = await service.start_workflow(
            ...     workflow_def={'schema_version': '2.0.0', 'triggers': [...], 'nodes': [...], 'edges': [...]},
            ...     workflow_name='my-workflow',
            ...     input_data={'user_id': 123}
            ... )
            >>> print(result.workflow_id)  # Internal workflow ID
            >>> print(result.temporal_workflow_id)  # Use this for Temporal API calls

        """
        try:
            recorder = get_metrics_recorder()

            # Validate V2 workflow structure (basic check)
            logger.info("Validating V2 workflow definition", workflow_name=workflow_name)
            schema_version = workflow_def.get("schema_version")
            if schema_version != "2.0.0":
                msg = (
                    f"Unsupported schema_version: {schema_version}. "
                    "Only V2 workflows (schema_version=2.0.0) are supported."
                )
                raise SafeValueError(msg)  # noqa: TRY301

            if not workflow_def.get("triggers"):
                msg = "V2 workflow must have at least one trigger"
                raise SafeValueError(msg)  # noqa: TRY301

            trigger_node_id, _ = resolve_trigger_node(workflow_def, trigger_node_id)

            # Generate internal workflow ID if not provided
            if workflow_id is None:
                workflow_id = str(uuid4())

            # Create execution record (will be the database record id)
            if execution_id is None:
                execution_id = str(uuid4())

            # Generate Temporal workflow ID (must be unique for Temporal)
            temporal_workflow_id = f"{workflow_name}-{execution_id}"

            logger.info(
                "Starting V2 workflow execution",
                workflow_id=workflow_id,
                execution_id=execution_id,
                temporal_workflow_id=temporal_workflow_id,
                trigger_id=trigger_node_id,
            )

            with recorder.time(
                MetricType.TEMPORAL_EXECUTION_SERVICE_DURATION,
                labels={"component": ComponentLabel.EXECUTION_SERVICE.value, "workflow_name": workflow_name},
            ):
                handle = await self.temporal_client.start_workflow(
                    OrchestratorWorkflow.run,
                    args=[
                        workflow_def,
                        execution_id,
                        trigger_node_id,
                        input_data or {},
                        include_node_results,
                        request_id,
                        pre_resolved_outputs,
                        stop_after_nodes,
                        workflow_metadata,
                    ],
                    id=temporal_workflow_id,
                    task_queue=self.background_task_queue if is_builtin else self.task_queue,
                )

            logger.info(
                "Workflow started successfully",
                temporal_workflow_id=temporal_workflow_id,
                temporal_run_id=handle.first_execution_run_id,
            )

            # Return execution information
            return WorkflowStartResponse(
                execution_id=execution_id,
                workflow_id=workflow_id,
                temporal_workflow_id=temporal_workflow_id,
                temporal_run_id=handle.first_execution_run_id,
                status="running",
                started_at=datetime.now(UTC).isoformat(),
            )

        except Exception:
            logger.exception("Failed to start workflow", workflow_name=workflow_name)
            raise

    async def cancel_workflow(
        self,
        temporal_workflow_id: str,
    ) -> None:
        """Cancel a running workflow.

        Sends a cancellation signal to Temporal. The actual status update
        happens asynchronously via activity_sync_service.

        Args:
            temporal_workflow_id: Temporal workflow ID

        Raises:
            Exception: If cancellation fails

        """
        try:
            handle = self.temporal_client.get_workflow_handle(temporal_workflow_id)

            logger.info("Cancelling workflow", temporal_workflow_id=temporal_workflow_id)

            await handle.cancel()

            logger.info("Workflow cancelled successfully", temporal_workflow_id=temporal_workflow_id)

        except RPCError as e:
            if "not found" in str(e).lower():
                logger.info(
                    "Workflow already completed, cancel is a no-op",
                    temporal_workflow_id=temporal_workflow_id,
                )
                return
            logger.exception("Failed to cancel workflow", temporal_workflow_id=temporal_workflow_id)
            raise

    async def complete_async_activity(
        self,
        temporal_workflow_id: str,
        activity_id: str,
        result: Any,  # noqa: ANN401
    ) -> None:
        """Complete an async activity that called raise_complete_async().

        Args:
            temporal_workflow_id: Temporal workflow ID
            activity_id: Activity ID from workflow definition
            result: Result value to return to the workflow

        """
        try:
            handle = self.temporal_client.get_async_activity_handle(
                workflow_id=temporal_workflow_id,
                run_id=None,
                activity_id=activity_id,
            )
            await handle.complete(result)

            logger.info(
                "Async activity completed",
                activity_id=activity_id,
                temporal_workflow_id=temporal_workflow_id,
            )

        except RPCError as e:
            if "not found" in str(e).lower():
                logger.warning(
                    "Async activity already completed or timed out (idempotent no-op)",
                    activity_id=activity_id,
                    temporal_workflow_id=temporal_workflow_id,
                )
                return
            logger.exception(
                "Failed to complete async activity",
                activity_id=activity_id,
                temporal_workflow_id=temporal_workflow_id,
            )
            raise

    async def fail_async_activity(
        self,
        temporal_workflow_id: str,
        activity_id: str,
        error: Exception,
    ) -> None:
        """Fail an async activity that called raise_complete_async().

        Args:
            temporal_workflow_id: Temporal workflow ID
            activity_id: Activity ID from workflow definition
            error: Error to report as the activity failure

        """
        try:
            handle = self.temporal_client.get_async_activity_handle(
                workflow_id=temporal_workflow_id,
                run_id=None,
                activity_id=activity_id,
            )
            await handle.fail(error)

            logger.info(
                "Async activity failed",
                activity_id=activity_id,
                temporal_workflow_id=temporal_workflow_id,
            )

        except RPCError as e:
            if "not found" in str(e).lower():
                logger.warning(
                    "Async activity already completed or timed out (idempotent no-op)",
                    activity_id=activity_id,
                    temporal_workflow_id=temporal_workflow_id,
                )
                return
            logger.exception(
                "Failed to fail async activity",
                activity_id=activity_id,
                temporal_workflow_id=temporal_workflow_id,
            )
            raise


async def create_temporal_execution_service(
    temporal_address: str | None = None,
    namespace: str | None = None,
    task_queue: str | None = None,
) -> TemporalExecutionService:
    """Create a temporal execution service with a new Temporal client.

    Args:
        temporal_address: Temporal server address (default from settings)
        namespace: Temporal namespace (default from settings)
        task_queue: Task queue name (default from settings)

    Returns:
        TemporalExecutionService instance

    Example:
        >>> service = await create_temporal_execution_service()
        >>> result = await service.start_yaml_workflow(...)

    """
    settings = get_settings()
    temporal_address = temporal_address or settings.temporal_address
    namespace = namespace or settings.temporal_namespace
    task_queue = task_queue or settings.task_queue

    client = await Client.connect(
        temporal_address,
        namespace=namespace,
        tls=build_temporal_tls_config(),
        interceptors=[WorkflowAuthClientInterceptor()],
    )
    # TODO: Handle how TemporalExecutionService is dispatched/deployed  # noqa: TD002, TD003
    # via containerization. This will be addressed in a future Containerization & Deployment ticket.
    return TemporalExecutionService(client, task_queue, background_task_queue=settings.background_task_queue)
