"""Credential resolution for AAP proxy endpoints.

Resolves Nexus credentials to extract AAP authentication details (token, username/password).
Non-sensitive connection details (URL, TLS) come from the integration configuration.
"""

from uuid import UUID

import httpx
import structlog
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.aap.auth import AAPConnection
from syntara.aap.exceptions import AAPAuthenticationError, AAPNotConfiguredError
from syntara.core.lib.encryption import EncryptionError
from syntara.core.services.secret_service import SecretService, create_secret_service
from syntara.credentials.lib.injector_resolver import InjectorResolver
from syntara.credentials.models.credential import Credential

logger = structlog.stdlib.get_logger(__name__)

# Expected credential type name for AAP credentials
AAP_CREDENTIAL_TYPE_NAME = "Ansible Automation Platform"


def _validate_credential_id(credential_id: UUID | str) -> UUID:
    """Validate and convert credential_id to UUID.

    Args:
        credential_id: UUID or string to validate.

    Returns:
        Valid UUID.

    Raises:
        AAPAuthenticationError: If credential_id is not a valid UUID format.

    """
    if isinstance(credential_id, str):
        try:
            return UUID(credential_id)
        except ValueError as e:
            msg = f"Invalid credential_id format: must be a valid UUID, got '{credential_id}'"
            raise AAPAuthenticationError(msg) from e
    return credential_id


async def _fetch_credential(session: AsyncSession, credential_id: UUID) -> Credential:
    """Fetch credential from database with credential_type relationship.

    Args:
        session: Async database session.
        credential_id: UUID of the credential.

    Returns:
        Credential instance.

    Raises:
        AAPNotConfiguredError: If credential not found.

    """
    stmt = (
        select(Credential)
        .where(
            Credential.id == credential_id,
        )
        .options(selectinload(Credential.credential_type))  # type: ignore[arg-type]
    )
    result = await session.exec(stmt)
    credential = result.one_or_none()

    if not credential:
        msg = f"Credential {credential_id} not found"
        raise AAPNotConfiguredError(msg)

    return credential


def _validate_credential_type(credential: Credential) -> None:
    """Verify credential is of AAP type.

    Args:
        credential: Credential to validate.

    Raises:
        AAPNotConfiguredError: If credential type is wrong.

    """
    if not credential.credential_type or credential.credential_type.name != AAP_CREDENTIAL_TYPE_NAME:
        actual_type = credential.credential_type.name if credential.credential_type else "Unknown"
        msg = f"Credential must be of type '{AAP_CREDENTIAL_TYPE_NAME}', got '{actual_type}'"
        raise AAPNotConfiguredError(msg)


def _validate_credential_enabled(credential: Credential) -> None:
    """Verify credential is enabled.

    Args:
        credential: Credential to validate.

    Raises:
        AAPNotConfiguredError: If credential is disabled.

    """
    if not credential.enabled:
        msg = f"Credential '{credential.name}' is disabled"
        raise AAPNotConfiguredError(msg)


def _validate_credential_ownership(credential: Credential, user_id: UUID) -> None:
    """Verify user is authorized to use the credential.

    Args:
        credential: Credential to check.
        user_id: User ID to verify.

    Raises:
        AAPAuthenticationError: If user is not authorized.

    """
    if not credential.is_owned_by(user_id):
        msg = f"User {user_id} is not authorized to use credential {credential.id}"
        raise AAPAuthenticationError(msg)


async def _decrypt_credential_inputs(
    credential: Credential, secret_service: SecretService
) -> dict[str, str | bool | int]:
    """Decrypt credential secret inputs.

    Args:
        credential: Credential containing secret_id.
        secret_service: Service for decrypting secrets.

    Returns:
        Decrypted inputs dictionary.

    Raises:
        AAPNotConfiguredError: If credential has no secret_id.
        AAPAuthenticationError: If decryption fails.

    """
    if not credential.secret_id:
        msg = f"Credential '{credential.name}' has no stored secret data"
        raise AAPNotConfiguredError(msg)

    try:
        return await secret_service.retrieve_secret(credential.secret_id)
    except EncryptionError as e:
        msg = f"Failed to decrypt credential '{credential.name}'"
        raise AAPAuthenticationError(msg) from e


def _resolve_credential_injectors(
    credential: Credential, decrypted_inputs: dict[str, str | bool | int]
) -> dict[str, str | bool | int]:
    """Resolve injector templates to get mapped field names.

    Args:
        credential: Credential with injector configuration.
        decrypted_inputs: Decrypted credential inputs.

    Returns:
        Resolved extra_vars dictionary.

    Raises:
        AAPNotConfiguredError: If credential type has no injector configuration.

    """
    if not credential.credential_type or not credential.credential_type.injectors:
        type_name = credential.credential_type.name if credential.credential_type else "Unknown"
        msg = f"Credential type '{type_name}' has no injector configuration"
        raise AAPNotConfiguredError(msg)

    resolved = InjectorResolver.resolve(
        injectors=credential.credential_type.injectors, decrypted_inputs=decrypted_inputs
    )
    return resolved.extra_vars


def _extract_auth_from_extra_vars(
    extra_vars: dict[str, str | bool | int],
) -> tuple[httpx.Headers, httpx.BasicAuth | None]:
    """Extract AAP authentication details from extra_vars.

    Args:
        extra_vars: Resolved credential extra_vars.

    Returns:
        Tuple of (auth_headers, basic_auth).

    Raises:
        AAPAuthenticationError: If required fields are missing.

    """
    oauth_token = extra_vars.get("aap_oauth_token", "")
    username = extra_vars.get("aap_username", "")
    password = extra_vars.get("aap_password", "")

    # Prefer OAuth token, fall back to basic auth
    if oauth_token:
        auth_headers = httpx.Headers({"Authorization": f"Bearer {oauth_token}"})
        basic_auth = None
    elif username and password:
        auth_headers = httpx.Headers()
        basic_auth = httpx.BasicAuth(str(username), str(password))
    else:
        msg = "Credential must provide either aap_oauth_token or aap_username+aap_password"
        raise AAPAuthenticationError(msg)

    return auth_headers, basic_auth


async def resolve_aap_connection_from_credential(
    session: AsyncSession,
    credential_id: UUID | str,
    user_id: UUID,
) -> AAPConnection:
    """Resolve AAP auth from a Nexus credential.

    Returns an AAPConnection with authentication fields populated.
    The caller must supply ``base_url`` and ``verify_ssl`` from the
    integration configuration (the credential no longer stores them).

    Args:
        session: Async database session.
        credential_id: UUID of the credential (accepts UUID or str for conversion).
        user_id: User ID (UUID) for authorization check (required - credential owner must match).

    Returns:
        AAPConnection with decrypted auth. ``base_url`` is empty and
        ``verify_ssl`` defaults to True — callers override both from
        the integration configuration.

    Raises:
        AAPNotConfiguredError: Credential not found, wrong type, or disabled.
        AAPAuthenticationError: Missing required fields, user not authorized, or invalid credential_id format.

    Security:
        - credential_id is validated as UUID format to prevent SQL injection vectors
        - user_id is required (not optional) to prevent accidental bypass of authorization

    """
    # Validate and convert credential_id to UUID
    validated_credential_id = _validate_credential_id(credential_id)

    # Fetch credential from database
    credential = await _fetch_credential(session, validated_credential_id)

    # Validate credential type, enabled status, and ownership
    _validate_credential_type(credential)
    _validate_credential_enabled(credential)
    _validate_credential_ownership(credential, user_id)

    # Decrypt credential fields
    secret_service: SecretService = create_secret_service(session)
    decrypted_inputs = await _decrypt_credential_inputs(credential, secret_service)

    # Resolve injector templates to get mapped field names
    extra_vars = _resolve_credential_injectors(credential, decrypted_inputs)

    # Extract AAP auth from resolved extra_vars
    auth_headers, basic_auth = _extract_auth_from_extra_vars(extra_vars)

    # Log credential auth resolution
    # Security: Log at INFO level to prevent infrastructure leakage
    logger.info(
        "AAP auth details resolved from credential",
        credential_id=str(validated_credential_id),
        credential_name=credential.name,
        auth_method="oauth" if basic_auth is None else "basic",
    )

    return AAPConnection(
        base_url="",
        headers=dict(auth_headers),
        basic_auth=basic_auth,
    )
