"""Queries for the database-backed Execution Plane plugin registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import select

from syntara.execution_plane.registry.models import ExecutionPlanePlugin

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


async def get_execution_plane_plugin(session: AsyncSession, name: str) -> ExecutionPlanePlugin | None:
    """Return the managed plugin record for an Action name, if seeded."""
    result = await session.exec(select(ExecutionPlanePlugin).where(ExecutionPlanePlugin.name == name))
    return result.first()
