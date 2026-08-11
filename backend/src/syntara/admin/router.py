"""Admin revocation API endpoints.

Provides endpoints for reading and setting the global revocation timestamp,
revoking sessions by user, and revoking sessions by identity provider.
"""

from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.admin.schemas import GlobalRevocationTimestampRead, RevocationResponse
from syntara.admin.services import (
    find_idp_by_name,
    find_user_by_username,
    get_revocation_timestamp,
    revoke_idp_sessions,
    revoke_user_sessions,
    set_global_revocation_timestamp,
)
from syntara.audit.decorators import audit
from syntara.audit.models.audit_event import EventCategory
from syntara.auth import get_current_user
from syntara.authz.dependencies import PermissionChecker
from syntara.core.database.session import get_db
from syntara.core.models import User
from syntara.core.nexus_router import NexusRouter

logger = structlog.stdlib.get_logger(__name__)

router = NexusRouter(prefix="/admin/revocation", tags=["Admin"])

_require_revocation_read = PermissionChecker("admin:revocation", "read")
_require_revocation_execute = PermissionChecker("admin:revocation", "execute")

_USER_NOT_FOUND = "User not found"
_IDP_NOT_FOUND = "Identity provider not found"


@router.get(
    "",
    dependencies=[Depends(_require_revocation_read)],
    operation_id="get_global_revocation_timestamp",
    summary="Get global revocation timestamp",
    description="Read the current global revocation timestamp. "
    "Returns null fields if no revocation has been performed.",
    response_description="Current global revocation timestamp",
)
async def get_global_revocation(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GlobalRevocationTimestampRead:
    """Read the global revocation timestamp."""
    row = await get_revocation_timestamp(db)
    if row is None:
        return GlobalRevocationTimestampRead()
    return GlobalRevocationTimestampRead(
        revoked_before=row.revoked_before,
        updated_at=row.updated_at,
        updated_by=row.updated_by,
    )


@router.post(
    "",
    dependencies=[Depends(_require_revocation_execute)],
    operation_id="revoke_all_sessions",
    summary="Revoke all sessions",
    description="Set the global revocation timestamp to the current time. "
    "All tokens issued before this time will be rejected.",
    response_description="Revocation result",
)
@audit(EventCategory.SECURITY_EVENT)
async def revoke_all(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RevocationResponse:
    """Set the global revocation timestamp to the current time."""
    now = await set_global_revocation_timestamp(
        db,
        actor_username=current_user.username,
        actor_source="api",
    )
    await db.commit()

    timestamp_str = now.isoformat()
    logger.info(
        "Global revocation timestamp set via API",
        timestamp=timestamp_str,
        actor=current_user.username,
    )

    return RevocationResponse(
        message=f"Global revocation timestamp set to {timestamp_str}. "
        f"All tokens issued before this time are now invalid.",
    )


@router.post(
    "/users/{username}",
    dependencies=[Depends(_require_revocation_execute)],
    operation_id="revoke_user_sessions",
    summary="Revoke sessions for a user",
    description="Revoke all active sessions for a specific user. The user will need to re-authenticate.",
    response_description="Revocation result",
    responses={
        404: {"description": "User not found"},
    },
)
@audit(EventCategory.SECURITY_EVENT)
async def revoke_user(
    username: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RevocationResponse:
    """Revoke all sessions for a specific user."""
    user = await find_user_by_username(db, username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_USER_NOT_FOUND,
        )

    revoked_count = await revoke_user_sessions(
        db,
        user,
        actor_username=current_user.username,
        actor_source="api",
    )
    await db.commit()

    logger.info(
        "Revoked user sessions via API",
        username=user.username,
        sessions_revoked=revoked_count,
        actor=current_user.username,
    )

    return RevocationResponse(
        message=f"Revoked {revoked_count} session(s) for user '{user.username}'.",
        sessions_revoked=revoked_count,
    )


@router.post(
    "/identity_providers/{idp_name}",
    dependencies=[Depends(_require_revocation_execute)],
    operation_id="revoke_idp_sessions",
    summary="Revoke sessions for an identity provider",
    description="Revoke all active sessions authenticated via a specific "
    "identity provider. Users who authenticated via this provider will "
    "need to re-authenticate.",
    response_description="Revocation result",
    responses={
        404: {"description": "Identity provider not found"},
    },
)
@audit(EventCategory.SECURITY_EVENT)
async def revoke_idp(
    idp_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RevocationResponse:
    """Revoke all sessions for a specific identity provider."""
    provider = await find_idp_by_name(db, idp_name)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_IDP_NOT_FOUND,
        )

    revoked_count = await revoke_idp_sessions(
        db,
        provider.id,
        idp_name=provider.name,
        actor_username=current_user.username,
        actor_source="api",
    )
    await db.commit()

    logger.info(
        "Revoked IdP sessions via API",
        idp_name=provider.name,
        sessions_revoked=revoked_count,
        actor=current_user.username,
    )

    return RevocationResponse(
        message=f"Revoked {revoked_count} session(s) for identity provider '{provider.name}'.",
        sessions_revoked=revoked_count,
    )
