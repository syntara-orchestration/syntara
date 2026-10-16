"""Kafka credential rules.

The credential stores only the SASL username and password. Connection settings
stay on the Kafka integration. This module decides when that credential is
required and resolves the login from the credential the caller supplied.
"""

from enum import StrEnum
from typing import Any
from uuid import UUID

from syntara.credentials.exceptions import CredentialValidationError

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

    username = str(decrypted_inputs.get("username") or "").strip()
    password = str(decrypted_inputs.get("password") or "").strip()
    if not username or not password:
        msg = "Kafka SASL username and password are required"
        raise CredentialValidationError(msg)
    return {KAFKA_USERNAME_KEY: username, KAFKA_PASSWORD_KEY: password}
