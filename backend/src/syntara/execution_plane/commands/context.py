"""AO infrastructure supplied to installed command handlers."""

from dataclasses import dataclass

from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.workflow_runtime.engines.temporal.services.temporal_execution_service import TemporalExecutionService


@dataclass(frozen=True)
class AOCommandContext:
    """Command-scoped database and workflow dependencies."""

    session: AsyncSession
    temporal_service: TemporalExecutionService | None
