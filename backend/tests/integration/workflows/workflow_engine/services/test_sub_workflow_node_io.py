"""Input/output contract for the parent sub-workflow node (C3: ASS-owned).

A sub-workflow node runs via the setup activity plus a Temporal child workflow,
so no ACTIVITY_TASK_COMPLETED event carries its input/output. As of C3 the setup
activity no longer persists the node row directly; ActivitySyncService
reconstructs the node's invocation summaries (which child, with what input, and
the resulting child execution id) from the setup activity's result payload and
writes them to the upfront-created row. The child's activities are never embedded
— those are fetched separately by the UI.

These tests drive ``SubWorkflowSetupActivity.run`` directly against the real,
alembic-built PostgreSQL schema to confirm (a) the activity no longer writes the
node row, and (b) its result payload reconstructs the exact input/output
summaries ActivitySyncService persists, for both the fresh invocation and the
resume (idempotent retry) path. The ASS write itself is covered by the unit
suite (``test_subworkflow_setup_sync.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
from sqlmodel import select

from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.activities.sub_workflow_setup_activity import SubWorkflowSetupActivity
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType
from syntara.workflows.workflow_engine.services.activity_sync_event_processor import ActivitySyncEventProcessorMixin

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User

_TASK_QUEUE = "sub-wf-node-io"
_PARENT_NODE_ID = "run_child"
_EMPTY_DEF = {"schema_version": "2.0.0", "name": "parent", "triggers": [], "nodes": [], "edges": []}


def _child_def() -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "name": "child",
        "triggers": [{"id": "child_trigger", "type": "subworkflow_trigger", "parameters": {}}],
        "nodes": [{"id": "child_script", "type": "script", "parameters": {"language": "bash", "code": "echo ok"}}],
        "edges": [{"from": "child_trigger", "to": "child_script"}],
    }


async def _create_published_child(session: AsyncSession, *, created_by: UUID, project_id: UUID, name: str) -> UUID:
    workflow_id = uuid4()
    workflow = Workflow(id=workflow_id, name=name, created_by=created_by, project_id=project_id)
    session.add(workflow)
    await session.flush()
    version = WorkflowVersion(
        id=uuid4(),
        workflow_id=workflow_id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=_child_def(),
        created_by=created_by,
    )
    session.add(version)
    await session.flush()
    workflow.is_enabled = True
    workflow.published_version_id = version.id
    await session.commit()
    return workflow_id


async def _create_parent_with_node_row(session: AsyncSession, *, created_by: UUID, project_id: UUID) -> UUID:
    """Create a parent Execution + the upfront PENDING sub_workflow node row (empty I/O)."""
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
    parent_exec_id = uuid4()
    session.add(
        Execution(
            id=parent_exec_id,
            workflow_id=wf_id,
            workflow_version_id=ver_id,
            project_id=project_id,
            temporal_workflow_id=f"p-{parent_exec_id.hex[:8]}",
            status=ExecutionStatus.RUNNING,
            created_by=created_by,
            updated_by=created_by,
        )
    )
    session.add(
        ActivityExecution(
            execution_id=parent_exec_id,
            activity_name=_PARENT_NODE_ID,
            node_type=NodeType.SUB_WORKFLOW,
            temporal_activity_id=_PARENT_NODE_ID,
            status=ActivityStatus.PENDING,
        )
    )
    await session.commit()
    return parent_exec_id


def _params(child_wf_id: UUID, input_mapping: dict[str, Any]) -> dict[str, Any]:
    return {"workflow_id": str(child_wf_id), "trigger_node_id": "child_trigger", "input_mapping": input_mapping}


async def _read_node_row(factory: async_sessionmaker[AsyncSession], parent_exec_id: UUID) -> ActivityExecution | None:
    async with factory() as session:
        return (
            await session.exec(
                select(ActivityExecution).where(
                    ActivityExecution.execution_id == parent_exec_id,
                    ActivityExecution.activity_name == _PARENT_NODE_ID,
                )
            )
        ).first()


def _assert_summaries_match(result: dict[str, Any], child_id: UUID) -> None:
    """The activity result reconstructs the exact input/output summaries ASS persists."""
    io = ActivitySyncEventProcessorMixin._build_subworkflow_io(result)
    assert io["input"]["execution_mode"] == "reference"
    assert io["input"]["workflow_id"] == str(child_id)
    assert io["input"]["trigger_node_id"] == "child_trigger"
    assert io["input"]["input_parameters"] == {"greeting": "hi"}

    assert io["output"]["child_workflow_version"] == 1
    assert io["output"]["workflow_id"] == str(child_id)
    assert io["output"]["child_execution_id"]
    # The child's activities are never duplicated into the parent node's output.
    assert "child_activities" not in io["output"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fresh_invocation_reconstructs_node_io(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """A fresh invocation leaves the row untouched; its result reconstructs the I/O summaries."""
    child_id = await _create_published_child(
        test_db_session, created_by=test_user.id, project_id=test_project_id, name="child-io"
    )
    parent_exec = await _create_parent_with_node_row(
        test_db_session, created_by=test_user.id, project_id=test_project_id
    )
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)

    result = await setup.run(
        _params(child_id, {"greeting": "hi"}), str(parent_exec), _PARENT_NODE_ID, str(test_user.id), 0
    )

    # C3: persistence moved to ActivitySyncService — the activity no longer writes the row.
    row = await _read_node_row(test_db_session_factory, parent_exec)
    assert row is not None
    assert row.input_data == {}
    assert row.output_data is None

    _assert_summaries_match(result, child_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resume_invocation_reconstructs_node_io(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """An idempotent-retry (resume) invocation returns a result that reconstructs the same I/O."""
    child_id = await _create_published_child(
        test_db_session, created_by=test_user.id, project_id=test_project_id, name="child-io-resume"
    )
    parent_exec = await _create_parent_with_node_row(
        test_db_session, created_by=test_user.id, project_id=test_project_id
    )
    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)

    # First call creates the child execution.
    await setup.run(_params(child_id, {"greeting": "hi"}), str(parent_exec), _PARENT_NODE_ID, str(test_user.id), 0)

    # Retry: the child already exists, so the resume (pinned-version) path runs.
    resume_result = await setup.run(
        _params(child_id, {"greeting": "hi"}), str(parent_exec), _PARENT_NODE_ID, str(test_user.id), 0
    )

    # The activity still does not write the row; the resume result reconstructs the same summaries.
    row = await _read_node_row(test_db_session_factory, parent_exec)
    assert row is not None
    assert row.input_data == {}
    assert row.output_data is None

    _assert_summaries_match(resume_result, child_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_missing_node_row_does_not_block_setup(
    test_db_session: AsyncSession,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    test_user: User,
    test_project_id: UUID,
) -> None:
    """The setup activity succeeds and returns its result even when no node row exists."""
    child_id = await _create_published_child(
        test_db_session, created_by=test_user.id, project_id=test_project_id, name="child-io-missing"
    )
    # A real parent execution, but NO upfront node row created for it.
    wf_id = uuid4()
    test_db_session.add(
        Workflow(id=wf_id, name=f"parent-{wf_id.hex[:8]}", created_by=test_user.id, project_id=test_project_id)
    )
    await test_db_session.flush()
    ver_id = uuid4()
    test_db_session.add(
        WorkflowVersion(
            id=ver_id,
            workflow_id=wf_id,
            version=1,
            schema_version="2.0.0",
            workflow_definition=_EMPTY_DEF,
            created_by=test_user.id,
        )
    )
    await test_db_session.flush()
    parent_exec = uuid4()
    test_db_session.add(
        Execution(
            id=parent_exec,
            workflow_id=wf_id,
            workflow_version_id=ver_id,
            project_id=test_project_id,
            temporal_workflow_id=f"p-{parent_exec.hex[:8]}",
            status=ExecutionStatus.RUNNING,
            created_by=test_user.id,
            updated_by=test_user.id,
        )
    )
    await test_db_session.commit()

    setup = SubWorkflowSetupActivity(session_factory=test_db_session_factory, task_queue=_TASK_QUEUE)

    result = await setup.run(
        _params(child_id, {"greeting": "hi"}), str(parent_exec), _PARENT_NODE_ID, str(test_user.id), 0
    )
    assert result["child_workflow_version"] == 1
    # No row was created, and the activity does not create one.
    assert await _read_node_row(test_db_session_factory, parent_exec) is None
