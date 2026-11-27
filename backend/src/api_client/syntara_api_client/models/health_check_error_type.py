from enum import Enum


class HealthCheckErrorType(str, Enum):
    AUTH_FAILURE = "auth_failure"
    CONNECTION_ERROR = "connection_error"
    MTLS_CERTIFICATE_KEY_MISMATCH = "mtls_certificate_key_mismatch"
    MTLS_HANDSHAKE_FAILED = "mtls_handshake_failed"
    MTLS_HOSTNAME_MISMATCH = "mtls_hostname_mismatch"
    MTLS_INVALID_CLIENT_CERTIFICATE = "mtls_invalid_client_certificate"
    MTLS_INVALID_PRIVATE_KEY = "mtls_invalid_private_key"
    MTLS_UNTRUSTED_CA = "mtls_untrusted_ca"
    MTLS_WRONG_PASSPHRASE = "mtls_wrong_passphrase"
    RATE_LIMIT = "rate_limit"
    SSL_ERROR = "ssl_error"
    TIMEOUT = "timeout"

    def __str__(self) -> str:
        return str(self.value)
