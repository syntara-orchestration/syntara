"""Shared helpers for sub-workflow setup-activity integration tests.

The sub-workflow setup activity enforces same-project isolation by loading the
parent ``Execution`` and comparing its project to the child workflow's project.
Tests that invoke the activity therefore need a real parent execution with valid
foreign keys. ``seed_parent_execution`` creates a minimal parent Workflow +
WorkflowVersion + Execution in a given project and returns the parent execution id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

_PARENT_DEF = {"schema_version": "2.0.0", "triggers": [], "nodes": [], "edges": []}


async def seed_parent_execution(
    session: AsyncSession,
    *,
    created_by: UUID,
    project_id: UUID,
    status: ExecutionStatus = ExecutionStatus.RUNNING,
) -> UUID:
    """Create a real parent Workflow + WorkflowVersion + Execution in ``project_id``.

    Returns the parent ``Execution`` id. The row exists so the setup activity's
    same-project gate can load it; pass a ``project_id`` that differs from the child
    to exercise cross-project rejection.
    """
    wf_id = uuid4()
    session.add(Workflow(id=wf_id, name=f"parent-{wf_id.hex[:8]}", created_by=created_by, project_id=project_id))
    await session.flush()

    ver_id = uuid4()
    session.add(
        WorkflowVersion(
            id=ver_id,
            workflow_id=wf_id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=_PARENT_DEF,
            created_by=created_by,
        )
    )
    await session.flush()

    parent_exec_id = uuid4()
    session.add(
        Execution(
            id=parent_exec_id,
            workflow_id=wf_id,
            workflow_version_id=ver_id,
            project_id=project_id,
            temporal_workflow_id=f"parent-{parent_exec_id.hex[:8]}",
            status=status,
            created_by=created_by,
            updated_by=created_by,
        )
    )
    await session.commit()
    return parent_exec_id
