"""Service Account Credential CRUD API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.decorators import audit
from syntara.audit.models.audit_event import EventCategory
from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.nexus_router import NexusRouter
from syntara.service_accounts.credential_schemas import (
    SACredentialCreate,
    SACredentialCreateResponse,
    SACredentialListParams,
    SACredentialListResponse,
    SACredentialRead,
    SACredentialRotateRequest,
    SACredentialRotateResponse,
)
from syntara.service_accounts.models.service_account import ServiceAccount
from syntara.service_accounts.services.credential_service import ServiceAccountCredentialService

router = NexusRouter(
    prefix="/service_accounts/{service_account_id}/credentials",
    tags=["Service Account Credentials"],
)

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
_sa_rotate_secret = PermissionChecker(
    "service_account",
    "rotate_secret",
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


def get_credential_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ServiceAccountCredentialService:
    """Dependency provider for ServiceAccountCredentialService."""
    return ServiceAccountCredentialService(db, current_user)


@router.post(
    "",
    summary="Create credential",
    response_model=SACredentialCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_sa_update)],
    operation_id="create_service_account_credential",
    response_description="Credential created",
)
@audit(EventCategory.USER_ACTION, event_action="sa_credential_create")
async def create_credential(
    service_account_id: UUID,
    request: SACredentialCreate,
    service: Annotated[ServiceAccountCredentialService, Depends(get_credential_service)],
) -> SACredentialCreateResponse:
    """Create a new credential for a service account; returns the one-time plaintext secret."""
    credential, plaintext_secret = await service.create_credential(
        service_account_id=service_account_id,
        credential_type=request.credential_type,
        grace_period_seconds=request.grace_period_seconds,
        expires_at=request.expires_at,
    )
    return service.to_create_response(credential, plaintext_secret)


@router.get(
    "",
    summary="List credentials",
    dependencies=[Depends(_sa_read)],
    operation_id="list_service_account_credentials",
    response_description="List of credentials",
)
async def list_credentials(
    service_account_id: UUID,
    request: Request,
    service: Annotated[ServiceAccountCredentialService, Depends(get_credential_service)],
    params: Annotated[SACredentialListParams, Query()],
) -> SACredentialListResponse:
    """List credentials for a service account with pagination."""
    return await service.list_credentials(
        service_account_id=service_account_id,
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=list(request.query_params.items()),
        include_total=params.include_total,
    )


@router.get(
    "/{credential_id}",
    summary="Get credential",
    dependencies=[Depends(_sa_read)],
    operation_id="get_service_account_credential",
    response_description="Credential details",
)
async def get_credential(
    service_account_id: UUID,
    credential_id: UUID,
    service: Annotated[ServiceAccountCredentialService, Depends(get_credential_service)],
) -> SACredentialRead:
    """Get a credential by ID (secret is never included)."""
    credential = await service.get_credential(credential_id, service_account_id=service_account_id)
    return service.to_read(credential)


@router.delete(
    "/{credential_id}",
    summary="Delete credential",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_sa_delete)],
    operation_id="delete_service_account_credential",
    response_description="Credential deleted",
)
@audit(EventCategory.USER_ACTION, event_action="sa_credential_delete", capture_args={"credential_id"})
async def delete_credential(
    service_account_id: UUID,
    credential_id: UUID,
    service: Annotated[ServiceAccountCredentialService, Depends(get_credential_service)],
) -> None:
    """Hard-delete a credential."""
    await service.delete_credential(credential_id, service_account_id=service_account_id)


@router.post(
    "/{credential_id}/rotate",
    summary="Rotate credential",
    dependencies=[Depends(_sa_rotate_secret)],
    operation_id="rotate_service_account_credential",
    response_description="Credential rotated",
)
@audit(EventCategory.USER_ACTION, event_action="sa_credential_rotate", capture_args={"credential_id"})
async def rotate_credential(
    service_account_id: UUID,
    credential_id: UUID,
    request: SACredentialRotateRequest,
    service: Annotated[ServiceAccountCredentialService, Depends(get_credential_service)],
) -> SACredentialRotateResponse:
    """Rotate a credential's secret; returns the new one-time plaintext secret."""
    credential, plaintext_secret = await service.rotate_credential(
        credential_id,
        service_account_id=service_account_id,
        grace_period_seconds=request.grace_period_seconds,
    )
    return service.to_rotate_response(credential, plaintext_secret)


@router.post(
    "/{credential_id}/disable",
    summary="Disable credential",
    dependencies=[Depends(_sa_disable)],
    operation_id="disable_service_account_credential",
    response_description="Credential disabled",
)
@audit(EventCategory.USER_ACTION, event_action="sa_credential_disable", capture_args={"credential_id"})
async def disable_credential(
    service_account_id: UUID,
    credential_id: UUID,
    service: Annotated[ServiceAccountCredentialService, Depends(get_credential_service)],
) -> SACredentialRead:
    """Set a credential's status to disabled."""
    credential = await service.disable_credential(credential_id, service_account_id=service_account_id)
    return service.to_read(credential)


@router.post(
    "/{credential_id}/enable",
    summary="Enable credential",
    dependencies=[Depends(_sa_enable)],
    operation_id="enable_service_account_credential",
    response_description="Credential enabled",
)
@audit(EventCategory.USER_ACTION, event_action="sa_credential_enable", capture_args={"credential_id"})
async def enable_credential(
    service_account_id: UUID,
    credential_id: UUID,
    service: Annotated[ServiceAccountCredentialService, Depends(get_credential_service)],
) -> SACredentialRead:
    """Set a credential's status to active."""
    credential = await service.enable_credential(credential_id, service_account_id=service_account_id)
    return service.to_read(credential)
