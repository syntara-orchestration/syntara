"""Scheduled workflow launcher for Temporal Schedule integration.

When a Temporal Schedule fires, it starts the ``ScheduledWorkflowLauncher``
workflow which delegates DB setup to the ``ScheduledExecutionLauncher``
activity, then starts ``NexusWorkflow`` as a child workflow and waits for
it to complete. This keeps the launcher alive for the full execution
lifecycle so Temporal's schedule overlap policy (Skip/Buffer/etc.) applies
to the actual work, not just the setup phase.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from temporalio import activity, workflow
from temporalio.exceptions import ApplicationError
from temporalio.workflow import ParentClosePolicy

with workflow.unsafe.imports_passed_through():
    import structlog
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.config.base import get_settings
    from syntara.core.models.principal import service_principal_id
    from syntara.metrics.dependencies import get_metrics_recorder
    from syntara.metrics.types import MetricType
    from syntara.workflows.exceptions import WorkflowNotPublishedError
    from syntara.workflows.models.execution import Execution, ExecutionStatus
    from syntara.workflows.models.workflow import Workflow
    from syntara.workflows.models.workflow_version import WorkflowVersion
    from syntara.workflows.utils.schedule_parser import build_schedule_id
    from syntara.workflows.utils.workflow_metadata import build_workflow_metadata, resolve_user_display_name
    from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName

    logger = structlog.stdlib.get_logger(__name__)

# Timeout for the setup activity. This covers DB queries + metadata
# preparation, so 60 seconds provides ample headroom.
_LAUNCHER_ACTIVITY_NAME = "setup_scheduled_execution"
_LAUNCHER_ACTIVITY_TIMEOUT_SECONDS = 60


@workflow.defn(name="scheduled_workflow_launcher")
class ScheduledWorkflowLauncher:
    """Temporal workflow that launches a NexusWorkflow on behalf of a schedule.

    This is the action target for Temporal Schedules. When a schedule fires,
    Temporal starts this workflow which delegates to a setup activity for DB
    operations, then starts NexusWorkflow as a child workflow.

    The launcher stays alive while NexusWorkflow runs, so Temporal's schedule
    overlap policy (Skip/Buffer One/Buffer All) correctly detects whether a
    previous execution is still in progress.
    """

    @workflow.run
    async def run(self, workflow_id: str, trigger_node_id: str) -> dict[str, str]:
        """Launch a scheduled workflow execution.

        Args:
            workflow_id: UUID of the workflow to execute (as string).
            trigger_node_id: Trigger node ID within the workflow definition.

        Returns:
            Dict with execution_id and temporal_workflow_id of the started workflow.

        """
        setup_result: dict[str, Any] = await workflow.execute_activity(
            _LAUNCHER_ACTIVITY_NAME,
            args=[workflow_id, trigger_node_id],
            start_to_close_timeout=timedelta(seconds=_LAUNCHER_ACTIVITY_TIMEOUT_SECONDS),
        )

        execution_id = setup_result["execution_id"]
        temporal_workflow_id = setup_result["temporal_workflow_id"]

        await workflow.execute_child_workflow(
            "orchestrator_workflow",
            args=[
                setup_result["workflow_definition"],
                execution_id,
                trigger_node_id,
                setup_result["input_data"],
                False,
                None,
                None,
                None,
                setup_result["workflow_metadata"],
            ],
            id=temporal_workflow_id,
            task_queue=setup_result["task_queue"],
            parent_close_policy=ParentClosePolicy.REQUEST_CANCEL,
        )

        return {
            "execution_id": execution_id,
            "temporal_workflow_id": temporal_workflow_id,
        }


class ScheduledExecutionLauncher:
    """Class-based Temporal activity that sets up scheduled workflow executions.

    Receives a ``session_factory`` and ``task_queue`` at construction time
    (injected during worker startup) to avoid creating new DB engines and
    Temporal clients per invocation.

    The activity handles DB operations for the launcher workflow:
    1. Load published workflow definition from DB
    2. Prepare execution identity and metadata
    3. Create Execution record in DB

    Starting NexusWorkflow is handled by the launcher workflow via
    ``execute_child_workflow``.

    """

    def __init__(
        self,
        session_factory: Callable[..., AsyncSession],
        task_queue: str,
    ) -> None:
        """Initialize with worker-provided dependencies.

        Args:
            session_factory: Async SQLModel session factory (e.g., ``AsyncSessionLocal``).
            task_queue: Temporal task queue name for starting NexusWorkflow.

        """
        self._session_factory = session_factory
        self._task_queue = task_queue

    @activity.defn(name=_LAUNCHER_ACTIVITY_NAME)
    async def run(self, workflow_id_str: str, trigger_node_id: str) -> dict[str, Any]:
        """Set up a scheduled workflow execution.

        Loads the published workflow version, creates the Execution record in
        the database using the service principal identity, and returns all data
        needed for the launcher workflow to start NexusWorkflow as a child
        workflow. Records schedule timing metadata and Prometheus metrics.

        Args:
            workflow_id_str: UUID of the workflow (as string).
            trigger_node_id: Trigger node ID to start from.

        Returns:
            Dict with execution setup data for child workflow start.

        Raises:
            ApplicationError: Non-retryable, if the workflow is missing,
                soft-deleted, disabled, or has no published version.

        """
        workflow_id = UUID(workflow_id_str)

        # Capture schedule timing from Temporal activity info
        info = activity.info()
        scheduled_at = info.scheduled_time
        triggered_at = info.started_time

        logger.info(
            "Setting up scheduled execution",
            workflow_id=workflow_id_str,
            trigger_node_id=trigger_node_id,
            scheduled_at=scheduled_at.isoformat(),
            triggered_at=triggered_at.isoformat(),
        )

        recorder = get_metrics_recorder()

        try:
            result = await self._create_execution(workflow_id, trigger_node_id, scheduled_at, triggered_at)

            try:
                recorder.record(
                    MetricType.SCHEDULED_TRIGGER_FIRES,
                    value=1,
                    labels={"status": "success"},
                )
                latency_ms = (triggered_at - scheduled_at).total_seconds() * 1000
                recorder.record(
                    MetricType.SCHEDULED_TRIGGER_LATENCY,
                    value=latency_ms,
                    labels={},
                )
            except Exception:  # noqa: BLE001
                logger.debug("Failed to record success metric", exc_info=True)

            return result
        except Exception as exc:
            try:
                recorder.record(
                    MetricType.SCHEDULED_TRIGGER_FIRES,
                    value=1,
                    labels={"status": "error"},
                )
            except Exception:  # noqa: BLE001
                logger.debug("Failed to record error metric", exc_info=True)
            if isinstance(exc, WorkflowNotPublishedError):
                # Permanent state: workflow is missing, soft-deleted, disabled,
                # or has no published version.  Mark non-retryable so Temporal
                # does not retry the activity forever (AAP-86776).
                raise ApplicationError(
                    str(exc),
                    type="WorkflowNotPublishedError",
                    non_retryable=True,
                ) from exc
            raise

    async def _create_execution(
        self,
        workflow_id: UUID,
        trigger_node_id: str,
        scheduled_at: datetime,
        triggered_at: datetime,
    ) -> dict[str, Any]:
        """Set up execution record and return data for child workflow start.

        Phase 1: Load workflow + published version (read session)
        Phase 2: Prepare execution identity and metadata
        Phase 3: Create Execution record in DB (write session)

        Returns all data the launcher workflow needs to start NexusWorkflow
        as a child workflow.
        """
        # Phase 1: Load published workflow definition (read-only session)
        settings = get_settings()
        svc_principal_id = service_principal_id(settings.service_identity)
        async with self._session_factory() as session:
            wf_workflow, wf_version = await self._load_published_workflow(session, workflow_id)
            wf_id = wf_workflow.id
            wf_name = wf_workflow.name
            wf_project_id = wf_workflow.project_id
            wf_version_id = wf_version.id
            workflow_def = wf_version.workflow_definition

            author_name = await resolve_user_display_name(session, wf_workflow.created_by)

        # Phase 2: Prepare execution identity and metadata
        pre_generated_execution_id = str(uuid4())
        temporal_workflow_id = f"{wf_name}-{pre_generated_execution_id}"
        workflow_metadata = build_workflow_metadata(
            workflow_name=wf_name,
            workflow_id=wf_id,
            workflow_version=wf_version.version,
            workflow_published=True,
            workflow_author=author_name,
            project_id=wf_project_id,
            execution_id=pre_generated_execution_id,
            execution_mode="scheduled",
            created_by=author_name,
            created_by_user_id=str(wf_workflow.created_by),
            created_at=triggered_at.isoformat(),
            workflow_version_id=wf_version_id,
        )
        input_data = {
            "scheduled_at": scheduled_at.isoformat(),
            "triggered_at": triggered_at.isoformat(),
        }

        execution_id = UUID(pre_generated_execution_id)

        logger.info(
            "Scheduled execution prepared",
            execution_id=str(execution_id),
            temporal_workflow_id=temporal_workflow_id,
        )

        # Phase 3: Create Execution record in DB with schedule metadata
        async with self._session_factory() as session:
            execution = Execution(
                id=execution_id,
                workflow_id=wf_id,
                workflow_version_id=wf_version_id,
                project_id=wf_project_id,
                temporal_workflow_id=temporal_workflow_id,
                status=ExecutionStatus.PENDING,
                input_data=input_data,
                trigger_node_id=trigger_node_id,
                trigger_type=ActivityName.SCHEDULED_TRIGGER.value,
                interface=None,
                created_by=svc_principal_id,
                updated_by=svc_principal_id,
                execution_metadata={
                    "trigger_type": ActivityName.SCHEDULED_TRIGGER,
                    "schedule_id": build_schedule_id(str(workflow_id), trigger_node_id),
                    "scheduled_at": scheduled_at.isoformat(),
                    "triggered_at": triggered_at.isoformat(),
                },
            )

            session.add(execution)
            await session.commit()

        logger.info(
            "Scheduled execution created",
            execution_id=str(execution_id),
            workflow_id=str(workflow_id),
            trigger_node_id=trigger_node_id,
        )

        return {
            "execution_id": str(execution_id),
            "temporal_workflow_id": temporal_workflow_id,
            "workflow_definition": workflow_def,
            "trigger_node_id": trigger_node_id,
            "input_data": input_data,
            "task_queue": self._task_queue,
            "workflow_metadata": workflow_metadata,
        }

    @staticmethod
    async def _load_published_workflow(
        session: AsyncSession,
        workflow_id: UUID,
    ) -> tuple[Workflow, WorkflowVersion]:
        """Load workflow and its published version from the database.

        Raises:
            WorkflowNotPublishedError: If the workflow is not found or not published.

        """
        result = await session.exec(
            select(Workflow, WorkflowVersion)
            .join(
                WorkflowVersion,
                WorkflowVersion.id == Workflow.published_version_id,  # type: ignore[arg-type]
            )
            .where(Workflow.id == workflow_id)
            .where(Workflow.deleted_at.is_(None))  # type: ignore[union-attr]
            .where(Workflow.is_enabled == True)  # noqa: E712
        )
        row = result.first()
        if row is None:
            raise WorkflowNotPublishedError(workflow_id)
        return row
