r"""Internal invocation endpoints for service-to-service calls.

These endpoints are excluded from the public OpenAPI spec and intended
for network-isolated internal callers (e.g. the Temporal worker).
Security relies on network-level isolation (k8s NetworkPolicy / service mesh),
not application-level mTLS or Bearer/JWT.

Example (internal callers only)::

    curl -X POST http://localhost:8000/_internal/invocations \
      -H "Content-Type: application/json" \
      -H "X-On-Behalf-Of: 550e8400-e29b-41d4-a716-446655440000" \
      -d '{"prompt": "What is Docker?", "sessionId": "session-456", "project_id": "<project-uuid>"}'

    curl 'http://localhost:8000/_internal/invocations/<invocation-id>'
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Path, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models import Invocation, InvocationCreateRequest
from syntara.agent_orchestrator.services import InvocationService
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.models.principal import make_service_user
from syntara.core.utils.session_factory import create_session_factory_from_request
from syntara.workflows.executions_router import get_temporal_execution_service
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService


def _get_internal_caller_user(request: Request) -> User:
    """Build a User from X-On-Behalf-Of header for created_by attribution.

    Internal endpoints skip auth middleware, so this reads the header
    directly rather than relying on cert or JWT authentication.
    Falls back to a service principal when the header is absent.

    Unauthenticated POST /_internal/invocations therefore returns 202 if the
    body is valid. Do not expose /_internal/ on a public ingress; network
    isolation is the only access control.
    """
    on_behalf_of = request.headers.get("x-on-behalf-of")
    if on_behalf_of:
        try:
            user_id = UUID(on_behalf_of)
        except ValueError:
            pass
        else:
            return User(
                id=user_id,
                username="internal-caller",
                email="internal-caller@internal",
                first_name="internal-caller",
                is_enabled=True,
            )
    return make_service_user("worker.ao.svc")


async def create_internal_invocation(
    request_body: InvocationCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(_get_internal_caller_user)],
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
