"""Transport-specific runtime credential checks without broker I/O."""

from collections.abc import Mapping

from syntara.core.exceptions import SafeValueError
from syntara.credentials.lib.kafka_connection import kafka_credential_required, validate_kafka_mtls_configuration
from syntara.credentials.lib.mtls_identity import MTLS_IDENTITY_VARS
from syntara.integrations.adapters.kafka_credentials import resolve_kafka_authentication


def validate_connection_credentials(
    transport: str,
    resolved_credential: Mapping[str, object],
    *,
    security_protocol: str = "SASL_SSL",
    insecure_skip_tls_verify: bool = False,
) -> None:
    """Reject unusable authentication fields before freezing a new admission."""
    if transport == "kafka":
        if not MTLS_IDENTITY_VARS.isdisjoint(resolved_credential):
            validate_kafka_mtls_configuration(
                security_protocol=security_protocol, insecure_skip_tls_verify=insecure_skip_tls_verify
            )
        elif kafka_credential_required(security_protocol):
            resolve_kafka_authentication(resolved_credential)
        return
    msg = "Unsupported event transport for runtime credential validation"
    raise SafeValueError(msg)
