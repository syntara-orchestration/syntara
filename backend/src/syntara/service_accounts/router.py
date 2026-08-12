"""Service Account CRUD API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.decorators import audit
from syntara.audit.models.audit_event import EventCategory
from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker, VisibilityFilter
from syntara.authz.engine import VisibilityResult
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.nexus_router import NexusRouter
from syntara.service_accounts.models.service_account import ServiceAccount
from syntara.service_accounts.schemas import (
    ServiceAccountCreate,
    ServiceAccountListParams,
    ServiceAccountListResponse,
    ServiceAccountRead,
    ServiceAccountUpdate,
)
from syntara.service_accounts.services.service_account_service import ServiceAccountService

router = NexusRouter(prefix="/service_accounts", tags=["Service Accounts"])

_sa_create = PermissionChecker("service_account", "create", body_project_field="project_id")
_sa_read = PermissionChecker(
    "service_account",
    "read",
    resource_model=ServiceAccount,
    resource_id_param="service_account_id",
)
_sa_update = PermissionChecker(
    "service_account",
    "update",
    resource_model=ServiceAccount,
    resource_id_param="service_account_id",
)
_sa_delete = PermissionChecker(
    "service_account",
    "delete",
    resource_model=ServiceAccount,
    resource_id_param="service_account_id",
)
_sa_disable = PermissionChecker(
    "service_account",
    "disable",
    resource_model=ServiceAccount,
    resource_id_param="service_account_id",
)
_sa_enable = PermissionChecker(
    "service_account",
    "enable",
    resource_model=ServiceAccount,
    resource_id_param="service_account_id",
)


# ============================================================================
# Dependency Injection
# ============================================================================


def get_service_account_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ServiceAccountService:
    """Dependency provider for ServiceAccountService."""
    return ServiceAccountService(db, current_user)


# ============================================================================
# Endpoints
# ============================================================================


@router.post(
    "",
    summary="Create service account",
    response_model=ServiceAccountRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_sa_create)],
    operation_id="create_service_account",
    response_description="Service account created",
)
@audit(EventCategory.USER_ACTION, event_action="service_account_create")
async def create_service_account(
    request: ServiceAccountCreate,
    service: Annotated[ServiceAccountService, Depends(get_service_account_service)],
) -> ServiceAccountRead:
    """Create a new service account."""
    service_account = await service.create_service_account(
        name=request.name,
        project_id=request.project_id,
        description=request.description,
    )
    return await service.to_read(service_account)


@router.get(
    "",
    summary="List service accounts",
    operation_id="list_service_accounts",
    response_description="List of service accounts",
)
async def list_service_accounts(
    request: Request,
    service: Annotated[ServiceAccountService, Depends(get_service_account_service)],
    params: Annotated[ServiceAccountListParams, Query()],
    visibility: Annotated[VisibilityResult, Depends(VisibilityFilter("service_account", "read"))],
) -> ServiceAccountListResponse:
    """List service accounts with project-scoped visibility and pagination."""
    return await service.list_service_accounts(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=request.query_params.items(),
        include_total=params.include_total,
        allowed_projects=visibility.to_allowed_projects(),
    )


@router.get(
    "/{service_account_id}",
    summary="Get service account",
    dependencies=[Depends(_sa_read)],
    operation_id="get_service_account",
    response_description="Service account details",
)
async def get_service_account(
    service_account_id: UUID,
    service: Annotated[ServiceAccountService, Depends(get_service_account_service)],
) -> ServiceAccountRead:
    """Get a service account by ID (secret is never included)."""
    service_account = await service.get_service_account(service_account_id)
    return await service.to_read(service_account)


@router.patch(
    "/{service_account_id}",
    summary="Update service account",
    dependencies=[Depends(_sa_update)],
    operation_id="update_service_account",
    response_description="Updated service account",
)
@audit(EventCategory.USER_ACTION, event_action="service_account_update", capture_args={"service_account_id"})
async def update_service_account(
    service_account_id: UUID,
    request: ServiceAccountUpdate,
    service: Annotated[ServiceAccountService, Depends(get_service_account_service)],
) -> ServiceAccountRead:
    """Update a service account's name and/or description."""
    service_account = await service.update_service_account(
        service_account_id,
        project_id=request.project_id,
        name=request.name,
        description=request.description,
    )
    return await service.to_read(service_account)


@router.delete(
    "/{service_account_id}",
    summary="Delete service account",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_sa_delete)],
    operation_id="delete_service_account",
    response_description="Service account deleted",
)
@audit(EventCategory.USER_ACTION, event_action="service_account_delete", capture_args={"service_account_id"})
async def delete_service_account(
    service_account_id: UUID,
    service: Annotated[ServiceAccountService, Depends(get_service_account_service)],
) -> None:
    """Soft-delete a service account."""
    await service.delete_service_account(service_account_id)


@router.post(
    "/{service_account_id}/disable",
    summary="Disable service account",
    dependencies=[Depends(_sa_disable)],
    operation_id="disable_service_account",
    response_description="Service account disabled",
)
@audit(EventCategory.USER_ACTION, event_action="service_account_disable", capture_args={"service_account_id"})
async def disable_service_account(
    service_account_id: UUID,
    service: Annotated[ServiceAccountService, Depends(get_service_account_service)],
) -> ServiceAccountRead:
    """Set a service account's status to disabled."""
    service_account = await service.disable_service_account(service_account_id)
    return await service.to_read(service_account)


@router.post(
    "/{service_account_id}/enable",
    summary="Enable service account",
    dependencies=[Depends(_sa_enable)],
    operation_id="enable_service_account",
    response_description="Service account enabled",
)
@audit(EventCategory.USER_ACTION, event_action="service_account_enable", capture_args={"service_account_id"})
async def enable_service_account(
    service_account_id: UUID,
    service: Annotated[ServiceAccountService, Depends(get_service_account_service)],
) -> ServiceAccountRead:
    """Set a service account's status to active."""
    service_account = await service.enable_service_account(service_account_id)
    return await service.to_read(service_account)
