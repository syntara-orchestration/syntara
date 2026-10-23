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
    username_value = resolved_credential.get(_KAFKA_USERNAME_KEY)
    password_value = resolved_credential.get(_KAFKA_PASSWORD_KEY)
    username = username_value.strip() if isinstance(username_value, str) else ""
    password = password_value if isinstance(password_value, str) else ""
    if not username or not password.strip():
        msg = "Authentication configuration is incomplete"
        raise SafeValueError(msg)
    return username, password
