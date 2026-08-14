"""Identity Provider API endpoints."""

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, Request, status
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.decorators import audit
from syntara.audit.models.audit_event import EventCategory
from syntara.auth import get_current_user
from syntara.auth.session import create_session_store
from syntara.authz.dependencies import PermissionChecker
from syntara.core.config.base import get_settings
from syntara.core.database.session import get_db
from syntara.core.models import User, UserIdentity
from syntara.core.services.secret_service import create_secret_service
from syntara.identity_providers.models import IdentityProviderListParams
from syntara.identity_providers.models.aap_setup import AAPOIDCSetupRequest
from syntara.identity_providers.models.identity_provider import (
    IdentityProviderCreate,
    IdentityProviderListResponse,
    IdentityProviderRead,
    IdentityProviderUpdate,
)
from syntara.identity_providers.services.aap_oidc_setup_service import AAPOIDCSetupService
from syntara.identity_providers.services.identity_provider_service import IdentityProviderService
from syntara.identity_providers.services.oidc_discovery import OIDCTestResult, test_oidc_connection

router = APIRouter(prefix="/identity_providers", tags=["Identity Providers"])

_idp_create = PermissionChecker("identity-provider", "create")
_idp_read = PermissionChecker("identity-provider", "read")
_idp_update = PermissionChecker("identity-provider", "update")
_idp_delete = PermissionChecker("identity-provider", "delete")
_idp_test = PermissionChecker("identity-provider", "test")

logger = structlog.stdlib.get_logger(__name__)


# ============================================================================
# Dependency Injection Providers
# ============================================================================


def get_identity_provider_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IdentityProviderService:
    """Dependency provider for IdentityProviderService."""
    return IdentityProviderService(db, current_user, create_secret_service(db))


# ============================================================================
# Test Connection
# ============================================================================


class OIDCTestRequest(IdentityProviderCreate):
    """Request body for testing an OIDC connection."""


@router.post(
    "/test",
    summary="Test identity provider",
    dependencies=[Depends(_idp_test)],
    operation_id="test_identity_provider",
    response_description="Test results",
)
async def test_identity_provider(
    provider_create: OIDCTestRequest,
    current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001
) -> OIDCTestResult:
    """Test identity provider connection without saving. Requires authentication."""
    return await test_oidc_connection(
        str(provider_create.configuration.issuer_url),
        disable_tls_verify=provider_create.configuration.disable_tls_verify,
    )


# ============================================================================
# AAP OIDC Push-Button Setup
# ============================================================================


@router.post(
    "/setup_aap_oidc",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_idp_create)],
    operation_id="setup_aap_oidc_provider",
    summary="Setup Ansible Automation Platform OIDC provider",
    description=(
        "Push-button setup: connects to Ansible Automation Platform, creates an OAuth2 application,"
        " and configures the identity provider with Ansible Automation Platform defaults."
    ),
    response_description="Ansible Automation Platform OIDC provider created",
)
@audit(EventCategory.USER_ACTION, event_action="identity_provider_aap_oidc_setup")
async def setup_aap_oidc_provider(
    setup_request: AAPOIDCSetupRequest,
    service: Annotated[IdentityProviderService, Depends(get_identity_provider_service)],
) -> IdentityProviderRead:
    """Set up an AAP OIDC identity provider."""
    settings = get_settings()
    setup_service = AAPOIDCSetupService(idp_service=service, settings=settings)
    return await setup_service.setup(setup_request)


# ============================================================================
# CRUD Endpoints
# ============================================================================


@router.get(
    "",
    summary="List identity providers",
    dependencies=[Depends(_idp_read)],
    operation_id="list_identity_providers",
    response_description="List of identity providers",
)
async def list_identity_providers(
    request: Request,
    service: Annotated[IdentityProviderService, Depends(get_identity_provider_service)],
    params: Annotated[IdentityProviderListParams, Query()],
) -> IdentityProviderListResponse:
    """List identity providers with filtering, sorting, and pagination."""
    return await service.list_providers(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=request.query_params.items(),
        include_total=params.include_total,
    )


@router.post(
    "",
    summary="Create identity provider",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_idp_create)],
    operation_id="create_identity_provider",
    response_description="Identity provider created",
)
@audit(EventCategory.USER_ACTION, event_action="identity_provider_create")
async def create_identity_provider(
    provider_create: IdentityProviderCreate,
    service: Annotated[IdentityProviderService, Depends(get_identity_provider_service)],
) -> IdentityProviderRead:
    """Create a new identity provider."""
    return await service.create_provider(provider_create)


@router.get(
    "/{provider_id}",
    summary="Get identity provider",
    dependencies=[Depends(_idp_read)],
    operation_id="get_identity_provider",
    response_description="Identity provider details",
)
async def get_identity_provider(
    provider_id: UUID,
    service: Annotated[IdentityProviderService, Depends(get_identity_provider_service)],
) -> IdentityProviderRead:
    """Get identity provider details by ID."""
    return await service.get_provider(provider_id)


@router.patch(
    "/{provider_id}",
    summary="Update identity provider",
    dependencies=[Depends(_idp_update)],
    operation_id="update_identity_provider",
)
@audit(EventCategory.USER_ACTION, event_action="identity_provider_update", capture_args={"provider_id"})
async def update_identity_provider(
    provider_id: UUID,
    provider_update: IdentityProviderUpdate,
    service: Annotated[IdentityProviderService, Depends(get_identity_provider_service)],
) -> IdentityProviderRead:
    """Update an identity provider."""
    return await service.update_provider(provider_id, provider_update)


@router.delete(
    "/{provider_id}",
    summary="Delete identity provider",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_idp_delete)],
    operation_id="delete_identity_provider",
    response_description="Identity provider deleted",
)
@audit(EventCategory.USER_ACTION, event_action="identity_provider_delete", capture_args={"provider_id"})
async def delete_identity_provider(
    provider_id: UUID,
    service: Annotated[IdentityProviderService, Depends(get_identity_provider_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Soft delete an identity provider."""
    # Find all users linked to this provider before deleting
    result = await db.exec(
        select(UserIdentity.user_id).where(col(UserIdentity.identity_provider_id) == provider_id).distinct()
    )
    affected_user_ids = result.all()

    await service.delete_provider(provider_id)

    # Invalidate tokens for all affected users so they get logged out
    if affected_user_ids:
        store = create_session_store(db)
        for user_id in affected_user_ids:
            await store.increment_token_version(user_id)
