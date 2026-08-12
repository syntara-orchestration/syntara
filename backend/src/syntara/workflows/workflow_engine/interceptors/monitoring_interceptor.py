"""Workflow interceptor for automatically scheduling activity monitoring.

Ensures activity monitoring starts for every workflow execution, even if the
worker restarts. Replaces the signal-based approach, which could be lost on
restart.

Scoped to ``orchestrator_workflow`` only. This interceptor runs globally on the
worker, so without that scope check it would also fire for
``scheduled_workflow_launcher`` (whose ``args[1]`` is a trigger_node_id
string, not a UUID) and fail with ``ValueError: badly formed hexadecimal
UUID string`` on every scheduled tick.
"""

from datetime import timedelta
from typing import Any

import structlog
from temporalio import workflow
from temporalio.worker import (
    ExecuteWorkflowInput,
    Interceptor,
    WorkflowInboundInterceptor,
    WorkflowInterceptorClassInput,
)

from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

logger = structlog.stdlib.get_logger(__name__)

# Only NexusWorkflow's run() signature carries execution_id at args[1] (see
# module docstring). Other workflow types registered on the same worker (e.g.
# ScheduledWorkflowLauncher) must be skipped.
_MONITORED_WORKFLOW_TYPES = frozenset({"orchestrator_workflow"})


class _MonitoringWorkflowInboundInterceptor(WorkflowInboundInterceptor):
    """Inbound interceptor that automatically starts activity monitoring for workflows.

    This interceptor is called when a workflow execution starts and schedules
    the activity monitoring task. It runs the monitoring activity outside the
    sandbox to perform I/O operations.
    """

    async def execute_workflow(self, input: ExecuteWorkflowInput) -> Any:  # noqa: A002, ANN401
        """Execute workflow with automatic monitoring setup.

        This method is called when a workflow starts. It schedules the monitoring
        activity and then proceeds with normal workflow execution.

        Args:
            input: Workflow execution input containing args and metadata

        Returns:
            Workflow execution result

        """
        # Args: [workflow_def_dict, execution_id, trigger_node_id, trigger_inputs,
        #        include_node_results, request_id, pre_resolved_outputs, stop_after_nodes]
        # Only valid for orchestrator_workflow — see module docstring for why other
        # workflow types must be excluded.
        min_args_for_monitoring = 2
        if len(input.args) >= min_args_for_monitoring and workflow.info().workflow_type in _MONITORED_WORKFLOW_TYPES:
            execution_id = input.args[1]
            temporal_workflow_id = workflow.info().workflow_id
            # request_id is the 6th argument (index 5), optional
            request_id_arg_index = 5
            request_id = input.args[request_id_arg_index] if len(input.args) > request_id_arg_index else None

            logger.info(
                "Starting activity monitoring for execution",
                execution_id=execution_id,
                temporal_workflow_id=temporal_workflow_id,
            )

            # Start activity monitoring in background (non-blocking)
            # This activity will handle:
            # 1. Waiting for the Execution record to be created in DB
            # 2. Checking if monitoring is already running
            # 3. Starting the monitoring if needed
            workflow.start_activity(
                ActivityName.ACTIVITY_MONITORING,
                args=[execution_id, temporal_workflow_id, request_id],
                activity_id="__internal__register_monitoring",
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=None,  # No automatic retry - activity handles retries internally
            )

        # Continue with normal workflow execution
        return await super().execute_workflow(input)


class MonitoringWorkflowInterceptor(Interceptor):
    """Interceptor that provides workflow monitoring functionality.

    This interceptor is registered with the Temporal worker and ensures that
    every workflow execution automatically starts activity monitoring.
    """

    def workflow_interceptor_class(
        self,
        input: WorkflowInterceptorClassInput,  # noqa: A002, ARG002
    ) -> type[WorkflowInboundInterceptor]:
        """Return the workflow inbound interceptor class.

        Args:
            input: Interceptor class input

        Returns:
            The monitoring workflow inbound interceptor class

        """
        return _MonitoringWorkflowInboundInterceptor
