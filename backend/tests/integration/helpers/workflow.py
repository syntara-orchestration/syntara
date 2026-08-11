"""Integration-test-only factories for workflows and activity executions."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.workflows.models import Workflow, WorkflowVersion
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow_publish_event import PublishAction, WorkflowPublishEvent
from tests.helpers.workflow import create_minimal_workflow_definition


class WorkflowFactory:
    """Factory for creating workflows with versions in integration tests."""

    def __init__(self, session: AsyncSession, user: User, project_id: UUID) -> None:
        """Initialize with database session, user, and project scope."""
        self.session = session
        self.user = user
        self.project_id = project_id

    async def create(
        self,
        name: str | None = None,
        *,
        is_enabled: bool = True,
    ) -> tuple[Workflow, WorkflowVersion]:
        """Create a workflow with a version. Returns (workflow, version)."""
        name = name or f"wf-{uuid4().hex[:8]}"
        wf = Workflow(
            name=name,
            created_by=self.user.id,
            is_enabled=False,
            current_version=1,
            project_id=self.project_id,
        )
        self.session.add(wf)
        version = WorkflowVersion(
            workflow_id=wf.id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=create_minimal_workflow_definition(name=name),
            created_by=self.user.id,
        )
        self.session.add(version)
        await self.session.flush()
        if is_enabled:
            wf.published_version_id = version.id
            wf.is_enabled = True
            publish_event = WorkflowPublishEvent(
                workflow_id=wf.id,
                version_id=version.id,
                action=PublishAction.PUBLISHED,
                actor_id=self.user.id,
            )
            self.session.add(publish_event)
        return wf, version

    async def create_many(
        self,
        count: int,
        *,
        is_enabled: bool = True,
        prefix: str = "wf",
    ) -> list[tuple[Workflow, WorkflowVersion]]:
        """Create multiple workflows. Returns list of (workflow, version) tuples."""
        results = []
        for i in range(count):
            results.append(await self.create(f"{prefix}-{i}-{uuid4().hex[:6]}", is_enabled=is_enabled))
        return results


class ActivitiesFactory:
    """Factory for creating test activity executions in integration tests.

    Unlike ``ExecutionsFactory``, the parent ``Execution`` is passed to
    ``create_activities`` so that a single injected factory can create
    activities for different executions.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize with database session."""
        self.session = session

    async def create_activities(
        self,
        execution: Execution,
        names: list[str],
        *,
        status: ActivityStatus = ActivityStatus.COMPLETED,
        duration_seconds: float = 1.5,
    ) -> list[ActivityExecution]:
        """Create activity executions with timing data."""
        now = datetime.now(UTC)
        is_terminal = status in {
            ActivityStatus.COMPLETED,
            ActivityStatus.FAILED,
            ActivityStatus.SKIPPED,
            ActivityStatus.CANCELLED,
        }
        activities = [
            ActivityExecution(
                execution_id=execution.id,
                activity_name=name,
                temporal_activity_id=f"temporal-{uuid4()}",
                status=status,
                node_type="script",
                started_at=now - timedelta(seconds=duration_seconds),
                completed_at=now if is_terminal else None,
                input_data={},
                output_data={},
            )
            for name in names
        ]
        self.session.add_all(activities)
        await self.session.commit()
        return activities


class ExecutionsFactory:
    """Factory class for creating test executions with configurable properties."""

    def __init__(self, session: AsyncSession, workflow: Workflow, user: User) -> None:
        """Initialize the ExecutionsFactory with database session and required entities."""
        self.session = session
        self.workflow = workflow
        self.user = user

    async def create_executions(
        self,
        count: int,
        status: ExecutionStatus = ExecutionStatus.PENDING,
        labels: dict[str, str] | None = None,
    ) -> list[Execution]:
        """Create multiple test executions."""
        result = await self.session.exec(
            select(WorkflowVersion.id).where(
                WorkflowVersion.workflow_id == self.workflow.id,
                WorkflowVersion.version == self.workflow.current_version,
            )
        )
        version_id: UUID = result.one()

        executions: list[Execution] = [
            Execution(
                workflow_id=self.workflow.id,
                workflow_version_id=version_id,
                temporal_workflow_id=f"exec-{uuid4()}",
                status=status,
                created_by=self.user.id,
                input_data={},
                labels=labels or {},
                project_id=self.workflow.project_id,
            )
            for _ in range(count)
        ]
        self.session.add_all(executions)
        await self.session.commit()
        return executions
