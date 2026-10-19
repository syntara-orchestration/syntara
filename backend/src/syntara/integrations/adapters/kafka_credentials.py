"""Local Kafka authentication checks shared by health checks and event preparation."""

from collections.abc import Mapping

from syntara.core.exceptions import SafeValueError

_KAFKA_USERNAME_KEY = "kafka_username"
_KAFKA_PASSWORD_KEY = "kafka_password"  # noqa: S105


def resolve_kafka_authentication(resolved_credential: Mapping[str, object]) -> tuple[str, str]:
    """Apply the existing SASL field checks without opening a broker connection.

    Returned values stay in the caller's local scope. Errors contain no field
    values, and neither credential contents nor ciphertext become revision data.
    """
    username = str(resolved_credential.get(_KAFKA_USERNAME_KEY) or "").strip()
    password = str(resolved_credential.get(_KAFKA_PASSWORD_KEY) or "").strip()
    if not username or not password:
        msg = "Authentication configuration is incomplete"
        raise SafeValueError(msg)
    return username, password
