"""Durable, engine-neutral completion acceptance in the caller's transaction."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.workflow_runtime.contracts import ActivityError
from syntara.workflow_runtime.models import ActivityCompletion


class CompletionService:
    """Accept a result atomically with its business decision; never call an engine."""

    def __init__(self, session: AsyncSession) -> None:
        """Use the caller's transaction, leaving commit ownership with the caller."""
        self.session = session

    async def defer(self, reference: UUID, *, execution_id: UUID, project_id: UUID, external_operation_id: str) -> None:
        """Commit a handoff atomically with creation of a durable business request.

        Providers using the same database can eliminate the crash window between
        publishing their request and returning Deferred to the activity wrapper.
        """
        row = (
            await self.session.exec(
                select(ActivityCompletion)
                .where(
                    ActivityCompletion.id == reference,
                    ActivityCompletion.execution_id == execution_id,
                    ActivityCompletion.project_id == project_id,
                )
                .with_for_update()
            )
        ).one_or_none()
        if row is None or row.state not in {"reserved", "received"}:
            msg = "Completion attempt is no longer active"
            raise ActivityError(msg, code="CompletionConflict")
        row.deferred = True
        row.external_operation_id = external_operation_id
        self.session.add(row)
        await self.session.flush()

    async def complete(self, reference: UUID, *, execution_id: UUID, project_id: UUID, output: dict[str, Any]) -> None:
        """Store a successful result for durable delivery after the handoff."""
        await self._accept(reference, execution_id, project_id, output=output, failure=None)

    async def fail(self, reference: UUID, *, execution_id: UUID, project_id: UUID, error: ActivityError) -> None:
        """Store an engine-independent failure for durable delivery."""
        await self._accept(
            reference,
            execution_id,
            project_id,
            output=None,
            failure={"message": str(error), "code": error.code, "retryable": error.retryable},
        )

    async def _accept(
        self,
        reference: UUID,
        execution_id: UUID,
        project_id: UUID,
        *,
        output: dict[str, Any] | None,
        failure: dict[str, Any] | None,
    ) -> None:
        json.dumps(output if output is not None else failure, allow_nan=False)
        row = (
            await self.session.exec(
                select(ActivityCompletion)
                .where(
                    ActivityCompletion.id == reference,
                    ActivityCompletion.execution_id == execution_id,
                    ActivityCompletion.project_id == project_id,
                )
                .with_for_update()
            )
        ).one_or_none()
        if row is None:
            msg = "Completion reference does not belong to this execution and project"
            raise ActivityError(msg, code="InvalidCompletion")
        if row.state in {"received", "delivered"} and row.output == output and row.failure == failure:
            return
        if row.state != "reserved" or row.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
            msg = "Completion reference is closed, expired, or already has a different outcome"
            raise ActivityError(msg, code="CompletionConflict")
        row.output = output
        row.failure = failure
        row.state = "received"
        self.session.add(row)
        await self.session.flush()
