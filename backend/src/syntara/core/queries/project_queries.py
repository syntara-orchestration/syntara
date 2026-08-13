"""Shared project query utilities.

Provides reusable query functions for project liveness checks, used by
services that create resources scoped to a project to prevent orphaned
resources against soft-deleted projects.
"""

from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.exceptions import ProjectNotFoundError
from syntara.authz.models.project import Project


async def assert_project_alive(session: AsyncSession, project_id: UUID) -> None:
    """Verify a project exists and is not soft-deleted.

    Args:
        session: Database session
        project_id: Project UUID to validate

    Raises:
        ProjectNotFoundError: If project not found or soft-deleted

    """
    result = await session.exec(
        select(Project.id).where(
            Project.id == project_id,
            Project.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    if result.first() is None:
        msg = f"Project {project_id} not found"
        raise ProjectNotFoundError(msg)
