"""Session-bound runtime availability and non-secret connection revision producer."""

import structlog
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.exceptions import SafeValueError
from syntara.core.lib.encryption import EncryptionError
from syntara.core.models.secret import EncryptedSecret
from syntara.core.services.secret_service import SecretService, create_secret_service
from syntara.core.storage_exceptions import StorageBackendNotFoundError
from syntara.credentials.lib.injector_resolver import InjectorResolver
from syntara.eventstreams.adapters.connection_credentials import validate_connection_credentials
from syntara.eventstreams.core.connection_revision import ConnectionRevision
from syntara.eventstreams.models.subscription_snapshot import SubscriptionSnapshot
from syntara.integrations.lib.credential_resolver import fetch_credential_with_type
from syntara.integrations.models.integration import Integration, IntegrationProjectAssignment, IntegrationScope

logger = structlog.stdlib.get_logger(__name__)


class EventConnectionProvider:
    """Check the published runtime binding using the existing secret service.

    The caller owns a short database transaction. The current database secret
    backend performs no external I/O. No broker connectivity is claimed here.
    """

    def __init__(self, session: AsyncSession, *, secret_service: SecretService | None = None) -> None:
        """Inject a session and optionally its secret service for isolated tests."""
        self.session = session
        self._secret_service = secret_service

    async def resolve_revision(self, snapshot: SubscriptionSnapshot) -> ConnectionRevision:
        """Validate current availability and return only non-secret change metadata."""
        integration = await self.session.get(Integration, snapshot.integration_id)
        if (
            integration is None
            or not integration.enabled
            or integration.id != snapshot.integration_identity
            or integration.integration_type.value != snapshot.transport
        ):
            msg = "Event Subscribe Integration is unavailable"
            raise SafeValueError(msg)
        if integration.scope == IntegrationScope.PROJECT:
            assignment = (
                await self.session.exec(
                    select(IntegrationProjectAssignment.id).where(
                        IntegrationProjectAssignment.integration_id == integration.id,
                        IntegrationProjectAssignment.project_id == snapshot.project_id,
                    )
                )
            ).first()
            if assignment is None:
                msg = "Event Subscribe Integration is outside the workflow project"
                raise SafeValueError(msg)
        if snapshot.runtime_credential_id is None:
            msg = "Event Subscribe requires a runtime credential"
            raise SafeValueError(msg)
        credential, credential_type = await fetch_credential_with_type(self.session, snapshot.runtime_credential_id)
        if not credential.enabled or credential.project_id != snapshot.project_id:
            msg = "Event Subscribe runtime credential is unavailable"
            raise SafeValueError(msg)
        secret_updated_at = (
            await self.session.exec(
                select(EncryptedSecret.updated_at).where(EncryptedSecret.secret_id == credential.secret_id)
            )
        ).one_or_none()
        if secret_updated_at is None:
            msg = "Event Subscribe runtime secret is unavailable"
            raise SafeValueError(msg)
        secret_service = (
            self._secret_service if self._secret_service is not None else create_secret_service(self.session)
        )
        try:
            # Values remain local and never contribute to the revision hash.
            decrypted = await secret_service.retrieve_secret(credential.secret_id)  # type: ignore[arg-type]
            resolved = InjectorResolver.resolve(credential_type.injectors or {}, decrypted)
            validate_connection_credentials(snapshot.transport, resolved.extra_vars)
        except (EncryptionError, StorageBackendNotFoundError, KeyError, TypeError, ValueError, AttributeError) as exc:
            logger.warning(
                "Event runtime credential resolution failed",
                credential_id=str(credential.id),
                error_type=type(exc).__name__,
            )
            msg = "Event Subscribe runtime credential cannot be resolved"
            raise SafeValueError(msg) from None
        return ConnectionRevision(
            integration_id=integration.id,
            integration_updated_at=integration.updated_at,
            credential_id=credential.id,
            credential_updated_at=credential.updated_at,
            credential_type_id=credential_type.id,
            credential_type_updated_at=credential_type.updated_at,
            secret_id=credential.secret_id,
            secret_updated_at=secret_updated_at,
        )
