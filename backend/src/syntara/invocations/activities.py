"""Invocation-owned activities for the workflow runtime prototype."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from uuid import UUID

from syntara.audit.context_managers import actor_context
from syntara.audit.emitter import AuditActorContext
from syntara.workflow_runtime.contracts import ActivityContext, ActivityError, Completed

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlmodel.ext.asyncio.session import AsyncSession


class InvocationActivities:
    """Create and execute invocations without starting a second workflow."""

    def __init__(self, session_factory: Any) -> None:  # noqa: ANN401
        """Inject the worker's database session factory."""
        self.session_factory = session_factory

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def execute(self, inputs: dict[str, Any], context: ActivityContext) -> Completed:
        """Create an invocation and execute it directly in this activity."""
        from syntara.agent_orchestrator.executor.invocation_executor import InvocationExecutor  # noqa: PLC0415
        from syntara.agent_orchestrator.models import InvocationStatus  # noqa: PLC0415
        from syntara.agent_orchestrator.models.invocation import Invocation  # noqa: PLC0415
        from syntara.agent_orchestrator.services.invocation_service import InvocationService  # noqa: PLC0415
        from syntara.core.models import User  # noqa: PLC0415

        created_by_value = str(inputs.get("created_by_user_id", ""))
        if not created_by_value:
            from syntara.core.config.base import get_settings  # noqa: PLC0415
            from syntara.core.models.principal import service_principal_id  # noqa: PLC0415

            created_by = service_principal_id(get_settings().service_identity)
        else:
            created_by = UUID(created_by_value)
        async with self._session() as session:
            user = await session.get(User, created_by)
            if user is None:
                msg = "Invocation creator does not exist"
                raise ActivityError(msg, code="InvalidActivityInput")
            with actor_context(
                actor=AuditActorContext(
                    actor_id=user.id,
                    actor_username=user.username,
                    actor_type=user.__principal_type__,
                ),
                execution_id=context.execution_id,
                activity_id=context.node_execution_id,
            ):
                service = InvocationService(session, user)
                invocation = await service.create_invocation(
                    prompt=str(inputs["prompt"]),
                    session_id=f"workflow:{context.execution_id}",
                    project_id=context.project_id,
                    context_data={
                        "agent": inputs.get("agent"),
                        "model": inputs.get("llm_model_id"),
                        "execution_id": str(context.execution_id),
                        "activity_id": context.node_execution_id,
                        "activity_name": "agentic_v2",
                        "timeout_seconds": inputs.get("timeout"),
                        "metadata": inputs.get("metadata", {}),
                    },
                    files=[],
                )

        try:
            await InvocationExecutor().execute_invocation(
                invocation.id,
                actor_context=AuditActorContext(
                    actor_id=user.id,
                    actor_username=user.username,
                    actor_type=user.__principal_type__,
                ),
            )
        except asyncio.CancelledError:
            async with self._session() as session:
                await InvocationService(session, user).cancel_invocation(invocation.id, "Workflow cancelled")
            raise
        async with self._session() as session:
            saved = await session.get(Invocation, invocation.id)
        if saved is None or saved.status != InvocationStatus.COMPLETED:
            status = saved.status.value if saved is not None else "missing"
            msg = f"Invocation finished with status {status}"
            raise ActivityError(msg, code="InvocationFailed")
        result = saved.result if isinstance(saved.result, dict) else {}
        return Completed(result)

    async def cancel(self, inputs: dict[str, Any], context: ActivityContext) -> Completed:
        """Cancel running direct invocations belonging to this workflow."""
        from sqlmodel import select  # noqa: PLC0415

        from syntara.agent_orchestrator.models import InvocationStatus  # noqa: PLC0415
        from syntara.agent_orchestrator.models.invocation import Invocation  # noqa: PLC0415
        from syntara.agent_orchestrator.services.invocation_service import InvocationService  # noqa: PLC0415
        from syntara.core.models import User  # noqa: PLC0415

        node_id = inputs.get("node_id")
        reason = str(inputs.get("reason", "Workflow cancelled"))
        cancelled = 0
        async with self._session() as session:
            rows = (await session.exec(select(Invocation).where(Invocation.project_id == context.project_id))).all()
            for invocation in rows:
                data = invocation.context_data or {}
                if data.get("execution_id") != str(context.execution_id):
                    continue
                if node_id is not None and data.get("activity_id") != node_id:
                    continue
                if invocation.status not in {InvocationStatus.CREATED, InvocationStatus.RUNNING}:
                    continue
                user = await session.get(User, invocation.created_by)
                if user is not None:
                    await InvocationService(session, user).cancel_invocation(invocation.id, reason)
                    cancelled += 1
        return Completed({"cancelled_count": cancelled})
