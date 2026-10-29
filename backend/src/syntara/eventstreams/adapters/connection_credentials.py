"""Transport-specific runtime credential checks without broker I/O."""

from collections.abc import Mapping

from syntara.core.exceptions import SafeValueError
from syntara.integrations.adapters.kafka_credentials import resolve_kafka_authentication


def validate_connection_credentials(transport: str, resolved_credential: Mapping[str, object]) -> None:
    """Reject unusable authentication fields before freezing a new admission."""
    if transport == "kafka":
        resolve_kafka_authentication(resolved_credential)
        return
    msg = "Unsupported event transport for runtime credential validation"
    raise SafeValueError(msg)
