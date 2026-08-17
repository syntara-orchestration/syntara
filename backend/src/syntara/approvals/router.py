"""Approvals API endpoints."""

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import Depends, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

if TYPE_CHECKING:
    from syntara.authz.evaluator import AuthzEvaluator

from syntara.approvals.models import ApprovalRequestRead
from syntara.approvals.models.api_models import (
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    BatchApprovalRequest,
)
from syntara.approvals.models.approval_request import ApprovalListResponse, ApprovalRequest
from syntara.approvals.models.batch_response import BatchApprovalResponse
from syntara.approvals.models.query_params import ApprovalListParams
from syntara.approvals.services.approval_service import ApprovalService
from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker, VisibilityFilter, get_authz_evaluator
from syntara.authz.engine import VisibilityResult
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.syntara_router import SyntaraRouter

router = SyntaraRouter(prefix="/approvals", tags=["Approvals"])

_ALL_ROLES = ["admin", "auditor", "user", "project-admin", "project-user", "project-auditor"]

_approval_perm_read = PermissionChecker(
    "approval",
    "read",
    resource_model=ApprovalRequest,
    resource_id_param="approval_id",
)
_approval_perm_decide = PermissionChecker(
    "approval",
    "decide",
    resource_model=ApprovalRequest,
    resource_id_param="approval_id",
)
_approval_perm_delete = PermissionChecker(
    "approval",
    "delete",
    resource_model=ApprovalRequest,
    resource_id_param="approval_id",
)

# Exception handlers are registered globally in main.py via the exception registry
# Domain exceptions raised by services automatically bubble up to global handlers


# ============================================================================
# Dependency Injection Providers
# ============================================================================


def get_approval_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    evaluator: Annotated["AuthzEvaluator", Depends(get_authz_evaluator)],
) -> ApprovalService:
    """Dependency provider for ApprovalService.

    FastAPI will call this function automatically, injecting all dependencies.
    This centralizes ApprovalService creation across all endpoints.

    Args:
        db: Database session
        current_user: Current authenticated user
        evaluator: Authorization evaluator for policy checks

    Returns:
        ApprovalService configured with database session and user

    """
    return ApprovalService(db, current_user, evaluator)


# ============================================================================
# Approvals endpoints
# ============================================================================


@router.get(
    "",
    operation_id="list_approvals",
    summary="List approval requests",
    response_description="List of approval requests",
)
async def list_approvals(
    request: Request,
    service: Annotated[ApprovalService, Depends(get_approval_service)],
    params: Annotated[ApprovalListParams, Depends()],
    visibility: Annotated[VisibilityResult, Depends(VisibilityFilter("approval", "read"))],
) -> ApprovalListResponse:
    """List approval requests with filtering, sorting, and pagination.

    Supports filtering using query parameters with standard operators:
    - status: Filter by approval status (status=pending)
    - execution_id: Filter by parent execution ID (execution_id=uuid)

    Uses cursor-based pagination for scalability and consistency.

    """
    return await service.list(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=request.query_params.items(),
        include_total=params.include_total,
        allowed_projects=visibility.to_allowed_projects(),
    )


# Service-to-service endpoint (Temporal worker creates approvals).
# Gated to admin for now; replace with proper service-to-service auth.
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionChecker("approval", "create"))],
    operation_id="create_approval",
    summary="Create approval request",
    response_description="Approval request created",
)
async def create_approval(
    request: ApprovalCreateRequest,
    service: Annotated[ApprovalService, Depends(get_approval_service)],
) -> ApprovalRequestRead:
    """Create a new approval request.

    This is an internal endpoint called by the Workflows component when
    a workflow execution reaches an approval node. It should not be called
    directly by end users.

    """
    return await service.create(request)


@router.get(
    "/{approval_id}",
    dependencies=[Depends(_approval_perm_read)],
    operation_id="get_approval",
    summary="Get approval request",
    response_description="Approval request details",
)
async def get_approval(
    approval_id: UUID,
    service: Annotated[ApprovalService, Depends(get_approval_service)],
) -> ApprovalRequestRead:
    """Get an approval request by ID.

    The response includes:
    - Full request context (workflow inputs, completed step outputs)
    - Next steps for both approval and rejection paths
    - Decision history if already decided

    """
    return await service.get(approval_id)


@router.patch(
    "/{approval_id}",
    dependencies=[Depends(_approval_perm_decide)],
    operation_id="decide_approval",
    summary="Submit approval decision",
    response_description="Updated approval request",
)
async def decide_approval(
    approval_id: UUID,
    request: ApprovalDecisionRequest,
    service: Annotated[ApprovalService, Depends(get_approval_service)],
) -> ApprovalRequestRead:
    """Submit an approval decision (approve or reject).

    Only pending approval requests can be decided. Attempting to modify an approval
    that is already approved, rejected, expired, or cancelled will return an error.

    When a decision is submitted:
    1. The approval request status is updated
    2. The decided_by, decided_at, and decision_notes fields are populated
    3. A signal is sent to the workflow to resume execution on the appropriate path

    """
    return await service.decide(approval_id, request)


@router.delete(
    "/{approval_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_approval_perm_delete)],
    operation_id="delete_approval",
    summary="Delete a pending approval request",
)
async def delete_approval(
    approval_id: UUID,
    service: Annotated[ApprovalService, Depends(get_approval_service)],
) -> None:
    """Delete a pending approval request.

    Only pending approval requests can be deleted. Attempting to delete an
    already-decided approval returns 409 Conflict.

    """
    await service.delete(approval_id)


@router.post(
    "/batch",
    operation_id="batch_decide_approvals",
    summary="Batch approve/reject multiple requests",
    response_description="Batch decision results",
)
async def batch_decide_approvals(
    request: BatchApprovalRequest,
    service: Annotated[ApprovalService, Depends(get_approval_service)],
) -> BatchApprovalResponse:
    """Submit decisions for multiple approval requests at once.

    Authorization is validated per-approval: Each approval is checked for project-scoped
    approval:decide permission AND approver list membership. Users with project-scoped
    permissions can batch approve requests within their authorized projects.

    This endpoint processes each decision independently. If some decisions fail due to
    authorization or validation errors, the successful ones are still recorded. The
    response includes detailed results for each decision.

    Use cases:
    - Approving multiple related requests at once
    - Bulk rejection of stale or irrelevant requests

    """
    return await service.batch_decide(request)
