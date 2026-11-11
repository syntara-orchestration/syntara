"""Persisted-status integration tests for sub-workflow node finalization.

A sub-workflow node executes via an internal setup activity plus a Temporal
child workflow, so no ACTIVITY_TASK_COMPLETED event reaches its per-node
activity row; the row stays PENDING until ``_finalize_non_terminal_activities``.
These tests drive that finalizer against the real, alembic-built PostgreSQL
schema and assert the **persisted** ``activity_execution.status`` after commit,
covering the FAILED > COMPLETED > SKIPPED precedence and mixed ``for_each``
outcomes in both iteration orders.

Note: per-iteration activity rows are not currently produced for sub-workflow
nodes (they are created from Temporal activity events, which the internal
setup activity never emits), so a ``for_each`` sub-workflow is represented by a
single aggregate row in practice. These tests exercise composite iteration rows
directly to pin the finalizer's base-node precedence behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy.orm import selectinload
from sqlmodel import select

from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType
from syntara.workflows.workflow_engine.services.activity_sync_service import ActivitySyncService

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User

_EMPTY_DEF = {"schema_version": "2.0.0", "triggers": [], "nodes": [], "edges": []}
# One activity row to seed: its name, node type, and initial status.
ActivitySpec = tuple[str, NodeType, ActivityStatus]


async def _create_execution_with_activities(
    session: AsyncSession,
    *,
    created_by: UUID,
    project_id: UUID,
    activities: list[ActivitySpec],
) -> UUID:
    """Persist a workflow + version + execution and the given activity rows; return the execution id."""
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
            workflow_definition=_EMPTY_DEF,
            created_by=created_by,
        )
    )
    await session.flush()

    exec_id = uuid4()
    session.add(
        Execution(
            id=exec_id,
            workflow_id=wf_id,
            workflow_version_id=ver_id,
            temporal_workflow_id=f"tmp-{exec_id.hex[:8]}",
            created_by=created_by,
            updated_by=created_by,
            project_id=project_id,
        )
    )
    await session.flush()

    for name, node_type, status in activities:
        session.add(
            ActivityExecution(
                execution_id=exec_id,
                activity_name=name,
                node_type=node_type,
                temporal_activity_id=name,
                status=status,
            )
        )
    await session.commit()
    return exec_id


async def _load_and_finalize(
    session: AsyncSession,
    exec_id: UUID,
    failed_map: dict[str, str] | None,
    completed_ids: set[str] | None,
) -> None:
    """Load the execution with its activities, run the finalizer, and commit."""
    loaded = await session.exec(
        select(Execution).where(Execution.id == exec_id).options(selectinload(Execution.activities))  # type: ignore[arg-type]
    )
    ActivitySyncService._finalize_non_terminal_activities(loaded.one(), exec_id, failed_map, completed_ids)
    await session.commit()


async def _read_rows(session: AsyncSession, exec_id: UUID) -> list[ActivityExecution]:
    """Re-read persisted activity rows for an execution."""
    rows = (await session.exec(select(ActivityExecution).where(ActivityExecution.execution_id == exec_id))).all()
    for row in rows:
        await session.refresh(row)
    return list(rows)


async def _finalize_and_read(
    session: AsyncSession,
    *,
    created_by: UUID,
    project_id: UUID,
    activities: list[ActivitySpec],
    failed_map: dict[str, str] | None = None,
    completed_ids: set[str] | None = None,
) -> dict[str, ActivityStatus]:
    """Persist, finalize, and return the persisted {activity_name: status} map."""
    exec_id = await _create_execution_with_activities(
        session, created_by=created_by, project_id=project_id, activities=activities
    )
    await _load_and_finalize(session, exec_id, failed_map, completed_ids)
    return {row.activity_name: row.status for row in await _read_rows(session, exec_id)}


_PENDING_SUB_WF: list[ActivitySpec] = [("sub_wf_node", NodeType.SUB_WORKFLOW, ActivityStatus.PENDING)]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_successful_sub_workflow_persists_completed(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """A PENDING sub-workflow row in completed_ids is persisted COMPLETED (not SKIPPED)."""
    statuses = await _finalize_and_read(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        activities=_PENDING_SUB_WF,
        completed_ids={"sub_wf_node"},
    )
    assert statuses["sub_wf_node"] == ActivityStatus.COMPLETED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_started_at_not_fabricated(test_db_session: AsyncSession, test_user: User, test_project_id: UUID) -> None:
    """Marking COMPLETED must not fabricate a started_at timestamp."""
    exec_id = await _create_execution_with_activities(
        test_db_session, created_by=test_user.id, project_id=test_project_id, activities=_PENDING_SUB_WF
    )
    await _load_and_finalize(test_db_session, exec_id, None, {"sub_wf_node"})

    row = (await _read_rows(test_db_session, exec_id))[0]
    assert row.status == ActivityStatus.COMPLETED
    assert row.started_at is None
    assert row.completed_at is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failed_child_persists_failed(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """A failed sub-workflow node is persisted FAILED."""
    statuses = await _finalize_and_read(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        activities=_PENDING_SUB_WF,
        failed_map={"sub_wf_node": "child failed"},
    )
    assert statuses["sub_wf_node"] == ActivityStatus.FAILED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unexecuted_node_persists_skipped(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """A node absent from both sets is persisted SKIPPED (legacy behavior preserved)."""
    statuses = await _finalize_and_read(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        activities=_PENDING_SUB_WF,
    )
    assert statuses["sub_wf_node"] == ActivityStatus.SKIPPED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failed_precedence_over_completed(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """A node in both sets is persisted FAILED (FAILED > COMPLETED)."""
    statuses = await _finalize_and_read(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        activities=_PENDING_SUB_WF,
        failed_map={"sub_wf_node": "boom"},
        completed_ids={"sub_wf_node"},
    )
    assert statuses["sub_wf_node"] == ActivityStatus.FAILED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_for_each_all_success_persists_completed(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """All composite iteration rows for a completed base node persist COMPLETED."""
    statuses = await _finalize_and_read(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        activities=[(f"sub_wf_node#iter-{i}", NodeType.SUB_WORKFLOW, ActivityStatus.PENDING) for i in range(3)],
        completed_ids={"sub_wf_node"},
    )
    assert all(s == ActivityStatus.COMPLETED for s in statuses.values())


@pytest.mark.integration
@pytest.mark.asyncio
async def test_for_each_mixed_order_a_fail_then_success(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """iter0 fails, iter1 succeeds: failure retained in failed_map -> aggregate FAILED.

    Engine state: base in failed_map (failures never cleared) AND in completed_ids
    (last iteration's namespace is 'completed'). Must not persist COMPLETED.
    """
    statuses = await _finalize_and_read(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        activities=[(f"sub_wf_node#iter-{i}", NodeType.SUB_WORKFLOW, ActivityStatus.PENDING) for i in range(2)],
        failed_map={"sub_wf_node": "iter0 failed"},
        completed_ids={"sub_wf_node"},
    )
    assert all(s == ActivityStatus.FAILED for s in statuses.values())


@pytest.mark.integration
@pytest.mark.asyncio
async def test_for_each_mixed_order_b_success_then_fail(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """iter0 succeeds, iter1 fails: last namespace 'failed' -> not in completed_ids -> FAILED."""
    statuses = await _finalize_and_read(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        activities=[(f"sub_wf_node#iter-{i}", NodeType.SUB_WORKFLOW, ActivityStatus.PENDING) for i in range(2)],
        failed_map={"sub_wf_node": "iter1 failed"},
        completed_ids=set(),
    )
    assert all(s == ActivityStatus.FAILED for s in statuses.values())


@pytest.mark.integration
@pytest.mark.asyncio
async def test_existing_terminal_rows_untouched(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """A row already terminal is not changed; only the PENDING sub-workflow row is reconciled."""
    statuses = await _finalize_and_read(
        test_db_session,
        created_by=test_user.id,
        project_id=test_project_id,
        activities=[
            ("normal_node", NodeType.SCRIPT, ActivityStatus.COMPLETED),
            ("sub_wf_node", NodeType.SUB_WORKFLOW, ActivityStatus.PENDING),
        ],
        completed_ids={"sub_wf_node"},
    )
    assert statuses["normal_node"] == ActivityStatus.COMPLETED
    assert statuses["sub_wf_node"] == ActivityStatus.COMPLETED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_idempotent_second_finalize(
    test_db_session: AsyncSession, test_user: User, test_project_id: UUID
) -> None:
    """Re-running the finalizer does not regress the already-terminal row."""
    exec_id = await _create_execution_with_activities(
        test_db_session, created_by=test_user.id, project_id=test_project_id, activities=_PENDING_SUB_WF
    )
    await _load_and_finalize(test_db_session, exec_id, None, {"sub_wf_node"})
    await _load_and_finalize(test_db_session, exec_id, None, {"sub_wf_node"})

    row = (await _read_rows(test_db_session, exec_id))[0]
    assert row.status == ActivityStatus.COMPLETED
