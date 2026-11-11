"""Regression tests for the sub-workflow ``nodetype`` enum values.

These guard the fix where the Python ``NodeType`` enum gained ``SUB_WORKFLOW``
and ``SUBWORKFLOW_TRIGGER`` but the PostgreSQL ``nodetype`` enum was not
extended, so persisting an ``ActivityExecution`` for a sub-workflow node or a
subworkflow-trigger node failed and stranded the execution in PENDING.

These are integration tests and run against the PostgreSQL schema built by
``alembic upgrade head`` (see ``tests/fixtures/database.py``). They are
meaningful only against that migration-built schema: ``node_type`` is a native
PostgreSQL enum, so a schema generated from current model metadata would
already contain every value and would not reproduce the drift.
"""

import pytest
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType


@pytest.mark.asyncio
@pytest.mark.parametrize("node_type", [NodeType.SUB_WORKFLOW, NodeType.SUBWORKFLOW_TRIGGER])
async def test_subworkflow_nodetypes_persist(
    test_db_session: AsyncSession,
    test_execution_minimal: Execution,
    node_type: NodeType,
) -> None:
    """An ActivityExecution with a sub-workflow node type must persist.

    ``commit`` sends the INSERT; before the enum migration PostgreSQL rejects it
    with ``DataError`` ("invalid input value for enum nodetype"), after it the
    row is stored.
    """
    activity = ActivityExecution(
        execution_id=test_execution_minimal.id,
        activity_name=f"node_{node_type.value}",
        node_type=node_type,
        temporal_activity_id=f"act-{node_type.value}",
        status=ActivityStatus.PENDING,
    )
    test_db_session.add(activity)
    await test_db_session.commit()

    # Refresh from PostgreSQL so the assertion reflects the stored value rather
    # than the in-memory enum (the test session uses expire_on_commit=False).
    await test_db_session.refresh(activity)

    assert activity.id is not None
    assert activity.node_type == node_type


@pytest.mark.asyncio
async def test_nodetype_enum_matches_python(test_db_session: AsyncSession) -> None:
    """Every Python ``NodeType`` value must exist in the PostgreSQL enum.

    Guards against future node types being added to the Python enum without a
    matching ``ALTER TYPE nodetype ADD VALUE`` migration. The query targets the
    specific ``public.nodetype`` type.
    """
    result = await test_db_session.exec(  # type: ignore[call-overload]
        text(
            "SELECT e.enumlabel "
            "FROM pg_enum e "
            "JOIN pg_type t ON t.oid = e.enumtypid "
            "JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE t.typname = 'nodetype' AND n.nspname = 'public'"
        )
    )
    db_labels = set(result.scalars().all())
    python_values = {member.value for member in NodeType}
    missing = python_values - db_labels
    assert not missing, f"public.nodetype is missing NodeType values: {sorted(missing)}"
