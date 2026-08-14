"""Credential Management API endpoints."""

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import Depends, Query, Request, status
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.decorators import audit
from syntara.audit.models.audit_event import EventCategory
from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker, VisibilityFilter, get_authz_evaluator
from syntara.authz.engine import VisibilityResult, resolve_credential_use_visibility, resolve_visibility
from syntara.authz.evaluator import AuthzEvaluator
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.nexus_router import NexusRouter
from syntara.core.services.secret_service import create_secret_service
from syntara.credentials.exceptions import CredentialNotFoundError
from syntara.credentials.models import (
    CredentialCreate,
    CredentialListParams,
    CredentialListResponse,
    CredentialRead,
    CredentialType,
    CredentialTypeListResponse,
    CredentialTypeRead,
    CredentialUpdate,
)
from syntara.credentials.models.credential import Credential, CredentialWorkflowListResponse
from syntara.credentials.services.credential_service import CredentialService

router = NexusRouter(tags=["Credentials"])

logger = structlog.stdlib.get_logger(__name__)


# ============================================================================
# Permission Checkers
# ============================================================================

_cred_perm_read = PermissionChecker(
    "credential",
    "read",
    resource_model=Credential,
    resource_id_param="credential_id",
)
_cred_perm_create = PermissionChecker(
    "credential",
    "create",
    body_project_field="project_id",
)
_cred_perm_update = PermissionChecker(
    "credential",
    "update",
    resource_model=Credential,
    resource_id_param="credential_id",
    owner_field="created_by",
)
_cred_perm_delete = PermissionChecker(
    "credential",
    "delete",
    resource_model=Credential,
    resource_id_param="credential_id",
)


# ============================================================================
# Dependency Injection
# ============================================================================


def get_credential_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CredentialService:
    """Dependency provider for CredentialService."""
    return CredentialService(db, current_user, create_secret_service(db))


# ============================================================================
# Credential Endpoints
# ============================================================================


@router.post(
    "/credentials",
    summary="Create credential",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_cred_perm_create)],
    operation_id="create_credential",
)
@audit(EventCategory.USER_ACTION, event_action="credential_create")
async def create_credential(
    data: CredentialCreate,
    service: Annotated[CredentialService, Depends(get_credential_service)],
) -> CredentialRead:
    """Create a new Credential with encrypted inputs."""
    return await service.create_credential(data)


class _CredentialVisibility(VisibilityFilter):
    """Credential list visibility: dispatches to use-scoped or read-scoped OPA path.

    Subclasses VisibilityFilter so the RBAC compliance check recognises it.
    For for_action=use: Python shortcut (0 OPA evals for standard roles).
    For standard list: delegates to VisibilityFilter for credential:read (1 OPA eval).
    """

    def __init__(self) -> None:
        super().__init__("credential", "read")

    async def __call__(  # type: ignore[override]
        self,
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
        evaluator: Annotated[AuthzEvaluator, Depends(get_authz_evaluator)],
    ) -> VisibilityResult:
        """Resolve visibility, skipping the read-path OPA call when for_action=use.

        Uses Depends(get_authz_evaluator) so test dependency_overrides apply correctly.
        """
        if getattr(request.state, "is_cert_authenticated", False):
            return VisibilityResult(unrestricted=True)
        if request.query_params.get("for_action") == "use":
            return await resolve_credential_use_visibility(
                db=db,
                evaluator=evaluator,
                user_id=current_user.id,
                user_labels=current_user.labels,
                user_metadata=current_user.authz_metadata,
            )
        return await resolve_visibility(
            db=db,
            evaluator=evaluator,
            user_id=current_user.id,
            resource_type="credential",
            action="read",
            user_labels=current_user.labels,
            user_metadata=current_user.authz_metadata,
        )


@router.get("/credentials", summary="List credentials", operation_id="list_credentials")
async def list_credentials(
    request: Request,
    service: Annotated[CredentialService, Depends(get_credential_service)],
    params: Annotated[CredentialListParams, Query()],
    visibility: Annotated[VisibilityResult, Depends(_CredentialVisibility())],
) -> CredentialListResponse:
    """List Credentials with filtering and pagination. Metadata only, no secrets.

    When for_action=use, returns only credentials the user has credential:use
    permission on (for workflow builder credential selection).
    """
    # Strip for_action from query params before passing to service (not a filterable field)
    filtered_query_params = [(k, v) for k, v in request.query_params.items() if k != "for_action"]
    return await service.list_credentials(
        limit=params.limit,
        cursor=params.cursor,
        sort=params.sort,
        query_params_items=filtered_query_params,
        include_total=params.include_total,
        allowed_projects=visibility.to_allowed_projects(),
    )


@router.get(
    "/credentials/{credential_id}",
    summary="Get credential",
    dependencies=[Depends(_cred_perm_read)],
    operation_id="get_credential",
)
async def get_credential(
    credential_id: UUID,
    service: Annotated[CredentialService, Depends(get_credential_service)],
) -> CredentialRead:
    """Get a Credential. Secret fields masked as $encrypted$."""
    return await service.get_credential(credential_id)


@router.patch(
    "/credentials/{credential_id}",
    summary="Update credential",
    dependencies=[Depends(_cred_perm_update)],
    operation_id="update_credential",
)
@audit(EventCategory.USER_ACTION, event_action="credential_update", capture_args={"credential_id"})
async def update_credential(
    credential_id: UUID,
    data: CredentialUpdate,
    service: Annotated[CredentialService, Depends(get_credential_service)],
) -> CredentialRead:
    """Update a Credential. Fields set to $encrypted$ retain existing values."""
    return await service.update_credential(credential_id, data)


@router.delete(
    "/credentials/{credential_id}",
    summary="Delete credential",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_cred_perm_delete)],
    operation_id="delete_credential",
)
@audit(EventCategory.USER_ACTION, event_action="credential_delete", capture_args={"credential_id"})
async def delete_credential(
    credential_id: UUID,
    service: Annotated[CredentialService, Depends(get_credential_service)],
) -> None:
    """Delete a Credential."""
    await service.delete_credential(credential_id)


@router.get(
    "/credentials/{credential_id}/workflows",
    summary="Get credential workflows",
    dependencies=[Depends(_cred_perm_read)],
    operation_id="get_credential_workflows",
)
async def get_credential_workflows(
    credential_id: UUID,
    service: Annotated[CredentialService, Depends(get_credential_service)],
) -> CredentialWorkflowListResponse:
    """Get workflows that reference this credential.

    Returns workflows with nodes that have credential_id in their executor configs.
    """
    workflows = await service.get_credential_workflows(credential_id)
    return CredentialWorkflowListResponse(resources=workflows)


# ============================================================================
# Credential Type Endpoints (read-only for GA, auth-only, no RBAC needed)
# ============================================================================


@router.get("/credential_types", summary="List credential types", operation_id="list_credential_types")
async def list_credential_types(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> CredentialTypeListResponse:
    """List all Credential Types including preseeded managed types.

    Each type includes a credential_count of credentials using it.
    """
    # Subquery: count credentials per type
    count_subq = (
        select(
            Credential.credential_type_id,
            func.count(Credential.id).label("credential_count"),  # type: ignore[arg-type]
        )
        .group_by(Credential.credential_type_id)  # type: ignore[arg-type]
        .subquery()
    )

    stmt = select(
        CredentialType,
        func.coalesce(count_subq.c.credential_count, 0).label("credential_count"),
    ).outerjoin(
        count_subq,
        CredentialType.id == count_subq.c.credential_type_id,  # type: ignore[arg-type]
    )

    result = await db.exec(stmt)
    rows = result.all()

    resources = []
    for row in rows:
        cred_type, count = row[0], row[1]
        read = CredentialTypeRead.model_validate(cred_type)
        read.credential_count = count
        resources.append(read)

    return CredentialTypeListResponse(resources=resources)


@router.get("/credential_types/{credential_type_id}", summary="Get credential type", operation_id="get_credential_type")
async def get_credential_type(
    credential_type_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> CredentialTypeRead:
    """Get a single Credential Type with credential_count."""
    cred_type = await db.get(CredentialType, credential_type_id)
    if not cred_type:
        msg = f"Credential type with ID '{credential_type_id}' not found"
        raise CredentialNotFoundError(msg)

    # Count credentials for this type
    count_stmt = select(func.count(Credential.id)).where(  # type: ignore[arg-type]
        Credential.credential_type_id == credential_type_id,
    )
    count_result = await db.exec(count_stmt)
    credential_count = count_result.one()

    read = CredentialTypeRead.model_validate(cred_type)
    read.credential_count = credential_count
    return read
