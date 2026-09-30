"""Integration test for retry loop-state resolution (AAP-92821, SDP R6b).

The unit tests mock the database session. This one runs the activity against a
real PostgreSQL schema, which is the only way to confirm that:

* ``col(ActivityExecution.status).in_([...])`` translates to working SQL rather
  than only being type-correct;
* the per-iteration ``iteration`` column round-trips as the authoritative index,
  independent of the ``#iter-<n>`` name suffix;
* ``output_data`` comes back as the same nested structure the engine's namespace
  held, so the rebuilt aggregation is byte-for-byte what a live run produced.

The resume decision is the highest-severity correctness risk in the restart
design in either direction: resuming too early replays side effects that already
happened, resuming too late skips the iteration that failed.
"""

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import patch

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionMode, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.workflow_engine.activities.retry_output_activity import fetch_retry_loop_state_activity
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType

pytestmark = pytest.mark.integration


@pytest.fixture
async def source_execution(test_db_session: AsyncSession, test_workflow: Workflow, test_user: User) -> Execution:
    """A FAILED execution to read loop state back from."""
    result = await test_db_session.exec(
        select(WorkflowVersion.id).where(
            WorkflowVersion.workflow_id == test_workflow.id,
            WorkflowVersion.version == test_workflow.current_version,
        )
    )
    version_id = result.one()

    execution = Execution(
        workflow_id=test_workflow.id,
        workflow_version_id=version_id,
        temporal_workflow_id=f"temporal-{uuid.uuid4()}",
        status=ExecutionStatus.FAILED,
        created_by=test_user.id,
        input_data={},
        labels={},
        project_id=test_workflow.project_id,
        mode=ExecutionMode.STANDARD,
        trigger_node_id="trigger_manual",
    )
    test_db_session.add(execution)
    await test_db_session.commit()
    await test_db_session.refresh(execution)
    return execution


def _activity(
    execution: Execution,
    activity_name: str,
    status: ActivityStatus,
    *,
    iteration: int | None = None,
    output: dict[str, Any] | None = None,
) -> ActivityExecution:
    return ActivityExecution(
        execution_id=execution.id,
        activity_name=activity_name,
        node_type=NodeType.SCRIPT,
        temporal_activity_id=f"temporal-{uuid.uuid4()}",
        status=status,
        iteration=iteration,
        output_data=output,
    )


async def _fetch(session: AsyncSession, execution: Execution, loops: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    """Run the activity against the real database.

    The activity opens its own session through ``get_db`` rather than through
    FastAPI, so the binding in its own module namespace is replaced with a
    generator yielding the test session. The schema, SQL translation and JSONB
    round trip are all still the real thing.
    """

    async def _test_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    with patch(
        "syntara.workflows.workflow_engine.activities.retry_output_activity.get_db",
        _test_get_db,
    ):
        return await fetch_retry_loop_state_activity(str(execution.id), loops)


async def test_resumes_at_the_failed_iteration(test_db_session: AsyncSession, source_execution: Execution) -> None:
    """The iteration that stopped the loop is the one a retry restarts at."""
    for index in (0, 1):
        test_db_session.add(
            _activity(
                source_execution,
                f"body_a{'' if index == 0 else f'#iter-{index}'}",
                ActivityStatus.COMPLETED,
                iteration=index,
                output={"receipt": f"r{index}", "nested": {"amount": index * 10}},
            )
        )
    test_db_session.add(_activity(source_execution, "body_a#iter-2", ActivityStatus.FAILED, iteration=2, output=None))
    await test_db_session.commit()

    result = await _fetch(test_db_session, source_execution, {"loop_1": ["body_a"]})

    assert result["loop_1"]["resume_iteration"] == 2
    results = result["loop_1"]["iteration_results"]
    assert results["body_a.receipt"] == ["r0", "r1"]
    # The engine's namespace carries this synthetic key that output_data lacks.
    assert results["body_a.status"] == ["completed", "completed"]
    # JSONB nesting survives the round trip unchanged.
    assert results["body_a.nested"] == [{"amount": 0}, {"amount": 10}]


async def test_tolerated_early_failure_is_not_replayed(
    test_db_session: AsyncSession, source_execution: Execution
) -> None:
    """A continue_on_failure iteration the loop moved past must not re-run.

    The source run holds two FAILED rows: an early tolerated one and the later
    one that stopped the loop. Resuming from the earliest would repeat an
    iteration whose side effect already happened.
    """
    test_db_session.add(
        _activity(source_execution, "body_a", ActivityStatus.COMPLETED, iteration=0, output={"receipt": "r0"})
    )
    test_db_session.add(_activity(source_execution, "body_a#iter-1", ActivityStatus.FAILED, iteration=1, output=None))
    test_db_session.add(
        _activity(source_execution, "body_a#iter-2", ActivityStatus.COMPLETED, iteration=2, output={"receipt": "r2"})
    )
    test_db_session.add(_activity(source_execution, "body_a#iter-3", ActivityStatus.FAILED, iteration=3, output=None))
    await test_db_session.commit()

    result = await _fetch(test_db_session, source_execution, {"loop_1": ["body_a"]})

    assert result["loop_1"]["resume_iteration"] == 3
    # r1 is absent: that iteration already ran.
    assert result["loop_1"]["iteration_results"]["body_a.receipt"] == ["r0", "r2"]


async def test_iteration_zero_failure_restores_nothing(
    test_db_session: AsyncSession, source_execution: Execution
) -> None:
    """TC0037: a failure on iteration 0 leaves nothing to skip, so the loop re-runs whole."""
    test_db_session.add(_activity(source_execution, "body_a", ActivityStatus.FAILED, iteration=0, output=None))
    await test_db_session.commit()

    result = await _fetch(test_db_session, source_execution, {"loop_1": ["body_a"]})

    assert result["loop_1"]["resume_iteration"] == 0
    assert result["loop_1"]["iteration_results"] == {}


async def test_completed_loop_needs_no_resume(test_db_session: AsyncSession, source_execution: Execution) -> None:
    """A loop that completed outright is not reported as needing a resume."""
    test_db_session.add(
        _activity(source_execution, "body_a", ActivityStatus.COMPLETED, iteration=0, output={"receipt": "r0"})
    )
    await test_db_session.commit()

    assert await _fetch(test_db_session, source_execution, {"loop_1": ["body_a"]}) == {}


async def test_rows_for_other_executions_are_ignored(
    test_db_session: AsyncSession, source_execution: Execution, test_workflow: Workflow, test_user: User
) -> None:
    """Resume state must not leak across executions of the same workflow."""
    result = await test_db_session.exec(
        select(WorkflowVersion.id).where(
            WorkflowVersion.workflow_id == test_workflow.id,
            WorkflowVersion.version == test_workflow.current_version,
        )
    )
    other = Execution(
        workflow_id=test_workflow.id,
        workflow_version_id=result.one(),
        temporal_workflow_id=f"temporal-{uuid.uuid4()}",
        status=ExecutionStatus.FAILED,
        created_by=test_user.id,
        input_data={},
        labels={},
        project_id=test_workflow.project_id,
        mode=ExecutionMode.STANDARD,
        trigger_node_id="trigger_manual",
    )
    test_db_session.add(other)
    await test_db_session.commit()
    await test_db_session.refresh(other)

    test_db_session.add(_activity(other, "body_a", ActivityStatus.COMPLETED, iteration=0, output={"receipt": "other"}))
    await test_db_session.commit()

    assert await _fetch(test_db_session, source_execution, {"loop_1": ["body_a"]}) == {}


async def test_rows_outside_the_loop_body_are_ignored(
    test_db_session: AsyncSession, source_execution: Execution
) -> None:
    """An identically-named node elsewhere in the workflow must not contribute."""
    test_db_session.add(
        _activity(source_execution, "body_a", ActivityStatus.COMPLETED, iteration=0, output={"receipt": "r0"})
    )
    test_db_session.add(_activity(source_execution, "other_node", ActivityStatus.FAILED, iteration=9, output=None))
    await test_db_session.commit()

    assert await _fetch(test_db_session, source_execution, {"loop_1": ["body_a"]}) == {}


async def test_iteration_column_wins_over_the_name_suffix(
    test_db_session: AsyncSession, source_execution: Execution
) -> None:
    """The column is authoritative, so a missing suffix cannot mis-key an iteration.

    Guards the mismatch case directly: if the suffix were parsed instead, this row
    would land on iteration 0 and be restored when it should be skipped.
    """
    test_db_session.add(
        _activity(source_execution, "body_a", ActivityStatus.COMPLETED, iteration=0, output={"receipt": "r0"})
    )
    # Named as iteration 0 but recorded as iteration 5.
    test_db_session.add(
        _activity(source_execution, "body_a", ActivityStatus.COMPLETED, iteration=5, output={"receipt": "r5"})
    )
    test_db_session.add(_activity(source_execution, "body_a#iter-6", ActivityStatus.FAILED, iteration=6, output=None))
    await test_db_session.commit()

    result = await _fetch(test_db_session, source_execution, {"loop_1": ["body_a"]})

    assert result["loop_1"]["resume_iteration"] == 6
    # Iteration 5 is below the resume point; the row named like iteration 0 is too.
    assert result["loop_1"]["iteration_results"]["body_a.receipt"] == ["r0", "r5"]
