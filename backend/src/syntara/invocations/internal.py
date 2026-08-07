"""Internal invocation endpoints for service-to-service calls.

These endpoints are excluded from the public OpenAPI spec and intended
for mTLS-authenticated internal callers (e.g. the Temporal worker).
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Path, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models import Invocation, InvocationCreateRequest
from syntara.agent_orchestrator.services import InvocationService
from syntara.auth import get_current_user
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.utils.session_factory import create_session_factory_from_request
from syntara.workflows.executions_router import get_temporal_execution_service
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService


async def create_internal_invocation(
    request_body: InvocationCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    temporal_service: Annotated[TemporalExecutionService | None, Depends(get_temporal_execution_service)],
) -> Invocation:
    """Accept an async invocation request (JSON) via internal route."""
    from syntara.workflows.services.execution_service import ExecutionService  # noqa: PLC0415

    session_factory = create_session_factory_from_request(request)
    execution_service = ExecutionService(db, current_user, temporal_service=temporal_service)
    service = InvocationService(
        db,
        current_user,
        session_factory=session_factory,
        execution_service=execution_service,
    )
    return await service.create_invocation(
        prompt=request_body.prompt,
        session_id=request_body.session_id,
        project_id=request_body.project_id,
        context_data=request_body.context_data,
        files=None,
    )


async def get_internal_invocation(
    invocation_id: Annotated[UUID, Path(description="UUID of the invocation")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Invocation:
    """Retrieve an invocation by ID via internal route."""
    invocation = await db.get(Invocation, invocation_id)
    if not invocation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invocation {invocation_id} not found",
        )
    return invocation
