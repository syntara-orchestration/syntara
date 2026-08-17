"""Shared revocation operations used by both CLI and API.

Each function accepts a database session and performs the revocation
operation within that session.  Audit events are dispatched immediately
after the mutation so they are as close to the action as possible.
The caller is responsible for committing the transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import update as sa_update
from sqlmodel import select

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.auth.audit.global_revocation import GlobalRevocationEvent
from syntara.auth.audit.session_revocation import SessionRevocationEvent
from syntara.auth.models.global_revocation_timestamp import GlobalRevocationTimestamp
from syntara.auth.session import create_session_store

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User
    from syntara.identity_providers.models.identity_provider import IdentityProvider

logger = structlog.stdlib.get_logger(__name__)


async def set_global_revocation_timestamp(
    db: AsyncSession,
    *,
    actor_username: str,
    actor_source: str,
) -> datetime:
    """Set the global revocation timestamp to the current UTC time.

    Upserts the singleton row in ``global_revocation_timestamp`` and
    dispatches a ``GlobalRevocationEvent`` audit event.

    Args:
        db: Active database session (caller must commit).
        actor_username: Username of the actor performing the revocation.
        actor_source: Source of the action (``"cli"`` or ``"api"``).

    Returns:
        The revocation timestamp that was set.

    """
    now = datetime.now(UTC)
    stmt = (
        sa_update(GlobalRevocationTimestamp)
        .where(GlobalRevocationTimestamp.id == 1)  # type: ignore[arg-type]
        .values(revoked_before=now, updated_at=now, updated_by=actor_username)
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:  # type: ignore[attr-defined]
        existing = (await db.exec(select(GlobalRevocationTimestamp))).one_or_none()
        if existing is None:
            db.add(GlobalRevocationTimestamp(id=1, revoked_before=now, updated_at=now, updated_by=actor_username))

    timestamp_str = now.isoformat()
    try:
        AuditEventDispatcher.dispatch(
            GlobalRevocationEvent(
                actor_username=actor_username,
                actor_source=actor_source,
                revocation_timestamp=timestamp_str,
            )
        )
    except Exception:
        logger.exception(
            "Audit dispatch failed for global revocation",
            timestamp=timestamp_str,
            actor=actor_username,
        )

    return now


async def get_revocation_timestamp(db: AsyncSession) -> GlobalRevocationTimestamp | None:
    """Read the global revocation timestamp from the database.

    Args:
        db: Active database session.

    Returns:
        The singleton row, or ``None`` if no revocation timestamp has been set.

    """
    result = await db.exec(select(GlobalRevocationTimestamp))
    return result.one_or_none()


async def find_user_by_username(db: AsyncSession, username: str) -> User | None:
    """Look up a non-deleted user by username (case-insensitive).

    Args:
        db: Active database session.
        username: Username to look up.

    Returns:
        The ``User`` object, or ``None`` if not found.

    """
    from syntara.core.models import User  # noqa: PLC0415

    result = await db.exec(
        select(User).filter(
            User.username == username.lower(),  # type: ignore[arg-type]
            User.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    return result.one_or_none()


async def revoke_user_sessions(
    db: AsyncSession,
    user: User,
    *,
    actor_username: str,
    actor_source: str,
) -> int:
    """Revoke all sessions for a user and increment their token version.

    Dispatches a ``SessionRevocationEvent`` audit event after revoking.

    Args:
        db: Active database session (caller must commit).
        user: The user whose sessions should be revoked.
        actor_username: Username of the actor performing the revocation.
        actor_source: Source of the action (``"cli"`` or ``"api"``).

    Returns:
        Number of sessions revoked.

    """
    store = create_session_store(db)
    revoked_count = await store.revoke_all_for_user(user.id)
    # Prefer request-scoped actor from audit middleware (API). Only fall back to
    # a username-only ContextVar when none is present (CLI) — never clobber a
    # populated actor_id (AAP-83651).
    from syntara.audit.context_managers import actor_context  # noqa: PLC0415
    from syntara.audit.emitter import AuditActorContext, actor_context_var  # noqa: PLC0415
    from syntara.core.models.principal import PrincipalType  # noqa: PLC0415

    existing = actor_context_var.get()
    if existing and existing.actor_id:
        await store.increment_token_version(user.id)
    else:
        with actor_context(
            actor=AuditActorContext(
                actor_id=None,
                actor_username=actor_username,
                actor_type=PrincipalType.USER,
            )
        ):
            await store.increment_token_version(user.id)

    try:
        AuditEventDispatcher.dispatch(
            SessionRevocationEvent(
                actor_username=actor_username,
                actor_source=actor_source,
                target_type="user",
                target_identifier=user.username,
                sessions_revoked=revoked_count,
            )
        )
    except Exception:
        logger.exception(
            "Audit dispatch failed for user session revocation",
            username=user.username,
            sessions_revoked=revoked_count,
            actor=actor_username,
        )

    return revoked_count


async def find_idp_by_name(db: AsyncSession, idp_name: str) -> IdentityProvider | None:
    """Look up a non-deleted identity provider by name.

    Args:
        db: Active database session.
        idp_name: Name of the identity provider.

    Returns:
        The ``IdentityProvider`` object, or ``None`` if not found.

    """
    from syntara.identity_providers.models.identity_provider import IdentityProvider  # noqa: PLC0415

    result = await db.exec(
        select(IdentityProvider).filter(
            IdentityProvider.name == idp_name,  # type: ignore[arg-type]
        )
    )
    return result.one_or_none()


async def revoke_idp_sessions(
    db: AsyncSession,
    idp_id: UUID,
    *,
    idp_name: str,
    actor_username: str,
    actor_source: str,
) -> int:
    """Revoke all sessions authenticated via an identity provider.

    Dispatches a ``SessionRevocationEvent`` audit event after revoking.

    Args:
        db: Active database session (caller must commit).
        idp_id: UUID of the identity provider.
        idp_name: Name of the identity provider (for the audit event).
        actor_username: Username of the actor performing the revocation.
        actor_source: Source of the action (``"cli"`` or ``"api"``).

    Returns:
        Number of sessions revoked.

    """
    store = create_session_store(db)
    revoked_count = await store.revoke_by_idp(str(idp_id))

    try:
        AuditEventDispatcher.dispatch(
            SessionRevocationEvent(
                actor_username=actor_username,
                actor_source=actor_source,
                target_type="idp",
                target_identifier=idp_name,
                sessions_revoked=revoked_count,
            )
        )
    except Exception:
        logger.exception(
            "Audit dispatch failed for IdP session revocation",
            idp_name=idp_name,
            sessions_revoked=revoked_count,
            actor=actor_username,
        )

    return revoked_count
