"""Test fixtures and helpers for execution factory."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from nexus.workflows.models.execution import Execution, ExecutionStatus
from tests.integration.helpers.workflow import WorkflowFactory

if TYPE_CHECKING:
    from datetime import datetime

    from sqlmodel.ext.asyncio.session import AsyncSession

    from nexus.core.models import User
    from nexus.workflows.models import Workflow, WorkflowVersion


async def create_test_execution(
    session: AsyncSession,
    user: User,
    project_id: UUID,
    *,
    status: ExecutionStatus = ExecutionStatus.RUNNING,
) -> Execution:
    """Create a committed Execution with Workflow/WorkflowVersion FKs.

    Composes ``WorkflowFactory`` + ``ExecutionFactory`` and commits so a
    separate session (e.g. websocket ``endpoint_factory``) can see the row.
    Pass fixture ``test_project_id`` — do not use the ``workflow_factory``
    fixture that creates its own project.
    """
    wf, version = await WorkflowFactory(session, user, project_id).create(is_enabled=False)
    execution = await ExecutionFactory(session, user).create(wf, version, status=status)
    await session.commit()
    await session.refresh(execution)
    return execution


class ExecutionFactory:
    """Factory for creating executions with configurable status."""

    def __init__(self, session: AsyncSession, user: User) -> None:
        """Initialize with database session and user."""
        self.session = session
        self.user = user

    async def create(
        self,
        workflow: Workflow,
        version: WorkflowVersion,
        *,
        status: ExecutionStatus = ExecutionStatus.PENDING,
        completed_at: datetime | None = None,
        trigger_type: str | None = None,
        interface: str | None = None,
    ) -> Execution:
        """Create a single execution."""
        execution = Execution(
            workflow_id=workflow.id,
            workflow_version_id=version.id,
            temporal_workflow_id=f"t-{uuid4()}",
            status=status,
            created_by=self.user.id,
            completed_at=completed_at,
            input_data={},
            project_id=workflow.project_id,
            trigger_type=trigger_type,
            interface=interface,
        )
        self.session.add(execution)
        await self.session.flush()
        return execution

    async def create_many(
        self,
        workflow: Workflow,
        version: WorkflowVersion,
        status_counts: list[tuple[ExecutionStatus, int]],
        *,
        completed_at: datetime | None = None,
    ) -> list[Execution]:
        """Create executions with specified status counts.

        Args:
            workflow: Parent workflow.
            version: Workflow version.
            status_counts: List of (status, count) tuples.
            completed_at: Completion timestamp for terminal statuses.

        """
        executions = []
        terminal = {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED}
        for status, count in status_counts:
            for _ in range(count):
                ts = completed_at if status in terminal else None
                executions.append(await self.create(workflow, version, status=status, completed_at=ts))
        return executions
