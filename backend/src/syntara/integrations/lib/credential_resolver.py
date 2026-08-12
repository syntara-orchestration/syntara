"""Shared credential resolution utilities for integrations."""

from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.services.secret_service import SecretService
from syntara.credentials.exceptions import CredentialDisabledError
from syntara.credentials.lib.injector_resolver import InjectorResolver
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.integrations.exceptions import IntegrationCredentialNotFoundError, IntegrationCredentialRequiredError
from syntara.integrations.models.integration import Integration


async def fetch_credential_with_type(
    session: AsyncSession,
    credential_id: UUID,
    *,
    require_secret: bool = True,
) -> tuple[Credential, CredentialType]:
    """Fetch a credential and its type, raising if either is missing.

    Shared helper that eliminates the repeated fetch-check-fetch-check
    pattern across credential resolution call sites.

    Args:
        session: Database session.
        credential_id: UUID of the credential to fetch.
        require_secret: When True (default), also checks that the credential
            has a secret_id.  Pass False when only the credential type is
            needed (e.g. type-compatibility validation).

    Returns:
        (credential, credential_type) tuple.

    Raises:
        IntegrationCredentialNotFoundError: If the credential, its
            secret (when required), or its type cannot be found.

    """
    credential = await session.get(Credential, credential_id)
    if not credential or (require_secret and not credential.secret_id):
        raise IntegrationCredentialNotFoundError(credential_id)

    cred_type = await session.get(CredentialType, credential.credential_type_id)
    if not cred_type:
        raise IntegrationCredentialNotFoundError(credential_id)

    return credential, cred_type


async def resolve_mcp_bearer_token(
    session: AsyncSession,
    secret_service: SecretService,
    integration_id: UUID,
) -> str:
    """Resolve the bearer token for an mcp_server integration's management credential.

    Call only immediately before an outbound external connection. The returned
    value is used in the caller's local scope and never stored.

    Raises IntegrationCredentialRequiredError if the integration has no credential
    configured or the credential cannot be resolved to a bearer token.
    Raises IntegrationCredentialNotFoundError if the credential record is missing.
    """
    integration = await session.get(Integration, integration_id)
    if not integration or not integration.management_credential_id:
        itype = integration.integration_type.value if integration else "mcp_server"
        raise IntegrationCredentialRequiredError(itype)

    credential, cred_type = await fetch_credential_with_type(session, integration.management_credential_id)
    if not credential.enabled:
        raise CredentialDisabledError(credential.name)
    # fetch_credential_with_type raises if secret_id is None
    decrypted = await secret_service.retrieve_secret(credential.secret_id)  # type: ignore[arg-type]
    resolved = InjectorResolver.resolve(cred_type.injectors or {}, decrypted)
    token: str | None = resolved.extra_vars.get("bearer_token")
    if not token:
        raise IntegrationCredentialRequiredError(integration.integration_type.value)
    return token
