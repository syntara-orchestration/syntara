"""Service account credential service layer for business logic."""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import structlog
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth.passwords import hash_password
from syntara.core.models import User
from syntara.core.services import BaseService
from syntara.core.services.extensions import ConvertResourceMixin
from syntara.service_accounts.constants import MAX_CREDENTIALS_PER_SA
from syntara.service_accounts.credential_schemas import (
    ServiceAccountCredentialCreateResponse,
    ServiceAccountCredentialListResponse,
    ServiceAccountCredentialRead,
    ServiceAccountCredentialRotateResponse,
)
from syntara.service_accounts.exceptions import (
    CredentialExpirationExceededError,
    CredentialExpirationInPastError,
    ServiceAccountCredentialLimitError,
    ServiceAccountCredentialNotFoundError,
)
from syntara.service_accounts.models.service_account_credential import (
    ServiceAccountCredential,
    ServiceAccountCredentialStatus,
    ServiceAccountCredentialType,
)
from syntara.settings.cache.settings_cache import get_runtime_settings

logger = structlog.stdlib.get_logger(__name__)


class ServiceAccountCredentialConvertMixin(ConvertResourceMixin):
    """Convert ServiceAccountCredential model to ServiceAccountCredentialRead response."""

    def convert_resource(self, resource: ServiceAccountCredential) -> ServiceAccountCredentialRead:  # type: ignore[override]
        """Convert credential to read schema."""
        return ServiceAccountCredentialRead.model_validate(resource)


class ServiceAccountCredentialService(BaseService):
    """Service for service account credential business logic."""

    def __init__(self, session: AsyncSession, user: User) -> None:
        """Initialize with database session and current user."""
        super().__init__(session, user, convert_resource_mixin=ServiceAccountCredentialConvertMixin())

    @staticmethod
    def _generate_credential(
        credential_type: ServiceAccountCredentialType,  # noqa: ARG004
    ) -> tuple[str, str, str]:
        """Generate a credential identifier and secret.

        Returns:
            Tuple of (identifier, plaintext_secret, hashed_secret).

        """
        identifier = f"nx_sa_{uuid4().hex[:16]}"
        plaintext_secret = secrets.token_urlsafe(48)
        hashed = hash_password(plaintext_secret)
        return identifier, plaintext_secret, hashed

    async def _check_credential_limit(self, service_account_id: UUID) -> None:
        query = select(func.count()).where(
            ServiceAccountCredential.service_account_id == service_account_id,
        )
        result = await self.session.exec(query)
        count = result.one()
        if count >= MAX_CREDENTIALS_PER_SA:
            raise ServiceAccountCredentialLimitError(str(service_account_id), MAX_CREDENTIALS_PER_SA)

    @staticmethod
    async def _resolve_expires_at(requested: datetime | None) -> datetime | None:
        if requested is not None and requested <= datetime.now(tz=UTC):
            msg = "expires_at must be in the future"
            raise CredentialExpirationInPastError(msg)

        max_days = await get_runtime_settings().get_int("service_accounts.credential_max_lifetime_days")

        # 0 means unlimited (no maximum), consistent with rate_limiting.requests_per_window.
        if max_days == 0:
            return requested

        max_expiry = datetime.now(tz=UTC) + timedelta(days=max_days)

        if requested is None:
            return max_expiry

        if requested > max_expiry:
            raise CredentialExpirationExceededError(max_days)

        return requested

    async def create_credential(
        self,
        service_account_id: UUID,
        credential_type: ServiceAccountCredentialType,
        *,
        grace_period_seconds: int = 3600,
        expires_at: datetime | None = None,
    ) -> tuple[ServiceAccountCredential, str]:
        """Create a new credential for a service account.

        Returns:
            Tuple of (created credential, plaintext secret/key).

        """
        await self._check_credential_limit(service_account_id)

        resolved_expires_at = await self._resolve_expires_at(expires_at)
        identifier, plaintext_secret, hashed = self._generate_credential(credential_type)

        credential = ServiceAccountCredential(
            service_account_id=service_account_id,
            credential_type=credential_type,
            identifier=identifier,
            hashed_secret=hashed,
            grace_period_seconds=grace_period_seconds,
            expires_at=resolved_expires_at,
            status=ServiceAccountCredentialStatus.ACTIVE,
            created_by=self.user.id,
            updated_by=self.user.id,
        )

        self.session.add(credential)
        await self.session.flush()
        await self.session.commit()

        logger.info(
            "Service account credential created",
            credential_id=str(credential.id),
            service_account_id=str(service_account_id),
            credential_type=credential_type.value,
            identifier=identifier,
        )

        return credential, plaintext_secret

    async def get_credential(self, credential_id: UUID, *, service_account_id: UUID) -> ServiceAccountCredential:
        """Get a credential by ID, scoped to the owning service account.

        Raises:
            ServiceAccountCredentialNotFoundError: If not found or not owned by the given SA.

        """
        query = select(ServiceAccountCredential).where(
            ServiceAccountCredential.id == credential_id,
            ServiceAccountCredential.service_account_id == service_account_id,
        )
        result = await self.session.exec(query)
        credential = result.one_or_none()

        if credential is None:
            msg = f"Credential {credential_id} not found"
            raise ServiceAccountCredentialNotFoundError(msg)

        return credential

    async def rotate_credential(
        self,
        credential_id: UUID,
        *,
        service_account_id: UUID,
        grace_period_seconds: int | None = None,
    ) -> tuple[ServiceAccountCredential, str]:
        """Rotate a credential's secret.

        Returns:
            Tuple of (updated credential, new plaintext secret/key).

        """
        credential = await self.get_credential(credential_id, service_account_id=service_account_id)

        grace = grace_period_seconds if grace_period_seconds is not None else credential.grace_period_seconds

        credential.old_hashed_secret = credential.hashed_secret
        credential.old_secret_valid_until = datetime.now(tz=UTC) + timedelta(seconds=grace)

        _, plaintext_secret, hashed = self._generate_credential(credential.credential_type)
        credential.hashed_secret = hashed
        credential.expires_at = await self._resolve_expires_at(None)

        credential.update_by_user(self.user.id)

        self.session.add(credential)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(credential)

        logger.info(
            "Service account credential rotated",
            credential_id=str(credential_id),
            grace_period_seconds=grace,
        )

        return credential, plaintext_secret

    async def disable_credential(self, credential_id: UUID, *, service_account_id: UUID) -> ServiceAccountCredential:
        """Set a credential's status to disabled.

        Raises:
            ServiceAccountCredentialNotFoundError: If not found or not owned by the given SA.

        """
        credential = await self.get_credential(credential_id, service_account_id=service_account_id)
        credential.status = ServiceAccountCredentialStatus.DISABLED
        credential.update_by_user(self.user.id)

        self.session.add(credential)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(credential)

        logger.info("Service account credential disabled", credential_id=str(credential_id))
        return credential

    async def enable_credential(self, credential_id: UUID, *, service_account_id: UUID) -> ServiceAccountCredential:
        """Set a credential's status to active.

        Raises:
            ServiceAccountCredentialNotFoundError: If not found or not owned by the given SA.

        """
        credential = await self.get_credential(credential_id, service_account_id=service_account_id)
        credential.status = ServiceAccountCredentialStatus.ACTIVE
        credential.update_by_user(self.user.id)

        self.session.add(credential)
        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(credential)

        logger.info("Service account credential enabled", credential_id=str(credential_id))
        return credential

    async def delete_credential(self, credential_id: UUID, *, service_account_id: UUID) -> None:
        """Hard-delete a credential.

        Raises:
            ServiceAccountCredentialNotFoundError: If not found or not owned by the given SA.

        """
        credential = await self.get_credential(credential_id, service_account_id=service_account_id)

        await self.session.delete(credential)
        await self.session.flush()
        await self.session.commit()

        logger.info("Service account credential deleted", credential_id=str(credential_id))

    async def list_credentials(
        self,
        service_account_id: UUID,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: list[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
    ) -> ServiceAccountCredentialListResponse:
        """List credentials for a service account."""
        sa_filter = [("service_account_id", str(service_account_id))]
        all_params = sa_filter + list(query_params_items or [])
        response = await self.list_resources(
            model=ServiceAccountCredential,
            response_type=ServiceAccountCredentialListResponse,
            limit=limit,
            cursor=cursor,
            sort=sort,
            query_params_items=all_params,
            include_total=include_total,
        )
        response.total_credentials = await self.count_resources(
            ServiceAccountCredential,
            service_account_id=service_account_id,
        )
        response.max_lifetime_days = await get_runtime_settings().get_int(
            "service_accounts.credential_max_lifetime_days"
        )
        return response

    def to_read(self, credential: ServiceAccountCredential) -> ServiceAccountCredentialRead:
        """Convert a credential to a read response."""
        return ServiceAccountCredentialRead.model_validate(credential)

    def to_create_response(
        self,
        credential: ServiceAccountCredential,
        plaintext_secret: str,
    ) -> ServiceAccountCredentialCreateResponse:
        """Convert a credential to a create response with one-time secret."""
        read_data = ServiceAccountCredentialRead.model_validate(credential).model_dump()
        return ServiceAccountCredentialCreateResponse(**read_data, client_secret=plaintext_secret)

    def to_rotate_response(
        self,
        credential: ServiceAccountCredential,
        plaintext_secret: str,
    ) -> ServiceAccountCredentialRotateResponse:
        """Convert a credential to a rotate response with new secret."""
        read_data = ServiceAccountCredentialRead.model_validate(credential).model_dump()
        return ServiceAccountCredentialRotateResponse(**read_data, client_secret=plaintext_secret)
