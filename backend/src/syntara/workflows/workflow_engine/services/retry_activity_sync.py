"""Persist retry completions without inventing Temporal activity executions."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution


async def sync_restored_activities(
    session: AsyncSession,
    execution_id: UUID,
    names: list[str],
) -> tuple[list[tuple[ActivityExecution, dict[str, Any]]], list[ActivityExecution]]:
    """Idempotently copy retained outputs from the linked source.

    Historical inputs are left untouched pending the input-display contract.
    Stored output is necessary for subsequent retries after this run fails.
    The caller owns the transaction and publishes only after commit.
    """
    execution = await session.get(Execution, execution_id)
    if execution is None or execution.retried_from_execution_id is None:
        return [], []
    sources = (
        await session.exec(
            select(ActivityExecution).where(
                ActivityExecution.execution_id == execution.retried_from_execution_id,
                col(ActivityExecution.activity_name).in_(names),
                ActivityExecution.status == ActivityStatus.COMPLETED,
            )
        )
    ).all()
    existing = {
        row.activity_name: row
        for row in (
            await session.exec(
                select(ActivityExecution).where(
                    ActivityExecution.execution_id == execution_id,
                    col(ActivityExecution.activity_name).in_(names),
                )
            )
        ).all()
    }
    updated: list[tuple[ActivityExecution, dict[str, Any]]] = []
    created: list[ActivityExecution] = []
    now = datetime.now(UTC)
    for source in sources:
        target = existing.get(source.activity_name)
        # Completed status also marks previously restored rows, making resync a no-op.
        if target is not None and target.status != ActivityStatus.PENDING:
            continue
        if target is None:
            target = ActivityExecution(
                execution_id=execution_id,
                activity_name=source.activity_name,
                node_type=source.node_type,
                temporal_activity_id=source.activity_name,
                status=ActivityStatus.COMPLETED,
                output_data=source.output_data,
                iteration=source.iteration,
                started_at=source.started_at,
                completed_at=source.completed_at,
            )
            session.add(target)
            created.append(target)
            existing[source.activity_name] = target
        else:
            updated.append(
                (
                    target,
                    {
                        "status": target.status,
                        "output_data": target.output_data,
                        "iteration": target.iteration,
                        "started_at": target.started_at,
                        "completed_at": target.completed_at,
                        "error_details": target.error_details,
                    },
                )
            )
        target.status = ActivityStatus.COMPLETED
        target.output_data = source.output_data
        target.iteration = source.iteration
        # The source run's own timestamps, not now(). A node's row records when
        # that work happened, so a restored row reporting the restore time would
        # show a five-minute job as having finished in milliseconds. Copying is
        # reversible; overwriting with now() is not recoverable.
        target.started_at = source.started_at
        target.completed_at = source.completed_at
        target.updated_at = now
    return updated, created
