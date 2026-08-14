"""Invocation API endpoints for v1."""

import json
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import (
    Depends,
    Form,
    HTTPException,
    Path,
    Query,
    Request,
    status,
)
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models import (
    Invocation,
    InvocationCancelRequest,
    InvocationCancelResponse,
    InvocationCreateRequest,
    InvocationListParams,
    InvocationListResponse,
    InvocationRequestWithFile,
    InvocationTraceRead,
)
from syntara.agent_orchestrator.models.request import CancellationResult
from syntara.agent_orchestrator.services import InvocationService
from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker, VisibilityFilter
from syntara.authz.engine import VisibilityResult
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.nexus_router import NexusRouter
from syntara.core.utils.session_factory import create_session_factory_from_request
from syntara.workflows.executions_router import get_temporal_execution_service
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService

router = NexusRouter(prefix="/invocations", tags=["Invocation"])


logger = structlog.stdlib.get_logger(__name__)

_INTERNAL_ONLY_CONTEXT_KEYS = frozenset({"callback_url"})


def _sanitize_context_data(context_data: dict[str, object], request: Request) -> dict[str, object]:
    """Strip internal-only fields from externally-supplied context_data."""
    if getattr(request.state, "is_cert_authenticated", False):
        return context_data
    stripped = _INTERNAL_ONLY_CONTEXT_KEYS & context_data.keys()
    if stripped:
        logger.warning(
            "Stripped internal-only fields from client-supplied context_data",
            stripped_fields=sorted(stripped),
        )
    return {k: v for k, v in context_data.items() if k not in _INTERNAL_ONLY_CONTEXT_KEYS}


_invocation_perm_create_json = PermissionChecker("invocation", "create", body_project_field="project_id")
_invocation_perm_create_form = PermissionChecker("invocation", "create", form_project_field="project_id")
_invocation_perm_read = PermissionChecker("invocation", "read")
_invocation_perm_cancel = PermissionChecker("invocation", "cancel")

# ============================================================================
# Dependency Injection Providers
# ============================================================================


def get_invocation_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> InvocationService:
    """Dependency provider for InvocationService.

    FastAPI will call this function automatically, injecting all dependencies.
    This centralizes InvocationService creation for endpoints that don't need
    background tasks or custom session factories.

    Args:
        db: Database session
        current_user: Current authenticated user

    Returns:
        InvocationService configured with database session and user

    """
    return InvocationService(db, current_user)


async def get_invocation_service_with_temporal(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    temporal_service: Annotated[TemporalExecutionService | None, Depends(get_temporal_execution_service)],
) -> InvocationService:
    """Dependency provider for InvocationService with Temporal workflow support.

    Args:
        db: Database session (injected by FastAPI)
        current_user: Current authenticated user
        request: FastAPI request object (contains app with dependency overrides)
        temporal_service: Temporal execution service (injected by FastAPI)

    Returns:
        InvocationService configured with Temporal execution support

    """
    from syntara.workflows.services.execution_service import ExecutionService  # noqa: PLC0415

    session_factory = create_session_factory_from_request(request)
    execution_service = ExecutionService(db, current_user, temporal_service=temporal_service)
    return InvocationService(
        db,
        current_user,
        session_factory=session_factory,
        execution_service=execution_service,
    )


def _validate_multipart_required_fields(prompt: str | None, session_id: str | None) -> tuple[str, str]:
    """Validate required fields for multipart requests.

    Args:
        prompt: Prompt field
        session_id: Session ID field

    Returns:
        Tuple of (prompt, session_id) after validation

    Raises:
        HTTPException: If required fields are missing

    """
    if prompt is None or session_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="prompt and session_id are required",
        )
    return (prompt, session_id)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create invocation (async)",
    description="Accept async agent invocation request and return invocation ID immediately.",
    dependencies=[Depends(_invocation_perm_create_json)],
    operation_id="create_invocation",
    response_description="Invocation accepted",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "workflowGeneration": {
                            "summary": "Workflow generation request",
                            "value": {
                                "prompt": "Create a workflow to deploy app to production",
                                "sessionId": "session-001",
                            },
                        }
                    }
                }
            }
        },
        "responses": {
            "202": {
                "content": {
                    "application/json": {
                        "examples": {
                            "invocationAccepted": {
                                "summary": "Invocation accepted",
                                "value": {
                                    "id": "550e8400-e29b-41d4-a716-446655440000",
                                    "prompt": "Create a workflow to deploy app",
                                    "session_id": "session-001",
                                    "status": "running",
                                },
                            }
                        }
                    }
                }
            }
        },
    },
)
async def create_invocation(
    request: Request,
    request_body: InvocationCreateRequest,
    service: Annotated[InvocationService, Depends(get_invocation_service_with_temporal)],
) -> Invocation:
    """Accept async invocation request (JSON).

    Args:
        request: FastAPI request object
        request_body: JSON request body with prompt, session_id, and optional context_data
        service: Invocation service (with background tasks support)

    Returns:
        Created invocation

    Raises:
        HTTPException: 503 if LLM not configured

    """
    return await service.create_invocation(
        prompt=request_body.prompt,
        session_id=request_body.session_id,
        project_id=request_body.project_id,
        context_data=_sanitize_context_data(request_body.context_data, request),
        files=None,
    )


@router.post(
    "/chat",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create invocation with file uploads (async)",
    description="Accept async agent invocation request with optional file uploads via multipart/form-data.",
    dependencies=[Depends(_invocation_perm_create_form)],
    operation_id="create_invocation_chat",
    response_description="Invocation accepted",
)
async def create_invocation_chat(
    request: Request,
    service: Annotated[InvocationService, Depends(get_invocation_service_with_temporal)],
    form: Annotated[InvocationRequestWithFile, Form(media_type="multipart/form-data")],
) -> Invocation:
    """Accept async invocation request with optional file uploads (multipart/form-data).

    Args:
        request: FastAPI request object
        service: Invocation service (with background tasks support)
        form: Multipart form body with prompt, session_id, optional context_data and files

    Returns:
        Created invocation with file_ids in context_data if files uploaded

    Raises:
        HTTPException: 400 for validation errors, 503 if LLM not configured

    """
    prompt, session_id = _validate_multipart_required_fields(form.prompt, form.session_id)
    context_data: dict[str, object] | None = json.loads(form.context_data) if form.context_data else None

    try:
        project_id = UUID(form.project_id)
    except ValueError:
        raise HTTPException(  # noqa: B904
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="project_id must be a valid UUID"
        )

    return await service.create_invocation(
        prompt=prompt,
        session_id=session_id,
        project_id=project_id,
        context_data=_sanitize_context_data(context_data, request) if context_data else context_data,
        files=form.files,
    )


@router.get(
    "",
    summary="List invocations",
    description="List invocations with cursor-based pagination and filtering",
    dependencies=[Depends(_invocation_perm_read)],
    operation_id="list_invocations",
    response_description="List of invocations",
    openapi_extra={
        "responses": {
            "200": {
                "content": {
                    "application/json": {
                        "examples": {
                            "paginatedList": {
                                "summary": "Paginated invocation list",
                                "value": {
                                    "resources": [
                                        {
                                            "id": "550e8400-e29b-41d4-a716-446655440000",
                                            "prompt": "Deploy app to production",
                                            "session_id": "session-001",
                                            "status": "running",
                                        }
                                    ],
                                    "next": None,
                                    "prev": None,
                                },
                            }
                        }
                    }
                }
            }
        }
    },
)
async def list_invocations(
    request: Request,
    service: Annotated[InvocationService, Depends(get_invocation_service)],
    params: Annotated[InvocationListParams, Query()],
    visibility: Annotated[VisibilityResult, Depends(VisibilityFilter("invocation", "read"))],
) -> InvocationListResponse:
    """List invocations with filtering, sorting, and pagination.

    Supports filtering using query parameters with advanced operators:
    - prompt: Filter by prompt text (prompt[contains]=text, prompt[starts_with]=text)
    - created_by: Filter by creator user ID (created_by=uuid)
    - session_id: Filter by session ID (session_id=id, session_id[contains]=text)
    - status: Filter by invocation status (status=created|running|completed|failed)
    - labels: Filter by labels using bracket notation (labels[environment]=production)
    - created_at: Filter by creation time (created_at[gt|gte|lt|lte]=timestamp)
    - updated_at: Filter by update time (updated_at[gt|gte|lt|lte]=timestamp)

    Uses cursor-based pagination for scalability and consistency.

    Args:
        request: FastAPI request object containing query parameters
        service: Invocation service
        params: Query parameters for pagination and filtering
        visibility: Resolved visibility for the current user

    Returns:
        InvocationListResponse with invocations, pagination metadata, and optional total

    """
    return await service.list_invocations(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=request.query_params.items(),
        include_total=params.include_total,
        allowed_projects=visibility.to_allowed_projects(),
    )


@router.get(
    "/{invocation_id}/trace",
    summary="Get invocation trace",
    description="Retrieve the agent execution trace for a completed invocation, "
    "including reasoning steps, tool calls, and tool results.",
    dependencies=[Depends(_invocation_perm_read)],
    operation_id="get_invocation_trace",
    response_description="Agent execution trace",
)
async def get_invocation_trace(
    invocation_id: Annotated[UUID, Path(description="UUID of the invocation")],
    service: Annotated[InvocationService, Depends(get_invocation_service)],
) -> InvocationTraceRead:
    """Get agent execution trace for an invocation.

    Returns the persisted trace data including reasoning blocks,
    tool calls, and tool results accumulated during agent execution.

    Args:
        invocation_id: UUID of the invocation
        service: Invocation service

    Returns:
        InvocationTraceRead with invocation_id, status, and agent_trace

    Raises:
        HTTPException: 404 if invocation not found

    """
    invocation = await service.get_invocation(invocation_id)
    if not invocation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invocation {invocation_id} not found",
        )

    # Prefer agent_trace from result (authoritative, includes computed aggregates).
    # Fall back to trace_events column if result doesn't contain it.
    agent_trace = None
    if isinstance(invocation.result, dict):
        agent_trace = invocation.result.get("agent_trace")
    if agent_trace is None and invocation.trace_events:
        agent_trace = {
            "model": invocation.model_name or "unknown",
            "total_tokens": sum(t for s in invocation.trace_events if isinstance(t := s.get("tokens"), int)),
            "total_duration_ms": sum(t for s in invocation.trace_events if isinstance(t := s.get("duration_ms"), int)),
            "steps": invocation.trace_events,
        }

    return InvocationTraceRead(
        invocation_id=invocation.id,
        status=invocation.status,
        agent_trace=agent_trace,
    )


# NOTE: This endpoint is primarily for TESTING and DEBUGGING purposes.
# In production, you would typically use WebSockets or Server-Sent Events
# for real-time result streaming instead of polling this endpoint.
# This is useful during development to:
# - View the actual LLM responses from GenericAgent
# - Inspect workflow execution results
# - Debug routing decisions and agent behavior
@router.get(
    "/{invocation_id}",
    summary="Get invocation details (testing/debug)",
    description="Retrieve full invocation details including the result. "
    "NOTE: This endpoint is for testing and debugging. "
    "Production systems should use WebSockets for real-time results.",
    dependencies=[Depends(_invocation_perm_read)],
    operation_id="get_invocation",
    response_description="Invocation details",
    openapi_extra={
        "responses": {
            "200": {
                "content": {
                    "application/json": {
                        "examples": {
                            "completedInvocation": {
                                "summary": "Completed invocation",
                                "value": {
                                    "id": "550e8400-e29b-41d4-a716-446655440000",
                                    "prompt": "What deployment tools are available?",
                                    "session_id": "test-session-123",
                                    "status": "completed",
                                },
                            }
                        }
                    }
                }
            }
        }
    },
)
async def get_invocation(
    invocation_id: Annotated[
        str,
        Path(
            description="UUID of the invocation to retrieve",
        ),
    ],
    service: Annotated[InvocationService, Depends(get_invocation_service)],
) -> Invocation:
    """Get invocation details including result.

    NOTE: This endpoint is primarily for TESTING and DEBUGGING.
    Use WebSockets for production real-time result streaming.

    Args:
        invocation_id: UUID of the invocation
        service: Invocation service

    Returns:
        Full invocation details including:
        - Metadata (id, status, timestamps)
        - The actual result from the agent (LLM response or workflow output)
        - Error information if failed
        - Context and checkpoint data

    Raises:
        HTTPException: 404 if invocation not found, 500 for other errors

    Example:
        # After creating an invocation, retrieve its result:
        # response = await client.get("/api/v1/invocations/{id}")
        # print(response.json()["result"])  # See the actual LLM response

    """
    # Parse UUID
    uuid_obj = UUID(invocation_id)

    # Retrieve invocation from database
    invocation = await service.get_invocation(uuid_obj)

    # Check if invocation exists
    if not invocation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invocation {invocation_id} not found",
        )

    # NOTE: The 'result' field contains the actual agent response.
    # For GenericAgent: {"type": "answer", "content": "...", "metadata": {...}}
    # For WorkflowGeneratorAgent: workflow execution results
    return invocation


@router.post(
    "/{invocation_id}/cancel",
    summary="Cancel invocation",
    description="Cancel a running or pending invocation.",
    dependencies=[Depends(_invocation_perm_cancel)],
    operation_id="cancel_invocation",
    response_description="Cancellation result",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "default_reason": {
                            "summary": "Default cancellation reason",
                            "value": {"reason": "User cancelled"},
                        }
                    }
                }
            }
        },
        "responses": {
            "200": {
                "content": {
                    "application/json": {
                        "examples": {
                            "success": {
                                "summary": "Successful cancellation",
                                "value": {
                                    "success": True,
                                    "message": "Invocation 550e8400-e29b-41d4-a716-446655440000 cancelled successfully",
                                },
                            }
                        }
                    }
                }
            }
        },
    },
)
async def cancel_invocation(
    invocation_id: Annotated[
        str,
        Path(
            description="UUID of the invocation to cancel",
        ),
    ],
    request_body: InvocationCancelRequest,
    service: Annotated[InvocationService, Depends(get_invocation_service)],
) -> InvocationCancelResponse:
    """Cancel a running or pending invocation.

    Args:
        invocation_id: UUID of the invocation to cancel
        request_body: Request containing optional cancellation reason
        service: Invocation service

    Returns:
        InvocationCancelResponse indicating success or failure

    Raises:
        HTTPException: 400 for invalid UUID, 404 if not found or unauthorized, 409 if not cancellable

    """
    # Parse UUID
    uuid_obj = UUID(invocation_id)

    # Attempt cancellation
    result = await service.cancel_invocation(uuid_obj, request_body.reason)

    if result == CancellationResult.SUCCESS:
        return InvocationCancelResponse(
            success=True,
            message=f"Invocation {invocation_id} cancelled successfully",
        )

    if result == CancellationResult.NOT_FOUND:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invocation {invocation_id} not found",
        )

    if result == CancellationResult.NOT_CANCELLABLE:
        # Get the invocation to provide current status in error message
        invocation = await service.get_invocation(uuid_obj)
        current_status = invocation.status.value if invocation else "unknown"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invocation {invocation_id} cannot be cancelled (status: {current_status})",
        )

    # Should never happen, but defensive programming
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unexpected cancellation result",
    )
