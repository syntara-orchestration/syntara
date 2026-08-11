"""PostgreSQL-based session store for refresh token management.

Usage:
    from syntara.auth.session import SessionStore

    store = SessionStore(db)
    await store.create(jti="abc123", user_id=user.id)
    session = await store.get("abc123")
    await store.revoke("abc123")
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import text, update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth.session.models import RefreshSession
from syntara.core.config.base import get_settings

logger = structlog.stdlib.get_logger(__name__)

OnTokenVersionInvalidated = Callable[[str], None]


@dataclass
class SessionInfo:
    """Information about an active session."""

    jti: str
    user_id: str
    issued_at: datetime
    device: str | None
    ip_address: str | None
    ttl: int = field(default=-1)
    amr: list[str] | None = None
    idp: str | None = None
    identity_id: str | None = None
    issuer: str | None = None
    subject: str | None = None
    idp_id: str | None = None
    id_token_hint: str | None = None
    rp_logout_enabled: bool = False


def _build_session_info(row: RefreshSession) -> SessionInfo:
    now = datetime.now(UTC)
    ttl = max(0, int((row.expires_at - now).total_seconds()))
    return SessionInfo(
        jti=row.jti,
        user_id=str(row.user_id),
        issued_at=row.issued_at,
        device=row.device,
        ip_address=row.ip_address,
        ttl=ttl,
        amr=row.amr,
        idp=row.idp,
        idp_id=row.idp_id,
        identity_id=row.identity_id,
        issuer=row.issuer,
        subject=row.subject,
        id_token_hint=row.id_token_hint,
        rp_logout_enabled=row.rp_logout_enabled,
    )


class SessionStore:
    """PostgreSQL-based session store for refresh token management."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        on_token_version_invalidated: OnTokenVersionInvalidated | None = None,
    ) -> None:
        """Initialize session store with a database session."""
        self._db = db
        self._settings = get_settings()
        self._on_token_version_invalidated = on_token_version_invalidated

    async def create(
        self,
        jti: str,
        user_id: UUID | str,
        *,
        device: str | None = None,
        ip_address: str | None = None,
        ttl_seconds: int | None = None,
        amr: list[str] | None = None,
        idp: str | None = None,
        idp_id: str | None = None,
        identity_id: str | None = None,
        issuer: str | None = None,
        subject: str | None = None,
        id_token_hint: str | None = None,
        rp_logout_enabled: bool = False,
    ) -> None:
        """Store refresh token session in PostgreSQL."""
        if ttl_seconds is None:
            ttl_seconds = self._settings.jwt_refresh_token_lifetime_hours * 3600

        now = datetime.now(UTC)
        session = RefreshSession(
            jti=jti,
            user_id=UUID(str(user_id)),
            issued_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            device=device,
            ip_address=ip_address,
            amr=amr,
            idp=idp,
            idp_id=idp_id,
            identity_id=identity_id,
            issuer=issuer,
            subject=subject,
            id_token_hint=id_token_hint,
            rp_logout_enabled=rp_logout_enabled,
        )
        self._db.add(session)
        await self._db.flush()
        logger.debug(
            "Created refresh token session",
            jti=jti,
            user_id=str(user_id),
            ttl_seconds=ttl_seconds,
        )

    async def get(self, jti: str) -> SessionInfo | None:
        """Get refresh token session. Returns None if not found, revoked, or expired."""
        now = datetime.now(UTC)
        result = await self._db.exec(
            select(RefreshSession).where(
                RefreshSession.jti == jti,
                RefreshSession.revoked_at.is_(None),  # type: ignore[union-attr]
                RefreshSession.expires_at > now,
            )
        )
        row = result.one_or_none()
        if row is None:
            logger.debug("Refresh token not found", jti=jti)
            return None
        return _build_session_info(row)

    async def get_with_token_version(self, jti: str) -> tuple[SessionInfo, int] | None:
        """Get session and user token_version in a single JOIN query.

        Returns (SessionInfo, token_version) or None.
        """
        from syntara.core.models.user import User  # noqa: PLC0415

        now = datetime.now(UTC)
        result = await self._db.exec(
            select(RefreshSession, User.token_version)
            .join(User, RefreshSession.user_id == User.id)  # type: ignore[arg-type]
            .where(
                RefreshSession.jti == jti,
                RefreshSession.revoked_at.is_(None),  # type: ignore[union-attr]
                RefreshSession.expires_at > now,
            )
        )
        row = result.one_or_none()
        if row is None:
            return None

        session, token_version = row
        return _build_session_info(session), token_version

    async def revoke(self, jti: str) -> bool:
        """Soft-revoke a refresh token session. Returns True if revoked."""
        now = datetime.now(UTC)
        result = await self._db.exec(
            update(RefreshSession)
            .where(
                RefreshSession.jti == jti,  # type: ignore[arg-type]
                RefreshSession.revoked_at.is_(None),  # type: ignore[union-attr]
            )
            .values(revoked_at=now)
        )
        revoked: bool = result.rowcount > 0
        if revoked:
            logger.debug("Revoked refresh token", jti=jti)
        else:
            logger.debug("Refresh token not found for revocation", jti=jti)
        return revoked

    async def revoke_all_for_user(self, user_id: UUID | str) -> int:
        """Revoke all active sessions for a user. O(1) via partial index."""
        user_id_val = UUID(str(user_id))
        now = datetime.now(UTC)
        result = await self._db.exec(
            update(RefreshSession)
            .where(
                RefreshSession.user_id == user_id_val,  # type: ignore[arg-type]
                RefreshSession.revoked_at.is_(None),  # type: ignore[union-attr]
            )
            .values(revoked_at=now)
        )
        revoked_count: int = result.rowcount
        logger.info(
            "Revoked all refresh tokens for user",
            user_id=str(user_id),
            revoked_count=revoked_count,
        )
        return revoked_count

    async def revoke_by_idp(self, idp_id: str) -> int:
        """Revoke all sessions for an identity provider. O(m) via partial index."""
        now = datetime.now(UTC)
        result = await self._db.exec(
            update(RefreshSession)
            .where(
                RefreshSession.idp_id == idp_id,  # type: ignore[arg-type]
                RefreshSession.revoked_at.is_(None),  # type: ignore[union-attr]
            )
            .values(revoked_at=now)
        )
        revoked_count: int = result.rowcount
        logger.info("Revoked sessions by IDP", idp_id=idp_id, revoked_count=revoked_count)
        return revoked_count

    async def revoke_by_identity(self, identity_id: UUID | str) -> int:
        """Revoke all sessions for a user identity. O(m) via partial index."""
        identity_id_str = str(identity_id)
        now = datetime.now(UTC)
        result = await self._db.exec(
            update(RefreshSession)
            .where(
                RefreshSession.identity_id == identity_id_str,  # type: ignore[arg-type]
                RefreshSession.revoked_at.is_(None),  # type: ignore[union-attr]
            )
            .values(revoked_at=now)
        )
        revoked_count: int = result.rowcount
        logger.info("Revoked sessions by identity", identity_id=identity_id_str, revoked_count=revoked_count)
        return revoked_count

    async def increment_token_version(self, user_id: UUID | str) -> int:
        """Increment the token version counter for a user. Returns new version."""
        # Core/raw SQL bypasses SQLAlchemy before_flush, so propagate actor
        # ContextVars to Postgres session vars before the UPDATE fires the
        # audit trigger (AAP-83651).
        from syntara.core.database.session import apply_audit_context  # noqa: PLC0415

        await self._db.run_sync(apply_audit_context)

        user_id_str = str(user_id)
        result = await self._db.exec(  # type: ignore[call-overload]
            text("UPDATE users SET token_version = token_version + 1 WHERE id = :user_id RETURNING token_version"),
            params={"user_id": user_id_str},
        )
        row = result.one_or_none()
        new_version = row[0] if row else 0

        if self._on_token_version_invalidated:
            self._on_token_version_invalidated(user_id_str)

        logger.debug("Incremented token version", user_id=user_id_str, version=new_version)
        return new_version

    async def get_token_version(self, user_id: UUID | str) -> int:
        """Get the current token version for a user. Returns 0 if not found."""
        result = await self._db.exec(  # type: ignore[call-overload]
            text("SELECT token_version FROM users WHERE id = :user_id"),
            params={"user_id": str(user_id)},
        )
        row = result.one_or_none()
        return row[0] if row else 0

    async def list_user_sessions(self, user_id: UUID | str, *, limit: int = 50) -> list[SessionInfo]:
        """List active sessions for a user, most recent first."""
        user_id_val = UUID(str(user_id))
        now = datetime.now(UTC)
        result = await self._db.exec(
            select(RefreshSession)
            .where(
                RefreshSession.user_id == user_id_val,
                RefreshSession.revoked_at.is_(None),  # type: ignore[union-attr]
                RefreshSession.expires_at > now,
            )
            .order_by(RefreshSession.issued_at.desc())  # type: ignore[attr-defined]
            .limit(limit)
        )
        rows = result.all()
        return [_build_session_info(row) for row in rows]
