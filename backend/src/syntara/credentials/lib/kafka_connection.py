"""Kafka credential rules.

The credential stores only the SASL username and password. Connection settings
stay on the Kafka integration. This module decides when that credential is
required and loads the login from the credential id the caller supplied.
"""

from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.lib.encryption import EncryptionError
from syntara.core.services.secret_service import SecretService
from syntara.credentials.exceptions import (
    CredentialDecryptionError,
    CredentialDisabledError,
    CredentialValidationError,
)
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType

KAFKA_CONNECTION_TYPE_NAME = "Kafka"
KAFKA_USERNAME_KEY = "kafka_username"
KAFKA_PASSWORD_KEY = "kafka_password"  # noqa: S105


class KafkaSecurityProtocol(StrEnum):
    """Transport modes that decide whether a Kafka credential is required."""

    PLAINTEXT = "PLAINTEXT"
    SSL = "SSL"
    SASL_SSL = "SASL_SSL"


def kafka_credential_required(security_protocol: str) -> bool:
    """Return whether the security mode needs a Kafka credential.

    ``SASL_SSL`` requires the username and password. Unauthenticated
    ``PLAINTEXT`` and ``SSL`` without SASL accept an omitted credential.

    Raises:
        CredentialValidationError: If ``security_protocol`` is not supported.

    """
    try:
        protocol = KafkaSecurityProtocol(security_protocol)
    except ValueError as exc:
        msg = f"Unsupported Kafka security protocol '{security_protocol}'"
        raise CredentialValidationError(msg) from exc
    return protocol is KafkaSecurityProtocol.SASL_SSL


def resolve_supplied_kafka_login(
    *,
    credential_id: UUID | None,
    decrypted_inputs: dict[str, Any] | None,
    security_protocol: str,
) -> dict[str, str] | None:
    """Resolve the SASL login from the credential id the caller supplied.

    The function has no other credential to read. A missing runtime credential
    fails for ``SASL_SSL`` and does not fall back to a management credential.

    Returns:
        Injector keys ``kafka_username`` and ``kafka_password``, or ``None``
        when the security mode allows the credential to be omitted.

    Raises:
        CredentialValidationError: If the protocol is unsupported, ``SASL_SSL``
            has no credential, or the supplied credential has a blank login.
            The error text does not include the password.

    """
    required = kafka_credential_required(security_protocol)
    if credential_id is None:
        if required:
            msg = "SASL_SSL requires a Kafka credential"
            raise CredentialValidationError(msg)
        return None
    if decrypted_inputs is None:
        msg = "Kafka credential inputs were not supplied for the requested credential"
        raise CredentialValidationError(msg)

    username_value = decrypted_inputs.get("username")
    password_value = decrypted_inputs.get("password")
    username = username_value.strip() if isinstance(username_value, str) else ""
    # Blank-check with strip(), but return the stored password unchanged.
    # A password may intentionally start or end with whitespace.
    password = password_value if isinstance(password_value, str) else ""
    if not username or not password.strip():
        msg = "Kafka SASL username and password are required"
        raise CredentialValidationError(msg)
    return {KAFKA_USERNAME_KEY: username, KAFKA_PASSWORD_KEY: password}


async def _load_supplied_kafka_login(
    session: AsyncSession,
    secret_service: SecretService,
    *,
    credential_id: UUID | None,
    security_protocol: str,
) -> dict[str, str] | None:
    """Load one credential id, decrypt it, and apply the Kafka login rules.

    There is no second id. Connector validation passes its management
    credential. Listener runtime passes its step-selected credential.
    A missing runtime id is not replaced with the management credential.
    """
    required = kafka_credential_required(security_protocol)
    if credential_id is None:
        if required:
            msg = "SASL_SSL requires a Kafka credential"
            raise CredentialValidationError(msg)
        return None

    credential = await session.get(Credential, credential_id)
    if credential is None or credential.secret_id is None:
        msg = "Kafka credential inputs were not supplied for the requested credential"
        raise CredentialValidationError(msg)
    if not credential.enabled:
        raise CredentialDisabledError(credential.name)

    cred_type = await session.get(CredentialType, credential.credential_type_id)
    if cred_type is None or cred_type.name != KAFKA_CONNECTION_TYPE_NAME:
        msg = "The supplied credential is not a Kafka credential"
        raise CredentialValidationError(msg)

    try:
        decrypted_inputs = await secret_service.retrieve_secret(credential.secret_id)
    except EncryptionError as exc:
        msg = "Kafka credential could not be decrypted"
        raise CredentialDecryptionError(msg) from exc

    return resolve_supplied_kafka_login(
        credential_id=credential_id,
        decrypted_inputs=decrypted_inputs,
        security_protocol=security_protocol,
    )


async def resolve_connector_kafka_login(
    session: AsyncSession,
    secret_service: SecretService,
    *,
    management_credential_id: UUID | None,
    security_protocol: str,
) -> dict[str, str] | None:
    """Resolve the Kafka login for connector validation.

    The id is the integration's management credential. This does not read
    any other credential.
    """
    return await _load_supplied_kafka_login(
        session,
        secret_service,
        credential_id=management_credential_id,
        security_protocol=security_protocol,
    )


async def resolve_listener_kafka_login(
    session: AsyncSession,
    secret_service: SecretService,
    *,
    runtime_credential_id: UUID | None,
    security_protocol: str,
) -> dict[str, str] | None:
    """Resolve the Kafka login for listener runtime.

    The id is the credential selected on the listener step. This function
    has no management-credential parameter, so it cannot substitute one.
    """
    return await _load_supplied_kafka_login(
        session,
        secret_service,
        credential_id=runtime_credential_id,
        security_protocol=security_protocol,
    )
