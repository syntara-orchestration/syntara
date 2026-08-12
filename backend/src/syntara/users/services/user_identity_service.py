"""UserIdentity service layer for federated identity management."""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth.exceptions import (
    IdentityOnBuiltinUserError,
    LastSignInMethodError,
    UserIdentityNotFoundError,
    UserNotFoundError,
)
from syntara.auth.session import create_session_store
from syntara.core.models import User, UserIdentity
from syntara.core.models.user import AuthType
from syntara.core.models.user_identity_schemas import UserIdentityListResponse, UserIdentityRead
from syntara.identity_providers.models.identity_provider import IdentityProvider

logger = structlog.stdlib.get_logger(__name__)


class UserIdentityService:
    """Service for managing federated user identities."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize with database session."""
        self.session = session

    async def find_by_issuer_and_subject(self, issuer: str, subject: str) -> UserIdentity | None:
        """Find a UserIdentity by (issuer, subject) pair."""
        result = await self.session.exec(
            select(UserIdentity).where(
                col(UserIdentity.issuer) == issuer,
                col(UserIdentity.subject) == subject,
            )
        )
        return result.one_or_none()

    async def list_for_user(self, user_id: UUID) -> UserIdentityListResponse:
        """List all federated identities for a user, with provider names."""
        # Verify user exists
        user_result = await self.session.exec(
            select(User).where(
                User.id == user_id,
                User.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )
        if not user_result.one_or_none():
            raise UserNotFoundError(user_id)

        result = await self.session.exec(
            select(UserIdentity, IdentityProvider.name)
            .join(
                IdentityProvider,
                col(UserIdentity.identity_provider_id) == col(IdentityProvider.id),
            )
            .where(
                col(UserIdentity.user_id) == user_id,
            )
        )
        rows = result.all()
        resources = [
            UserIdentityRead(
                id=identity.id,
                user_id=identity.user_id,
                identity_provider_id=identity.identity_provider_id,
                issuer=identity.issuer,
                subject=identity.subject,
                created_at=identity.created_at,
                updated_at=identity.updated_at,
                last_used_at=identity.last_used_at,
                provider_name=provider_name,
            )
            for identity, provider_name in rows
        ]
        return UserIdentityListResponse(resources=resources)

    async def create_identity(
        self,
        user_id: UUID,
        identity_provider_id: UUID,
        issuer: str,
        subject: str,
    ) -> UserIdentity:
        """Create a new federated identity link.

        If the user is a non-builtin local user, they are converted to
        federated: password_hash is cleared, auth_type set to FEDERATED,
        and all sessions are revoked.
        """
        user_result = await self.session.exec(select(User).where(User.id == user_id))
        user = user_result.one_or_none()
        if user and user.is_builtin:
            raise IdentityOnBuiltinUserError(user_id)

        identity = UserIdentity(
            user_id=user_id,
            identity_provider_id=identity_provider_id,
            issuer=issuer,
            subject=subject,
        )
        self.session.add(identity)

        if user and user.auth_type == AuthType.LOCAL:
            await self._convert_to_federated(user)

        await self.session.flush()
        logger.info(
            "Created user identity",
            identity_id=str(identity.id),
            user_id=str(user_id),
            issuer=issuer,
        )
        return identity

    async def delete_identity(
        self,
        identity_id: UUID,
        *,
        expected_user_id: UUID | None = None,
        force: bool = False,
    ) -> None:
        """Hard-delete a federated identity.

        Args:
            identity_id: The identity to delete.
            expected_user_id: If provided, validates that the identity belongs to this user.
            force: If True, skip the last-sign-in-method safety check (e.g. provider cleanup).

        """
        result = await self.session.exec(select(UserIdentity).where(UserIdentity.id == identity_id))
        identity = result.one_or_none()
        if not identity:
            raise UserIdentityNotFoundError(identity_id)
        if expected_user_id is not None and identity.user_id != expected_user_id:
            raise UserIdentityNotFoundError(identity_id)

        # Prevent deleting the last sign-in method (unless force is set for admin cleanup).
        # With mutual exclusivity, federated users never have passwords, so the only
        # sign-in method check is whether this is the user's last identity.
        if not force:
            remaining = await self.session.exec(
                select(UserIdentity).where(col(UserIdentity.user_id) == identity.user_id)
            )
            if len(remaining.all()) <= 1:
                raise LastSignInMethodError

        # Revoke ALL sessions for user before deleting identity
        user_id = identity.user_id
        store = create_session_store(self.session)
        revoked_count = await store.revoke_all_for_user(user_id)
        logger.info(
            "Revoked sessions for user during identity deletion",
            user_id=str(user_id),
            identity_id=str(identity_id),
            revoked_count=revoked_count,
        )

        await self.session.delete(identity)
        await self.session.flush()
        await store.increment_token_version(user_id)
        logger.info("Deleted user identity", identity_id=str(identity_id), force=force)

    async def attach_identity(self, identity_id: UUID, target_user_id: UUID) -> UserIdentityRead:
        """Move a federated identity to a different user.

        The source user is intentionally kept intact even if they have no
        remaining identities or password — preserving the record for audit.

        Args:
            identity_id: The identity to move.
            target_user_id: The user to attach the identity to.

        Returns:
            UserIdentityRead with provider_name populated.

        """
        # Load identity with provider name in a single query
        result = await self.session.exec(
            select(UserIdentity, IdentityProvider.name)
            .join(
                IdentityProvider,
                col(UserIdentity.identity_provider_id) == col(IdentityProvider.id),
            )
            .where(UserIdentity.id == identity_id)
        )
        row = result.one_or_none()
        if not row:
            raise UserIdentityNotFoundError(identity_id)

        identity, provider_name = row

        # Verify target user exists
        target_result = await self.session.exec(
            select(User).where(
                User.id == target_user_id,
                User.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )
        target_user = target_result.one_or_none()
        if not target_user:
            raise UserNotFoundError(target_user_id)

        if target_user.is_builtin:
            raise IdentityOnBuiltinUserError(target_user_id)

        source_user_id = identity.user_id

        # Revoke ALL sessions for source user before moving identity
        store = create_session_store(self.session)
        revoked_count = await store.revoke_all_for_user(source_user_id)
        logger.info(
            "Revoked sessions for source user during identity attach",
            source_user_id=str(source_user_id),
            identity_id=str(identity_id),
            revoked_count=revoked_count,
        )

        # Move identity to target user
        identity.user_id = target_user_id
        identity.updated_at = datetime.now(UTC)
        self.session.add(identity)

        if target_user.auth_type == AuthType.LOCAL:
            # _convert_to_federated handles revoke + increment for the target user
            await self._convert_to_federated(target_user)
        else:
            # Target is already FEDERATED — revoke and increment here
            target_revoked_count = await store.revoke_all_for_user(target_user_id)
            await store.increment_token_version(target_user_id)
            logger.info(
                "Revoked sessions for target user during identity attach",
                target_user_id=str(target_user_id),
                identity_id=str(identity_id),
                revoked_count=target_revoked_count,
            )

        await self.session.flush()

        await store.increment_token_version(source_user_id)

        logger.info(
            "Attached identity to user",
            identity_id=str(identity_id),
            target_user_id=str(target_user_id),
            source_user_id=str(source_user_id),
        )
        return UserIdentityRead(
            id=identity.id,
            user_id=identity.user_id,
            identity_provider_id=identity.identity_provider_id,
            issuer=identity.issuer,
            subject=identity.subject,
            created_at=identity.created_at,
            updated_at=identity.updated_at,
            last_used_at=identity.last_used_at,
            provider_name=provider_name,
        )

    async def _convert_to_federated(self, user: User) -> None:
        """Convert a local user to federated by clearing their password and revoking sessions."""
        user.auth_type = AuthType.FEDERATED
        user.password_hash = None
        self.session.add(user)

        store = create_session_store(self.session)
        revoked = await store.revoke_all_for_user(user.id)
        await store.increment_token_version(user.id)
        logger.info(
            "Converted local user to federated",
            user_id=str(user.id),
            sessions_revoked=revoked,
        )
