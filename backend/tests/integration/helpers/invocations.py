"""Helper functions for Invocations."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models.invocation import Invocation, InvocationStatus
from syntara.authz.models.project import Project
from syntara.core.models import User


@asynccontextmanager
async def wait_for_invocation_execution(
    client: AsyncClient, invocation_id: str, max_wait_time: float = 5.0, wait_interval: float = 0.1
) -> AsyncGenerator[dict[str, Any] | None, None]:
    """Context manager that waits for an invocation to start execution.

    This ensures that tests can treat invocation creation as if it were synchronous,
    even though execution happens in background tasks.

    Args:
        client: The HTTP client to use for polling
        invocation_id: The ID of the invocation to monitor
        max_wait_time: Maximum time to wait in seconds (default: 5.0)
        wait_interval: How often to check in seconds (default: 0.1)

    Yields:
        The final invocation data after execution has started or timeout

    """
    elapsed_time = 0.0
    final_data: dict[str, Any] | None = None

    while elapsed_time < max_wait_time:
        # Check the current status of the invocation
        status_response = await client.get(f"/api/v1/invocations/{invocation_id}")
        if status_response.status_code == 200:
            status_data = status_response.json()
            if status_data["status"] in ["completed", "failed"]:
                final_data = status_data
                break

        await asyncio.sleep(wait_interval)
        elapsed_time += wait_interval

    # If we didn't get execution state, get the current state for testing
    if final_data is None:
        status_response = await client.get(f"/api/v1/invocations/{invocation_id}")
        if status_response.status_code == 200:
            final_data = status_response.json()

    yield final_data


class InvocationFactory:
    """Factory for creating invocations in integration tests.

    Collapses the hand-rolled ``_make_invocation`` helpers that each test
    module used to carry. ``project_id`` defaults to a project the factory
    creates on first use, so tests that only need *an* invocation do not have
    to reach for a project fixture.
    """

    def __init__(self, session: AsyncSession, user: User) -> None:
        """Initialize with database session and owning user."""
        self.session = session
        self.user = user
        self._default_project_id: UUID | None = None

    async def _resolve_project_id(self) -> UUID:
        if self._default_project_id is None:
            project = Project(
                name=f"invocation-factory-project-{uuid4().hex[:8]}",
                description="Invocation factory project",
            )
            self.session.add(project)
            await self.session.flush()
            self._default_project_id = project.id
        return self._default_project_id

    async def create(
        self,
        *,
        project_id: UUID | None = None,
        status: InvocationStatus = InvocationStatus.RUNNING,
        context_data: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> Invocation:
        """Create a single invocation.

        Args:
            project_id: Owning project; a factory-owned project is used if omitted.
            status: Initial invocation status.
            context_data: Raw context JSONB.
            commit: Commit (and refresh) instead of only flushing.

        Returns:
            The persisted invocation.

        """
        invocation = Invocation(
            prompt="summarise the incident report",
            created_by=self.user.id,
            session_id=f"session-{uuid4()}",
            project_id=project_id if project_id is not None else await self._resolve_project_id(),
            status=status,
            context_data=context_data or {},
        )
        self.session.add(invocation)
        if commit:
            await self.session.commit()
            await self.session.refresh(invocation)
        else:
            await self.session.flush()
        return invocation
